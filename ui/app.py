"""KachraCheck chat UI (Streamlit).

Run from the repo root (backend must be running first):
    streamlit run ui/app.py

Features: chat via /agent, /ask or /chat, citations, thumbs up/down saved to
data/feedback.jsonl, and a per-answer 2016 vs 2026 toggle with the change highlighted.
"""
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
import api_client as api  # noqa: E402
import compare  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FEEDBACK = Path(os.getenv("KACHRACHECK_FEEDBACK", str(ROOT / "data" / "feedback.jsonl")))
DEFAULT_API = os.getenv("KACHRACHECK_API_URL", "http://127.0.0.1:8000")
SAMPLES = [
    "Which bin does a banana peel go in?",
    "Where should I throw an old CFL bulb?",
    "What must a bulk waste generator do?",
    "What happens if someone breaks the rules?",
]

st.set_page_config(page_title="KachraCheck", page_icon="♻️", layout="wide")
st.markdown(compare.CSS, unsafe_allow_html=True)


# ---------- state ----------
def init_state():
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("thread_id", uuid.uuid4().hex)
    st.session_state.setdefault("pending", None)


def new_chat():
    st.session_state.messages = []
    st.session_state.pending = None
    st.session_state.thread_id = uuid.uuid4().hex


@st.cache_data
def changes_data() -> dict:
    return compare.load_changes()


# ---------- feedback ----------
def save_feedback(idx: int, rating: str):
    m = st.session_state.messages[idx]
    m["rating"] = rating
    FEEDBACK.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rating": rating,
        "question": m.get("question", ""),
        "answer": m["content"],
        "endpoint": m.get("endpoint", ""),
        "thread_id": m.get("thread_id", ""),
    }
    with open(FEEDBACK, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def feedback_counts() -> tuple[int, int]:
    up = down = 0
    if FEEDBACK.exists():
        for line in FEEDBACK.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line).get("rating")
            except ValueError:
                continue
            up += r == "up"
            down += r == "down"
    return up, down


# ---------- backend calls ----------
def add_answer(question: str, result: dict, endpoint: str):
    st.session_state.messages.append({
        "role": "assistant",
        "content": result["answer"],
        "question": question,
        "confidence": result["confidence"],
        "follow_up": result["follow_up"],
        "citations": result["citations"],
        "tools": result["tools"],
        "endpoint": endpoint,
        "thread_id": result.get("thread_id") or st.session_state.thread_id,
        "rating": None,
    })


def ask_backend(question: str, base: str, endpoint: str, need_approval: bool, provider: str | None):
    try:
        data = api.call_backend(base, endpoint, question, st.session_state.thread_id, need_approval, provider)
    except api.BackendError as e:
        st.session_state.messages.append({"role": "assistant", "content": f"⚠️ {e}", "question": question, "error": True})
        return
    result = api.normalise(data)
    if result["status"] == "awaiting_approval":
        st.session_state.pending = {**result, "question": question, "endpoint": endpoint}
    else:
        add_answer(question, result, endpoint)


def resolve_pending(approved: bool, base: str):
    p = st.session_state.pending
    try:
        data = api.approve(base, p["thread_id"], approved)
    except api.BackendError as e:
        st.session_state.messages.append({"role": "assistant", "content": f"⚠️ {e}", "error": True})
        st.session_state.pending = None
        return
    add_answer(p["question"], api.normalise(data), p["endpoint"])
    st.session_state.pending = None


