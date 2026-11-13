"""One-time helper: wires /chat into app/main.py and updates requirements/.gitignore.
Run from the repo root after unzipping:  python apply_day6.py
Safe to run twice."""
from pathlib import Path


def append_once(path, line):
    p = Path(path)
    text = p.read_text(encoding="utf-8") if p.exists() else ""
    if line not in text.splitlines():
        p.write_text(text.rstrip("\n") + ("\n" if text else "") + line + "\n", encoding="utf-8")
        print(f"updated {path}: {line}")


main = Path("app/main.py")
if main.exists():
    text = main.read_text(encoding="utf-8")
    if "chat_router" not in text:
        text = text.rstrip("\n") + "\n\nfrom app.chat import router as chat_router  # Day 6\napp.include_router(chat_router)\n"
        main.write_text(text, encoding="utf-8")
        print("updated app/main.py: /chat router added")
else:
    print("app/main.py not found: add the two lines yourself (see README_DAY6.md)")

append_once("requirements.txt", "python-dotenv")
append_once("requirements.txt", "requests")
append_once(".gitignore", ".env")
