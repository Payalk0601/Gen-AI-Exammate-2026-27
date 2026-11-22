---
title: KachraCheck
sdk: docker
app_port: 8000
---

![CI](https://github.com/Payalk0601/Gen-AI-Exammate-2026-27/actions/workflows/ci.yml/badge.svg)

# KachraCheck

**A stakeholder-wise duty checker for India's Solid Waste Management Rules, 2026.**
Pick who you are (household, bulk generator, municipal body, regulator...) and see exactly what the
Rules expect from you, by when, and how it differs from the 2016 Rules.

| | |
|---|---|
| **Product** | REST API and command-line lookup over a structured dataset of duty clauses |
| **User** | A household or bulk waste generator, a municipal or panchayat officer, a facility operator, a student or compliance analyst |
| **Problem** | The 2026 Rules replace the 2016 Rules, run to 40+ pages, and split duties across 15+ stakeholders (generators, bulk generators, urban and rural local bodies, state departments, SPCBs, facility operators). Most people cannot tell which clause binds them or what changed. |
| **Data source** | Solid Waste Management Rules, 2026 (Gazette S.O. 388(E), 27 Jan 2026, in force 1 April 2026), published by CPCB: <https://swmp.cpcb.gov.in/img/cpcb_doc/solid-waste-management-rules-2026.pdf>. 2016 clause mapping comes from the SWM Rules 2016 toolkit (MoEFCC/MoHUA/CPCB/NPC). |

**Author:** Payal, B.Tech (AI & ML), Sanjivani University, Kopargaon Â· Gen AI Exammate 2026-27

## Six questions KachraCheck should answer
1. Who has to separate waste at home, and into which streams?
2. Is my housing society a bulk waste generator and what must it do?
3. By when must a processing facility file its annual return?
4. What bin colours must my municipality use?
5. How did the 2026 rules change sanitary waste wrapping compared with 2016?
6. What is the exact fine in rupees for a household that burns waste? *(my data cannot answer this one, and the API says so)*

All ten test questions: [docs/user_questions.md](docs/user_questions.md) Â· How LLMs work: [docs/how_llms_work.md](docs/how_llms_work.md) Â· Checkpoint 1: [docs/checkpoint-1.md](docs/checkpoint-1.md) Â· Data pipeline results: [docs/data_pipeline.md](docs/data_pipeline.md)

## Record fields
`id, rule_reference, stakeholder, category, obligation, timeline, rules_version, rule_2016_match, source_url`

`rule_2016_match` is `null` where no direct 2016 clause was identified (for example portal registration and
bulk-generator duties are new in 2026). Clause letters follow the Devanagari lettering printed in the gazette PDF.

## How to run
```bash
git clone https://github.com/Payalk0601/Gen-AI-Exammate-2026-27.git && cd Gen-AI-Exammate-2026-27
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

uvicorn app.main:app --reload          # API on http://127.0.0.1:8000  (interactive docs: /docs)
```
| Endpoint | What it does |
|---|---|
| `GET /health` | status, record count, search engine in use |
| `GET /records?limit=10&offset=0` | list records (limit 1-100) |
| `GET /records/{id}` | one record, `404` if the id does not exist |
| `GET /search?q=annual return&limit=5` | TF-IDF + cosine ranked records with scores |
| `POST /questions` | body `{"question": "...", "name": "optional"}` returns the 3 closest duty clauses (`201`) |

```bash
curl "http://127.0.0.1:8000/search?q=bin%20colours%20for%20municipalities"
curl -X POST http://127.0.0.1:8000/questions -H "Content-Type: application/json" \
     -d '{"question": "Who must file an annual return?", "name": "Payal"}'
```
Other commands:
```bash
python analysis/explore.py                 # 3 facts about the records (pandas)
python analysis/check_questions.py         # scores the 10 user questions
python -m unittest discover tests          # API tests
python day01_intro.py && python day01_menu.py
python -m app.cli search "30 June"         # command-line lookup
python -m app.fetch && python -m app.ingest   # download sources, rebuild data/records.json
```

## Layout
```
README.md
day01_intro.py          # prints the project card, asks name + question
day01_menu.py           # while-loop menu incl. bulk-generator rule check
s1_records_demo.py      # print all / search / count per category (plain dicts)
data/sample_records.json   # 20 hand-curated duty records
data/records.json          # cleaned output of app/ingest.py
data/records_from_pdf.json # 222 clause rows built by app/ingest.py from the PDF
data/raw/                  # downloaded source documents + manifest (committed as evidence)
app/models.py   records.py   cli.py   ingest.py   fetch.py
app/main.py                # FastAPI service
app/tools.py               # waste_stream_sorter (CSV + difflib) and search_rules
app/agent_loop.py          # hand-written agent loop
app/graph.py               # the same agent in LangGraph: memory + one approval step
ui/                        # Streamlit chat: app.py, compare.py (2016 vs 2026), feedback.py, preflight.py
data/waste_items.csv       # 60 household items -> wet / dry / sanitary / special care
data/rule_changes.json     # 12 duties: the 2016 rule next to the 2026 rule
app/rag.py                 # RAG: retrieve chunks, cite them, or say "I don't know"
app/llm.py                 # Groq / Gemini wrapper (keys in .env, never committed)
app/smart_search.py        # TF-IDF + cosine ranking (stemming + plain-language synonyms)
app/chunking.py            # PDF -> chunks that keep source, page and title
app/embed.py               # embedders (MiniLM / offline hash), in-memory semantic search, eval report
app/vectorstore.py         # persistent Chroma collection of all chunks
eval/eval_set.json        # 15 evaluation questions (2 must be refused)
eval/run_eval.py           # compares chunk size / top-k configurations, writes the table below
eval/search_results.md     # hits of the 10 questions (written by `python -m app.embed --eval`)
analysis/explore.py        # pandas facts
tests/test_api.py
```

## Run
```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python day01_intro.py
python day01_menu.py
python s1_records_demo.py

python -m app.cli list
python -m app.cli search "30 June"
python -m app.cli count --by stakeholder
python -m app.cli show 14

python -m app.fetch                  # download source documents into data/raw/
python -m app.ingest                 # clean -> data/records.json (+ PDF cross-check if the PDF is present)
```

## Data pipeline
```
python -m app.fetch      # downloads the SWM Rules 2026 PDF (+ 3 other documents) into data/raw/, writes data/raw/manifest.json
python -m app.ingest     # PDF -> English pages -> rules -> clauses -> data/records_from_pdf.json
python -m app.ingest --merge   # optional: also append those rows to data/records.json
```
| File | What it is |
|---|---|
| `data/raw/solid-waste-management-rules-2026.pdf` | the source document (committed as evidence) |
| `data/raw/manifest.json` | URL, size, SHA-256 and time of every download |
| `data/raw/rule_index.json` | rule number and heading found in the PDF |
| `data/records_from_pdf.json` | one row per clause, built by `app/ingest.py` from the PDF |
| `data/records.json` | 20 hand-checked records (English paraphrase) that the API serves |

PDF rows hold the clause text as printed and a timeline picked out by pattern matching, so they are rougher than the
20 curated records. They are kept separate on purpose: merging them changes search results, so run
`python analysis/check_questions.py` after `--merge`.

## Semantic search
```
python -m app.chunking                   # what gets indexed: chunks per PDF, with page and title
python -m app.embed --eval               # run the 10 questions -> eval/search_results.md
python -m app.vectorstore --rebuild      # index every chunk into the persistent Chroma collection (data/chroma/)
uvicorn app.main:app --reload            # then: GET /search/semantic?q=bin colours for municipalities&k=5
```
| Module | What it does |
|---|---|
| `app/chunking.py` | reads `data/raw/*.pdf`, keeps only English pages, cuts each page at rule headings, packs sentences into chunks of up to 800 characters with one sentence of overlap. Every chunk keeps `source`, `page` and `title` (for example `Rule 5: Duties of waste generator`). |
| `app/embed.py` | turns text into vectors with all-MiniLM-L6-v2 (default) and searches them by cosine similarity. `KACHRACHECK_EMBEDDER=hash` switches to an offline spelling-based embedder used only by the tests. |
| `app/vectorstore.py` | stores chunk text, vector and metadata in a persistent Chroma collection; re-indexing replaces chunks instead of duplicating them, and an index built with one embedder cannot be queried with another. |

The first run downloads the MiniLM model (about 80 MB) into `data/model_cache/` (git-ignored; change it with `KACHRACHECK_MODEL_DIR`) and needs internet. If Chroma has trouble with a path that contains
non-English folder names or a OneDrive folder, store the index elsewhere: `set KACHRACHECK_CHROMA_DIR=C:\kachracheck_chroma`.

## Ask a question (RAG)
`POST /ask` retrieves the best chunks of the PDFs and answers **only from them**, with citations (rule title, file, page).
If the sources do not contain the answer it says `I don't know`.
```bash
curl -X POST http://127.0.0.1:8000/ask -H "Content-Type: application/json" \
     -d '{"question": "What bin colours must my municipality use?", "k": 4}'
```
```json
{ "answered": true, "reason": "ok",
  "answer": "Local bodies shall paint public bins green for wet waste and blue for dry waste ... [1]",
  "citations": [ { "n": 1, "title": "Rule 39: ...", "source": "solid-waste-management-rules-2026.pdf", "page": 30 } ] }
```
When it refuses, `reason` says why: `low_similarity`, `no_amount_in_sources` (the question asks for a fine or price and no
amount appears in the sources), `low_coverage` (the question's words appear nowhere in the sources), `model_said_unknown`, `no_citation`.

Two answer modes, set with `KACHRACHECK_GENERATOR`:
- `extractive`: no key needed. The answer is the best matching sentence copied from each of the top chunks.
- `llm`: Groq or Gemini writes the answer and must cite `[1]`, `[2]`. Copy `.env.example` to `.env`, add a key, and keep `.env` out of Git.
- `auto` (default): `llm` when a key exists, otherwise `extractive`. If the provider fails, it falls back to `extractive`.

A similarity score alone cannot find unanswerable questions: "What is the exact fine in rupees for a household that burns
waste?" scored higher than some correct questions. That is why the refusal checks look at what the question asks for.

## RAG evaluation
`python eval/run_eval.py --write-readme` runs the 15 questions in `eval/eval_set.json` through two configurations (chunk size and
top-k) and writes the table below. A question counts as correct when an answerable question is answered **and** cites an expected rule,
or when a must-refuse question gets "I don't know". Per-question detail: `eval/eval_results.md`.

<!-- eval-table:start -->
_Not run yet. Run `python eval/run_eval.py --write-readme`._
<!-- eval-table:end -->

## Agent: item sorter + Rules search
The agent has two tools. `waste_stream_sorter` looks an item up in `data/waste_items.csv` (60 hand-built items, with aliases) and says
which of the four 2026 streams it belongs to (wet, dry, sanitary, special care), with a handling note and the rule reference. It
tolerates spelling mistakes with `difflib`. `search_rules` is the RAG search above.

| File | What it does |
|---|---|
| `app/tools.py` | the two tools and a `ToolBox` that never raises (a failing tool comes back as `{"error": ...}`) |
| `app/agent_loop.py` | hand-written loop: planner picks a tool, the loop runs it, reads the result, repeats (at most 4 steps) |
| `app/graph.py` | the same agent as a LangGraph graph, with **memory** (last item and stream per `thread_id`) and **one approval step** |

The planner only chooses tools (`KACHRACHECK_PLANNER=rules|llm|auto`). The reply is built from the tool results, so the stream
comes from the table and the rule text from the cited chunks. Each item row says whether the Rules name it
(`basis`) or whether it is my reading of the stream definitions, and the answer carries that caveat.

`POST /agent` keeps a conversation with a `thread_id`. When the table had to guess a spelling, the graph pauses:
```bash
curl -X POST http://127.0.0.1:8000/agent -H "Content-Type: application/json" -d '{"message": "batery"}'
# {"status": "needs_approval", "thread_id": "ab12...", "approval": {"message": "I read 'batery' as 'battery' (special care stream). Is that what you meant?"}}
curl -X POST http://127.0.0.1:8000/agent -H "Content-Type: application/json" -d '{"thread_id": "ab12...", "approve": true}'
```
`GET /agent/{thread_id}` shows what the agent remembers.

## Chat UI
```bash
uvicorn app.main:app            # terminal 1: the API
streamlit run ui/app.py         # terminal 2: the chat on http://localhost:8501
python ui/preflight.py          # before a demo: 8 checks on the whole stack
```
<!-- screenshot
![Chat with the 2016 vs 2026 toggle](docs/img/ui_toggle.png)
-->
- **Two modes:** *Ask the Rules* (`/ask`) and *Agent* (`/agent`, with the approval step as Yes / No buttons).
- **Citations:** every answer lists its sources with rule title, file and page.
- **Thumbs up / down:** saved in `data/feedback.db` (one row per answer, git-ignored).
- **2016 vs 2026 toggle:** every answer can flip to show the old rule next to the new rule, with removed words in red (2016) and
  added words in green (2026), a one-line *what changed*, and the full 2026 clause. It covers 12 duties; an answer outside them
  says so. Both sides are plain-language summaries in matching wording so the highlights show real differences; check the gazette
  before relying on a line.

Checkpoint 2 demo script: [docs/checkpoint-2.md](docs/checkpoint-2.md)

## Limits
Hand-curated from the gazette text; verify against the official PDF before relying on any clause.
This is a study project, not legal advice.

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




**Live demo:** https://payalk06-kachracheck.hf.space
**Health check:** https://payalk06-kachracheck.hf.space/health






