# Day 6 - LLM wrapper, /chat, prompts, prompt comparison

1. `python apply_day6.py` (wires /chat into app/main.py, updates requirements and .gitignore)
2. `copy .env.example .env` and paste your real Groq or Gemini key into `.env`
3. `pip install python-dotenv requests`
4. `uvicorn app.main:app --reload` then POST to /chat (or use /docs)
5. Put YOUR 10 questions in eval/questions.txt, run `python -m eval.run_compare`
6. Fill the "Better" column and observations in eval/prompt_compare.md by hand
7. `git status` must NOT list .env. Then commit and push.

If app/main.py has no `app = FastAPI()`, add manually:
    from app.chat import router as chat_router
    app.include_router(chat_router)
