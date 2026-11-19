"""Run:  python -m unittest discover tests
The Streamlit tests run the real ui/app.py with a fake API (no server, no network)."""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ui import client, compare, feedback

ROOT = Path(__file__).resolve().parent.parent
PAIRS = compare.load_pairs()
BINS_SENTENCE = "Local bodies shall paint public bins green for wet waste and blue for dry waste."


def ask_response(**over):
    base = {"question": "What bin colours must my municipality use?", "answer": f"{BINS_SENTENCE} [1]", "answered": True,
            "reason": "ok", "generator": "extractive",
            "citations": [{"n": 1, "title": "Rule 39: Duties of local bodies", "source": "rules.pdf", "page": 30, "score": 0.4,
                           "text": BINS_SENTENCE, "chunk_id": "c1"}], "considered": []}
    base.update(over)
    return base


def agent_response(item_rule="Rule 5(1)(b); Rule 5(1)(c)", **over):
    obs = {"found": True, "query": "diaper", "match_type": "exact", "matched_item": "diaper", "stream": "sanitary",
           "rule_reference": item_rule, "needs_confirmation": False}
    base = {"thread_id": "t1", "status": "done", "answer": "**Diaper** goes in the **sanitary** stream.", "approval": None,
            "steps": [{"n": 1, "tool": "waste_stream_sorter", "input": {"item": "diaper"}, "observation": obs}],
            "tools_used": ["waste_stream_sorter"], "citations": [], "planner": "rules", "memory": {}}
    base.update(over)
    return base


class DiffTests(unittest.TestCase):
    def test_changed_words_are_marked_on_the_right_side(self):
        old, new, stats = compare.word_diff("three separate streams", "four separate streams")
        self.assertIn('<span class="del">three</span>', old)
        self.assertIn('<span class="add">four</span>', new)
        self.assertNotIn("<span", old.replace('<span class="del">three</span>', ""))
        self.assertEqual(stats, {"removed_words": 1, "added_words": 1})

    def test_identical_text_has_no_highlight(self):
        old, new, stats = compare.word_diff("same text.", "same text.")
        self.assertNotIn("<span", old + new)
        self.assertEqual(stats["removed_words"] + stats["added_words"], 0)

    def test_pure_addition_and_html_is_escaped(self):
        old, new, _ = compare.word_diff("", "a <b>new</b> duty")
        self.assertEqual(old, "")
        self.assertIn("&lt;b&gt;new&lt;/b&gt;", new)
        self.assertNotIn("<b>", new)

    def test_punctuation_and_case_do_not_count_as_changes(self):
        old, _, stats = compare.word_diff("Bins, green.", "bins green")
        self.assertEqual(stats["removed_words"], 0)


class PairDataTests(unittest.TestCase):
    def test_every_pair_is_complete_and_the_diff_is_meaningful(self):
        self.assertGreaterEqual(len(PAIRS), 10)
        for p in PAIRS:
            for key in ("id", "topic", "rule_2026", "rule_number", "rule_2016", "status", "text_2026", "what_changed", "keywords"):
                self.assertIn(key, p, p.get("id"))
            _, _, stats = compare.word_diff(p["text_2016"], p["text_2026"])
            if p["status"] == "unchanged":
                self.assertEqual(stats["removed_words"] + stats["added_words"], 0, p["id"])
            if p["status"] == "changed":
                self.assertGreater(stats["removed_words"] + stats["added_words"], 0, p["id"])
            if p["status"] == "new":
                self.assertEqual(p["text_2016"], "")

    def test_streams_example_highlights_three_to_four(self):
        p = next(p for p in PAIRS if p["id"] == "streams")
        old, new, _ = compare.word_diff(p["text_2016"], p["text_2026"])
        self.assertIn('<span class="del">three</span>', old)
        self.assertIn('<span class="add">four</span>', new)
        self.assertIn('<span class="add">sanitary</span>', new)


