"""Retrieval-augmented answers for KachraCheck: answer ONLY from retrieved chunks, cite them, or say "I don't know".

  retrieve  -> top-k chunks (Chroma store or in-memory index)
  gates     -> refuse when the evidence is not there (low similarity, an amount is asked but no amount appears,
               most of the question's words appear in none of the chunks)
  generate  -> extractive (copies the best sentences, no key needed) or an LLM that must cite [1], [2] ...
  result    -> answer text, citations (title, source, page), and why it answered or refused

A meaning-based score alone cannot say "no answer": "What is the exact fine in rupees for burning waste?" scored higher
than some correct questions. So the gates look at what the question actually asks for.
"""
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Callable, List, Optional, Tuple

from app.chunking import SENTENCE_SPLIT
from app.smart_search import GENERIC, SYNONYMS, _STOP, analyze, stem

IDK = "I don't know. The SWM Rules documents I have do not say this."
MIN_SCORE = float(os.environ.get("KACHRACHECK_MIN_SCORE", "0.30"))
MIN_COVERAGE = 0.2     # refuse only when almost none of the question's words appear in the sources

AMOUNT_ASKED = re.compile(r"(?i)\b(fines?|penalt(?:y|ies)|rupees?|rs\.?|charges?d?|cost|price|amount|how much)\b|\u20b9")
AMOUNT_FOUND = re.compile(r"(?i)(?:\u20b9|\bRs\.?|\bINR\b|\brupees?\b)\s*\d[\d,]*|\d[\d,]*\s*(?:rupees?|\bRs\b)")

SYSTEM_PROMPT = (
    "You are KachraCheck, an assistant for India's Solid Waste Management Rules, 2026.\n"
    "Answer ONLY from the numbered sources in the user message. Do not use outside knowledge.\n"
    "After every sentence that states a fact, add the source number in square brackets, like [1] or [2][3].\n"
    "If the sources do not contain the answer, reply with exactly: I don't know.\n"
    "Never guess an amount, date or rule number that is not written in the sources. Keep the answer under 120 words."
)


@dataclass
class Source:
    n: int
    title: str
    source: str
    page: int
    score: float
    text: str
    chunk_id: str = ""


@dataclass
class Answer:
    question: str
    answer: str
    answered: bool
    reason: str
    generator: str
    citations: List[Source] = field(default_factory=list)
    considered: List[Source] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        for s in d["considered"]:
            s["text"] = s["text"][:200]
        return d


# ---------------------------------------------------------------- retrieval adapters
def retrieve_from_store(store) -> Callable[[str, int], List[dict]]:
    """Adapter for app.vectorstore.VectorStore."""
    return lambda q, k: store.search(q, k)


def retrieve_from_index(index) -> Callable[[str, int], List[dict]]:
    """Adapter for app.embed.SemanticIndex (used by the evaluation)."""
    def run(q: str, k: int) -> List[dict]:
        return [{"chunk_id": c.id, "score": s, "text": c.text, "title": c.title, "source": c.source, "page": c.page}
                for c, s in index.search(q, k)]
    return run


def _sources(hits: List[dict]) -> List[Source]:
    return [Source(n=i, title=h["title"], source=h["source"], page=int(h["page"]), score=float(h["score"]),
                   text=h["text"], chunk_id=h.get("chunk_id", "")) for i, h in enumerate(hits, 1)]


# ---------------------------------------------------------------- gates
def needs_amount(question: str) -> bool:
    return bool(AMOUNT_ASKED.search(question))


def has_amount(text: str) -> bool:
    return bool(AMOUNT_FOUND.search(text))


def term_coverage(question: str, texts: List[str]) -> Tuple[float, List[str]]:
    """Share of the question's meaningful words found in the retrieved texts (directly or through a synonym)."""
    vocab = {t for text in texts for t in analyze(text)}
    words = [w for w in re.findall(r"[a-z0-9]+", question.lower()) if w not in _STOP and w not in GENERIC]
    if not words:
        return 1.0, []
    missing = []
    for w in words:
        s = stem(w)
        if s in vocab or (s in SYNONYMS and any(t in vocab for t in analyze(SYNONYMS[s]))):
            continue
        missing.append(w)
    return round(1 - len(missing) / len(words), 2), missing


