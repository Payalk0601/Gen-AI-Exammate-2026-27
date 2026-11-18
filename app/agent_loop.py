"""A hand-written agent: a planner picks a tool, the loop runs it, looks at the result, and repeats until it is done.

  question -> planner.next_action -> tool -> observation -> planner.next_action -> ... -> final answer

The planner only DECIDES which tool to call. The final answer is built from the tool results by `compose_answer`, so
nothing the user reads is invented by the planner: item streams come from the CSV, rule answers come from the cited chunks.

Two planners:
  RulePlanner  keyword rules, no key needed (default when no LLM key exists)
  LLMPlanner   asks Groq/Gemini for one JSON action per step, and falls back to RulePlanner if the reply is unusable
Choose with KACHRACHECK_PLANNER = rules | llm | auto.
"""
import json
import os
import re
from dataclasses import asdict, dataclass, field
from typing import List, Optional

from app.rag import IDK
from app.tools import TOOL_SPECS, ToolBox

MAX_STEPS = 4
HELP_TEXT = ("I can tell you which stream a household item goes in (wet, dry, sanitary or special care), "
             "or answer questions about the Solid Waste Management Rules, 2026. What would you like to know?")
PRONOUNS = {"it", "this", "that", "them", "these", "those", "one"}
SMALL_TALK = {"hi", "hello", "hey", "thanks", "thank", "ok", "okay", "help", "bye", "yes", "no", "test"}


@dataclass
class Step:
    n: int
    tool: str
    input: dict
    observation: dict

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------- understanding the question
ITEM_PATTERNS = [
    r"(?:where|which (?:bin|stream|category))\s+(?:does|do|should|can|would|will)\s+(?:my |the |a |an |this |these |that )?(.+?)\s+(?:go|belong|be (?:thrown|put|disposed)|come)\b",
    r"(?:how|where)\s+(?:do|can|should)\s+i\s+(?:dispose(?: of)?|throw(?: away)?|segregate|sort|get rid of)\s+(?:my |the |a |an )?(.+?)\s*[\?\.]?$",
    r"(?:which|what)\s+(?:bin|stream|category|kind of waste|type of waste)\s+(?:is|for)\s+(?:my |the |a |an )?(.+?)\s*[\?\.]?$",
    r"\b(?:is|are)\s+(?:my |the |a |an )?(.+?)\s+(?:wet|dry|sanitary|special[- ]care)\b",
    r"\b(?:can|should)\s+i\s+(?:put|throw|dispose(?: of)?)\s+(?:my |the |a |an )?(.+?)\s+(?:in|into)\b",
    r"^(?:sort|classify|segregate)\s+(?:my |the |a |an )?(.+?)\s*[\?\.]?$",
]
RULE_WORDS = re.compile(r"(?i)\b(rules?|law|legal|clauses?|penalt\w*|fines?|who must|by when|deadline|duty|duties|bye-?laws?|"
                        r"register|registration|returns?|portal|municipal\w*|local bod\w+|bulk|says?|required|mandatory)\b")
FOLLOW_UP = re.compile(r"(?i)^\s*(?:and\s+)?(?:why|which rule|what rule|how come|explain|what does the rule say|rule)\b")


def extract_item(question: str) -> Optional[str]:
    """The household item the question is about, or None. Pronouns come back as 'it', 'this', ..."""
    q = re.sub(r"\s+", " ", question.strip())
    for pattern in ITEM_PATTERNS:
        m = re.search(pattern, q, re.I)
        if m:
            return m.group(1).strip(" ?.,")
    words = re.findall(r"[A-Za-z][A-Za-z\-']*", q)
    if 0 < len(words) <= 4 and not (SMALL_TALK & {w.lower() for w in words}) and not RULE_WORDS.search(q) and not FOLLOW_UP.match(q) and not q.endswith("?"):
        return " ".join(words)                              # a bare item name such as "plastic bottle" or "batery"
    return None


def rules_query(memory: dict) -> str:
    stream = memory.get("last_stream") or "this kind of"
    return f"Which rule requires {stream} waste to be segregated or handled separately, and what must the waste generator do?"


