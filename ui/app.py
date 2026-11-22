"""KachraCheck chat. Run the API first, then:   streamlit run ui/app.py

 - Ask mode   -> POST /ask    answers from the Rules with citations, or says "I don't know"
 - Agent mode -> POST /agent  sorts household items and searches the Rules; a guessed spelling asks you to confirm
 - Every answer has thumbs up / down (saved in data/feedback.db) and a "Compare with the 2016 Rules" switch that shows the
   old rule next to the new one with the changes highlighted.
"""
import os
import sys
import uuid
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ui import client, compare, feedback          # noqa: E402

DEFAULT_API = os.environ.get("KACHRACHECK_API", "http://127.0.0.1:8000")
SAMPLES = ["Who has to separate waste at home, and into which streams?",
           "What bin colours must my municipality use?",
           "Is my housing society a bulk waste generator and what must it do?",
           "By when must a processing facility file its annual return?",
           "What is the exact fine in rupees for a household that burns waste?"]
ITEM_SAMPLES = ["Where does a used battery go?", "batery", "Is a diaper wet or dry?"]

CSS = """
<style>
.del {background: rgba(220, 38, 38, .20); text-decoration: line-through; border-radius: 3px; padding: 0 2px;}
.add {background: rgba(22, 163, 74, .25); font-weight: 600; border-radius: 3px; padding: 0 2px;}
.cmp-box {border: 1px solid rgba(128, 128, 128, .40); border-radius: 8px; padding: .6rem .8rem; line-height: 1.7;}
</style>
"""
BADGES = {"changed": "🟠 changed", "unchanged": "🟢 same duty", "new": "🔵 new in 2026"}


@st.cache_data(show_spinner=False)
def load_reference():
    return compare.load_pairs(), compare.load_json(compare.PDF_ROWS_PATH), compare.load_json(compare.CURATED_PATH)


PAIRS, PDF_ROWS, CURATED = load_reference()


# ---------------------------------------------------------------- state and actions
def init_state():
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("thread_id", None)
    st.session_state.setdefault("pending", None)


def new_conversation():
    st.session_state.messages, st.session_state.thread_id, st.session_state.pending = [], None, None


def queue(text: str):
    st.session_state.queued = text


def rate(message_id: str, value: int):
    msg = next(m for m in st.session_state.messages if m["id"] == message_id)
    feedback.save_feedback(message_id, value, msg.get("question", ""), msg["content"], msg.get("mode", ""), msg.get("thread_id") or "")
    msg["rating"] = value


def add_answer(resp: dict, question: str, mode: str):
    st.session_state.messages.append({"id": uuid.uuid4().hex, "role": "assistant", "content": resp.get("answer", ""),
                                      "resp": {**resp, "question": question}, "question": question, "mode": mode,
                                      "thread_id": resp.get("thread_id"), "rating": 0})


def add_error(text: str):
    st.session_state.messages.append({"id": uuid.uuid4().hex, "role": "assistant", "content": text, "error": True})


def handle_response(resp: dict, question: str, mode: str):
    if resp.get("status") == "needs_approval":
        st.session_state.thread_id = resp["thread_id"]
        st.session_state.pending = {"thread_id": resp["thread_id"], "approval": resp["approval"], "question": question}
    else:
        if mode == "agent":
            st.session_state.thread_id = resp.get("thread_id")
        add_answer(resp, question, mode)


def send(prompt: str, mode: str, api: str, k: int):
    st.session_state.messages.append({"id": uuid.uuid4().hex, "role": "user", "content": prompt})
    try:
        with st.spinner("Looking in the Rules..."):
            resp = client.ask(api, prompt, k) if mode == "ask" else client.agent(api, prompt, st.session_state.thread_id)
        handle_response(resp, prompt, mode)
    except client.ApiError as err:
        add_error(f"⚠️ {err}")


def answer_approval(approved: bool, api: str):
    pending = st.session_state.pending
    st.session_state.pending = None
    try:
        resp = client.approve(api, pending["thread_id"], approved)
        handle_response(resp, pending["question"], "agent")
    except client.ApiError as err:
        add_error(f"⚠️ {err}")


