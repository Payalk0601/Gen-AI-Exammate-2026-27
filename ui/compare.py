"""2016 vs 2026: pick the comparison that belongs to an answer, and highlight what changed.

data/rule_changes.json pairs each 2026 duty with the 2016 duty it replaces. Both sides are written in matching wording,
so a word-by-word diff shows real differences: removed words on the 2016 side, added words on the 2026 side.
"""
import difflib
import html
import json
import re
from pathlib import Path
from typing import List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
CHANGES_PATH = ROOT / "data" / "rule_changes.json"
PDF_ROWS_PATH = ROOT / "data" / "records_from_pdf.json"
CURATED_PATH = ROOT / "data" / "records.json"

STOP = {"the", "a", "an", "of", "to", "and", "or", "in", "on", "for", "is", "are", "be", "by", "with", "it", "that", "this",
        "what", "which", "who", "how", "do", "does", "my", "must", "shall", "can", "should", "when", "where"}


def load_json(path) -> list:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return data["pairs"] if isinstance(data, dict) and "pairs" in data else data


def load_pairs(path=CHANGES_PATH) -> List[dict]:
    return load_json(path)


def normalise_ref(ref: str) -> str:
    return re.sub(r"\s+", "", (ref or "").lower())


def tokens(text: str) -> set:
    return {w for w in re.findall(r"[a-z0-9][a-z0-9,\-]*", (text or "").lower()) if w not in STOP}


def pairs_for_response(resp: dict, pairs: List[dict], limit: int = 2) -> List[dict]:
    """The comparisons that belong to an /ask or /agent response.

    Strong signal: the item sorter named the exact rule ("Rule 5(1)(c)"). Weaker: a citation comes from the same rule
    number and the answer or cited text shares words with the pair. Refused answers (no citations) get none.
    """
    refs = set()
    for step in resp.get("steps", []) or []:
        obs = step.get("observation", {})
        if step.get("tool") == "waste_stream_sorter" and obs.get("found"):
            refs.update(normalise_ref(r) for r in obs.get("rule_reference", "").split(";") if r.strip())
    numbers = set()
    for c in resp.get("citations", []) or []:
        m = re.match(r"\s*Rule\s+(\d+)", c.get("title", ""))
        if m:
            numbers.add(int(m.group(1)))
    blob = tokens(" ".join([resp.get("question", ""), resp.get("answer", "")] +
                           [c.get("text", "") for c in resp.get("citations", []) or []]))
    scored = []
    for p in pairs:
        if normalise_ref(p["rule_2026"]) in refs:
            scored.append((100, p))
        elif p["rule_number"] in numbers:
            overlap = len(blob & tokens(" ".join(p.get("keywords", []) + [p["topic"]])))
            if overlap >= 2:
                scored.append((overlap, p))
    scored.sort(key=lambda sp: -sp[0])
    return [p for _, p in scored[:limit]]


def _norm_word(word: str) -> str:
    return re.sub(r"[^\w%]", "", word.lower()) or word.lower()


def word_diff(old: str, new: str) -> Tuple[str, str, dict]:
    """HTML for both sides with <span class="del"> on removed words (old) and <span class="add"> on added words (new)."""
    a, b = (old or "").split(), (new or "").split()
    matcher = difflib.SequenceMatcher(None, [_norm_word(w) for w in a], [_norm_word(w) for w in b], autojunk=False)
    old_out, new_out, removed, added = [], [], 0, 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        old_words, new_words = a[i1:i2], b[j1:j2]
        if tag == "equal":
            old_out += [html.escape(w) for w in old_words]
            new_out += [html.escape(w) for w in new_words]
            continue
        old_out += [f'<span class="del">{html.escape(w)}</span>' for w in old_words]
        new_out += [f'<span class="add">{html.escape(w)}</span>' for w in new_words]
        removed += len(old_words)
        added += len(new_words)
    return " ".join(old_out), " ".join(new_out), {"removed_words": removed, "added_words": added}


def full_2026_text(pair: dict, pdf_rows: List[dict], curated: List[dict]) -> Tuple[Optional[str], str]:
    """The 2026 clause behind a pair: the PDF row when it exists, otherwise my curated summary."""
    ref = pair.get("lookup_ref")
    if ref:
        for row in pdf_rows:
            if row.get("rule_reference") == ref:
                return row["obligation"], "Clause as printed in the 2026 gazette PDF"
    if pair.get("curated_id"):
        for row in curated:
            if row.get("id") == pair["curated_id"]:
                return row["obligation"], "My summary of the 2026 clause"
    return None, ""
