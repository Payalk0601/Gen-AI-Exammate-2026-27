# Resume bullets: KachraCheck

## The three bullets

- Built **KachraCheck**, a retrieval-augmented assistant that answers questions about India's Solid Waste Management Rules 2026 with rule citations; parsed a 144-page gazette PDF into 222 clause records (20 curated) and answered 10 of 10 test questions from retrieved evidence.
- Designed a **tool-using agent** (hand-written loop, then rebuilt in LangGraph) with a fuzzy-matching waste-stream sorter, conversation memory and a human approval step, served through FastAPI and a Streamlit UI with citations, user feedback and a 2016-vs-2026 rule comparison.
<!-- BENCH-BULLET:START -->
- Hardened the API for production: logged latency and token use per request, added a TTL response cache, enforced input limits (413 and 422) and tested a prompt-injection attack with secret redaction, backed by an automated pytest suite.
<!-- BENCH-BULLET:END -->

## One-line version

KachraCheck: an AI assistant that explains India's SWM Rules 2026 with citations, a tool-using agent, and a 2016-vs-2026 rule comparison. Python, FastAPI, LangGraph, Streamlit.

## Skills to list

Python, FastAPI, retrieval-augmented generation, LLM tool use and agents (LangGraph), prompt engineering and evaluation, pytest and ruff, prompt-injection defence.

Only keep a bullet if you can explain every word in it.
