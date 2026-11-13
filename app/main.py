"""KachraCheck FastAPI service.

Run:  uvicorn app.main:app --reload      then open http://127.0.0.1:8000/docs
"""
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from app import records as rec

try:                                    # TF-IDF ranking (scikit-learn); plain keyword search if absent
    from app.smart_search import SmartSearch
except ImportError:                     # pragma: no cover
    SmartSearch = None

MIN_COVERAGE = 0.4

app = FastAPI(
    title="KachraCheck API",
    version="0.2.0",
    description="Stakeholder-wise duty lookup over the Solid Waste Management Rules, 2026.",
)

RECORDS = rec.load_records()
ENGINE = SmartSearch(RECORDS) if SmartSearch else None
QUESTIONS: list = []                    # in-memory log of POST /questions


class RecordOut(BaseModel):
    id: int
    rule_reference: str
    stakeholder: str
    category: str
    obligation: str
    timeline: str
    rules_version: str
    source_url: str
    rule_2016_match: Optional[str] = None


class SearchHit(BaseModel):
    score: Optional[float] = Field(None, description="TF-IDF cosine score (null for keyword fallback)")
    record: RecordOut


class SearchOut(BaseModel):
    query: str
    engine: str
    answerable: bool = Field(True, description="False when most of the question's words appear nowhere in the data")
    coverage: Optional[float] = None
    missing_terms: List[str] = []
    count: int
    results: List[SearchHit]


class QuestionIn(BaseModel):
    question: str = Field(..., min_length=3, max_length=500, examples=["Who must file an annual return?"])
    name: Optional[str] = Field(None, max_length=80)


class QuestionOut(BaseModel):
    id: int
    received_at: str
    name: Optional[str]
    question: str
    answerable: bool
    missing_terms: List[str]
    answers: List[SearchHit]
    note: str


def _search(q: str, limit: int) -> SearchOut:
    if not q.strip():
        raise HTTPException(status_code=422, detail="q must not be blank")
    coverage, missing = None, []
    if ENGINE:
        hits = [SearchHit(score=s, record=r.to_dict()) for r, s in ENGINE.rank(q, limit)]
        engine = "tfidf-cosine"
        coverage, missing = ENGINE.coverage(q)
    else:
        hits = [SearchHit(score=None, record=r.to_dict()) for r in rec.search(RECORDS, q)[:limit]]
        engine = "keyword"
    answerable = coverage is None or coverage >= MIN_COVERAGE
    return SearchOut(query=q, engine=engine, answerable=answerable, coverage=coverage,
                     missing_terms=missing, count=len(hits), results=hits)


@app.get("/health")
def health():
    return {"status": "ok", "records": len(RECORDS), "search_engine": "tfidf-cosine" if ENGINE else "keyword"}


@app.get("/records", response_model=List[RecordOut])
def list_records(limit: int = Query(10, ge=1, le=100), offset: int = Query(0, ge=0)):
    return [r.to_dict() for r in RECORDS[offset:offset + limit]]


@app.get("/records/{record_id}", response_model=RecordOut)
def get_record(record_id: int):
    record = rec.get_by_id(RECORDS, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Record {record_id} not found")
    return record.to_dict()


@app.get("/search", response_model=SearchOut)
def search(q: str = Query(..., min_length=1, description="Words to search for"),
           limit: int = Query(5, ge=1, le=50)):
    return _search(q, limit)


@app.post("/questions", response_model=QuestionOut, status_code=201)
def ask_question(payload: QuestionIn):
    result = _search(payload.question, 3)
    if not result.answerable:
        result.results = []
    entry = QuestionOut(
        id=len(QUESTIONS) + 1,
        received_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        name=payload.name,
        question=payload.question,
        answerable=result.answerable,
        missing_terms=result.missing_terms,
        answers=result.results,
        note=("Closest duty clauses shown; verify against the official gazette." if result.results
              else "The KachraCheck data has no clause about: " + ", ".join(result.missing_terms) + "."
              if not result.answerable else "No matching clause found. Try other words, e.g. 'annual return'."),
    )
    QUESTIONS.append(entry)
    return entry

from app.chat import router as chat_router  # Day 6
app.include_router(chat_router)
