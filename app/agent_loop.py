"""Hand-written agent loop (no framework).

Cycle: ask the LLM what to do -> if it picks a tool, run it and show the result back to the LLM
-> repeat until the LLM gives a final answer or MAX_STEPS is reached.

Try it:  python -m app.agent_loop "Where does a banana peel go?"
"""
import json
import re
import sys
from pathlib import Path

from app.llm import generate
from app.tools import run_tool, tool_descriptions

PROMPTS = Path(__file__).resolve().parent.parent / "prompts"
MAX_STEPS = 5


def system_prompt() -> str:
    text = (PROMPTS / "agent_system.md").read_text(encoding="utf-8")
    return text.replace("{tools}", tool_descriptions())


def build_user_prompt(question: str, scratch: list, history: list | None = None) -> str:
    parts = []
    if history:
        convo = "\n".join(f"User: {h['q']}\nKachraCheck: {h['a']}" for h in history[-3:])
        parts.append("PREVIOUS CONVERSATION:\n" + convo)
    parts.append(f"QUESTION: {question}")
    if scratch:
        obs = "\n".join(
            f"[{i}] {s['tool']}({json.dumps(s['input'], ensure_ascii=False)}) -> {s['observation']}"
            for i, s in enumerate(scratch, 1)
        )
        parts.append("TOOL RESULTS SO FAR:\n" + obs)
    parts.append("Decide the next step. Reply with ONE JSON object only.")
    return "\n\n".join(parts)


def parse_decision(raw: str) -> dict:
    raw = re.sub(r"```(?:json)?", "", raw).strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("model reply had no JSON object")
    obj = json.loads(raw[start : end + 1])
    action = obj.get("action")
    if action == "tool":
        if not isinstance(obj.get("tool"), str):
            raise ValueError("tool action without a tool name")
        obj["input"] = obj.get("input") if isinstance(obj.get("input"), dict) else {}
        return obj
    if action == "final":
        return obj
    raise ValueError(f"unknown action: {action!r}")


def normalise_final(obj: dict) -> dict:
    conf = str(obj.get("confidence", "low")).lower()
    return {
        "answer": str(obj.get("answer", "")).strip(),
        "confidence": conf if conf in ("high", "medium", "low") else "low",
        "follow_up": str(obj.get("follow_up", "")).strip(),
    }


def decide(question: str, scratch: list, history: list | None = None, provider: str | None = None) -> dict:
    """One LLM call -> one validated decision. Retries once if the JSON is broken."""
    user = build_user_prompt(question, scratch, history)
    last_err = None
    for _ in range(2):
        raw = generate(system_prompt(), user, provider)
        try:
            return parse_decision(raw)
        except (ValueError, json.JSONDecodeError) as e:
            last_err = e
            user += f"\n\nYour last reply was invalid ({e}). Reply with ONE valid JSON object."
    raise ValueError(f"could not get a valid decision: {last_err}")


def observation_text(result: object, limit: int = 1500) -> str:
    text = json.dumps(result, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + "...(truncated)"


def run_agent(question: str, provider: str | None = None, history: list | None = None, max_steps: int = MAX_STEPS) -> dict:
    scratch: list[dict] = []
    for step in range(1, max_steps + 1):
        decision = decide(question, scratch, history, provider)
        if decision["action"] == "final":
            out = normalise_final(decision)
            out["steps"] = scratch
            return out
        tool, tool_input = decision["tool"], decision["input"]
        if any(s["tool"] == tool and s["input"] == tool_input for s in scratch):
            obs = "You already ran this exact call. Use the earlier result and give the final answer now."
        else:
            obs = observation_text(run_tool(tool, tool_input))
        scratch.append({"step": step, "tool": tool, "input": tool_input, "observation": obs})
    return {
        "answer": "I could not finish within the step limit. Please rephrase or narrow the question.",
        "confidence": "low",
        "follow_up": "Which single item or rule should I look at first?",
        "steps": scratch,
    }


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "Which bin does a banana peel go in?"
    result = run_agent(q)
    for s in result["steps"]:
        print(f"[step {s['step']}] {s['tool']} {s['input']}\n   -> {s['observation'][:200]}")
    print("\nANSWER:", result["answer"])
    print("CONFIDENCE:", result["confidence"], "| FOLLOW-UP:", result["follow_up"])
