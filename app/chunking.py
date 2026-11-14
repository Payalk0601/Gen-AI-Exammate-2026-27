"""Split the KachraCheck source documents (data/raw/*.pdf) into chunks that remember where they came from.

Every chunk keeps:
  source     file name, e.g. solid-waste-management-rules-2026.pdf
  page       1-based page number of the PDF (a chunk never crosses a page)
  title      the section it belongs to, e.g. "Rule 5: Duties of waste generator"
             (falls back to the document title when no rule heading is found)

  python -m app.chunking            # print a summary of what would be indexed
"""
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from app.ingest import HEADING, latin_ratio, read_pages, split_title

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"

DOC_TITLES = {
    "solid-waste-management-rules-2026.pdf": "Solid Waste Management Rules, 2026",
    "swm-rules-2016-cag-summary.pdf": "Solid Waste Management Rules, 2016: salient features (CAG)",
    "swm-rules-2016-toolkit-npc.pdf": "Solid Waste Management Rules, 2016: toolkit (NPC)",
}
MIN_CHUNK_CHARS = 60
SENTENCE_SPLIT = re.compile(r"(?<=[.;:])\s+(?=[A-Z(\d\"\u201c])")


@dataclass
class Chunk:
    id: str
    text: str
    source: str
    page: int
    title: str
    doc_title: str
    chunk_index: int
    source_url: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------- splitting text
def split_text(text: str, max_chars: int = 800, overlap_sentences: int = 1) -> List[str]:
    """Pack whole sentences into pieces of at most `max_chars`; each piece repeats the last
    `overlap_sentences` sentence(s) of the previous one so an answer on a boundary is not lost."""
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    sentences = []
    for s in SENTENCE_SPLIT.split(text):
        while len(s) > max_chars:                       # a single very long sentence: cut at a space
            cut = s.rfind(" ", 0, max_chars)
            cut = cut if cut > 0 else max_chars
            sentences.append(s[:cut])
            s = s[cut:].strip()
        if s:
            sentences.append(s)

    pieces, current = [], []
    for s in sentences:
        if current and len(" ".join(current + [s])) > max_chars:
            pieces.append(" ".join(current))
            current = current[-overlap_sentences:] if overlap_sentences else []
            if current and len(" ".join(current + [s])) > max_chars:
                current = []
        current.append(s)
    if current:
        pieces.append(" ".join(current))
    return pieces


# ---------------------------------------------------------------- one PDF
def _segments(page_text: str, state: dict) -> List[Tuple[str, str]]:
    """Cut a page at its rule headings -> [(title, text)]. `state` carries the current rule across pages."""
    marks = []
    for m in HEADING.finditer(page_text):
        n = int(m.group(1))
        if state["last"] < n <= state["last"] + 4:   # tolerate a heading the PDF text lost
            title, _ = split_title(re.sub(r"\s+", " ", page_text[m.start(2):m.start(2) + 220]))
            marks.append((m.start(), f"Rule {n}: {title}"))
            state["last"] = n
    if not marks:
        return [(state["title"], page_text)]
    segments = []
    if marks[0][0] > 0:
        segments.append((state["title"], page_text[:marks[0][0]]))
    for i, (start, title) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(page_text)
        segments.append((title, page_text[start:end]))
        state["title"] = title
    return segments


def chunk_pdf(path, doc_title: Optional[str] = None, source_url: str = "",
              max_chars: int = 800) -> Tuple[List[Chunk], dict]:
    """Chunk one PDF. Non-English pages (the gazette also prints Hindi) are skipped because the
    embedding model reads English. Returns (chunks, stats)."""
    path = Path(path)
    doc_title = doc_title or DOC_TITLES.get(path.name) or path.stem.replace("-", " ").replace("_", " ").title()
    pages = read_pages(path)
    state = {"last": 0, "title": doc_title}
    chunks, skipped = [], 0
    for page_no, page_text in enumerate(pages, start=1):
        letters = len(re.findall(r"[A-Za-z]", page_text))
        if letters < 100 or latin_ratio(page_text) <= 0.8:
            skipped += 1
            continue
        index = 0
        for title, text in _segments(page_text, state):
            for piece in split_text(text, max_chars=max_chars):
                if len(piece) < MIN_CHUNK_CHARS:
                    continue
                chunks.append(Chunk(id=f"{path.stem}:p{page_no}:c{index}", text=piece, source=path.name,
                                    page=page_no, title=title, doc_title=doc_title,
                                    chunk_index=index, source_url=source_url))
                index += 1
    return chunks, {"source": path.name, "pages": len(pages), "pages_skipped": skipped, "chunks": len(chunks)}


# ---------------------------------------------------------------- everything in data/raw
def _manifest_urls(raw_dir: Path) -> dict:
    try:
        return {e["name"]: e.get("url", "") for e in json.loads((raw_dir / "manifest.json").read_text(encoding="utf-8"))}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def chunk_raw_dir(raw_dir=RAW_DIR, max_chars: int = 800) -> Tuple[List[Chunk], List[dict]]:
    """Chunk every PDF in data/raw. A PDF that cannot be read is reported and skipped."""
    raw_dir = Path(raw_dir)
    urls = _manifest_urls(raw_dir)
    chunks, stats = [], []
    for pdf in sorted(raw_dir.glob("*.pdf")):
        try:
            c, s = chunk_pdf(pdf, source_url=urls.get(pdf.name, ""), max_chars=max_chars)
        except RuntimeError as err:
            stats.append({"source": pdf.name, "error": str(err)})
            continue
        chunks.extend(c)
        stats.append(s)
    return chunks, stats


def main():
    chunks, stats = chunk_raw_dir()
    if not stats:
        print("No PDFs in data/raw. Run `python -m app.fetch` first.")
        return 1
    for s in stats:
        print(s)
    print(f"{len(chunks)} chunks in total")
    for c in chunks[:3]:
        print(f"\n[{c.source} p.{c.page}] {c.title}\n  {c.text[:150]}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
