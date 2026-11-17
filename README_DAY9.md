# Day 9 - agent tool, hand-written loop, LangGraph + approval, POST /agent

1. `python apply_day9.py`
2. `pip install langgraph`
3. `python tests/test_day9.py` (offline checks, no key needed)
4. `python -m app.agent_loop "Which bin does a bannana peel go in?"` (needs your key in .env)
5. `uvicorn app.main:app --reload`, then in /docs:
   - POST /agent {"question": "Where does an old CFL bulb go?"}  -> status "awaiting_approval" + thread_id
   - POST /agent/approve {"thread_id": "...", "approve": true}  -> status "done" + final answer
   - POST /agent again with the SAME thread_id and a follow-up question to see memory work
6. In data/waste_items.csv, replace the generic rule_reference text with the real clause numbers from your records.

If app/main.py has no `app = FastAPI()`, add manually:
    from app.agent_api import router as agent_router
    app.include_router(agent_router)
