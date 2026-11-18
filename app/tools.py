"""Tools the KachraCheck agent can call.

  waste_stream_sorter(item)   household item -> one of the four 2026 streams, with a handling note and rule reference.
                              Looks the item up in data/waste_items.csv and tolerates spelling mistakes (difflib).
  search_rules(question)      answers from the SWM Rules documents with citations (the RAG module), or says "I don't know".

Every tool returns a plain dict, so the result can be shown to the user, logged, or given back to an LLM.
"""
import csv
import difflib
import re
from functools import lru_cache
from pathlib import Path
from typing import Callable, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
ITEMS_CSV = ROOT / "data" / "waste_items.csv"
STREAMS = ("wet", "dry", "sanitary", "special care")
REQUIRED_COLUMNS = ("item", "aliases", "stream", "handling_note", "rule_reference", "basis")

FUZZY_ACCEPT = 0.80      # similarity needed to accept a misspelt item (the user is asked to confirm it)
SUGGEST_MIN = 0.55       # similarity needed to offer "did you mean ..."
CONTAIN_SHARE = 0.60     # a known name inside a longer phrase counts if it makes up this much of the phrase
TOKEN_CLOSE = 0.82       # a suggestion must share a word that is this close to one of the item's words
MODIFIERS = {"used", "old", "empty", "dirty", "waste", "discarded", "expired", "broken"}
MAX_INPUT_CHARS = 300

TOOL_SPECS = {
    "waste_stream_sorter": {
        "description": ("Look up a household item and say which of the four 2026 streams (wet, dry, sanitary, special care) "
                        "it belongs to, with a handling note and the rule reference. Tolerates spelling mistakes."),
        "input": {"item": "string, the item, for example 'plastic bottle'"},
    },
    "search_rules": {
        "description": ("Search the Solid Waste Management Rules 2026 documents and answer a question about duties, deadlines, "
                        "bins, registration or fines, with citations. Says I don't know when the documents do not contain the answer."),
        "input": {"question": "string, the question in plain words"},
    },
}


# ---------------------------------------------------------------- text helpers
def normalise(text: str) -> str:
    """lower case, letters/digits/spaces only, no leading articles"""
    text = (text or "").lower().replace("&", " and ").replace("-", " ")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    while True:
        stripped = re.sub(r"^(?:a|an|the|my|some|this|that|one)\s+", "", text)
        if stripped == text:
            return text
        text = stripped


def strip_modifiers(phrase: str) -> str:
    """'used battery' -> 'battery' (only leading modifier words; the caller tries the original first)."""
    words = phrase.split()
    while len(words) > 1 and words[0] in MODIFIERS:
        words = words[1:]
    return " ".join(words)


def _shares_close_word(query: str, name: str) -> bool:
    return any(difflib.SequenceMatcher(None, a, b).ratio() >= TOKEN_CLOSE for a in query.split() for b in name.split())


def singular(phrase: str) -> str:
    """Make the last word singular: bottles -> bottle, batteries -> battery."""
    words = phrase.split()
    if not words:
        return phrase
    w = words[-1]
    if len(w) > 3 and w.endswith("ies"):
        w = w[:-3] + "y"
    elif len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        w = w[:-1]
    words[-1] = w
    return " ".join(words)


# ---------------------------------------------------------------- the item table
@lru_cache(maxsize=4)
def _load(path_str: str) -> tuple:
    rows, problems = [], []
    with open(path_str, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path_str} is missing column(s): {', '.join(missing)}")
        for line, row in enumerate(reader, start=2):
            row = {k: (v or "").strip() for k, v in row.items()}
            if not row["item"] or row["stream"] not in STREAMS:
                problems.append(f"line {line}: bad item or stream ({row.get('item')!r}, {row.get('stream')!r})")
                continue
            row["names"] = [normalise(row["item"])] + [normalise(a) for a in row["aliases"].split(";") if a.strip()]
            rows.append(row)
    return tuple(rows), tuple(problems)


def load_items(path=ITEMS_CSV) -> List[dict]:
    """Rows of the CSV; rows with a missing item or an unknown stream are skipped (see csv_problems)."""
    return list(_load(str(path))[0])


def csv_problems(path=ITEMS_CSV) -> List[str]:
    return list(_load(str(path))[1])


def _index(items: List[dict]) -> Dict[str, dict]:
    index = {}
    for row in items:
        for name in row["names"]:
            index.setdefault(name, row)
            index.setdefault(singular(name), row)
    return index


