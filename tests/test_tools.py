"""Run:  python -m unittest discover tests"""
import collections
import unittest

from app import tools
from app.tools import ToolBox, waste_stream_sorter as sort_item


class CsvTests(unittest.TestCase):
    def test_table_is_valid_and_complete(self):
        items = tools.load_items()
        self.assertEqual(tools.csv_problems(), [])
        self.assertGreaterEqual(len(items), 50)
        self.assertEqual({r["stream"] for r in items}, set(tools.STREAMS))
        for r in items:
            self.assertTrue(r["handling_note"] and r["rule_reference"].startswith("Rule 5"), r["item"])
            self.assertIn(r["basis"][:3], ("nam", "my "), r["item"])

    def test_no_name_or_alias_belongs_to_two_items(self):
        seen = collections.defaultdict(set)
        for r in tools.load_items():
            for n in r["names"]:
                seen[n].add(r["item"])
        self.assertEqual({n: v for n, v in seen.items() if len(v) > 1}, {})

    def test_sanitary_items_point_to_the_wrapping_rule(self):
        for r in tools.load_items():
            if r["stream"] == "sanitary":
                self.assertIn("Rule 5(1)(c)", r["rule_reference"])


class SorterTests(unittest.TestCase):
    def test_exact_alias_case_and_plural(self):
        self.assertEqual(sort_item("plastic bottle")["stream"], "dry")
        self.assertEqual(sort_item("PET bottle")["matched_item"], "plastic bottle")
        self.assertEqual(sort_item("Batteries")["stream"], "special care")
        self.assertEqual(sort_item("  The diapers! ")["stream"], "sanitary")
        self.assertEqual(sort_item("banana peel")["stream"], "wet")
        for q in ("plastic bottle", "batteries"):
            r = sort_item(q)
            self.assertEqual((r["match_type"], r["needs_confirmation"]), ("exact", False))

    def test_modifier_and_phrase_around_a_known_item(self):
        self.assertEqual(sort_item("a used battery")["matched_item"], "battery")
        self.assertEqual(sort_item("empty plastic bottle")["stream"], "dry")
        self.assertEqual(sort_item("used mask")["stream"], "sanitary")          # 'used mask' is itself an item

    def test_misspelling_is_matched_but_needs_confirmation(self):
        for typo, expected in [("batery", "battery"), ("plastic botle", "plastic bottle"), ("sanitry napkin", "sanitary napkin"),
                               ("vegitable peel", "vegetable peels"), ("cfl blub", "cfl bulb")]:
            r = sort_item(typo)
            self.assertTrue(r["found"], typo)
            self.assertEqual(r["matched_item"], expected)
            self.assertEqual(r["match_type"], "fuzzy")
            self.assertTrue(r["needs_confirmation"])
            self.assertGreaterEqual(r["similarity"], tools.FUZZY_ACCEPT)

    def test_unknown_item_is_not_guessed(self):
        r = sort_item("battery operated toy")
        self.assertFalse(r["found"])
        r = sort_item("xylophone")
        self.assertFalse(r["found"])
        self.assertEqual(r["suggestions"], [])                                  # no look-alike noise

    def test_empty_input(self):
        self.assertFalse(sort_item("   ")["found"])
        self.assertIn("error", sort_item(""))

    def test_result_fields(self):
        r = sort_item("expired tablets")
        for key in ("found", "query", "match_type", "similarity", "needs_confirmation", "matched_item", "stream",
                    "handling_note", "rule_reference", "basis"):
            self.assertIn(key, r)
        self.assertIn("authorised", r["handling_note"])


class ToolBoxTests(unittest.TestCase):
    def test_unknown_tool_and_bad_arguments_return_errors(self):
        box = ToolBox(rules_search=lambda q, k: {"answered": False})
        self.assertIn("unknown tool", box.call("delete_everything", {})["error"])
        self.assertIn("non-empty", box.call("waste_stream_sorter", {})["error"])
        self.assertIn("non-empty", box.call("search_rules", {"question": "  "})["error"])
        self.assertIn("non-empty", box.call("search_rules", "not a dict")["error"])

    def test_a_failing_tool_does_not_raise(self):
        def boom(q, k):
            raise RuntimeError("index exploded")
        out = ToolBox(rules_search=boom).call("search_rules", {"question": "anything"})
        self.assertIn("index exploded", out["error"])

    def test_both_tools_work_through_call(self):
        box = ToolBox(rules_search=lambda q, k: {"answered": True, "answer": q, "citations": []})
        self.assertEqual(box.call("waste_stream_sorter", {"item": "diaper"})["stream"], "sanitary")
        self.assertEqual(box.call("search_rules", {"question": "hi there"})["answer"], "hi there")

    def test_long_input_is_cut(self):
        out = ToolBox().call("waste_stream_sorter", {"item": "x" * 5000})
        self.assertFalse(out["found"])


if __name__ == "__main__":
    unittest.main()
