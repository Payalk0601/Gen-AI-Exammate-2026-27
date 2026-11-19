"""Tests for the UI helper modules (loaded by path, so Streamlit is not needed)."""
import importlib.util
from pathlib import Path

UI_DIR = Path(__file__).resolve().parent.parent / "ui"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, UI_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


compare = _load("compare")
api_client = _load("api_client")


def test_diff_highlights_removed_and_added_words():
    old, new = compare.diff_html(
        "segregate into three streams: wet, dry and hazardous",
        "segregate into four streams: wet, dry, sanitary and special care",
    )
    assert '<span class="del">three</span>' in old
    assert '<span class="add">four</span>' in new
    assert "segregate into" in old and "segregate into" in new


def test_diff_escapes_html_in_rule_text():
    old, _ = compare.diff_html("a <b> c", "a <i> c")
    assert "<b>" not in old and "&lt;b&gt;" in old


def test_comparison_data_is_complete_and_matches_topics():
    entries = compare.load_changes()["changes"]
    assert len(entries) >= 6
    for e in entries:
        assert e["rule_2016"] and e["rule_2026"] and e["change_summary"]
    assert compare.match_changes("Where does an old CFL bulb go?", entries)[0]["id"] == "special_care"
    assert compare.match_changes("what about a diaper", entries)[0]["id"] == "sanitary"
    assert compare.match_changes("zzz qqq", entries) == []


def test_normalise_pulls_citations_out_of_agent_steps():
    data = {
        "status": "done",
        "thread_id": "t1",
        "answer": "Wet bin.",
        "confidence": "high",
        "steps": [
            {"tool": "waste_stream_sorter", "result": {"found": True, "matched_item": "banana peel", "stream": "wet", "handling_note": "Green bin.", "rule_reference": "Rule X"}},
            {"tool": "rag_search", "observation": '[{"id": "R12", "text": "Segregate waste into four streams."}]'},
        ],
    }
    result = api_client.normalise(data)
    labels = [c["label"] for c in result["citations"]]
    assert "Rule X" in labels and "R12" in labels
    assert result["tools"] == ["waste_stream_sorter", "rag_search"]


def test_normalise_handles_awaiting_approval_and_plain_ask_responses():
    pending = api_client.normalise({"status": "awaiting_approval", "thread_id": "t", "draft": {"answer": "Draft", "confidence": "low"}})
    assert pending["status"] == "awaiting_approval" and pending["answer"] == "Draft"
    plain = api_client.normalise({"answer": "Hi", "sources": [{"rule_id": "5", "text": "Some rule"}]})
    assert plain["citations"][0]["label"] == "5"
