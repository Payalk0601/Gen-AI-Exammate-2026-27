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

**Author:** Payal, B.Tech (AI & ML), Sanjivani University, Kopargaon · Gen AI Exammate 2026-27

## Six questions KachraCheck should answer
1. Who has to separate waste at home, and into which streams?
2. Is my housing society a bulk waste generator and what must it do?
3. By when must a processing facility file its annual return?
4. What bin colours must my municipality use?
5. How did the 2026 rules change sanitary waste wrapping compared with 2016?
6. What is the exact fine in rupees for a household that burns waste? *(my data cannot answer this one, and the API says so)*

All ten test questions: [docs/user_questions.md](docs/user_questions.md) · How LLMs work: [docs/how_llms_work.md](docs/how_llms_work.md) · Checkpoint 1: [docs/checkpoint-1.md](docs/checkpoint-1.md)

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
data/raw/                  # downloaded source documents (git-ignored)
app/models.py   records.py   cli.py   ingest.py   fetch.py
app/main.py                # FastAPI service
app/smart_search.py        # TF-IDF + cosine ranking (stemming + plain-language synonyms)
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

## Limits
Hand-curated from the gazette text; verify against the official PDF before relying on any clause.
This is a study project, not legal advice.
