import csv

from app.tools import ITEMS_CSV, run_tool, waste_stream_sorter

FOUR_STREAMS = {"wet", "dry", "sanitary", "special_care"}


def test_item_csv_covers_all_four_streams_and_is_complete():
    with open(ITEMS_CSV, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) >= 30
    assert {r["stream"] for r in rows} == FOUR_STREAMS
    for r in rows:
        assert r["item"] and r["handling_note"] and r["rule_reference"]


def test_sorter_exact_match():
    r = waste_stream_sorter("banana peel")
    assert r["found"] and r["match_type"] == "exact" and r["stream"] == "wet"


def test_sorter_fixes_spelling_mistakes():
    r = waste_stream_sorter("bannana peel")
    assert r["found"] and r["match_type"] == "fuzzy" and r["stream"] == "wet"
    assert waste_stream_sorter("platic botle")["stream"] == "dry"


def test_sorter_partial_and_single_word_matches():
    assert waste_stream_sorter("old plastic bottle")["stream"] == "dry"
    assert waste_stream_sorter("batary")["stream"] == "special_care"


def test_sorter_unknown_item_and_empty_input():
    assert waste_stream_sorter("quantum teleporter")["found"] is False
    assert waste_stream_sorter("   ")["found"] is False


def test_run_tool_never_raises():
    assert "error" in run_tool("no_such_tool", {})
    assert "error" in run_tool("waste_stream_sorter", {"wrong_arg": 1})
    assert "error" in run_tool("waste_stream_sorter", "not a dict")
