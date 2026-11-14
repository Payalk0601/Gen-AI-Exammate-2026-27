"""Embeddings and in-memory semantic search over the chunks.

Two embedders:
  minilm  all-MiniLM-L6-v2 (ONNX, the model Chroma ships). Real semantic search. Needs `pip install chromadb`
          and internet the first time (about 80 MB model download, then cached). This is the default.
  hash    offline, deterministic bag-of-words + character n-gram hashing. NOT semantic: it only matches
          similar spellings. It exists so the tests run without downloading a model.
Choose with the KACHRACHECK_EMBEDDER environment variable or --embedder.

  python -m app.embed --eval                       # 10 questions -> eval/search_results.md
  python -m app.embed --query "bin colours"        # one question
"""
import argparse
import hashlib
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import numpy as np

from app.chunking import Chunk, chunk_raw_dir

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS = ROOT / "data" / "questions.json"
EVAL_OUT = ROOT / "eval" / "search_results.md"


def _normalise(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.where(norms == 0, 1, norms)


class HashEmbedder:
    """Lexical, offline. Words and character trigrams are hashed into 384 buckets."""
    name = "hash-384"
    dim = 384

    def embed(self, texts: List[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim))
        for row, text in enumerate(texts):
            words = re.findall(r"[a-z0-9]+", text.lower())
            grams = [w for w in words] + [w[i:i + 3] for w in words if len(w) > 3 for i in range(len(w) - 2)]
            for g in grams:
                h = int(hashlib.md5(g.encode()).hexdigest(), 16)
                out[row, h % self.dim] += 1.0 if (h >> 64) % 2 else -1.0
        return _normalise(out)


class MiniLMEmbedder:
    """all-MiniLM-L6-v2 through Chroma's ONNX runtime (no PyTorch needed)."""
    name = "all-MiniLM-L6-v2"
    dim = 384

    def __init__(self):
        try:
            from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
        except ImportError as err:
            raise RuntimeError("chromadb is not installed: run `pip install -r requirements.txt`") from err
        self._use_project_model_dir()
        self._fn = DefaultEmbeddingFunction()

    @staticmethod
    def _use_project_model_dir():
        """Chroma saves the model under the user profile (~/.cache), which Windows can block
        (PermissionError). Save it in data/model_cache instead, or in KACHRACHECK_MODEL_DIR."""
        try:
            from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2
        except ImportError:
            return
        folder = Path(os.environ.get("KACHRACHECK_MODEL_DIR") or ROOT / "data" / "model_cache")
        ONNXMiniLM_L6_V2.DOWNLOAD_PATH = folder / ONNXMiniLM_L6_V2.MODEL_NAME

    def embed(self, texts: List[str]) -> np.ndarray:
        return _normalise(np.array(self._fn(list(texts)), dtype=float))


def get_embedder(name: Optional[str] = None):
    name = (name or os.environ.get("KACHRACHECK_EMBEDDER") or "minilm").lower()
    if name == "hash":
        return HashEmbedder()
    if name == "minilm":
        return MiniLMEmbedder()
    raise ValueError(f"unknown embedder {name!r}; use 'minilm' or 'hash'")


class SemanticIndex:
    """All chunk vectors in memory; cosine similarity is a dot product because vectors are normalised."""

    def __init__(self, chunks: List[Chunk], embedder=None, batch: int = 64):
        self.chunks = list(chunks)
        self.embedder = embedder or get_embedder()
        parts = [self.embedder.embed([c.text for c in self.chunks[i:i + batch]])
                 for i in range(0, len(self.chunks), batch)]
        self.matrix = np.vstack(parts) if parts else np.zeros((0, self.embedder.dim))

    def search(self, query: str, k: int = 5):
        """Return [(chunk, score)] best first. Score is cosine similarity (1.0 = identical direction)."""
        if not self.chunks or not query.strip():
            return []
        scores = self.matrix @ self.embedder.embed([query])[0]
        order = np.argsort(scores)[::-1][:k]
        return [(self.chunks[i], round(float(scores[i]), 4)) for i in order]


# ---------------------------------------------------------------- evaluation report
def _expected_rule_numbers(question: dict) -> set:
    """Rule numbers of the curated records that answer the question (from data/records.json)."""
    from app import records as rec
    by_id = {r.id: r for r in rec.load_records()}
    numbers = set()
    for rid in question.get("expected_record_ids", []):
        m = re.search(r"Rule\s+(\d+)", by_id[rid].rule_reference) if rid in by_id else None
        if m:
            numbers.add(int(m.group(1)))
    return numbers


def _rule_of(chunk: Chunk) -> Optional[int]:
    m = re.match(r"Rule (\d+):", chunk.title)
    return int(m.group(1)) if m else None


def write_eval(index: SemanticIndex, questions: List[dict], stats: List[dict], out: Path = EVAL_OUT, k: int = 3):
    lines = [
        "# Semantic search results: the 10 KachraCheck questions", "",
        f"- Run: {datetime.now().strftime('%d %B %Y, %H:%M')}",
        f"- Embedder: `{index.embedder.name}`",
        f"- Chunks searched: {len(index.chunks)} from {', '.join(s['source'] for s in stats if 'chunks' in s)}",
        f"- A hit counts as **correct** when a top-{k} chunk sits under the rule that the question's expected record "
        "comes from (the rule number is read from the chunk's title).", "",
    ]
    hits_total = answerable = 0
    summary = []
    sections = []
    for q in questions:
        results = index.search(q["question"], k)
        expected = _expected_rule_numbers(q)
        found = {_rule_of(c) for c, _ in results} & expected
        if q["answerable"]:
            answerable += 1
            hits_total += bool(found)
            verdict = "HIT" if found else "MISS"
        else:
            verdict = f"no answer expected (top score {results[0][1] if results else 0})"
        summary.append(f"| {q['id']} | {q['question']} | {', '.join(f'Rule {n}' for n in sorted(expected)) or 'none'} | "
                       f"{results[0][1] if results else 0} | {verdict} |")
        sec = [f"### Q{q['id']}. {q['question']}", "", f"Expected: {', '.join(f'Rule {n}' for n in sorted(expected)) or 'nothing (data cannot answer)'} "
               f"· Result: **{verdict}**", ""]
        for rank, (c, score) in enumerate(results, 1):
            snippet = c.text[:220].replace("\n", " ")
            sec.append(f"{rank}. **{score}** · {c.title} · `{c.source}` p.{c.page}  \n   {snippet}...")
        sections.append("\n".join(sec))
    lines += [f"**Answerable questions with a correct hit in the top {k}: {hits_total} of {answerable}.**", "",
              "| Q | Question | Expected rule | Top score | Result |", "|---|---|---|---|---|", *summary, "",
              "## Hits per question", "", "\n\n".join(sections), ""]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    return hits_total, answerable


def main(argv=None):
    import json
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--embedder", choices=["minilm", "hash"], default=None)
    ap.add_argument("--eval", action="store_true", help="run the 10 questions and write eval/search_results.md")
    ap.add_argument("--query", help="search for one question")
    ap.add_argument("-k", type=int, default=3)
    args = ap.parse_args(argv)

    chunks, stats = chunk_raw_dir()
    if not chunks:
        print("No chunks: put the PDFs in data/raw (run `python -m app.fetch`).")
        return 1
    index = SemanticIndex(chunks, get_embedder(args.embedder))
    if args.query:
        for c, score in index.search(args.query, args.k):
            print(f"{score}  {c.title} | {c.source} p.{c.page}\n      {c.text[:160]}...")
    if args.eval:
        questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))
        hits, total = write_eval(index, questions, stats, k=args.k)
        print(f"{hits} of {total} answerable questions have a correct hit in the top {args.k} -> {EVAL_OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