class MatchingTests(unittest.TestCase):
    def ids(self, resp):
        return [p["id"] for p in compare.pairs_for_response(resp, PAIRS)]

    def test_sorter_rule_reference_selects_exact_pairs(self):
        self.assertEqual(self.ids(agent_response()), ["streams", "sanitary"])
        self.assertEqual(self.ids(agent_response(item_rule="Rule 5(1)(b)")), ["streams"])

    def test_citation_rule_number_and_text_pick_the_bins_pair(self):
        self.assertEqual(self.ids(ask_response())[0], "bins")

    def test_refused_or_uncited_answers_have_no_comparison(self):
        self.assertEqual(self.ids(ask_response(answered=False, citations=[], answer="I don't know.")), [])
        self.assertEqual(self.ids({"answer": "hello", "steps": [], "citations": []}), [])

    def test_citation_from_a_rule_with_no_matching_words_gets_nothing(self):
        resp = ask_response(answer="Unrelated sentence about nothing.", citations=[
            {"n": 1, "title": "Rule 39: x", "source": "r.pdf", "page": 1, "text": "Unrelated sentence about nothing."}],
            question="Unrelated?")
        self.assertEqual(self.ids(resp), [])

    def test_full_2026_text_prefers_the_pdf_row_then_the_curated_summary(self):
        pair = next(p for p in PAIRS if p["id"] == "bins")
        text, label = compare.full_2026_text(pair, [{"rule_reference": "Rule 39(51)", "obligation": "FROM PDF"}], [])
        self.assertEqual((text, label), ("FROM PDF", "Clause as printed in the 2026 gazette PDF"))
        curated = compare.load_json(compare.CURATED_PATH)
        text, label = compare.full_2026_text(pair, [], curated)
        self.assertTrue(text and label.startswith("My summary"))
        self.assertEqual(compare.full_2026_text({"lookup_ref": None, "curated_id": None}, [], curated), (None, ""))


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"KACHRACHECK_FEEDBACK_DB": str(Path(tempfile.mkdtemp()) / "f.db")})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_one_row_per_answer_and_the_other_thumb_replaces_it(self):
        feedback.save_feedback("m1", 1, "q", "a", "ask", "t")
        feedback.save_feedback("m2", -1, "q2", "a2", "agent", "t")
        self.assertEqual(feedback.counts(), {"up": 1, "down": 1})
        feedback.save_feedback("m1", -1, "q", "a", "ask", "t")
        self.assertEqual(feedback.counts(), {"up": 0, "down": 2})
        self.assertEqual(len(feedback.recent()), 2)

    def test_bad_rating_is_rejected_and_empty_db_counts_zero(self):
        self.assertEqual(feedback.counts(), {"up": 0, "down": 0})
        with self.assertRaises(ValueError):
            feedback.save_feedback("m", 0)


class ClientTests(unittest.TestCase):
    def test_connection_timeout_and_http_errors_become_api_errors(self):
        import requests
        with mock.patch.object(client.requests, "request", side_effect=requests.exceptions.ConnectionError()):
            with self.assertRaises(client.ApiError) as cm:
                client.ask("http://127.0.0.1:9", "q")
        self.assertIn("uvicorn app.main:app", str(cm.exception))
        with mock.patch.object(client.requests, "request", side_effect=requests.exceptions.Timeout()):
            with self.assertRaises(client.ApiError):
                client.ask("http://x", "q")
        bad = mock.Mock(status_code=503)
        bad.json.return_value = {"detail": "The vector index is empty."}
        with mock.patch.object(client.requests, "request", return_value=bad):
            with self.assertRaises(client.ApiError) as cm:
                client.ask("http://x", "q")
        self.assertIn("vector index is empty", str(cm.exception))


try:
    from streamlit.testing.v1 import AppTest
except ImportError:                                   # pragma: no cover
    AppTest = None