# ---------- 2016 vs 2026 ----------
def render_comparison(idx: int, text: str):
    data = changes_data()
    entries = data["changes"]
    matches = compare.match_changes(text, entries)
    if not matches:
        st.info("No 2016 rule recorded for this exact topic. Pick one to compare:")
        topic = st.selectbox("Topic", [e["topic"] for e in entries], key=f"topic_{idx}")
        matches = [e for e in entries if e["topic"] == topic]
    st.caption("🟥 struck-through = old wording that changed or was dropped · 🟩 bold = new wording in 2026")
    for e in matches:
        old_html, new_html = compare.diff_html(e["rule_2016"], e["rule_2026"])
        st.markdown(f"**{e['topic']}**")
        c1, c2 = st.columns(2)
        ref16 = f" · {e['ref_2016']}" if e.get("ref_2016") else ""
        ref26 = f" · {e['ref_2026']}" if e.get("ref_2026") else ""
        c1.markdown(f"**SWM Rules 2016**{ref16}")
        c1.markdown(f'<div class="rule-box">{old_html}</div>', unsafe_allow_html=True)
        c2.markdown(f"**SWM Rules 2026**{ref26}")
        c2.markdown(f'<div class="rule-box">{new_html}</div>', unsafe_allow_html=True)
        st.markdown(f"**What changed:** {e['change_summary']}")
        if "2016" in e.get("verify_against_pdf", []):
            st.caption("⚠️ Check the 2016 wording against the official PDF.")
    st.caption(f"Sources: {data['sources']['2016']}; {data['sources']['2026']}")


# ---------- rendering ----------
def render_message(i: int, m: dict):
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        if m["role"] != "assistant" or m.get("error"):
            return
        if m.get("confidence"):
            st.caption(f"Confidence: **{m['confidence']}**" + (f" · tools: {', '.join(m['tools'])}" if m.get("tools") else ""))
        if m.get("follow_up"):
            st.caption(f"💬 {m['follow_up']}")
        cites = m.get("citations") or []
        with st.expander(f"📚 Citations ({len(cites)})"):
            if not cites:
                st.write("No citations were returned by this endpoint.")
            for c in cites:
                label = f"**{c['label']}**: " if c.get("label") else ""
                st.markdown(f"- {label}{c['text']}")
        a, b, _ = st.columns([1, 1, 6])
        a.button("👍", key=f"up_{i}", on_click=save_feedback, args=(i, "up"), disabled=m.get("rating") is not None)
        b.button("👎", key=f"down_{i}", on_click=save_feedback, args=(i, "down"), disabled=m.get("rating") is not None)
        if m.get("rating"):
            st.caption(f"Feedback saved ({m['rating']}).")
        if st.toggle("Compare with 2016 rules", key=f"cmp_{i}"):
            render_comparison(i, f"{m.get('question', '')} {m['content']}")


# ---------- page ----------
init_state()

with st.sidebar:
    st.header("Settings")
    base = st.text_input("Backend URL", DEFAULT_API)
    endpoint = st.radio("Endpoint", ["/agent", "/ask", "/chat"], help="/agent uses tools + memory; /ask is the Week 1 search; /chat is the Day 6 LLM answer.")
    need_approval = st.checkbox("Require human approval (/agent)", value=False) if endpoint == "/agent" else False
    provider = st.selectbox("LLM provider", ["server default", "groq", "gemini"]) if endpoint != "/ask" else "server default"
    provider = None if provider == "server default" else provider
    st.button("🗑️ New chat", on_click=new_chat)
    up, down = feedback_counts()
    st.caption(f"Feedback saved: 👍 {up} · 👎 {down}")
    st.divider()
    st.caption("Try a sample:")
    for q in SAMPLES:
        if st.button(q, key=f"s_{q}"):
            st.session_state.queued = q

st.title("♻️ KachraCheck")
st.caption("Duty checker for India's Solid Waste Management Rules 2026. Guidance only, not legal advice.")

for i, m in enumerate(st.session_state.messages):
    render_message(i, m)

pending = st.session_state.pending
if pending:
    with st.chat_message("assistant"):
        st.warning("This draft answer is waiting for human approval.")
        st.markdown(pending["answer"])
        ok, no, _ = st.columns([1, 1, 6])
        ok.button("✅ Approve", on_click=resolve_pending, args=(True, base))
        no.button("❌ Reject", on_click=resolve_pending, args=(False, base))

prompt = st.chat_input("Ask about a waste rule or where an item goes...", disabled=bool(pending))
prompt = prompt or st.session_state.pop("queued", None)
if prompt and not pending:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.spinner("Checking the rules..."):
        ask_backend(prompt, base, endpoint, need_approval, provider)
    st.rerun()
