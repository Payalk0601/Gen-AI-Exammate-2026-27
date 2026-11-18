"""Thumbs up / down on answers, saved in a small SQLite file (data/feedback.db, git-ignored)."""
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def db_path() -> Path:
    return Path(os.environ.get("KACHRACHECK_FEEDBACK_DB") or ROOT / "data" / "feedback.db")


def _connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("""CREATE TABLE IF NOT EXISTS feedback (
        message_id TEXT PRIMARY KEY, ts TEXT NOT NULL, mode TEXT, thread_id TEXT,
        question TEXT, answer TEXT, rating INTEGER NOT NULL CHECK (rating IN (-1, 1)))""")
    return con


def save_feedback(message_id: str, rating: int, question: str = "", answer: str = "", mode: str = "", thread_id: str = "") -> None:
    """One row per answer: pressing the other thumb replaces the earlier rating."""
    if rating not in (-1, 1):
        raise ValueError("rating must be 1 (thumbs up) or -1 (thumbs down)")
    with _connect() as con:
        con.execute("INSERT OR REPLACE INTO feedback VALUES (?,?,?,?,?,?,?)",
                    (message_id, datetime.now(timezone.utc).isoformat(timespec="seconds"), mode, thread_id, question, answer, rating))


def counts() -> dict:
    with _connect() as con:
        up, down = con.execute("SELECT COALESCE(SUM(rating = 1), 0), COALESCE(SUM(rating = -1), 0) FROM feedback").fetchone()
    return {"up": int(up), "down": int(down)}


def recent(limit: int = 20) -> list:
    with _connect() as con:
        rows = con.execute("SELECT ts, mode, question, rating FROM feedback ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
    return [{"ts": r[0], "mode": r[1], "question": r[2], "rating": r[3]} for r in rows]
