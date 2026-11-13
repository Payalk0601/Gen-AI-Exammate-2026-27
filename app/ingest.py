"""Build KachraCheck records from the SWM Rules 2026 PDF in data/raw/.

  python -m app.fetch                  # 1. download the PDF into data/raw/
  python -m app.ingest                 # 2. parse it -> data/records_from_pdf.json (+ clean data/records.json)
  python -m app.ingest --merge         # optional: also append the PDF rows to data/records.json

What it does
  PDF -> page text (pypdf) -> keep the English pages -> split into numbered rules ("5. Duties of ...")
      -> split each rule into sub-rules (1) and clauses (a) -> one row per clause with
      rule_reference, stakeholder, obligation, timeline, rules_version, source_url.
  Bad rows are logged and skipped (try/except); they never stop the run.
  The hand-written, English-paraphrased records (data/sample_records.json) are cleaned and kept as
  data/records.json, and are cross-checked against the rule headings found in the PDF.
"""
import argparse
import hashlib
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.models import Record

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
SEED = ROOT / "data" / "sample_records.json"
OUT = ROOT / "data" / "records.json"
PDF_OUT = ROOT / "data" / "records_from_pdf.json"
LOG = ROOT / "data" / "ingest_errors.log"
PDF_NAME = "solid-waste-management-rules-2026.pdf"
PDF_DEFAULT = RAW_DIR / PDF_NAME
PDF_URL = "https://swmp.cpcb.gov.in/img/cpcb_doc/" + PDF_NAME
RULES_VERSION = "SWM Rules 2026"
MIN_OBLIGATION_CHARS = 25
MAX_OBLIGATION_CHARS = 700

log = logging.getLogger("ingest")


# ---------------------------------------------------------------- cleaning (curated records)
def clean_text(value):
    """Collapse whitespace and strip the ends."""
    return None if value is None else re.sub(r"\s+", " ", str(value)).strip()


def clean_row(raw: dict) -> Record:
    cleaned = {k: clean_text(v) if isinstance(v, str) else v for k, v in raw.items()}
    return Record.from_dict(cleaned)


def ingest(seed=SEED, out=OUT):
    """Clean the curated records, skipping bad rows and duplicates. Returns (records, errors)."""
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
            errors.append(f"row {i} skipped: {err}")
            log.warning("row %s skipped: %s", i, err)
    write_records(records, out)
    return records, errors


def write_records(records, path):
    Path(path).write_text(json.dumps([r.to_dict() for r in records], indent=2, ensure_ascii=False),
                          encoding="utf-8")


# ---------------------------------------------------------------- reading the PDF
def read_pages(pdf_path) -> list:
    """Text of every page. Raises RuntimeError with a clear message if the PDF cannot be read."""
    try:
        from pypdf import PdfReader
        return [(p.extract_text() or "") for p in PdfReader(str(pdf_path)).pages]
    except Exception as err:        # missing pypdf, corrupt or encrypted PDF
        raise RuntimeError(f"cannot read {pdf_path}: {err}") from err


def latin_ratio(text: str) -> float:
    latin = len(re.findall(r"[A-Za-z]", text))
    other = len(re.findall(r"[\u0900-\u097F]", text))      # Devanagari
    return latin / (latin + other + 1)


def english_pages(pages: list) -> list:
    return [p for p in pages if latin_ratio(p) > 0.8 and len(re.findall(r"[A-Za-z]", p)) > 200]


# ---------------------------------------------------------------- splitting into rules
HEADING = re.compile(r"(?m)^[ \t]*(\d{1,2})\.[ \t]+(\S.{3,400})$")
DUTY_TITLE = re.compile(r"(?i)\b(duties|duty|responsibilit\w*|obligations?)\b")
PREFIX = re.compile(r"(?i)^(?:duties|responsibilit(?:y|ies)|obligations?)(?:\s+and\s+(?:duties|responsibilit(?:y|ies)))?"
                    r"(?:\s+(?:of|for))?\s+(?:the\s+)?")


