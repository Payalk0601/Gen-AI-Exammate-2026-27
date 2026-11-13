"""Run all questions through prompt v1 and v2 and write eval/prompt_compare.md.

Usage (from repo root):  python -m eval.run_compare
Edit eval/questions.txt first so it holds YOUR 10 questions.
"""
from pathlib import Path

from app.chat import answer_question

HERE = Path(__file__).resolve().parent
questions = [q.strip() for q in (HERE / "questions.txt").read_text(encoding="utf-8").splitlines() if q.strip()]


def cell(text: str) -> str:
    return text.replace("\n", " ").replace("|", "/")


lines = [
    "# Prompt comparison: v1 (direct) vs v2 (stepwise)",
    "",
    "Same system prompt, same retrieval, same model. Only the task prompt differs.",
    "",
    "| # | Question | v1 answer | v1 conf | v2 answer | v2 conf | Better |",
    "|---|---|---|---|---|---|---|",
]
for i, q in enumerate(questions, 1):
    row = [str(i), cell(q)]
    for v in ("v1", "v2"):
        try:
            r = answer_question(q, v)
            row += [cell(r["answer"]), r["confidence"]]
        except Exception as e:  # keep going so one failure doesn't lose the table
            row += [f"ERROR: {cell(str(e))}", "-"]
    row.append("")  # fill in v1 / v2 by hand
    lines.append("| " + " | ".join(row) + " |")

lines += [
    "",
    "## My observations (write in your own words)",
    "- JSON format: which version returned valid JSON more reliably?",
    "- Grounding: which version used the records and rule ids better?",
    "- Hallucination: which version made up fewer details?",
    "- Decision: which version is the default and why?",
]
(HERE / "prompt_compare.md").write_text("\n".join(lines), encoding="utf-8")
print(f"Wrote {HERE / 'prompt_compare.md'}")
