import dataclasses

import pytest
from helpers import RECORDS_PATH, load_records


def test_records_file_exists_and_has_enough_records():
    assert RECORDS_PATH.exists()
    assert len(load_records()) >= 15


def test_every_record_is_a_dict_with_real_rule_text():
    for rec in load_records():
        assert isinstance(rec, dict)
        assert any(isinstance(v, str) and len(v.strip()) >= 20 for v in rec.values()), rec


def test_record_ids_are_unique_and_not_empty():
    records = load_records()
    key = next((k for k in ("id", "rule_id", "record_id", "clause") if k in records[0]), None)
    if key is None:
        pytest.skip("records have no id-like field")
    ids = [r.get(key) for r in records]
    assert all(ids)
    assert len(ids) == len(set(ids))


def test_record_model_is_a_dataclass():
    try:
        from app.models import Record
    except ImportError:
        pytest.skip("app.models.Record not found")
    assert dataclasses.is_dataclass(Record)
