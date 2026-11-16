"""Compare RAG configurations (chunk size, top-k) on eval/eval_set.json and write the winner table.

  python eval/run_eval.py                           # two configs: chunk 800 / top-3 and chunk 500 / top-5
  python eval/run_eval.py --configs 800:3,500:3,500:5
  python eval/run_eval.py --grid                    # all four chunk-size x top-k combinations
  python eval/run_eval.py --generator extractive    # or llm (needs a key in .env); default uses KACHRACHECK_GENERATOR
  python eval/run_eval.py --write-readme            # put the winner table into README.md

A row is CORRECT when
  - an answerable question is answered AND a cited chunk comes from one of the expected rules, or
  - a must-refuse question gets "I don't know".
Retrieval hit = an expected rule appears among the retrieved chunks (answerable questions only).
"""
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import rag                                    # noqa: E402
from app.chunking import chunk_raw_dir                 # noqa: E402
from app.embed import SemanticIndex, get_embedder      # noqa: E402

EVAL_SET = ROOT / "eval" / "eval_set.json"
RESULTS_JSON = ROOT / "eval" / "eval_results.json"
RESULTS_MD = ROOT / "eval" / "eval_results.md"
README = ROOT / "README.md"
MARK_START, MARK_END = "<!-- eval-table:start -->", "<!-- eval-table:end -->"


def rule_of(title: str):
    m = re.match(r"Rule (\d+):", title or "")
    return int(m.group(1)) if m else None


def parse_configs(text: str):
    return [tuple(int(x) for x in part.split(":")) for part in text.split(",") if part.strip()]


def evaluate(rows, retrieve, generator, k: int):
    """Run every row through answer_question; return (per-row results, summary dict)."""
    results = []
    for row in rows:
        ans = rag.answer_question(row["question"], retrieve, k=k, generator=generator)
        expected = set(row["expected_rules"])
        retrieved = {rule_of(s.title) for s in ans.considered} - {None}
        cited = {rule_of(s.title) for s in ans.citations} - {None}
        if row["must_refuse"]:
            correct = not ans.answered
            hit = None
        else:
            hit = bool(expected & retrieved)
            correct = ans.answered and bool(expected & cited)
        results.append({"id": row["id"], "question": row["question"], "must_refuse": row["must_refuse"],
                        "expected": sorted(expected), "answered": ans.answered, "reason": ans.reason,
                        "retrieved_rules": sorted(retrieved), "cited_rules": sorted(cited), "hit": hit,
                        "correct": correct, "n_citations": len(ans.citations), "answer": ans.answer[:200],
                        "top_score": ans.considered[0].score if ans.considered else 0.0})
    answerable = [r for r in results if not r["must_refuse"]]
    refuse = [r for r in results if r["must_refuse"]]
    answered = [r for r in results if r["answered"]]
    summary = {
        "accuracy": round(sum(r["correct"] for r in results) / len(results), 3),
        "retrieval_hit": round(sum(bool(r["hit"]) for r in answerable) / max(len(answerable), 1), 3),
        "refusals_right": f"{sum(r['correct'] for r in refuse)}/{len(refuse)}",
        "false_refusals": sum(not r["answered"] for r in answerable),
        "wrong_answers": sum(r["answered"] and not r["correct"] for r in answerable),
        "avg_citations": round(sum(r["n_citations"] for r in answered) / max(len(answered), 1), 2),
        "correct": sum(r["correct"] for r in results), "total": len(results),
    }
    return results, summary


def pick_winner(runs):
    """Highest accuracy, then highest retrieval hit, then the smaller top-k (cheaper)."""
    return min(runs, key=lambda r: (-r["summary"]["accuracy"], -r["summary"]["retrieval_hit"], r["k"]))