def split_rules(text: str) -> dict:
    """Return {rule_number: (title, body)}. Headings must run 1, 2, 3 ... (small gaps allowed),
    which keeps list items inside rules and the Schedules from being mistaken for rules."""
    marks, last = [], 0
    for m in HEADING.finditer(text):
        n = int(m.group(1))
        if last < n <= last + 2:
            marks.append((n, m.start(2)))
            last = n
    rules = {}
    for i, (n, start) in enumerate(marks):
        end = marks[i + 1][1] if i + 1 < len(marks) else len(text)
        chunk = re.sub(r"\s+", " ", text[start:end]).strip()
        title, body = split_title(chunk)
        rules[n] = (title, body)
    return rules


def split_title(chunk: str):
    """'Duties of waste generators.— (1) Every ...' -> ('Duties of waste generators', '(1) Every ...')."""
    m = re.search(r"\s*\.?\s*[\u2014\u2013]\s*|\s*\.\s*-\s+|\s+(?=\(1\))", chunk)
    if m and m.start() < 200:
        return chunk[:m.start()].strip(" .:-"), chunk[m.end():].strip()
    return chunk[:100].strip(" .:-"), chunk[100:].strip()


def stakeholder_from_title(title: str) -> str:
    s = PREFIX.sub("", title).strip(" .:-\u2014")
    return (s[:1].upper() + s[1:]) if s else title


# ---------------------------------------------------------------- splitting a rule into clauses
MARKER = re.compile(r"(?:^|(?<=[\s;:,\u2014\u2013]))\(([0-9]{1,3}|[a-z]{1,3})\)(?=\s+[A-Za-z\"\u201c])")


def split_clauses(body: str) -> list:
    """Return [(sub_rule, letter, text)]. Numbered sub-rules (1),(2).. and lettered clauses (a),(b)..
    are recognised only in sequence; anything else, such as (i),(ii) lists, stays inside its clause."""
    accepted, sub, last_letter = [], None, None
    for m in MARKER.finditer(body):
        label = m.group(1)
        if label.isdigit():
            n = int(label)
            if (sub is None and n == 1) or (sub is not None and sub < n <= sub + 3):
                sub, last_letter = n, None
                accepted.append((sub, None, m.start(), m.end()))
        elif (last_letter is None and label == "a") or \
                (last_letter is not None and len(label) == 1 and ord(label) == ord(last_letter) + 1):
            last_letter = label
            accepted.append((sub, label, m.start(), m.end()))
    if not accepted:
        return [(None, None, body)]

    pieces = []
    head = body[:accepted[0][2]].strip()
    if head:
        pieces.append((None, None, head))
    for i, (s, letter, _, text_start) in enumerate(accepted):
        end = accepted[i + 1][2] if i + 1 < len(accepted) else len(body)
        pieces.append((s, letter, body[text_start:end].strip()))

    # Merge a sub-rule's introduction ("Every waste generator shall,") into each of its lettered clauses.
    clauses = []
    for i, (s, letter, text) in enumerate(pieces):
        if letter is None:
            has_letters = any(p[0] == s and p[1] for p in pieces[i + 1:])
            if not has_letters:
                clauses.append((s, None, text))
            continue
        intro = next((p[2] for p in pieces if p[0] == s and p[1] is None), "")
        intro = intro.rstrip(" ,;:\u2014\u2013-")
        clauses.append((s, letter, f"{intro[-160:]} {text}".strip() if intro else text))
    return clauses


