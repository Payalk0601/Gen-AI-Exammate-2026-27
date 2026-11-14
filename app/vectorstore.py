"""Persistent Chroma collection holding every chunk (text + vector + source, page, title).

  python -m app.vectorstore --rebuild                  # chunk data/raw/*.pdf, embed, store in data/chroma/
  python -m app.vectorstore --query "bin colours"      # search the stored index
  python -m app.vectorstore --count

The index lives in data/chroma/ (git-ignored, rebuild any time). To keep it elsewhere, for example outside OneDrive,
set KACHRACHECK_CHROMA_DIR.
"""
import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional

from app.chunking import Chunk, chunk_raw_dir
from app.embed import get_embedder

ROOT = Path(__file__).resolve().parent.parent
COLLECTION = "kachracheck_chunks"


def default_dir() -> Path:
    return Path(os.environ.get("KACHRACHECK_CHROMA_DIR") or ROOT / "data" / "chroma")


class VectorStore:
    def __init__(self, path=None, embedder=None, name: str = COLLECTION):
        import chromadb                                  # ImportError is handled by the caller
        self.path = Path(path) if path else default_dir()
        self.embedder = embedder or get_embedder()
        self.name = name
        self.client = chromadb.PersistentClient(path=str(self.path))
        self.collection = self._open()

    def _open(self):
        return self.client.get_or_create_collection(
            self.name, metadata={"hnsw:space": "cosine", "embedder": self.embedder.name})

    def reset(self):
        """Delete the collection and start empty."""
        try:
            self.client.delete_collection(self.name)
        except Exception:                                # collection did not exist yet
            pass
        self.collection = self._open()

    def count(self) -> int:
        return self.collection.count()

    def _check_embedder(self):
        stored = (self.collection.metadata or {}).get("embedder")
        if self.count() and stored and stored != self.embedder.name:
            raise ValueError(f"the index was built with '{stored}' but the current embedder is "
                             f"'{self.embedder.name}'. Rebuild: python -m app.vectorstore --rebuild")

    def index(self, chunks: List[Chunk], batch: int = 64) -> int:
        """Embed and upsert chunks (same id = replaced, so running it twice does not duplicate). Returns the count."""
        self._check_embedder()
        for i in range(0, len(chunks), batch):
            part = chunks[i:i + batch]
            self.collection.upsert(
                ids=[c.id for c in part],
                embeddings=self.embedder.embed([c.text for c in part]).tolist(),
                documents=[c.text for c in part],
                metadatas=[{"source": c.source, "page": c.page, "title": c.title, "doc_title": c.doc_title,
                            "chunk_index": c.chunk_index, "source_url": c.source_url} for c in part])
        return len(chunks)

    def search(self, query: str, k: int = 5) -> List[dict]:
        """Best chunks first. score = 1 - cosine distance (higher is closer)."""
        if not query.strip() or self.count() == 0:
            return []
        self._check_embedder()
        res = self.collection.query(query_embeddings=self.embedder.embed([query]).tolist(),
                                    n_results=min(k, self.count()))
        hits = []
        for cid, doc, meta, dist in zip(res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]):
            hits.append({"chunk_id": cid, "score": round(1 - float(dist), 4), "text": doc, **meta})
        return hits


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rebuild", action="store_true", help="re-chunk data/raw and rebuild the whole index")
    ap.add_argument("--query")
    ap.add_argument("--count", action="store_true")
    ap.add_argument("--embedder", choices=["minilm", "hash"], default=None)
    ap.add_argument("-k", type=int, default=5)
    args = ap.parse_args(argv)

    try:
        store = VectorStore(embedder=get_embedder(args.embedder))
    except (ImportError, RuntimeError) as err:
        print(f"Cannot open the vector store: {err}")
        return 1
    if args.rebuild:
        chunks, stats = chunk_raw_dir()
        if not chunks:
            print("No chunks: put the PDFs in data/raw (run `python -m app.fetch`).")
            return 1
        store.reset()
        n = store.index(chunks)
        for s in stats:
            print(s)
        print(f"Indexed {n} chunks into {store.path} (embedder: {store.embedder.name})")
    if args.count:
        print(f"{store.count()} chunks in '{store.name}'")
    if args.query:
        for h in store.search(args.query, args.k):
            print(f"{h['score']}  {h['title']} | {h['source']} p.{h['page']}\n      {h['text'][:160]}...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
