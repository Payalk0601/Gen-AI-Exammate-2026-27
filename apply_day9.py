"""One-time helper: wires /agent into app/main.py and adds langgraph to requirements.txt.
Run from the repo root after unzipping:  python apply_day9.py   (safe to run twice)"""
from pathlib import Path

main = Path("app/main.py")
if main.exists():
    text = main.read_text(encoding="utf-8")
    if "agent_router" not in text:
        text = text.rstrip("\n") + "\n\nfrom app.agent_api import router as agent_router  # Day 9\napp.include_router(agent_router)\n"
        main.write_text(text, encoding="utf-8")
        print("updated app/main.py: /agent router added")
else:
    print("app/main.py not found: add the two lines yourself (see README_DAY9.md)")

req = Path("requirements.txt")
text = req.read_text(encoding="utf-8") if req.exists() else ""
if "langgraph" not in text.lower():
    req.write_text(text.rstrip("\n") + ("\n" if text else "") + "langgraph\n", encoding="utf-8")
    print("updated requirements.txt: langgraph")
