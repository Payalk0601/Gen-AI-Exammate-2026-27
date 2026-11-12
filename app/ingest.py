"""Clean raw records into data/records.json.

Stage 1: read data/sample_records.json, normalise text, validate every row with the Record
         dataclass (bad rows are logged and skipped, never crash the run), drop duplicates.
Stage 2: if data/raw/solid-waste-management-rules-2026.pdf exists (run `python -m app.fetch`),
         index its rule headings and warn about records whose rule number is not found in it.

  python -m app.ingest
  python -m app.ingest --pdf data/raw/solid-waste-management-rules-2026.pdf
"""
import argparse
import json
import logging
import re
import sys
from pathlib import Path

from app.models import Record

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "data" / "sample_records.json"
OUT = ROOT / "data" / "records.json"
LOG = ROOT / "data" / "ingest_errors.log"
PDF_DEFAULT = ROOT / "data" / "raw" / "solid-waste-management-rules-2026.pdf"

log = logging.getLogger("ingest")


def clean_text(value):
    """Collapse whitespace and strip stray punctuation spacing."""
    if value is None:
        return None
    return re.sub(r"\s+", " ", str(value)).strip()


def clean_row(raw: dict) -> Record:
    cleaned = {k: clean_text(v) if isinstance(v, str) else v for k, v in raw.items()}
    return Record.from_dict(cleaned)


def ingest(seed=SEED, out=OUT):
    records, seen, errors = [], set(), []
    try:
        rows = json.loads(Path(seed).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as err:
        log.error("cannot read %s: %s", seed, err)
        return [], [f"cannot read seed: {err}"]

    for i, raw in enumerate(rows):
        try:
            rec = clean_row(raw)
            key = (rec.rule_reference, rec.stakeholder)
            if key in seen:
                raise ValueError(f"duplicate of {key}")
            seen.add(key)
            records.append(rec)
        except (ValueError, KeyError, TypeError) as err:
            msg = f"row {i} skipped: {err}"
            errors.append(msg)
            log.warning(msg)

    Path(out).write_text(
        json.dumps([r.to_dict() for r in records], indent=2, ensure_ascii=False), encoding="utf-8")
    return records, errors


def index_pdf(pdf_path) -> dict:
    """Map rule number -> heading text found in the PDF. Returns {} if unreadable."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(pdf_path))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as err:  # corrupt/encrypted PDF, missing pypdf, etc.
        log.warning("could not read %s: %s", pdf_path, err)
        return {}
    index, last = {}, 0
    for m in re.finditer(r"(?m)^\s*(\d{1,2})\.\s+(\S.{3,90})$", text):
        n = int(m.group(1))
        if n == last + 1:                      # headings run 1, 2, 3 ... in order
            index[n] = m.group(2).strip()
            last = n
    return index


def cross_check(records, index) -> list:
    missing = []
    for r in records:
        m = re.search(r"Rule\s+(\d+)", r.rule_reference)
        if m and int(m.group(1)) not in index:
            missing.append(r.rule_reference)
    return missing


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", default=str(PDF_DEFAULT))
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(LOG, encoding="utf-8")])

    records, errors = ingest()
    print(f"{len(records)} records written to {OUT.relative_to(ROOT)}; {len(errors)} bad row(s) skipped")

    pdf = Path(args.pdf)
    if pdf.exists():
        index = index_pdf(pdf)
        (pdf.parent / "rule_index.json").write_text(
            json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
        missing = cross_check(records, index)
        print(f"PDF indexed: {len(index)} rule headings found")
        if missing:
            print("Not found in PDF index (check manually):", ", ".join(missing))
    else:
        print(f"PDF not found at {pdf} - run `python -m app.fetch` first for the cross-check")
    return 0 if records else 1


if __name__ == "__main__":
    sys.exit(main())
