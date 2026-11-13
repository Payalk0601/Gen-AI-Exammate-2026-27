"""Run:  python -m unittest discover tests"""
import json
import tempfile
import unittest
from pathlib import Path

from app import ingest

SAMPLE = """THE GAZETTE OF INDIA : EXTRAORDINARY
1. Short title and commencement.\u2014 (1) These rules may be called the Solid Waste Management Rules, 2026.
2. Application.\u2014 These rules shall apply to every waste generator in the country.
3. Definitions.\u2014 In these rules, unless the context otherwise requires, terms are defined below.
4. General principles.\u2014 Local bodies shall follow the polluter pays principle in all actions.
5. Duties of waste generators.\u2014 (1) Every waste generator shall,\u2014
(a) segregate the waste at source into wet, dry, sanitary and special care waste and hand it over
to authorised waste pickers as directed by the local body from time to time;
(b) pay the user fee as specified in the bye-laws of the local body.
(2) Large premises shall ensure source segregation within one year of notification of these rules.
6. Duties of bulk waste generators.\u2014 Every bulk waste generator shall register on the centralised portal
and file an annual return by 30th June every year.
7. Duties and responsibilities of waste processing facility operators.\u2014 (1) The operator shall file quarterly
returns by the 15th of the first month of the next quarter and an annual return (i) in Form III, (ii) on the portal.
8. Annexure list.\u2014 Not a duty rule but present as a heading with enough words to be kept.
"""


class ParsingTests(unittest.TestCase):
    def test_split_rules_in_order(self):
        rules = ingest.split_rules(SAMPLE)
        self.assertEqual(list(rules)[:5], [1, 2, 3, 4, 5])
        self.assertEqual(rules[5][0], "Duties of waste generators")

    def test_stakeholder_prefix_removed(self):
        self.assertEqual(ingest.stakeholder_from_title("Duties of waste generators"), "Waste generators")
        self.assertEqual(ingest.stakeholder_from_title("Duties and responsibilities of the State Pollution Control Boards"),
                         "State Pollution Control Boards")

    def test_clauses_get_sub_rule_and_letter_and_intro(self):
        body = ingest.split_rules(SAMPLE)[5][1]
        clauses = ingest.split_clauses(body)
        refs = [(s, l) for s, l, _ in clauses]
        self.assertEqual(refs, [(1, "a"), (1, "b"), (2, None)])
        self.assertTrue(clauses[0][2].startswith("Every waste generator shall"))

    def test_standalone_clause_does_not_get_intro(self):
        body = "(1) Every waste generator shall,\u2014 (a) pay the fee; (b) Every street vendor shall keep the area clean."
        clauses = ingest.split_clauses(body)
        self.assertTrue(clauses[0][2].startswith("Every waste generator shall pay"))
        self.assertEqual(clauses[1][2], "Every street vendor shall keep the area clean.")

    def test_roman_list_stays_inside_clause(self):
        body = ingest.split_rules(SAMPLE)[7][1]
        self.assertEqual(len(ingest.split_clauses(body)), 1)

    def test_timeline_extraction(self):
        self.assertIn("30th June", ingest.extract_timeline("file an annual return by 30th June every year"))
        self.assertIn("within one year", ingest.extract_timeline("ensure this within one year of notification"))
        self.assertIn("15th of the first month", ingest.extract_timeline("by the 15th of the first month of the next quarter"))
        self.assertEqual(ingest.extract_timeline("keep the premises clean"), "Not stated in clause")
        self.assertEqual(ingest.extract_timeline("as the local body directs from time to time"), "from time to time")

    def test_category(self):
        self.assertEqual(ingest.classify("file an annual return"), "Reporting")
        self.assertEqual(ingest.classify("register on the portal"), "Registration")

    def test_language_detection(self):
        self.assertGreater(ingest.latin_ratio("Duties of waste generators " * 20), 0.9)
        self.assertLess(ingest.latin_ratio("\u0905\u092a\u0936\u093f\u0937\u094d\u091f " * 40), 0.1)


class PdfPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from fpdf import FPDF
        except ImportError:
            raise unittest.SkipTest("fpdf2 not installed (only needed for this test)")
        cls.tmp = tempfile.mkdtemp()
        cls.pdf = Path(cls.tmp) / "rules.pdf"
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", size=10)
        for line in SAMPLE.replace("\u2014", "-").splitlines():
            pdf.multi_cell(0, 5, line, new_x="LMARGIN", new_y="NEXT")
        pdf.output(str(cls.pdf))

    def test_rows_built_from_pdf(self):
        rows, stats = ingest.build_from_pdf(self.pdf)
        refs = [r.rule_reference for r in rows]
        self.assertIn("Rule 5(1)(a)", refs)
        self.assertIn("Rule 6", refs)
        bulk = next(r for r in rows if r.rule_reference == "Rule 6")
        self.assertEqual(bulk.stakeholder, "Bulk waste generators")
        self.assertIn("30th June", bulk.timeline)
        self.assertEqual(bulk.category, "Reporting")
        self.assertGreaterEqual(stats["rows_built"], 4)

    def test_unreadable_pdf_gives_clear_error(self):
        bad = Path(self.tmp) / "bad.pdf"
        bad.write_text("not a pdf")
        with self.assertRaises(RuntimeError):
            ingest.build_from_pdf(bad)


class CuratedCleaningTests(unittest.TestCase):
    def test_bad_rows_and_duplicates_skipped(self):
        base = json.loads(Path(ingest.SEED).read_text(encoding="utf-8"))
        rows = [dict(base[0]), dict(base[0]), {**base[1], "obligation": ""}, {"id": "x"}]
        tmp = Path(tempfile.mkdtemp())
        (tmp / "seed.json").write_text(json.dumps(rows), encoding="utf-8")
        recs, errors = ingest.ingest(seed=tmp / "seed.json", out=tmp / "out.json")
        self.assertEqual(len(recs), 1)
        self.assertEqual(len(errors), 3)


if __name__ == "__main__":
    unittest.main()