def tidy_obligation(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip(" ;,.\u2014\u2013-")
    text = re.sub(r"\s+(and|or)$", "", text)
    if len(text) > MAX_OBLIGATION_CHARS:
        text = text[:MAX_OBLIGATION_CHARS].rsplit(" ", 1)[0] + " ..."
    return text


# ---------------------------------------------------------------- timeline and category
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
ORD = r"\d{1,2}(?:st|nd|rd|th)?"
TIMELINE_PATTERNS = [
    rf"\b(?:by|on or before)\s+(?:the\s+)?{ORD}\s+(?:day\s+of\s+)?(?:{MONTHS})(?:,?\s+\d{{4}})?",
    rf"\b(?:by|on or before)\s+(?:the\s+)?{ORD}\s+of\s+(?:the\s+)?(?:first|every|each)\s+month"
    rf"(?:\s+of\s+(?:the\s+)?(?:next|every|each)\s+quarter)?",
    r"\bwithin\s+(?:a\s+period\s+of\s+)?(?:one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+"
    r"(?:years?|months?|weeks?|days?)(?:\s+(?:of|from)\s+[^;,.]{3,70})?",
    r"\bat least (?:once|twice)\s+(?:a|in a|every|each)\s+(?:year|quarter|month)\b",
    r"\b(?:every|each)\s+(?:year|quarter|month)\b",
    r"\bquarterly\b",
    r"\bannual(?:ly)?\b",
]
CATEGORY_KEYWORDS = [
    ("Reporting", r"\b(return|report|submit|furnish)\w*"),
    ("Registration", r"\bregist\w+"),
    ("Authorisation", r"\bauthori[sz]ation|\bconsent\b|\bapproval\b"),
    ("Segregation", r"\bsegregat\w+"),
    ("Fees", r"\b(fee|fees|charges?)\b"),
    ("Bye-laws", r"\bbye-?laws?\b"),
    ("Planning", r"\b(plan|policy|strategy)\b"),
    ("Collection", r"\bcollect\w+"),
    ("Enforcement", r"\b(review|monitor\w*|enforce\w*|inspect\w*|complian\w+)"),
    ("Infrastructure", r"\b(facilit\w+|infrastructure|portal|site|land)\b"),
]


def extract_timeline(text: str) -> str:
    """Deadlines and frequencies found in a clause, most specific first; 'Not stated in clause' if none."""
    found = []
    for pattern in TIMELINE_PATTERNS:
        for m in re.finditer(pattern, text, re.I):
            phrase = re.sub(r"\s+", " ", m.group(0)).strip(" ,;.")
            overlaps = any(phrase.lower() in f.lower() or f.lower() in phrase.lower() for f in found)
            generic = phrase.lower() in ("every year", "each year", "annual", "annually")
            has_date = any(re.search(MONTHS, f, re.I) for f in found)
            if not overlaps and not (generic and has_date):   # "by 30th June" already says it is yearly
                found.append(phrase)
    return "; ".join(found[:3]) if found else "Not stated in clause"


def classify(text: str) -> str:
    for category, pattern in CATEGORY_KEYWORDS:
        if re.search(pattern, text, re.I):
            return category
    return "General"


# ---------------------------------------------------------------- PDF -> Record rows
def build_from_pdf(pdf_path, url=PDF_URL):
    """Return (records, stats). Never raises for bad rows; raises RuntimeError if the PDF is unreadable."""
    pages = read_pages(pdf_path)
    eng = english_pages(pages)
    text = "\n".join(eng) if eng else "\n".join(pages)
    rules = split_rules(text)
    duty = {n: v for n, v in rules.items() if DUTY_TITLE.search(v[0])}
    chosen = duty if len(duty) >= 3 else rules          # fallback: keep every rule if titles are not recognisable

    records, skipped = [], 0
    for n, (title, body) in sorted(chosen.items()):
        stakeholder = stakeholder_from_title(title)
        for sub, letter, clause in split_clauses(body):
            try:
                ref = f"Rule {n}" + (f"({sub})" if sub else "") + (f"({letter})" if letter else "")
                obligation = tidy_obligation(clause)
                if len(obligation) < MIN_OBLIGATION_CHARS:
                    raise ValueError("clause too short to be a duty")
                records.append(Record.from_dict({
                    "id": len(records) + 1, "rule_reference": ref, "stakeholder": stakeholder,
                    "category": classify(obligation), "obligation": obligation,
                    "timeline": extract_timeline(clause), "rules_version": RULES_VERSION,
                    "source_url": url, "rule_2016_match": None}))
            except (ValueError, KeyError, TypeError) as err:
                skipped += 1
                log.warning("Rule %s clause skipped: %s", n, err)
    stats = {"pages": len(pages), "english_pages": len(eng), "rules_found": len(rules),
             "duty_rules_used": len(chosen), "rows_built": len(records), "rows_skipped": skipped,
             "language": "English pages" if eng else "no English pages found; parsed all pages"}
    return records, stats


# ---------------------------------------------------------------- checks and manifest
def index_rules(pdf_path) -> dict:
    """{rule number: heading text} over all pages (Hindi and English)."""
    text = "\n".join(read_pages(pdf_path))
    return {n: re.sub(r"\s+", " ", text[start:start + 90]).strip() for n, start in
            [(int(m.group(1)), m.start(2)) for m in _sequential(HEADING.finditer(text))]}


def _sequential(matches):
    last = 0
    for m in matches:
        n = int(m.group(1))
        if last < n <= last + 2:
            last = n
            yield m


def cross_check(records, index) -> list:
    """Curated references whose rule number is not among the PDF's rule headings."""
    missing = []
    for r in records:
        m = re.search(r"Rule\s+(\d+)", r.rule_reference)
        if m and int(m.group(1)) not in index:
            missing.append(r.rule_reference)
    return missing


def ensure_manifest(pdf_path, url=PDF_URL):
    """If app.fetch has not written data/raw/manifest.json yet, record this PDF in one."""
    manifest = Path(pdf_path).parent / "manifest.json"
    if manifest.exists():
        return
    data = Path(pdf_path).read_bytes()
    entry = {"name": Path(pdf_path).name, "url": url, "status": "ok", "bytes": len(data),
             "sha256": hashlib.sha256(data).hexdigest(),
             "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "error": None}
    manifest.write_text(json.dumps([entry], indent=2), encoding="utf-8")


# ---------------------------------------------------------------- command line
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pdf", default=str(PDF_DEFAULT), help="path to the SWM Rules 2026 PDF")
    ap.add_argument("--merge", action="store_true", help="append PDF-built rows to data/records.json")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(LOG, encoding="utf-8")])

    curated, errors = ingest()
    print(f"[1/2] curated records: {len(curated)} cleaned -> {OUT.relative_to(ROOT)} ({len(errors)} bad row(s) skipped)")

    pdf = Path(args.pdf)
    if not pdf.exists():
        print(f"[2/2] PDF not found at {pdf}\n      run `python -m app.fetch` first (or save the PDF there by hand)")
        return 1
    try:
        rows, stats = build_from_pdf(pdf)
        index = index_rules(pdf)
    except RuntimeError as err:
        print(f"[2/2] {err}")
        return 1

    ensure_manifest(pdf)
    write_records(rows, PDF_OUT)
    (pdf.parent / "rule_index.json").write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[2/2] PDF parsed ({stats['language']}): {stats['pages']} pages, {stats['english_pages']} English, "
          f"{stats['rules_found']} rules, {stats['duty_rules_used']} duty rules")
    print(f"      {stats['rows_built']} rows built, {stats['rows_skipped']} skipped -> {PDF_OUT.relative_to(ROOT)}")
    missing = cross_check(curated, index)
    print("      curated records cross-checked against PDF headings:",
          "all found" if not missing else f"NOT found: {', '.join(missing)}")

    if args.merge and rows:
        merged = list(curated)
        for r in rows:
            merged.append(Record.from_dict({**r.to_dict(), "id": len(merged) + 1}))
        write_records(merged, OUT)
        print(f"      merged: {len(merged)} records now in {OUT.relative_to(ROOT)} "
              f"(run `python analysis/check_questions.py` to confirm search still works)")
    if stats["rows_built"] < 10:
        print("      WARNING: very few rows built; the PDF layout may differ. Open data/raw/rule_index.json to see what was found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
