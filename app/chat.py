"""POST /chat: answers a question about SWM Rules 2026 using retrieved records + an LLM."""
import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.llm import LLMError, generate

ROOT = Path(__file__).resolve().parent.parent
PROMPTS = ROOT / "prompts"
RECORDS = ROOT / "data" / "records.json"
VERSIONS = {"v1": "task_v1_direct.md", "v2": "task_v2_stepwise.md"}
STOP = {"the", "and", "for", "what", "does", "how", "who", "are", "can", "must", "should", "under", "with", "this", "that"}

router = APIRouter()


class ChatRequest(BaseModel):
    question: str = Field(min_length=3)
    prompt_version: str = "v2"
    provider: str | None = None


class ChatResponse(BaseModel):
    answer: str
    confidence: str
    follow_up: str


def _load_records() -> list:
    data = json.loads(RECORDS.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        for key in ("records", "data", "items"):
            if key in data and isinstance(data[key], list):
                return data[key]
        return [data]
    return data


def retrieve(question: str, k: int = 4) -> list:
    """Simple keyword-overlap retrieval, works with any record field names."""
    words = {w for w in re.findall(r"[a-z0-9]+", question.lower()) if len(w) > 2 and w not in STOP}
    scored = []
    for rec in _load_records():
        text = json.dumps(rec, ensure_ascii=False).lower()
        score = sum(1 for w in words if w in text)
        if score:
            scored.append((score, rec))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:k]]


def parse_output(raw: str) -> dict:
    """Pull a clean {answer, confidence, follow_up} dict out of model text."""
    raw = re.sub(r"```(?:json)?", "", raw).strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in model output")
    obj = json.loads(raw[start : end + 1])
    conf = str(obj.get("confidence", "low")).lower()
    return {
        "answer": str(obj.get("answer", "")).strip(),
        "confidence": conf if conf in ("high", "medium", "low") else "low",
        "follow_up": str(obj.get("follow_up", "")).strip(),
    }


def answer_question(question: str, version: str = "v2", provider: str | None = None) -> dict:
    if version not in VERSIONS:
        raise ValueError(f"prompt_version must be one of {list(VERSIONS)}")
    system = (PROMPTS / "system.md").read_text(encoding="utf-8")
    task = (PROMPTS / VERSIONS[version]).read_text(encoding="utf-8")
    context = json.dumps(retrieve(question), ensure_ascii=False, indent=1)
    user = task.replace("{context}", context).replace("{question}", question)
    return parse_output(generate(system, user, provider))


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    try:
        return answer_question(req.question, req.prompt_version, req.provider)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LLMError as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not process model output: {e}")
