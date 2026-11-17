"""Offline checks for Day 9 (no API key, no network). Run:  python tests/test_day9.py"""
import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import agent_loop
from app.tools import run_tool, waste_stream_sorter


def test_sorter_exact_fuzzy_partial_and_miss():
    assert waste_stream_sorter("banana peel")["stream"] == "wet"
    r = waste_stream_sorter("bannana peel")  # typo
    assert r["found"] and r["match_type"] == "fuzzy" and r["stream"] == "wet"
    assert waste_stream_sorter("old plastic bottle")["stream"] == "dry"
    assert waste_stream_sorter("sanitary napkins")["stream"] == "sanitary"
    assert waste_stream_sorter("batary")["stream"] == "special_care"
    assert waste_stream_sorter("quantum teleporter")["found"] is False


def test_run_tool_never_raises():
    assert "error" in run_tool("nope", {})
    assert "error" in run_tool("waste_stream_sorter", {"wrong": 1})


def test_agent_loop_calls_tool_then_answers():
    replies = iter(
        [
            json.dumps({"action": "tool", "tool": "waste_stream_sorter", "input": {"item": "bannana peel"}}),
            json.dumps({"action": "final", "answer": "Wet bin.", "confidence": "high", "follow_up": "Anything else?"}),
        ]
    )
    with patch("app.agent_loop.generate", lambda *a, **k: next(replies)):
        out = agent_loop.run_agent("where does a bannana peel go")
    assert out["answer"] == "Wet bin." and out["confidence"] == "high"
    assert out["steps"][0]["tool"] == "waste_stream_sorter"
    assert '"stream": "wet"' in out["steps"][0]["observation"]


def test_agent_loop_step_limit():
    call = json.dumps({"action": "tool", "tool": "waste_stream_sorter", "input": {"item": "battery"}})
    with patch("app.agent_loop.generate", lambda *a, **k: call):
        out = agent_loop.run_agent("loop forever", max_steps=3)
    assert out["confidence"] == "low" and len(out["steps"]) == 3


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
