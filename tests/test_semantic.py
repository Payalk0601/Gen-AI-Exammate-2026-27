"""Run:  python -m unittest discover tests
Chunking tests need fpdf2 for the PDF fixture; vector store tests need chromadb. Missing packages skip, they do not fail."""
import tempfile
import unittest
from pathlib import Path

from app import chunking
from app.embed import HashEmbedder, SemanticIndex

TEXT = """Part header text for the gazette page that is long enough to count as English text. It continues here with more words
so that the page passes the English-page check used by the chunker, which needs at least one hundred letters on the page.
1. Short title and commencement.- These rules may be called the Solid Waste Management Rules 2026 and come into force soon.
2. Application.- These rules apply to every waste generator, local body and operator of a processing facility in the country.
3. Definitions.- In these rules unless the context requires otherwise the following words have the meanings given below.
4. General principles.- Local bodies shall follow the polluter pays principle and the waste hierarchy in every action they take.
5. Duties of waste generator.- (1) Every waste generator shall segregate waste at source into wet dry sanitary and special care waste.
(a) Wrap used sanitary waste securely and place it in the sanitary bin. (b) Pay the user fee set by the local body.
6. Duties of bulk waste generators.- Every bulk waste generator shall register on the centralised portal and file an annual return by 30th June.
"""


class SplitTextTests(unittest.TestCase):
    def test_pieces_respect_max_and_overlap(self):
        text = " ".join(f"Sentence number {i} says something about waste." for i in range(30))
        pieces = chunking.split_text(text, max_chars=200, overlap_sentences=1)
        self.assertGreater(len(pieces), 3)
        self.assertTrue(all(len(p) <= 200 for p in pieces))
        self.assertIn(pieces[0].split(". ")[-1].strip(), pieces[1])       # last sentence repeats

    def test_very_long_sentence_is_cut(self):
        pieces = chunking.split_text("word " * 500, max_chars=100)
        self.assertTrue(all(len(p) <= 100 for p in pieces))

    def test_empty(self):
        self.assertEqual(chunking.split_text("   "), [])


class PdfChunkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from fpdf import FPDF
        except ImportError:
            raise unittest.SkipTest("fpdf2 not installed")
        cls.dir = Path(tempfile.mkdtemp())
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", size=10)
        for line in TEXT.splitlines():
            pdf.multi_cell(0, 5, line, new_x="LMARGIN", new_y="NEXT")
        pdf.add_page()
        pdf.set_font("Helvetica", size=10)
        pdf.multi_cell(0, 5, "7. Duties of operators of facilities.- The operator shall file quarterly returns by the 15th of the first month of the next quarter and keep records of all waste received and processed at the plant during the quarter. " * 2,
                       new_x="LMARGIN", new_y="NEXT")
        cls.pdf = cls.dir / "solid-waste-management-rules-2026.pdf"
        pdf.output(str(cls.pdf))

    def test_chunks_keep_source_page_title(self):
        chunks, stats = chunking.chunk_pdf(self.pdf)
        self.assertTrue(chunks)
        self.assertTrue(all(c.source == self.pdf.name and c.page in (1, 2) and c.title for c in chunks))
        by_title = {c.title.split(":")[0] for c in chunks}
        self.assertTrue({"Rule 5", "Rule 6", "Rule 7"} <= by_title)
        rule7 = next(c for c in chunks if c.title.startswith("Rule 7"))
        self.assertEqual(rule7.page, 2)
        self.assertEqual(stats["pages"], 2)

    def test_chunk_ids_are_unique(self):
        chunks, _ = chunking.chunk_pdf(self.pdf)
        self.assertEqual(len({c.id for c in chunks}), len(chunks))

    def test_in_memory_semantic_index_finds_rule(self):
        chunks, _ = chunking.chunk_pdf(self.pdf)
        index = SemanticIndex(chunks, HashEmbedder())
        top = index.search("annual return by 30th June for bulk generators", 1)[0][0]
        self.assertTrue(top.title.startswith("Rule 6"))


class ModelDirTests(unittest.TestCase):
    def test_model_is_saved_inside_the_project_not_the_user_profile(self):
        try:
            from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2
        except ImportError:
            raise unittest.SkipTest("chromadb not installed")
        import os
        from app.embed import MiniLMEmbedder
        old_path, old_env = ONNXMiniLM_L6_V2.DOWNLOAD_PATH, os.environ.get("KACHRACHECK_MODEL_DIR")
        try:
            os.environ["KACHRACHECK_MODEL_DIR"] = str(Path(tempfile.mkdtemp()) / "models")
            MiniLMEmbedder._use_project_model_dir()
            self.assertEqual(ONNXMiniLM_L6_V2.DOWNLOAD_PATH.parent, Path(os.environ["KACHRACHECK_MODEL_DIR"]))
            self.assertNotIn(".cache", str(ONNXMiniLM_L6_V2.DOWNLOAD_PATH))
        finally:
            ONNXMiniLM_L6_V2.DOWNLOAD_PATH = old_path
            os.environ.pop("KACHRACHECK_MODEL_DIR", None)
            if old_env:
                os.environ["KACHRACHECK_MODEL_DIR"] = old_env


class VectorStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import chromadb  # noqa: F401
            from fpdf import FPDF  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("chromadb or fpdf2 not installed")
        PdfChunkTests.setUpClass()
        cls.chunks, _ = chunking.chunk_pdf(PdfChunkTests.pdf)

    def test_index_is_persistent_and_idempotent(self):
        from app.vectorstore import VectorStore
        path = Path(tempfile.mkdtemp()) / "chroma"
        store = VectorStore(path=path, embedder=HashEmbedder())
        store.index(self.chunks)
        store.index(self.chunks)                        # same ids: replaced, not duplicated
        self.assertEqual(store.count(), len(self.chunks))
        reopened = VectorStore(path=path, embedder=HashEmbedder())
        self.assertEqual(reopened.count(), len(self.chunks))
        hit = reopened.search("quarterly returns by the 15th", 1)[0]
        self.assertTrue(hit["title"].startswith("Rule 7"))
        self.assertEqual(hit["page"], 2)
        self.assertEqual(hit["source"], self.pdf_name)

    pdf_name = "solid-waste-management-rules-2026.pdf"

    def test_embedder_mismatch_is_reported(self):
        from app.vectorstore import VectorStore
        path = Path(tempfile.mkdtemp()) / "chroma"
        VectorStore(path=path, embedder=HashEmbedder()).index(self.chunks)

        class Other(HashEmbedder):
            name = "other-model"
        with self.assertRaises(ValueError):
            VectorStore(path=path, embedder=Other()).search("anything", 1)

    def test_api_endpoint(self):
        from fastapi.testclient import TestClient
        import app.main as main
        from app.vectorstore import VectorStore
        store = VectorStore(path=Path(tempfile.mkdtemp()) / "chroma", embedder=HashEmbedder())
        client = TestClient(main.app)
        main._STORE = store
        try:
            self.assertEqual(client.get("/search/semantic", params={"q": "register on the portal"}).status_code, 503)  # empty
            store.index(self.chunks)
            r = client.get("/search/semantic", params={"q": "register on the portal file annual return", "k": 2})
            body = r.json()
            self.assertEqual(r.status_code, 200)
            self.assertEqual(len(body["results"]), 2)
            self.assertEqual(body["results"][0]["title"].split(":")[0], "Rule 6")
            self.assertIn("page", body["results"][0])
            self.assertEqual(client.get("/search/semantic", params={"q": ""}).status_code, 422)
        finally:
            main._STORE = None


if __name__ == "__main__":
    unittest.main()