# ---------------------------------------------------------------- rendering
def render_comparison(resp: dict):
    pairs = compare.pairs_for_response(resp, PAIRS)
    if not pairs:
        st.info("No 2016 comparison for this answer. It is not one of the 12 duties in my comparison table, "
                "or the question is outside the Rules.")
        return
    for p in pairs:
        st.markdown(f"**{p['topic']}** · {BADGES.get(p['status'], p['status'])}")
        old_html, new_html, _ = compare.word_diff(p["text_2016"], p["text_2026"])
        left, right = st.columns(2)
        left.markdown(f"**2016 · {p['rule_2016']}**")
        left.markdown(f'<div class="cmp-box">{old_html or "<em>No matching duty in the 2016 Rules.</em>"}</div>', unsafe_allow_html=True)
        right.markdown(f"**2026 · {p['rule_2026']}**")
        right.markdown(f'<div class="cmp-box">{new_html}</div>', unsafe_allow_html=True)
        st.markdown(f"**What changed:** {p['what_changed']}")
        text, label = compare.full_2026_text(p, PDF_ROWS, CURATED)
        if text:
            with st.expander(f"Full 2026 text ({p['rule_2026']})"):
                st.caption(label)
                st.write(text)
    st.caption("Red = only in 2016 · green = only in 2026. Both sides are plain-language summaries written in matching wording "
               "so the differences show. Check the gazette before relying on a line.")


def render_assistant(msg: dict):
    st.markdown(msg["content"])
    if msg.get("error"):
        return
    resp = msg["resp"]
    bits = [msg["mode"].upper()]
    if resp.get("planner"):
        bits.append(f"planner: {resp['planner']}")
    if resp.get("generator"):
        bits.append(f"generator: {resp['generator']}")
    if resp.get("reason") and resp["reason"] != "ok":
        bits.append(f"refused: {resp['reason']}")
    st.caption(" · ".join(bits))

    citations = resp.get("citations") or []
    if citations:
        with st.expander(f"Sources ({len(citations)})"):
            for c in citations:
                st.markdown(f"**[{c['n']}] {c['title']}** · {c['source']} · page {c['page']}")
                if c.get("text"):
                    st.caption(c["text"])
    if resp.get("steps"):
        with st.expander("What the agent did"):
            for s in resp["steps"]:
                st.markdown(f"{s['n']}. `{s['tool']}` {s['input']}")

    up, down, _ = st.columns([1, 1, 8])
    up.button("👍", key=f"up_{msg['id']}", on_click=rate, args=(msg["id"], 1),
              type="primary" if msg.get("rating") == 1 else "secondary")
    down.button("👎", key=f"down_{msg['id']}", on_click=rate, args=(msg["id"], -1),
                type="primary" if msg.get("rating") == -1 else "secondary")
    if st.toggle("Compare with the 2016 Rules", key=f"cmp_{msg['id']}"):
        render_comparison(resp)


# ---------------------------------------------------------------- the page
def main():
    st.set_page_config(page_title="KachraCheck", page_icon="♻️", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    init_state()

    with st.sidebar:
        st.title("♻️ KachraCheck")
        st.caption("Solid Waste Management Rules, 2026 · with the 2016 Rules one click away")
        mode_label = st.radio("Mode", ["Ask the Rules", "Agent (items + Rules)"], key="mode_label",
                              help="Ask answers from the Rules documents. Agent can also sort a household item into its stream.")
        mode = "ask" if mode_label.startswith("Ask") else "agent"
        api = st.text_input("API address", DEFAULT_API)
        k = st.slider("Sources to retrieve (k)", 1, 8, 4) if mode == "ask" else 4
        try:
            h = client.health(api)
            st.success(f"API online · {h.get('records', '?')} records · {h.get('search_engine', '')}")
        except client.ApiError as err:
            st.error(str(err))
        st.button("New conversation", on_click=new_conversation)
        st.divider()
        st.caption("Try one:")
        for i, q in enumerate(SAMPLES if mode == "ask" else ITEM_SAMPLES + SAMPLES[:2]):
            st.button(q, key=f"sample_{i}", on_click=queue, args=(q,), use_container_width=True)
        st.divider()
        c = feedback.counts()
        st.metric("Feedback saved", f"👍 {c['up']}   👎 {c['down']}")

    st.header("Ask about the Rules, or name a household item")
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            if msg["role"] == "user":
                st.markdown(msg["content"])
            else:
                render_assistant(msg)

    pending = st.session_state.pending
    if pending:
        with st.chat_message("assistant"):
            st.info(pending["approval"]["message"])
            yes, no, _ = st.columns([1, 1, 6])
            yes.button("Yes, that's right", on_click=answer_approval, args=(True, api), type="primary")
            no.button("No", on_click=answer_approval, args=(False, api))

    queued = st.session_state.pop("queued", None)
    prompt = st.chat_input("Ask about the SWM Rules 2026, or name an item (e.g. plastic bottle)", disabled=bool(pending)) or queued
    if prompt and not pending:
        send(prompt, mode, api, k)
        st.rerun()


main()
