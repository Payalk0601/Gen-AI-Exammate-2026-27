"""Load and query KachraCheck records: load_records, search, count_by, get_by_id."""
import json
from collections import Counter
from pathlib import Path
from typing import Optional

from app.models import Record

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CLEAN_PATH = DATA_DIR / "records.json"
SAMPLE_PATH = DATA_DIR / "sample_records.json"


def load_records(path=None) -> list:
    """Load records as Record objects.
    Uses data/records.json (ingest output) if present, else data/sample_records.json."""
    path = Path(path) if path else (CLEAN_PATH if CLEAN_PATH.exists() else SAMPLE_PATH)
    with path.open(encoding="utf-8") as f:
        return [Record.from_dict(row) for row in json.load(f)]


def search(records: list, keyword: str) -> list:
    """Case-insensitive keyword search across every field."""
    keyword = keyword.strip()
    return [r for r in records if r.matches(keyword)] if keyword else []


def count_by(records: list, field: str = "category") -> dict:
    """Count records per value of `field`, most common first."""
    if records and not hasattr(records[0], field):
        raise ValueError(f"unknown field: {field}")
    return dict(Counter(getattr(r, field) for r in records).most_common())


def get_by_id(records: list, record_id: int) -> Optional[Record]:
    return next((r for r in records if r.id == record_id), None)
