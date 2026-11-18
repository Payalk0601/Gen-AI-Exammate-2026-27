"""Check everything a live demo needs BEFORE you go on stage.

  python ui/preflight.py                      # API on http://127.0.0.1:8000
  python ui/preflight.py --api http://127.0.0.1:8000
"""
import argparse
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ui import client, compare, feedback          # noqa: E402


def check(label, fn):
    try:
        detail = fn()
        print(f"[PASS] {label}" + (f": {detail}" if detail else ""))
        return True
    except Exception as err:                      # a failed check must not stop the others
        print(f"[FAIL] {label}: {err}")
        return False


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    api = ap.parse_args(argv).api
    results = []

    def health():
        h = client.health(api)
        assert h["records"] > 0, "no records"
        return f"{h['records']} records, search {h['search_engine']}"

    def index():
        r = client._call("GET", f"{api}/search/semantic", params={"q": "bin colours", "k": 1})
        assert r["count"] == 1, "vector index is empty: python -m app.vectorstore --rebuild"
        return f"top hit {r['results'][0]['title']}"

    def ask_answers():
        r = client.ask(api, "What bin colours must my municipality use?", 4)
        assert r["answered"] and r["citations"], f"not answered ({r['reason']})"
        return f"cites {r['citations'][0]['title']} p.{r['citations'][0]['page']} ({r['generator']})"

    def ask_refuses():
        r = client.ask(api, "What is the exact fine in rupees for a household that burns waste?", 4)
        assert not r["answered"] and "don't know" in r["answer"], "Q6 was answered"
        return f"refused ({r['reason']})"

    def agent_sorts():
        r = client.agent(api, "Where does a used battery go?")
        assert "special care" in r["answer"], r["answer"][:80]
        return f"planner {r['planner']}"

    def agent_approval():
        r = client.agent(api, "batery")
        assert r["status"] == "needs_approval", "no approval step"
        done = client.approve(api, r["thread_id"], True)
        assert done["status"] == "done"
        return "typo -> asked to confirm -> answered"

    def comparison():
        pairs = compare.load_pairs()
        assert len(pairs) >= 10, "data/rule_changes.json missing"
        r = client.ask(api, "What bin colours must my municipality use?", 4)
        assert compare.pairs_for_response(r, pairs), "the 2016 toggle has nothing to show for the bins answer"
        return f"{len(pairs)} comparisons, bins answer has one"

    def feedback_db():
        os.environ["KACHRACHECK_FEEDBACK_DB"] = str(Path(tempfile.mkdtemp()) / "check.db")
        feedback.save_feedback("preflight", 1)
        return "can write thumbs"

    for label, fn in [("API is up", health), ("Vector index has chunks", index), ("Ask answers with a citation", ask_answers),
                      ("Ask refuses Q6", ask_refuses), ("Agent sorts an item", agent_sorts),
                      ("Agent asks to confirm a typo", agent_approval), ("2016 comparison data", comparison),
                      ("Feedback can be saved", feedback_db)]:
        results.append(check(label, fn))
    print(f"\n{sum(results)} of {len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
