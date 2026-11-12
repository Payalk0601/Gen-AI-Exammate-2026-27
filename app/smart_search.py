"""TF-IDF + cosine-similarity ranking over KachraCheck records (powers GET /search)."""
import re
from typing import List, Tuple

from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.models import Record


# Plain-language words people use -> words the Rules use. Appended to the query before ranking.
SYNONYMS = {
    "municipality": "urban local bodies", "municipal": "urban local bodies", "corporation": "urban local bodies",
    "ulb": "urban local bodies", "panchayat": "rural local bodies", "village": "rural local bodies",
    "household": "waste generators", "citizen": "waste generators", "resident": "waste generators",
    "colour": "paint green blue red", "color": "paint green blue red",
    "spcb": "state pollution control boards", "pollution": "pollution control",
    "collector": "district magistrates", "magistrate": "district magistrates",
    "dustbin": "bins", "garbage": "waste", "rubbish": "waste", "kachra": "waste",
    "deadline": "timeline", "check": "review enforce compliance", "following": "comply compliance", "penalty": "environmental compensation", "mrf": "material recovery facility",
}
_STOP = set(ENGLISH_STOP_WORDS)
GENERIC = {"must", "use", "make", "does", "need", "get", "like", "rules", "rule"}
MIN_COVERAGE = 0.4   # below this, most of the question's words appear nowhere in the data


def stem(word: str) -> str:
    """Very small suffix stripper: bins->bin, bodies->body, municipalities->municipality."""
    for suffix, repl in (("ies", "y"), ("sses", "ss"), ("es", "e"), ("s", "")):
        if len(word) > 4 and word.endswith(suffix) and not word.endswith("ss"):
            return word[: -len(suffix)] + repl
    return word


def analyze(text: str) -> List[str]:
    return [stem(t) for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _STOP]


def _with_bigrams(tokens: List[str]) -> List[str]:
    return tokens + [f"{a} {b}" for a, b in zip(tokens, tokens[1:])]


def expand_query(query: str) -> str:
    """Add the Rules' own vocabulary for everyday words found in the query."""
    extra = [SYNONYMS[t] for t in (stem(w) for w in re.findall(r"[a-z]+", query.lower())) if t in SYNONYMS]
    return " ".join([query] + extra)


def record_text(r: Record) -> str:
    """The text a record is searched by. Stakeholder and category are repeated so that
    'who must...' style queries favour the right stakeholder over a passing mention."""
    return " ".join([r.stakeholder, r.stakeholder, r.category, r.category,
                     r.rule_reference, r.obligation, r.timeline, r.rule_2016_match or ""])


class SmartSearch:
    def __init__(self, records: List[Record]):
        self.records = list(records)
        self.vectorizer = TfidfVectorizer(analyzer=lambda t: _with_bigrams(analyze(t)), sublinear_tf=True)
        self.matrix = self.vectorizer.fit_transform(record_text(r) for r in self.records)
        self.vocab = {t for r in self.records for t in analyze(record_text(r))}

    def coverage(self, query: str) -> Tuple[float, List[str]]:
        """Share of the question's meaningful words that exist in the data (directly or via a
        synonym), plus the words that do not. A low share means the data cannot answer it,
        even when TF-IDF still returns a best-looking record."""
        words = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if w not in _STOP and w not in GENERIC]
        if not words:
            return 0.0, []
        missing = []
        for w in words:
            s = stem(w)
            known = s in self.vocab or (s in SYNONYMS and any(t in self.vocab for t in analyze(SYNONYMS[s])))
            if not known:
                missing.append(w)
        return round(1 - len(missing) / len(words), 2), missing

    def rank(self, query: str, limit: int = 5) -> List[Tuple[Record, float]]:
        """Return up to `limit` (record, score) pairs, best first; zero-score records are dropped."""
        query = (query or "").strip()
        if not query or not self.records:
            return []
        scores = cosine_similarity(self.vectorizer.transform([expand_query(query)]), self.matrix).ravel()
        order = scores.argsort()[::-1][:limit]
        return [(self.records[i], round(float(scores[i]), 4)) for i in order if scores[i] > 0]
