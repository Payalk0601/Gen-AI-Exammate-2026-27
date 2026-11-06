"""Record handling for KachraCheck: load, validate, search, add, summarise."""
import json
from collections import Counter
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "sample_records.json"

BIN_BY_CATEGORY = {
    "wet": "green",
    "dry": "blue",
    "hazardous": "red",
    "e-waste": "red",
    "sanitary": "black",
}
REQUIRED_FIELDS = ("id", "item", "category", "bin", "recyclable", "tip")


def load_records(path=DATA_PATH):
    """Return the list of records stored at `path` (empty list if file missing)."""
    path = Path(path)
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def save_records(records, path=DATA_PATH):
    with Path(path).open("w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)


def validate_record(record):
    """Return a list of problems found in a record (empty list means valid)."""
    problems = [f"missing field: {k}" for k in REQUIRED_FIELDS if k not in record]
    cat = record.get("category")
    if cat is not None and cat not in BIN_BY_CATEGORY:
        problems.append(f"unknown category: {cat}")
    elif cat and record.get("bin") and record["bin"] != BIN_BY_CATEGORY[cat]:
        problems.append(f"bin '{record['bin']}' does not match category '{cat}'")
    return problems


def next_id(records):
    return max((r["id"] for r in records), default=0) + 1


def search_records(records, keyword):
    """Case-insensitive match on item name or any alias."""
    kw = keyword.strip().lower()
    hits = []
    for r in records:
        names = [r["item"].lower()] + [a.lower() for a in r.get("aliases", [])]
        if any(kw in n for n in names):
            hits.append(r)
    return hits


def filter_by_category(records, category):
    return [r for r in records if r["category"] == category.lower()]


def add_record(records, item, category, tip, recyclable=False, aliases=None):
    """Build, validate and append a new record. Raises ValueError if invalid."""
    category = category.lower()
    record = {
        "id": next_id(records),
        "item": item.strip(),
        "aliases": aliases or [],
        "category": category,
        "bin": BIN_BY_CATEGORY.get(category, ""),
        "recyclable": recyclable,
        "tip": tip.strip(),
    }
    problems = validate_record(record)
    if problems:
        raise ValueError("; ".join(problems))
    if search_records(records, record["item"]):
        raise ValueError(f"'{record['item']}' already exists")
    records.append(record)
    return record


def category_counts(records):
    return dict(Counter(r["category"] for r in records))


def recyclable_share(records):
    """Percentage of records flagged recyclable (0.0 for an empty list)."""
    if not records:
        return 0.0
    return round(100 * sum(r["recyclable"] for r in records) / len(records), 1)
