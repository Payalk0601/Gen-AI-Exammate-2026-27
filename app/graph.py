"""The same agent rebuilt as a LangGraph graph, with memory and one human approval step.

        START -> begin -> plan --(final)------------------------------> respond -> END
                           |  ^                                           ^  ^
                           |  +---------------- rag <-- (search_rules) ---+  |
                           +--(waste_stream_sorter)--> sorter --exact--> plan |
                                                          |                   |
                                                          +--fuzzy--> approve --(rejected)-+
                                                                         +--(approved)--> plan

  memory    a checkpointer keeps the state of each thread_id between turns: the last item and stream (so "why?" and
            "what about it?" work) and the history of questions and answers.
  approval  when the item table had to GUESS a spelling ("batery" -> "battery"), the graph pauses with `interrupt` and
            waits for the user to confirm, because a wrong guess means the item goes in the wrong bin.
"""
import uuid
from typing import List, Optional, TypedDict, Annotated
import operator

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.agent_loop import MAX_STEPS, HELP_TEXT, Step, compose_answer, make_planner, memory_from
from app.tools import ToolBox


class AgentState(TypedDict, total=False):
    question: str
    plan: dict
    steps: List[dict]                       # replaced every turn
    answer: str
    approved: Optional[bool]
    memory: dict                            # last_item, last_stream, last_rule: kept between turns
    history: Annotated[list, operator.add]  # every question and answer of the thread


def _steps(state) -> List[Step]:
    return [Step(**s) for s in state.get("steps", [])]


def build_graph(toolbox: ToolBox, planner=None, checkpointer=None):
    planner = planner or make_planner()

    def begin(state: AgentState):
        return {"steps": [], "plan": {}, "answer": "", "approved": None}

    def plan(state: AgentState):
        steps = _steps(state)
        if len(steps) >= MAX_STEPS:
            return {"plan": {"action": "final"}}
        try:
            action = planner.next_action(state["question"], state.get("memory", {}), steps)
        except Exception:
            from app.agent_loop import RulePlanner
            action = RulePlanner().next_action(state["question"], state.get("memory", {}), steps)
        if "tool" in action and any(s.tool == action["tool"] and s.input == action["input"] for s in steps):
            action = {"action": "final"}                   # repeating a call changes nothing
        return {"plan": action}

    def route_plan(state: AgentState):
        tool = state["plan"].get("tool")
        return {"waste_stream_sorter": "sorter", "search_rules": "rag"}.get(tool, "respond")

    def run_tool(state: AgentState):
        steps = state.get("steps", [])
        action = state["plan"]
        obs = toolbox.call(action["tool"], action["input"])
        return {"steps": steps + [Step(len(steps) + 1, action["tool"], action["input"], obs).to_dict()]}

    def route_sorter(state: AgentState):
        obs = state["steps"][-1]["observation"]
        return "approve" if obs.get("found") and obs.get("needs_confirmation") else "plan"

    def approve(state: AgentState):
        last = state["steps"][-1]["observation"]
        decision = interrupt({
            "type": "confirm_item",
            "message": f"I read '{last['query']}' as '{last['matched_item']}' ({last['stream']} stream). Is that what you meant?",
            "typed": last["query"], "proposed_item": last["matched_item"], "stream": last["stream"]})
        approved = bool(decision.get("approve")) if isinstance(decision, dict) else bool(decision)
        if approved:
            return {"approved": True}
        steps = list(state["steps"])
        rejected = {"found": False, "query": last["query"], "match_type": "none", "similarity": last["similarity"],
                    "needs_confirmation": False, "rejected_by_user": True, "suggestions": last.get("suggestions", [])}
        steps[-1] = {**steps[-1], "observation": rejected}
        return {"approved": False, "steps": steps}

    def route_approve(state: AgentState):
        return "plan" if state.get("approved") else "respond"

    def respond(state: AgentState):
        steps = _steps(state)
        if state.get("approved") is False:
            rejected = steps[-1].observation
            hint = f" Did you mean one of: {', '.join(rejected['suggestions'])}?" if rejected.get("suggestions") else ""
            answer = f"Okay, I won't guess.{hint} Tell me the item again, maybe spelled differently."
        else:
            answer = compose_answer(steps) or state["plan"].get("message") or HELP_TEXT
        return {"answer": answer, "memory": memory_from(steps, state.get("memory", {})),
                "history": [{"question": state["question"], "answer": answer}]}

    g = StateGraph(AgentState)
    g.add_node("begin", begin)
    g.add_node("plan", plan)
    g.add_node("sorter", run_tool)
    g.add_node("rag", run_tool)
    g.add_node("approve", approve)
    g.add_node("respond", respond)
    g.add_edge(START, "begin")
    g.add_edge("begin", "plan")
    g.add_conditional_edges("plan", route_plan, {"sorter": "sorter", "rag": "rag", "respond": "respond"})
    g.add_conditional_edges("sorter", route_sorter, {"approve": "approve", "plan": "plan"})
    g.add_edge("rag", "plan")
    g.add_conditional_edges("approve", route_approve, {"plan": "plan", "respond": "respond"})
    g.add_edge("respond", END)
    return g.compile(checkpointer=checkpointer or InMemorySaver()), planner


class PendingApproval(Exception):
    """A new message arrived while the thread is waiting for the user to confirm an item."""


class AgentService:
    """What POST /agent talks to: one graph, one memory store, many threads."""

    def __init__(self, toolbox: ToolBox, planner=None):
        self.graph, self.planner = build_graph(toolbox, planner)

    @staticmethod
    def _config(thread_id: str) -> dict:
        return {"configurable": {"thread_id": thread_id}}

    def waiting_for_approval(self, thread_id: str) -> bool:
        return bool(self.graph.get_state(self._config(thread_id)).next)

    def known(self, thread_id: str) -> bool:
        return bool(self.graph.get_state(self._config(thread_id)).values)

    def ask(self, message: str, thread_id: Optional[str] = None) -> dict:
        thread_id = thread_id or uuid.uuid4().hex[:12]
        if self.waiting_for_approval(thread_id):
            raise PendingApproval(thread_id)
        result = self.graph.invoke({"question": message}, self._config(thread_id))
        return self._shape(thread_id, result)

    def resume(self, thread_id: str, approve: bool) -> dict:
        if not self.waiting_for_approval(thread_id):
            raise KeyError(thread_id)
        result = self.graph.invoke(Command(resume={"approve": approve}), self._config(thread_id))
        return self._shape(thread_id, result)

    def memory(self, thread_id: str) -> dict:
        values = self.graph.get_state(self._config(thread_id)).values or {}
        return {"thread_id": thread_id, "memory": values.get("memory", {}), "history": values.get("history", [])}

    def _shape(self, thread_id: str, result: dict) -> dict:
        state = self.graph.get_state(self._config(thread_id)).values
        steps = state.get("steps", [])
        out = {"thread_id": thread_id, "planner": self.planner.name, "steps": steps,
               "tools_used": [s["tool"] for s in steps], "memory": state.get("memory", {}),
               "citations": [c for s in steps if s["tool"] == "search_rules" for c in s["observation"].get("citations", [])]}
        interrupts = result.get("__interrupt__")
        if interrupts:
            out.update(status="needs_approval", answer="", approval=interrupts[0].value)
        else:
            out.update(status="done", answer=state.get("answer", ""), approval=None)
        return out
