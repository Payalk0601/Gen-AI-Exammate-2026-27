"""Run the 10 KachraCheck user questions through the search engine and score the result.

  python analysis/check_questions.py

hit@3 = at least one expected record is in the top 3 results.
For an unanswerable question the correct behaviour is answerable=False (nothing returned).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import records as rec                      # noqa: E402
from app.smart_search import MIN_COVERAGE, SmartSearch  # noqa: E402

questions = json.loads((Path(__file__).resolve().parent.parent / "data" / "questions.json").read_text(encoding="utf-8"))
engine = SmartSearch(rec.load_records())

correct = 0
print(f"{'Q':<3}{'expected':<12}{'system says':<14}{'top-3 ids':<14}{'cover':<7}result")
print("-" * 62)
for q in questions:
    hits = engine.rank(q["question"], 3)
    ids = [r.id for r, _ in hits]
    cov, missing = engine.coverage(q["question"])
    says_answerable = cov >= MIN_COVERAGE
    if q["answerable"]:
        ok = says_answerable and any(i in q["expected_record_ids"] for i in ids)
    else:
        ok = not says_answerable
    correct += ok
    print(f"{q['id']:<3}{'answer' if q['answerable'] else 'NO ANSWER':<12}"
          f"{'answer' if says_answerable else 'NO ANSWER':<14}{str(ids):<14}{cov:<7}{'PASS' if ok else 'FAIL'}")
    if not q["answerable"] or not ok:
        print(f"   words not in the data: {missing}")
print(f"\n{correct} of {len(questions)} questions handled correctly")
