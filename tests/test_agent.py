"""Run:  python -m unittest discover tests"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import agent_loop, llm
from app.agent_loop import LLMPlanner, RulePlanner, Step, compose_answer, extract_item, run_agent
from app.tools import ToolBox


def fake_rules(question, k):
    return {"answered": True, "answer": f"RULES: {question}", "reason": "ok",
            "citations": [{"n": 1, "title": "Rule 5: Duties of waste generator", "source": "rules.pdf", "page": 12}]}


def refusing_rules(question, k):
    return {"answered": False, "answer": "I don't know.", "reason": "low_similarity", "citations": []}


BOX = ToolBox(rules_search=fake_rules)


class ExtractItemTests(unittest.TestCase):
    def test_phrasings(self):
        cases = {"Where does a used battery go?": "used battery",
                 "Which bin should my old paint tin go in?": None,
                 "How do I dispose of expired tablets?": "expired tablets",
                 "What stream is a diaper?": "diaper",
                 "Is a pizza box wet or dry?": "pizza box",
                 "Can I put a diaper in the dry bin?": "diaper",
                 "plastic bottle": "plastic bottle", "batery": "batery",
                 "Where does it go?": "it"}
        for question, item in cases.items():
            if item is not None:
                self.assertEqual(extract_item(question), item, question)

    def test_rule_questions_and_small_talk_are_not_items(self):
        for q in ["What does the rule say about bulk generators", "Who must register on the portal?", "hello", "thanks"]:
            self.assertIsNone(extract_item(q), q)


class RunAgentTests(unittest.TestCase):
    def run_q(self, q, box=BOX, memory=None):
        return run_agent(q, box, RulePlanner(), memory)

    def test_item_question_uses_only_the_sorter(self):
        r = self.run_q("Where does a used battery go?")
        self.assertEqual([s.tool for s in r.steps], ["waste_stream_sorter"])
        self.assertIn("special care", r.answer)
        self.assertEqual(r.memory["last_item"], "battery")

    def test_rule_question_uses_only_the_search(self):
        r = self.run_q("What does the rule say about bulk waste generators?")
        self.assertEqual([s.tool for s in r.steps], ["search_rules"])
        self.assertIn("Sources: Rule 5", r.answer)

    def test_a_question_that_needs_both_tools_uses_both_in_order(self):
        r = self.run_q("Where does a used battery go and which rule says so?")
        self.assertEqual([s.tool for s in r.steps], ["waste_stream_sorter", "search_rules"])
        self.assertIn("special care waste", r.steps[1].input["question"])

    def test_unknown_item_falls_back_to_the_rules_search(self):
        r = self.run_q("Where does a pizza box go?")
        self.assertEqual([s.tool for s in r.steps], ["waste_stream_sorter", "search_rules"])
        self.assertIn("I don't have 'pizza box'", r.answer)

    def test_unknown_item_and_no_rules_evidence_says_i_dont_know(self):
        r = self.run_q("Where does a pizza box go?", ToolBox(rules_search=refusing_rules))
        self.assertIn("I don't know", r.answer)

    def test_pronoun_uses_memory_or_asks(self):
        r = self.run_q("Where does it go?", memory={"last_item": "diaper", "last_stream": "sanitary"})
        self.assertEqual(r.steps[0].input, {"item": "diaper"})
        self.assertIn("Which item", self.run_q("Where does it go?").answer)

    def test_follow_up_why_searches_the_rules_for_the_remembered_stream(self):
        r = self.run_q("why?", memory={"last_item": "diaper", "last_stream": "sanitary"})
        self.assertEqual([s.tool for s in r.steps], ["search_rules"])
        self.assertIn("sanitary waste", r.steps[0].input["question"])

    def test_small_talk_gets_help_text_and_no_tool_call(self):
        r = self.run_q("hello")
        self.assertEqual(r.steps, [])
        self.assertIn("which stream", r.answer)

    def test_loop_stops_at_max_steps_and_on_repeats(self):
        class Endless:
            name = "endless"
            def __init__(self): self.n = 0
            def next_action(self, q, m, s):
                self.n += 1
                return {"tool": "search_rules", "input": {"question": f"q{self.n}"}}
        self.assertEqual(len(run_agent("x", BOX, Endless(), max_steps=3).steps), 3)

        class Repeats:
            name = "repeats"
            def next_action(self, q, m, s):
                return {"tool": "search_rules", "input": {"question": "same"}}
        self.assertEqual(len(run_agent("x", BOX, Repeats()).steps), 1)

    def test_a_crashing_planner_falls_back_to_rules(self):
        class Broken:
            name = "broken"
            def next_action(self, q, m, s):
                raise RuntimeError("planner down")
        r = run_agent("plastic bottle", BOX, Broken())
        self.assertIn("dry", r.answer)

    def test_tool_errors_are_reported_not_raised(self):
        def boom(q, k):
            raise RuntimeError("index exploded")
        r = self.run_q("What does the rule say about bulk waste generators?", ToolBox(rules_search=boom))
        self.assertIn("could not search", r.answer)


class ComposeTests(unittest.TestCase):
    def step(self, **obs):
        return Step(1, "waste_stream_sorter", {"item": "x"}, obs)

    def test_fuzzy_match_is_announced_and_judgement_items_carry_a_caveat(self):
        obs = {"found": True, "query": "batery", "match_type": "fuzzy", "matched_item": "battery", "stream": "special care",
               "handling_note": "Note.", "rule_reference": "Rule 5(1)(b)", "basis": "named in published summaries of the Rules"}
        self.assertIn("I read 'batery' as 'battery'", compose_answer([self.step(**obs)]))
        obs.update(match_type="exact", basis="my reading of the stream definitions")
        self.assertIn("The Rules do not name this item", compose_answer([self.step(**obs)]))
        obs.update(basis="named in published summaries of the Rules")
        self.assertNotIn("do not name", compose_answer([self.step(**obs)]))

    def test_not_found_lists_suggestions(self):
        text = compose_answer([self.step(found=False, query="batry", suggestions=["battery"])])
        self.assertIn("Did you mean: battery?", text)


class LLMPlannerTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"GROQ_API_KEY": "test", "LLM_PROVIDER": "groq"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def planner_with(self, replies):
        planner = LLMPlanner()
        patcher = mock.patch.object(llm, "complete", side_effect=replies)
        patcher.start()
        self.addCleanup(patcher.stop)
        return planner

    def test_valid_json_actions_are_followed(self):
        planner = self.planner_with(['Sure! {"action": "tool", "tool": "waste_stream_sorter", "input": {"item": "diaper"}}', '{"action": "final"}'])
        r = run_agent("anything", BOX, planner)
        self.assertEqual(r.steps[0].input, {"item": "diaper"})
        self.assertEqual(len(r.steps), 1)
        self.assertTrue(r.planner.startswith("llm:groq/"))

    def test_garbage_unknown_tool_or_exception_falls_back_to_the_rule_planner(self):
        for reply in ["no json here", '{"action": "tool", "tool": "rm_rf", "input": {}}', RuntimeError("down"),
                      '{"action": "tool", "tool": "search_rules", "input": "not a dict"}']:
            planner = self.planner_with([reply, reply, reply])
            r = run_agent("plastic bottle", BOX, planner)
            self.assertEqual(r.steps[0].tool, "waste_stream_sorter", reply)
            self.assertIn("dry", r.answer)

    def test_make_planner_modes(self):
        self.assertIsInstance(agent_loop.make_planner("rules"), RulePlanner)
        self.assertIsInstance(agent_loop.make_planner("auto"), LLMPlanner)
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "", "GEMINI_API_KEY": ""}), mock.patch.object(llm, "load_env"):
            self.assertIsInstance(agent_loop.make_planner("auto"), RulePlanner)
            with self.assertRaises(ValueError):
                agent_loop.make_planner("llm")
        with self.assertRaises(ValueError):
            agent_loop.make_planner("magic")


class GraphTests(unittest.TestCase):
    def setUp(self):
        from app.graph import AgentService
        self.svc = AgentService(BOX, RulePlanner())

    def test_exact_item_finishes_without_approval(self):
        r = self.svc.ask("Where does a used battery go?")
        self.assertEqual(r["status"], "done")
        self.assertIn("special care", r["answer"])
        self.assertEqual(r["memory"]["last_item"], "battery")

    def test_memory_carries_over_within_a_thread_only(self):
        t = self.svc.ask("diaper")["thread_id"]
        again = self.svc.ask("why?", t)
        self.assertIn("sanitary waste", again["steps"][0]["input"]["question"])
        other = self.svc.ask("why?")
        self.assertNotIn("sanitary", other["steps"][0]["input"]["question"])
        self.assertEqual(len(self.svc.memory(t)["history"]), 2)

    def test_guessed_spelling_pauses_for_approval_then_continues(self):
        r = self.svc.ask("batery")
        self.assertEqual(r["status"], "needs_approval")
        self.assertEqual(r["approval"]["proposed_item"], "battery")
        self.assertEqual(r["answer"], "")
        done = self.svc.resume(r["thread_id"], True)
        self.assertEqual(done["status"], "done")
        self.assertIn("I read 'batery' as 'battery'", done["answer"])

    def test_rejecting_the_guess_does_not_sort_the_item(self):
        r = self.svc.ask("batery")
        done = self.svc.resume(r["thread_id"], False)
        self.assertIn("won't guess", done["answer"])
        self.assertNotIn("special care stream", done["answer"])
        self.assertEqual(done["memory"], {})                      # nothing was remembered from the rejected guess

    def test_new_message_while_waiting_is_refused_and_resume_needs_a_pending_approval(self):
        from app.graph import PendingApproval
        t = self.svc.ask("batery")["thread_id"]
        with self.assertRaises(PendingApproval):
            self.svc.ask("something else", t)
        self.svc.resume(t, True)
        with self.assertRaises(KeyError):
            self.svc.resume(t, True)

    def test_rules_question_runs_the_search_node(self):
        r = self.svc.ask("What does the rule say about bulk waste generators?")
        self.assertEqual(r["tools_used"], ["search_rules"])
        self.assertTrue(r["citations"])


class AgentEndpointTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        import app.main as main
        from app.graph import AgentService
        self.main = main
        main._AGENT = AgentService(BOX, RulePlanner())
        self.client = TestClient(main.app)
        self.addCleanup(lambda: setattr(main, "_AGENT", None))

    def test_full_conversation_over_http(self):
        r = self.client.post("/agent", json={"message": "batery"}).json()
        self.assertEqual(r["status"], "needs_approval")
        self.assertIn("battery", r["approval"]["message"])
        busy = self.client.post("/agent", json={"message": "hi", "thread_id": r["thread_id"]})
        self.assertEqual(busy.status_code, 409)
        done = self.client.post("/agent", json={"thread_id": r["thread_id"], "approve": True}).json()
        self.assertEqual(done["status"], "done")
        memory = self.client.get(f"/agent/{r['thread_id']}").json()
        self.assertEqual(memory["memory"]["last_item"], "battery")

    def test_validation(self):
        self.assertEqual(self.client.post("/agent", json={}).status_code, 422)
        self.assertEqual(self.client.post("/agent", json={"approve": True}).status_code, 422)
        self.assertEqual(self.client.post("/agent", json={"thread_id": "nope", "approve": True}).status_code, 404)
        self.assertEqual(self.client.get("/agent/unknown").status_code, 404)
        self.assertEqual(self.client.post("/agent", json={"message": ""}).status_code, 422)


if __name__ == "__main__":
    unittest.main()