def _result(row: dict, query: str, match_type: str, similarity: float, confirm: bool, suggestions: List[str]) -> dict:
    return {"found": True, "query": query, "match_type": match_type, "similarity": round(similarity, 2),
            "needs_confirmation": confirm, "matched_item": row["item"], "stream": row["stream"],
            "handling_note": row["handling_note"], "rule_reference": row["rule_reference"], "basis": row["basis"],
            "suggestions": suggestions}


def waste_stream_sorter(item: str, path=ITEMS_CSV) -> dict:
    """Which of the four streams does `item` belong to?

    match_type: exact (name or alias), contains (a known name inside a longer phrase), fuzzy (a close spelling:
    needs_confirmation is True, because a wrong guess means a wrong bin), none (not found, with suggestions).
    """
    query = (item or "").strip()
    q = normalise(query)
    if not q:
        return {"found": False, "query": query, "match_type": "none", "similarity": 0.0, "needs_confirmation": False,
                "suggestions": [], "error": "no item given"}
    q = q[:MAX_INPUT_CHARS]
    items = load_items(path)
    index = _index(items)
    stripped = strip_modifiers(q)
    variants = list(dict.fromkeys([q, singular(q), stripped, singular(stripped)]))

    for v in variants:                                                       # 1. exact
        if v in index:
            return _result(index[v], query, "exact", 1.0, False, [])

    contained = [(len(n), n) for n in index
                 if len(n) >= 3 and any(re.search(rf"\b{re.escape(n)}\b", v) for v in variants)
                 and len(n) / len(q) >= CONTAIN_SHARE]
    if contained:                                                            # 2. a known name inside the phrase
        n = max(contained)[1]
        return _result(index[n], query, "contains", len(n) / len(q), False, [])

    names = list(index)                                                      # 3. spelling mistakes (difflib)
    scored = {}
    for v in variants:
        for n in difflib.get_close_matches(v, names, n=6, cutoff=SUGGEST_MIN):
            ratio = difflib.SequenceMatcher(None, v, n).ratio()
            if ratio >= FUZZY_ACCEPT or _shares_close_word(v, n):      # drop look-alikes that only share letters
                scored[n] = max(scored.get(n, 0.0), ratio)
    ranked = sorted(scored.items(), key=lambda kv: -kv[1])
    suggestions = list(dict.fromkeys(index[n]["item"] for n, _ in ranked))[:3]
    if ranked and ranked[0][1] >= FUZZY_ACCEPT:
        name, score = ranked[0]
        return _result(index[name], query, "fuzzy", score, True, [s for s in suggestions if s != index[name]["item"]])
    return {"found": False, "query": query, "match_type": "none", "similarity": round(ranked[0][1], 2) if ranked else 0.0,
            "needs_confirmation": False, "suggestions": suggestions}


# ---------------------------------------------------------------- the tool box
class ToolBox:
    """The tools, bound to where they get their data. `call` never raises: problems come back as {"error": ...}."""

    def __init__(self, get_store: Optional[Callable] = None, rules_search: Optional[Callable] = None, items_path=ITEMS_CSV):
        self.get_store = get_store
        self._rules_search = rules_search
        self.items_path = items_path

    def specs(self) -> dict:
        return TOOL_SPECS

    def waste_stream_sorter(self, item: str) -> dict:
        return waste_stream_sorter(item, self.items_path)

    def search_rules(self, question: str, k: int = 4) -> dict:
        if self._rules_search:
            return self._rules_search(question, k)
        from app import rag
        if self.get_store is None:
            return {"error": "the rules index is not available"}
        store = self.get_store()
        if store.count() == 0:
            return {"error": "the vector index is empty: run python -m app.vectorstore --rebuild"}
        ans = rag.answer_question(question, rag.retrieve_from_store(store), k=k)
        return {"answered": ans.answered, "answer": ans.answer, "reason": ans.reason, "generator": ans.generator,
                "citations": [{"n": c.n, "title": c.title, "source": c.source, "page": c.page} for c in ans.citations]}

    def call(self, name: str, args: dict) -> dict:
        if name not in TOOL_SPECS:
            return {"error": f"unknown tool '{name}'"}
        key = "item" if name == "waste_stream_sorter" else "question"
        value = args.get(key) if isinstance(args, dict) else None
        if not isinstance(value, str) or not value.strip():
            return {"error": f"tool '{name}' needs a non-empty text argument '{key}'"}
        value = value.strip()[:MAX_INPUT_CHARS]
        try:
            return getattr(self, name)(value)
        except ImportError:
            return {"error": "a required package is missing: run pip install -r requirements.txt"}
        except Exception as err:                         # a tool failing must not crash the agent
            return {"error": f"{name} failed: {type(err).__name__}: {err}"}