def evidence_gate(question: str, sources: List[Source], min_score: float) -> Optional[str]:
    """Return the reason to refuse, or None when the evidence is good enough to try an answer."""
    if not sources:
        return "no_sources"
    if sources[0].score < min_score:
        return "low_similarity"
    if needs_amount(question) and not any(has_amount(s.text) for s in sources):
        return "no_amount_in_sources"
    if term_coverage(question, [s.text for s in sources])[0] < MIN_COVERAGE:
        return "low_coverage"
    return None


# ---------------------------------------------------------------- generators
def _question_terms(question: str) -> set:
    words = [w for w in re.findall(r"[a-z0-9]+", question.lower()) if w not in _STOP and w not in GENERIC]
    terms = set()
    for w in words:
        s = stem(w)
        terms.add(s)
        if s in SYNONYMS:
            terms.update(analyze(SYNONYMS[s]))
    return terms


class ExtractiveGenerator:
    """No LLM: copies the sentence that best matches the question from each of the best chunks."""
    name = "extractive"

    def generate(self, question: str, sources: List[Source]):
        terms = _question_terms(question)
        need = min(2, len(terms))
        candidates = []
        for rank, src in enumerate(sources):
            best = None
            for sentence in SENTENCE_SPLIT.split(re.sub(r"\s+", " ", src.text)):
                overlap = len(terms & set(analyze(sentence)))
                if overlap >= need and (best is None or overlap > best[0]):
                    best = (overlap, sentence.strip())
            if best:
                candidates.append((-best[0], rank, src, best[1]))
        if not candidates:
            return None, "no_supporting_sentence"
        chosen = sorted(candidates)[:2]
        chosen.sort(key=lambda c: c[1])
        parts, cited = [], []
        for i, (_, _, src, sentence) in enumerate(chosen, 1):
            parts.append(f"{sentence[:350].rstrip(' ;,')} [{i}]")
            cited.append(Source(**{**asdict(src), "n": i, "text": sentence[:350]}))
        return (" ".join(parts), cited), None


class LLMGenerator:
    """Asks an LLM to answer from the numbered sources and cite them. Falls back to nothing if it refuses."""

    def __init__(self):
        from app import llm
        self.llm = llm
        provider = llm.available_provider()
        self.name = f"llm:{provider}/{llm.model_name(provider)}" if provider else "llm:none"

    def generate(self, question: str, sources: List[Source]):
        context = "\n\n".join(f"[{s.n}] ({s.title}, {s.source} p.{s.page})\n{s.text}" for s in sources)
        reply = self.llm.complete(SYSTEM_PROMPT, f"Sources:\n{context}\n\nQuestion: {question}")
        if re.match(r"(?is)\s*i don'?t know", reply):
            return None, "model_said_unknown"
        used = sorted({int(n) for n in re.findall(r"\[(\d+)\]", reply) if 1 <= int(n) <= len(sources)})
        if not used:
            return None, "no_citation"
        return (reply, [sources[n - 1] for n in used]), None


def make_generator(name: Optional[str] = None):
    name = (name or os.environ.get("KACHRACHECK_GENERATOR") or "auto").lower()
    if name == "extractive":
        return ExtractiveGenerator()
    if name in ("llm", "auto"):
        from app import llm
        if llm.available_provider():
            return LLMGenerator()
        if name == "llm":
            raise ValueError("generator 'llm' needs a key: copy .env.example to .env and add GROQ_API_KEY or GEMINI_API_KEY")
        return ExtractiveGenerator()
    raise ValueError(f"unknown generator {name!r}; use extractive, llm or auto")


# ---------------------------------------------------------------- the entry point
def answer_question(question: str, retrieve: Callable[[str, int], List[dict]], k: int = 4,
                    generator=None, min_score: float = MIN_SCORE) -> Answer:
    """Retrieve k chunks, check the evidence, answer with citations or say I don't know."""
    generator = generator or make_generator()
    sources = _sources(retrieve(question, k))

    def refuse(reason: str, gen: str) -> Answer:
        return Answer(question, IDK, False, reason, gen, [], sources)

    reason = evidence_gate(question, sources, min_score)
    if reason:
        return refuse(reason, generator.name)

    gen_name = generator.name
    try:
        result, why = generator.generate(question, sources)
    except Exception as err:                                  # LLMError, network trouble: fall back, never crash
        gen_name = f"extractive (fallback, {generator.name} failed: {err})"
        result, why = ExtractiveGenerator().generate(question, sources)
    if result is None:
        return refuse(why, gen_name)
    text, cited = result
    return Answer(question, text, True, "ok", gen_name, cited, sources)
