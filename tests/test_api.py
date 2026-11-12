"""Run:  python -m unittest discover tests"""
import unittest

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class ApiTests(unittest.TestCase):
    def test_health(self):
        r = client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ok")

    def test_records_limit(self):
        self.assertEqual(len(client.get("/records?limit=3").json()), 3)
        self.assertEqual(client.get("/records?limit=0").status_code, 422)

    def test_record_found_and_404(self):
        self.assertEqual(client.get("/records/1").json()["id"], 1)
        self.assertEqual(client.get("/records/9999").status_code, 404)

    def test_search_ranks_relevant_first(self):
        body = client.get("/search", params={"q": "annual return 30 June"}).json()
        self.assertGreater(body["count"], 0)
        self.assertIn("30 June", str(body["results"][0]["record"]["timeline"]) +
                      body["results"][0]["record"]["obligation"])
        self.assertEqual(client.get("/search?q=").status_code, 422)

    def test_questions(self):
        r = client.post("/questions", json={"question": "What bin colours must municipalities use?"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["answers"][0]["record"]["rule_reference"], "Rule 39(51)")
        self.assertEqual(client.post("/questions", json={"question": "hi"}).status_code, 422)

    def test_unanswerable_question_is_flagged(self):
        r = client.post("/questions", json={"question": "What is the exact fine in rupees for a household that burns waste?"})
        body = r.json()
        self.assertEqual(r.status_code, 201)
        self.assertFalse(body["answerable"])
        self.assertEqual(body["answers"], [])
        self.assertIn("fine", body["missing_terms"])

    def test_answerable_question_is_not_flagged(self):
        body = client.get("/search", params={"q": "annual return 30 June"}).json()
        self.assertTrue(body["answerable"])


if __name__ == "__main__":
    unittest.main()