@unittest.skipIf(AppTest is None, "streamlit not installed")
class AppTests(unittest.TestCase):
    def setUp(self):
        self.db = Path(tempfile.mkdtemp()) / "f.db"
        patcher = mock.patch.dict(os.environ, {"KACHRACHECK_FEEDBACK_DB": str(self.db)})
        patcher.start()
        self.addCleanup(patcher.stop)
        health = mock.patch.object(client, "health", return_value={"records": 20, "search_engine": "tfidf-cosine"})
        health.start()
        self.addCleanup(health.stop)
        self.at = AppTest.from_file(str(ROOT / "ui" / "app.py"), default_timeout=30)

    def say(self, text):
        self.at.chat_input[0].set_value(text).run()

    def all_markdown(self):
        return " ".join(m.value for m in self.at.markdown)

    def test_page_loads_with_sidebar_and_no_exception(self):
        self.at.run()
        self.assertFalse(self.at.exception)
        self.assertEqual(self.at.sidebar.radio[0].options, ["Ask the Rules", "Agent (items + Rules)"])
        self.assertIn("API online", self.at.sidebar.success[0].value)

    def test_ask_shows_answer_sources_and_saves_thumbs(self):
        with mock.patch.object(client, "ask", return_value=ask_response()) as ask:
            self.at.run()
            self.say("What bin colours must my municipality use?")
        self.assertFalse(self.at.exception)
        self.assertEqual(ask.call_args.args[1], "What bin colours must my municipality use?")
        self.assertEqual([m.name for m in self.at.chat_message], ["user", "assistant"])
        self.assertIn("paint public bins green", self.all_markdown())
        self.assertEqual([e.label for e in self.at.expander], ["Sources (1)"])
        up = next(b for b in self.at.button if b.label == "👍")
        up.click().run()
        self.assertEqual(feedback.counts(), {"up": 1, "down": 0})
        next(b for b in self.at.button if b.label == "👎").click().run()
        self.assertEqual(feedback.counts(), {"up": 0, "down": 1})
        rows = sqlite3.connect(self.db).execute("SELECT question, mode, rating FROM feedback").fetchall()
        self.assertEqual(rows, [("What bin colours must my municipality use?", "ask", -1)])

    def test_toggle_shows_2016_next_to_2026_with_highlights(self):
        with mock.patch.object(client, "ask", return_value=ask_response()):
            self.at.run()
            self.say("What bin colours must my municipality use?")
            self.assertNotIn("What changed", self.all_markdown())
            self.at.toggle[0].set_value(True).run()
        text = self.all_markdown()
        self.assertIn("2016 · Rule 15(h)", text)
        self.assertIn("2026 · Rule 39(51)", text)
        self.assertIn('<span class="del">white</span>', text)
        self.assertIn('<span class="add">blue</span>', text)
        self.assertIn("What changed", text)

    def test_toggle_on_an_answer_without_a_comparison_explains_why(self):
        refusal = ask_response(answered=False, citations=[], answer="I don't know.", reason="no_amount_in_sources")
        with mock.patch.object(client, "ask", return_value=refusal):
            self.at.run()
            self.say("What is the exact fine in rupees for a household that burns waste?")
            self.at.toggle[0].set_value(True).run()
        self.assertIn("No 2016 comparison for this answer", " ".join(i.value for i in self.at.info))

    def test_agent_mode_asks_for_approval_then_answers(self):
        needs = {"thread_id": "t9", "status": "needs_approval", "answer": "", "steps": [], "tools_used": [], "citations": [],
                 "planner": "rules", "memory": {}, "approval": {"message": "I read 'batery' as 'battery' (special care stream). Is that what you meant?"}}
        done = agent_response(thread_id="t9", answer="I read 'batery' as 'battery'. **Battery** goes in the **special care** stream.",
                              item_rule="Rule 5(1)(b)")
        with mock.patch.object(client, "agent", return_value=needs), mock.patch.object(client, "approve", return_value=done) as approve:
            self.at.run()
            self.at.sidebar.radio[0].set_value("Agent (items + Rules)").run()
            self.say("batery")
            self.assertIn("I read 'batery' as 'battery'", " ".join(i.value for i in self.at.info))
            self.assertTrue(self.at.chat_input[0].disabled)
            next(b for b in self.at.button if b.label.startswith("Yes")).click().run()
        self.assertEqual(approve.call_args.args[1:], ("t9", True))
        self.assertIn("goes in the **special care** stream", self.all_markdown())
        self.assertFalse(self.at.chat_input[0].disabled)

    def test_agent_answer_toggle_uses_the_sorters_rule_reference(self):
        with mock.patch.object(client, "agent", return_value=agent_response()):
            self.at.run()
            self.at.sidebar.radio[0].set_value("Agent (items + Rules)").run()
            self.say("diaper")
            self.at.toggle[0].set_value(True).run()
        text = self.all_markdown()
        self.assertIn("Wrapping sanitary waste", text)
        self.assertIn('<span class="del">dry</span>', text)

    def test_api_down_shows_a_helpful_message_and_does_not_crash(self):
        with mock.patch.object(client, "ask", side_effect=client.ApiError("Cannot reach the API. Start it with: uvicorn app.main:app")):
            self.at.run()
            self.say("anything")
        self.assertFalse(self.at.exception)
        self.assertIn("uvicorn app.main:app", self.all_markdown())

    def test_sample_question_button_sends_it(self):
        with mock.patch.object(client, "ask", return_value=ask_response()) as ask:
            self.at.run()
            next(b for b in self.at.sidebar.button if "bin colours" in b.label).click().run()
        self.assertIn("bin colours", ask.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
