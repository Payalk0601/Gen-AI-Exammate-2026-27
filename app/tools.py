"""Tools the KachraCheck agent can call.

1. waste_stream_sorter - looks an item up in data/waste_items.csv and returns which of the
   four SWM Rules 2026 streams it belongs to (wet, dry, sanitary, special_care). Spelling
   mistakes are handled with difflib.
2. rag_search - looks up rule records (the same retrieval /chat uses).

TOOLS is the registry both agent_loop.py and graph.py read from.
"""
import csv
import difflib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ITEMS_CSV = ROOT / "data" / "waste_items.csv"

_cache: list[dict] | None = None


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", str(text).lower()).strip()


def _items() -> list[dict]:
    global _cache
    if _cache is None:
        with open(ITEMS_CSV, encoding="utf-8", newline="") as f:
            _cache = [dict(r, _key=_norm(r["item"])) for r in csv.DictReader(f)]
    return _cache


def _row_result(row: dict, query: str, match_type: str, score: float, alternatives: list[str]) -> dict:
    return {
        "found": True,
        "query": query,
        "matched_item": row["item"],
        "match_type": match_type,
        "score": round(score, 2),
        "stream": row["stream"],
        "handling_note": row["handling_note"],
        "rule_reference": row["rule_reference"],
        "alternatives": alternatives,
    }


def waste_stream_sorter(item: str) -> dict:
    """Return the waste stream for a household item (exact, partial or fuzzy match)."""
    query = _norm(item)
    if not query:
        return {"found": False, "query": item, "reason": "empty item name", "suggestions": []}
    rows = _items()
    keys = [r["_key"] for r in rows]

    # 1. exact
    for r in rows:
        if r["_key"] == query:
            return _row_result(r, item, "exact", 1.0, [])

    # 2. one name contained in the other ("old plastic bottle" -> "plastic bottle")
    contained = [r for r in rows if len(r["_key"]) >= 3 and (r["_key"] in query or query in r["_key"])]
    if contained:
        contained.sort(key=lambda r: len(r["_key"]), reverse=True)
        best = contained[0]
        return _row_result(best, item, "partial", 0.9, [r["item"] for r in contained[1:3]])

    # 3. fuzzy spelling ("bannana peel", "platic botle")
    close = difflib.get_close_matches(query, keys, n=3, cutoff=0.6)
    if close:
        by_key = {r["_key"]: r for r in rows}
        score = difflib.SequenceMatcher(None, query, close[0]).ratio()
        return _row_result(by_key[close[0]], item, "fuzzy", score, [by_key[k]["item"] for k in close[1:]])

    # 4. fuzzy on single words ("batary" -> "battery")
    words = {w for k in keys for w in k.split()}
    hits = []
    for w in query.split():
        hits += difflib.get_close_matches(w, list(words), n=1, cutoff=0.75)
    for h in hits:
        for r in rows:
            if h in r["_key"].split():
                return _row_result(r, item, "fuzzy-word", 0.7, [])

    return {"found": False, "query": item, "reason": "no close match in the item list", "suggestions": []}


def rag_search(query: str, k: int = 3) -> list:
    """Return the rule records most relevant to a query."""
    from app.chat import retrieve  # imported here to avoid a circular import

    return retrieve(str(query), k=int(k))


TOOLS = {
    "waste_stream_sorter": {
        "fn": waste_stream_sorter,
        "args": {"item": "name of a household item, e.g. 'plastic bottle'"},
        "description": "Tells which of the four 2026 streams (wet, dry, sanitary, special_care) a household item goes in, with a handling note.",
    },
    "rag_search": {
        "fn": rag_search,
        "args": {"query": "short search phrase about a rule or duty"},
        "description": "Searches the SWM Rules 2026 records for duties, definitions and rule references.",
    },
}


def tool_descriptions() -> str:
    lines = []
    for name, t in TOOLS.items():
        args = ", ".join(f'"{a}": {d!r}' for a, d in t["args"].items())
        lines.append(f"- {name}({{{args}}}): {t['description']}")
    return "\n".join(lines)


def run_tool(name: str, tool_input: dict) -> object:
    """Run a tool by name. Never raises: errors come back as {'error': ...}."""
    tool = TOOLS.get(name)
    if tool is None:
        return {"error": f"unknown tool '{name}'", "available": list(TOOLS)}
    if not isinstance(tool_input, dict):
        return {"error": "tool input must be a JSON object"}
    try:
        return tool["fn"](**tool_input)
    except TypeError as e:
        return {"error": f"bad arguments: {e}", "expected": tool["args"]}
    except Exception as e:  # keep the agent alive if a tool breaks
        return {"error": f"{type(e).__name__}: {e}"}
