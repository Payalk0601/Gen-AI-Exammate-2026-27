"""One-time helper for Day 11. Run from the repo root:  python apply_day11.py   (safe to run twice)
Adds the README sections, .gitignore lines and the missing requirements."""
from pathlib import Path

README_SECTION = """
## Run with Docker

You need Docker Desktop (or Docker Engine with the compose plugin).

1. Copy the example settings and add your key:
   ```
   copy .env.example .env      # Windows (use cp on Mac/Linux)
   ```
   Open `.env` and put your Groq or Gemini key in it. `.env` is never committed or copied into the image.
2. Build and start the API and the UI:
   ```
   docker compose up --build
   ```
3. Open the apps:
   - API docs: http://localhost:8000/docs
   - Health check: http://localhost:8000/health
   - Chat UI: http://localhost:8501
4. Stop everything with `Ctrl+C`, then `docker compose down`.

The `api` and `ui` services use the same image. The UI waits until the API health check passes, and it talks to the API at `http://api:8000` inside the Docker network. Thumbs up/down feedback is kept in a Docker volume called `feedback`.

## Run tests and lint

```
pip install -r requirements-dev.txt
pytest
ruff check .
```
"""

readme = Path("README.md")
text = readme.read_text(encoding="utf-8") if readme.exists() else "# KachraCheck\n"
if "## Run with Docker" not in text:
    readme.write_text(text.rstrip("\n") + "\n" + README_SECTION, encoding="utf-8")
    print("README.md: added 'Run with Docker' and 'Run tests and lint'")

gitignore = Path(".gitignore")
existing = gitignore.read_text(encoding="utf-8").splitlines() if gitignore.exists() else []
add = [x for x in (".pytest_cache/", ".ruff_cache/", "__pycache__/") if x not in existing]
if add:
    gitignore.write_text("\n".join(existing + add) + "\n", encoding="utf-8")
    print(".gitignore: added", ", ".join(add))

req = Path("requirements.txt")
have = {line.split("==")[0].strip().lower() for line in req.read_text(encoding="utf-8").splitlines()} if req.exists() else set()
missing = [p for p in ("fastapi", "uvicorn", "requests", "python-dotenv", "langgraph", "streamlit") if p not in have]
if missing:
    with open(req, "a", encoding="utf-8") as f:
        f.write("\n".join(missing) + "\n")
    print("requirements.txt: added", ", ".join(missing))
