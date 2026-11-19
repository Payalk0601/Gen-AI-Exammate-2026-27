import json
import re

import pytest
from helpers import load_records


@pytest.fixture
def retrieve():
    pytest.importorskip("fastapi")  # app.chat imports FastAPI
    from app.chat import retrieve as fn

    return fn


def _words(rec: dict) -> set:
    return set(re.findall(r"[a-z]{6,}", json.dumps(rec, ensure_ascii=False).lower()))


def test_retrieve_finds_a_record_from_its_own_rare_words(retrieve):
    records = load_records()
    target = records[0]
    doc_freq = {}
    for rec in records:
        for w in _words(rec):
            doc_freq[w] = doc_freq.get(w, 0) + 1
    rare = sorted(_words(target), key=lambda w: (doc_freq[w], -len(w)))[:3]
    assert rare, "first record has no searchable words"
    assert target in retrieve(" ".join(rare), k=8)


def test_retrieve_returns_nothing_for_gibberish(retrieve):
    assert retrieve("zzqx wvvk plorghx") == []


def test_retrieve_respects_k(retrieve):
    assert len(retrieve("waste rules duty", k=2)) <= 2
