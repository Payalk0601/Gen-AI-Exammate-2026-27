"""POST /agent (ask) and POST /agent/approve (human approval step)."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import graph
from app.llm import LLMError

router = APIRouter()


class AgentRequest(BaseModel):
    question: str = Field(min_length=3)
    thread_id: str | None = None  # reuse it to keep memory across questions
    require_approval: bool = True
    provider: str | None = None


class ApprovalRequest(BaseModel):
    thread_id: str
    approve: bool
    note: str = ""


@router.post("/agent")
def agent(req: AgentRequest):
    try:
        return graph.ask(req.question, req.thread_id, req.require_approval, req.provider)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LLMError as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent failed: {e}")


@router.post("/agent/approve")
def agent_approve(req: ApprovalRequest):
    try:
        return graph.approve(req.thread_id, req.approve, req.note)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LLMError as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Approval failed: {e}")