# ---------------------------------------------------------------- planners
class RulePlanner:
    name = "rules"

    def next_action(self, question: str, memory: dict, steps: List[Step]) -> dict:
        used = [s.tool for s in steps]
        sorted_step = next((s for s in steps if s.tool == "waste_stream_sorter"), None)
        asks_rule = bool(RULE_WORDS.search(question))

        words = {w.lower() for w in re.findall(r"[A-Za-z]+", question)}
        if not steps and len(words) <= 3 and SMALL_TALK & words:
            return {"action": "final", "message": HELP_TEXT}
        if FOLLOW_UP.match(question) and memory.get("last_stream") and not steps:
            return {"tool": "search_rules", "input": {"question": rules_query(memory)}}

        item = extract_item(question)
        if item and item.lower() in PRONOUNS:
            item = memory.get("last_item")
            if not item:
                return {"action": "final", "message": "Which item do you mean? Tell me its name, for example 'plastic bottle'."}

        if item and not sorted_step and not (asks_rule and not re.search(r"\b(where|which bin|which stream|dispose|throw)\b", question, re.I)):
            return {"tool": "waste_stream_sorter", "input": {"item": item}}
        if "search_rules" not in used:
            if sorted_step and sorted_step.observation.get("found") and asks_rule:
                return {"tool": "search_rules", "input": {"question": rules_query({"last_stream": sorted_step.observation["stream"]})}}
            if not sorted_step and (asks_rule or not item):
                return {"tool": "search_rules", "input": {"question": question}}
            if sorted_step and not sorted_step.observation.get("found"):
                return {"tool": "search_rules", "input": {"question": question}}      # the table does not know it: try the Rules
        return {"action": "final"}


PLANNER_PROMPT = (
    "You are the planner of KachraCheck, an assistant about household waste under India's Solid Waste Management Rules, 2026.\n"
    "Choose the next action. Tools:\n{tools}\n"
    "Reply with ONE JSON object and nothing else:\n"
    '{{"action": "tool", "tool": "waste_stream_sorter", "input": {{"item": "plastic bottle"}}}}\n'
    '{{"action": "tool", "tool": "search_rules", "input": {{"question": "..."}}}}\n'
    '{{"action": "final"}}   (when the observations are enough, or the question is off topic)\n'
    "Use waste_stream_sorter when the user asks where an item goes. Use search_rules for questions about the Rules. "
    "Use both when asked for both. Never call the same tool with the same input twice. "
    "If the user says it/this/that, use the item from memory."
)


def summarise(observation: dict) -> str:
    if "error" in observation:
        return f"error: {observation['error']}"
    if "stream" in observation or "match_type" in observation:
        if observation.get("found"):
            return f"found '{observation['matched_item']}' -> {observation['stream']} ({observation['match_type']} match)"
        return f"not found; suggestions: {observation.get('suggestions') or 'none'}"
    if observation.get("answered"):
        return f"answered with {len(observation.get('citations', []))} citation(s)"
    return f"I don't know ({observation.get('reason', 'no evidence')})"


def extract_json(text: str) -> Optional[dict]:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(text[start:end + 1])
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


class LLMPlanner:
    """Asks the LLM for the next action. Falls back to RulePlanner for a step whose reply is unusable."""

    def __init__(self):
        from app import llm
        self.llm = llm
        provider = llm.available_provider()
        self.name = f"llm:{provider}/{llm.model_name(provider)}" if provider else "llm:none"
        self.fallback = RulePlanner()

    def next_action(self, question: str, memory: dict, steps: List[Step]) -> dict:
        tools = "\n".join(f"- {n}: {s['description']} Input: {json.dumps(s['input'])}" for n, s in TOOL_SPECS.items())
        history = "\n".join(f"{s.n}. {s.tool}({json.dumps(s.input)}) -> {summarise(s.observation)}" for s in steps) or "none yet"
        mem = f"last item: {memory.get('last_item')} ({memory.get('last_stream')})" if memory.get("last_item") else "nothing yet"
        user = f"Question: {question}\nMemory: {mem}\nSteps so far:\n{history}"
        try:
            reply = self.llm.complete(PLANNER_PROMPT.format(tools=tools), user, max_tokens=200)
        except Exception:
            return self.fallback.next_action(question, memory, steps)
        action = extract_json(reply)
        if action and action.get("action") == "final":
            return {"action": "final"}
        if action and action.get("action") == "tool" and action.get("tool") in TOOL_SPECS and isinstance(action.get("input"), dict):
            return {"tool": action["tool"], "input": action["input"]}
        return self.fallback.next_action(question, memory, steps)