def winner_table(runs, winner, meta) -> str:
    lines = ["| Config | Chunk size | Top-k | Chunks | Accuracy | Retrieval hit | Refusals right | Wrong answers | Winner |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in runs:
        s = r["summary"]
        lines.append(f"| {r['name']} | {r['chunk_size']} | {r['k']} | {r['chunks']} | "
                     f"{s['correct']}/{s['total']} ({s['accuracy']:.0%}) | {s['retrieval_hit']:.0%} | {s['refusals_right']} | "
                     f"{s['wrong_answers']} | {'**yes**' if r is winner else ''} |")
    lines += ["", f"Generator: `{meta['generator']}` · Embedder: `{meta['embedder']}` · {meta['questions']} questions "
                  f"({meta['answerable']} answerable, {meta['refuse']} must say \"I don't know\") · run {meta['date']}"]
    return "\n".join(lines)


def update_readme(table: str, path: Path = README) -> None:
    text = path.read_text(encoding="utf-8")
    block = f"{MARK_START}\n{table}\n{MARK_END}"
    if MARK_START in text and MARK_END in text:
        text = re.sub(re.escape(MARK_START) + r".*?" + re.escape(MARK_END), lambda _: block, text, flags=re.S)
    else:
        text += f"\n## RAG evaluation\n\n{block}\n"
    path.write_text(text, encoding="utf-8")


def detail_markdown(runs, winner, meta) -> str:
    out = ["# RAG evaluation: per-question results", "", winner_table(runs, winner, meta), ""]
    for r in runs:
        out += [f"## {r['name']}: chunk size {r['chunk_size']}, top-k {r['k']}{' (winner)' if r is winner else ''}", "",
                "| Q | Question | Expected rule | Retrieved rules | Answered | Reason | Result |", "|---|---|---|---|---|---|---|"]
        for x in r["results"]:
            out.append(f"| {x['id']} | {x['question']} | {', '.join(map(str, x['expected'])) or 'none (refuse)'} | "
                       f"{', '.join(map(str, x['retrieved_rules']))} | {'yes' if x['answered'] else 'no'} | {x['reason']} | "
                       f"{'OK' if x['correct'] else 'FAIL'} |")
        out.append("")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--configs", default="800:3,500:5", help="chunk_size:top_k pairs, comma separated")
    ap.add_argument("--grid", action="store_true", help="all combinations of chunk sizes 800/500 and top-k 3/5")
    ap.add_argument("--generator", default=None, choices=["extractive", "llm", "auto"])
    ap.add_argument("--embedder", default=None, choices=["minilm", "hash"])
    ap.add_argument("--raw-dir", default=str(ROOT / "data" / "raw"))
    ap.add_argument("--write-readme", action="store_true")
    args = ap.parse_args(argv)

    rows = json.loads(EVAL_SET.read_text(encoding="utf-8"))
    configs = [(800, 3), (800, 5), (500, 3), (500, 5)] if args.grid else parse_configs(args.configs)
    embedder, generator = get_embedder(args.embedder), rag.make_generator(args.generator)

    indexes, runs = {}, []
    for i, (size, k) in enumerate(configs):
        if size not in indexes:
            chunks, _ = chunk_raw_dir(args.raw_dir, max_chars=size)
            if not chunks:
                print("No chunks: put the PDFs in data/raw (python -m app.fetch).")
                return 1
            print(f"chunk size {size}: {len(chunks)} chunks, embedding ...")
            indexes[size] = SemanticIndex(chunks, embedder)
        results, summary = evaluate(rows, rag.retrieve_from_index(indexes[size]), generator, k)
        runs.append({"name": chr(ord("A") + i), "chunk_size": size, "k": k, "chunks": len(indexes[size].chunks),
                     "summary": summary, "results": results})
        print(f"config {runs[-1]['name']} (chunk {size}, top-{k}): {summary['correct']}/{summary['total']} correct, "
              f"retrieval hit {summary['retrieval_hit']:.0%}, refusals {summary['refusals_right']}")

    winner = pick_winner(runs)
    meta = {"generator": generator.name, "embedder": embedder.name, "questions": len(rows),
            "answerable": sum(not r["must_refuse"] for r in rows), "refuse": sum(r["must_refuse"] for r in rows),
            "date": datetime.now().strftime("%d %B %Y")}
    RESULTS_JSON.write_text(json.dumps({"meta": meta, "winner": winner["name"], "runs": runs}, indent=2), encoding="utf-8")
    RESULTS_MD.write_text(detail_markdown(runs, winner, meta), encoding="utf-8")
    table = winner_table(runs, winner, meta)
    print("\n" + table)
    if args.write_readme:
        update_readme(table)
        print("\nREADME.md updated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
