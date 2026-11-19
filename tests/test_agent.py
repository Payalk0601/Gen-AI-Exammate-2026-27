import json

import pytest

from app import agent_loop

TOOL_CALL = json.dumps({"action": "tool", "tool": "waste_stream_sorter", "input": {"item": "bannana peel"}})
FINAL = json.dumps({"action": "final", "answer": "Wet bin.", "confidence": "high", "follow_up": "More?"})


def test_agent_loop_calls_the_tool_then_answers(fake_llm):
    fake_llm.script(TOOL_CALL, FINAL)
    out = agent_loop.run_agent("where does a bannana peel go")
    assert out["answer"] == "Wet bin." and out["confidence"] == "high"
    step = out["steps"][0]
    assert step["tool"] == "waste_stream_sorter"
    assert step["result"]["stream"] == "wet"
    assert len(fake_llm.calls) == 2
    assert "TOOL RESULTS SO FAR" in fake_llm.calls[1]["user"]


def test_agent_loop_stops_at_the_step_limit(fake_llm):
    fake_llm.script(TOOL_CALL)  # asks for a tool forever
    out = agent_loop.run_agent("loop forever", max_steps=3)
    assert out["confidence"] == "low" and len(out["steps"]) == 3


def test_agent_loop_retries_once_when_the_model_returns_garbage(fake_llm):
    fake_llm.script("this is not json", FINAL)
    assert agent_loop.run_agent("hello")["answer"] == "Wet bin."


def test_agent_loop_does_not_repeat_the_same_tool_call(fake_llm):
    fake_llm.script(TOOL_CALL, TOOL_CALL, FINAL)
    out = agent_loop.run_agent("repeat test")
    assert "already ran" in out["steps"][1]["observation"]
    assert out["steps"][1]["result"] is None


def test_agent_endpoint_without_approval(client, fake_llm):
    pytest.importorskip("langgraph")
    fake_llm.script(TOOL_CALL, FINAL)
    resp = client.post("/agent", json={"question": "bannana peel?", "require_approval": False})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "done" and body["answer"] == "Wet bin."
    assert body["steps"][0]["tool"] == "waste_stream_sorter"


def test_agent_endpoint_approval_step_and_memory(client, fake_llm):
    pytest.importorskip("langgraph")
    fake_llm.script(FINAL, FINAL)
    first = client.post("/agent", json={"question": "first question", "require_approval": True}).json()
    assert first["status"] == "awaiting_approval" and first["draft"]["answer"] == "Wet bin."
    tid = first["thread_id"]

    done = client.post("/agent/approve", json={"thread_id": tid, "approve": True}).json()
    assert done["status"] == "done" and done["approved"] is True

    second = client.post("/agent", json={"question": "second question", "thread_id": tid, "require_approval": False}).json()
    assert second["turns_in_memory"] == 2
    assert "first question" in fake_llm.calls[1]["user"]  # memory reached the prompt
