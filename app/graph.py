r"""The same agent rebuilt in LangGraph, with memory and one human approval step.

Graph:  start -> plan --(tool)--> run_tool -> plan ...
                     \--(final)--> draft --(approval on)--> approval -> commit -> END
                                          \--(approval off)------------> commit -> END

* Memory: a MemorySaver checkpointer keeps state per thread_id, so follow-up questions on the
  same thread see earlier turns (the `history` list).
* Approval: the `approval` node calls interrupt(). The graph pauses and the API returns the draft
  answer; a human then approves or rejects it through POST /agent/approve.
"""
import operator
import uuid
from typing import Annotated, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.agent_loop import MAX_STEPS, decide, normalise_final, observation_text
from app.tools import run_tool


class AgentState(TypedDict, total=False):
    question: str
    provider: str | None
    require_approval: bool
    history: Annotated[list, operator.add]  # grows across turns = memory
    scratch: list
    steps: int
    decision: dict
    draft: dict
    final: dict
    approved: bool | None


def start_node(state: AgentState) -> dict:
    return {"scratch": [], "steps": 0, "decision": {}, "draft": {}, "final": {}, "approved": None}


def plan_node(state: AgentState) -> dict:
    decision = decide(state["question"], state["scratch"], state.get("history", []), state.get("provider"))
    return {"decision": decision, "steps": state["steps"] + 1}


def route_after_plan(state: AgentState) -> str:
    if state["decision"]["action"] == "tool" and state["steps"] < MAX_STEPS:
        return "run_tool"
    return "draft"


def tool_node(state: AgentState) -> dict:
    d = state["decision"]
    scratch = state["scratch"]
    if any(s["tool"] == d["tool"] and s["input"] == d["input"] for s in scratch):
        obs = "You already ran this exact call. Use the earlier result and give the final answer now."
    else:
        obs = observation_text(run_tool(d["tool"], d["input"]))
    return {"scratch": scratch + [{"step": state["steps"], "tool": d["tool"], "input": d["input"], "observation": obs}]}


def draft_node(state: AgentState) -> dict:
    d = state["decision"]
    if d["action"] == "final":
        return {"draft": normalise_final(d)}
    return {
        "draft": {
            "answer": "I could not finish within the step limit. Please rephrase or narrow the question.",
            "confidence": "low",
            "follow_up": "Which single item or rule should I look at first?",
        }
    }


def route_after_draft(state: AgentState) -> str:
    return "approval" if state.get("require_approval") else "commit"


def approval_node(state: AgentState) -> dict:
    """Pause here until a human approves or rejects the draft."""
    reply = interrupt(
        {
            "type": "approval_needed",
            "draft": state["draft"],
            "tools_used": [s["tool"] for s in state["scratch"]],
        }
    )
    approved = bool(reply.get("approve")) if isinstance(reply, dict) else bool(reply)
    if approved:
        return {"approved": True}
    note = reply.get("note", "") if isinstance(reply, dict) else ""
    return {
        "approved": False,
        "draft": {
            "answer": "A reviewer rejected the draft answer, so nothing is shown. Please rephrase or ask a human.",
            "confidence": "low",
            "follow_up": note,
        },
    }


def commit_node(state: AgentState) -> dict:
    final = state["draft"]
    return {"final": final, "history": [{"q": state["question"], "a": final["answer"]}]}


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("start", start_node)
    g.add_node("plan", plan_node)
    g.add_node("run_tool", tool_node)
    g.add_node("draft", draft_node)
    g.add_node("approval", approval_node)
    g.add_node("commit", commit_node)

    g.add_edge(START, "start")
    g.add_edge("start", "plan")
    g.add_conditional_edges("plan", route_after_plan, {"run_tool": "run_tool", "draft": "draft"})
    g.add_edge("run_tool", "plan")
    g.add_conditional_edges("draft", route_after_draft, {"approval": "approval", "commit": "commit"})
    g.add_edge("approval", "commit")
    g.add_edge("commit", END)
    return g.compile(checkpointer=MemorySaver())


GRAPH = build_graph()


def _result(thread_id: str) -> dict:
    config = {"configurable": {"thread_id": thread_id}}
    snap = GRAPH.get_state(config)
    values = snap.values or {}
    steps = values.get("scratch", [])
    if snap.next:  # paused at the approval node
        pending = None
        for task in snap.tasks:
            if task.interrupts:
                pending = task.interrupts[0].value
                break
        return {"status": "awaiting_approval", "thread_id": thread_id, "draft": (pending or {}).get("draft", values.get("draft")), "steps": steps}
    final = values.get("final") or {}
    return {
        "status": "done",
        "thread_id": thread_id,
        "approved": values.get("approved"),
        **final,
        "steps": steps,
        "turns_in_memory": len(values.get("history", [])),
    }


def ask(question: str, thread_id: str | None = None, require_approval: bool = True, provider: str | None = None) -> dict:
    """Start (or continue) a conversation on a thread."""
    thread_id = thread_id or uuid.uuid4().hex
    config = {"configurable": {"thread_id": thread_id}}
    if GRAPH.get_state(config).next:
        raise ValueError("this thread is waiting for approval; call /agent/approve first")
    GRAPH.invoke({"question": question, "provider": provider, "require_approval": require_approval}, config)
    return _result(thread_id)


def approve(thread_id: str, approved: bool, note: str = "") -> dict:
    """Resume a paused thread with the human's decision."""
    config = {"configurable": {"thread_id": thread_id}}
    if not GRAPH.get_state(config).next:
        raise ValueError("no pending approval on this thread")
    GRAPH.invoke(Command(resume={"approve": approved, "note": note}), config)
    return _result(thread_id)