def make_planner(name: Optional[str] = None):
    name = (name or os.environ.get("KACHRACHECK_PLANNER") or "auto").lower()
    if name == "rules":
        return RulePlanner()
    if name in ("llm", "auto"):
        from app import llm
        if llm.available_provider():
            return LLMPlanner()
        if name == "llm":
            raise ValueError("planner 'llm' needs a key: copy .env.example to .env and add GROQ_API_KEY or GEMINI_API_KEY")
        return RulePlanner()
    raise ValueError(f"unknown planner {name!r}; use rules, llm or auto")


# ---------------------------------------------------------------- the answer
def compose_answer(steps: List[Step]) -> str:
    """Build the reply from the tool results only."""
    parts = []
    for s in steps:
        obs = s.observation
        if "error" in obs and s.tool == "waste_stream_sorter" and not obs.get("query"):
            parts.append(f"I could not sort that: {obs['error']}.")
        elif s.tool == "waste_stream_sorter":
            if obs.get("found"):
                text = f"**{obs['matched_item'].capitalize()}** goes in the **{obs['stream']}** stream. {obs['handling_note']} ({obs['rule_reference']})"
                if obs["match_type"] == "fuzzy":
                    text = f"I read '{obs['query']}' as '{obs['matched_item']}'. " + text
                if obs.get("basis", "").startswith("my reading"):
                    text += " The Rules do not name this item; I placed it using the stream definitions, so check with your local body if unsure."
                parts.append(text)
            else:
                text = f"I don't have '{obs.get('query')}' in my item list."
                if obs.get("suggestions"):
                    text += f" Did you mean: {', '.join(obs['suggestions'])}?"
                parts.append(text)
        elif s.tool == "search_rules":
            if "error" in obs:
                parts.append(f"I could not search the Rules: {obs['error']}")
            elif obs.get("answered"):
                cites = "; ".join(f"{c['title']} ({c['source']} p.{c['page']})" for c in obs.get("citations", []))
                parts.append(f"{obs['answer']}\n\nSources: {cites}" if cites else obs["answer"])
            else:
                parts.append(IDK)
    return "\n\n".join(parts)


def memory_from(steps: List[Step], memory: dict) -> dict:
    """Remember the last item that was sorted, so 'why?' and 'it' can refer to it."""
    for s in reversed(steps):
        if s.tool == "waste_stream_sorter" and s.observation.get("found"):
            memory = {**memory, "last_item": s.observation["matched_item"], "last_stream": s.observation["stream"],
                      "last_rule": s.observation["rule_reference"]}
            break
    return memory


@dataclass
class AgentResult:
    answer: str
    steps: List[Step] = field(default_factory=list)
    planner: str = ""
    memory: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        citations = [c for s in self.steps if s.tool == "search_rules" for c in s.observation.get("citations", [])]
        return {"answer": self.answer, "steps": [s.to_dict() for s in self.steps],
                "tools_used": [s.tool for s in self.steps], "citations": citations,
                "planner": self.planner, "memory": self.memory}


def run_agent(question: str, toolbox: ToolBox, planner=None, memory: Optional[dict] = None, max_steps: int = MAX_STEPS) -> AgentResult:
    """Plan -> call a tool -> read the result -> repeat, at most `max_steps` times."""
    planner = planner or make_planner()
    memory = dict(memory or {})
    steps: List[Step] = []
    message = None
    for _ in range(max_steps):
        try:
            action = planner.next_action(question, memory, steps)
        except Exception:
            action = RulePlanner().next_action(question, memory, steps)
        if action.get("action") == "final" or "tool" not in action:
            message = action.get("message")
            break
        if any(s.tool == action["tool"] and s.input == action["input"] for s in steps):
            break                                           # the same call again would change nothing
        steps.append(Step(len(steps) + 1, action["tool"], action["input"], toolbox.call(action["tool"], action["input"])))
    answer = compose_answer(steps) or message or HELP_TEXT
    return AgentResult(answer, steps, planner.name, memory_from(steps, memory))
