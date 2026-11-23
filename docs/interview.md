# KachraCheck: interview notes

How to use this file: read the pitch aloud twice, then answer each question out loud without looking. Every claim below can be shown in the repo (see "Prove it" at the end). If the code does not do something a sentence says, change the sentence, not the truth.

## 60-second pitch
KachraCheck answers one question: "what does the law require of me?" for India's Solid Waste Management Rules 2026.

The 2026 rules replaced the 2016 rules on 1 April 2026. They run to a 144-page gazette and spread duties across more than 15 kinds of stakeholder, so most people cannot tell which clause applies to them or what changed.

I turned the gazette into clause records. You ask a question, and it retrieves the matching clauses, answers in plain language and shows citations with rule title and page. An agent also sorts household items into the four 2026 streams and remembers the conversation.

My favourite feature is the 2016 vs 2026 toggle: any answer flips to show the old rule next to the new one, with the changed words highlighted, and the two versions are never mixed.

It is FastAPI, Streamlit, tests, CI and Docker, and I measured its latency, caching and injection defences.

(About 150 words, roughly 60 seconds at a normal speaking pace. Time yourself.)

## My hardest problem: two versions of the same law

**Situation.** The 2026 rules supersede the 2016 rules, but the CPHEEO manual (2016) and most web content still quote 2016 clauses. A system that mixes the two will confidently give a duty that no longer applies.

**Task.** Tag every chunk with the rules version it came from, prefer 2026, and show differences between versions without ever blending them.

**What I did.**
1. Made the version a field on every record and chunk, set at ingest from which document it came from, never guessed from the text.
2. Made 2026 the default in retrieval; 2016 appears only when the user asks to compare.
3. Made every citation carry its source and page, and told the model never to combine clauses from two versions in one sentence.
4. Built the 2016 vs 2026 toggle: a side-by-side view with a word-level diff, so the reader sees exactly which words changed (for example "three streams" became "four streams").
5. When there is no 2016 equivalent for a topic, the toggle says so instead of inventing one. A test covers that case.

**Result.** Every answer says which version it uses, and the comparison is explicit. The limit I am honest about: the 2016 side is a short summary per topic, not a clause-by-clause copy of the manual.

**What I learned.** For legal text, provenance (which document, which version, which page) is a feature, not metadata. A cautious "I could not find a 2016 equivalent" beats a smooth answer that blends two laws.

## Ten likely questions

**1. Walk me through the architecture.**
A PDF pipeline (fetch, ingest) turns the gazette into clause records. A FastAPI service retrieves clauses with TF-IDF ranking and answers through a language model, with citations. A LangGraph agent can call two tools, a rule search and a waste-stream sorter (CSV plus fuzzy spelling matching), keeps memory per conversation and has a human approval step. A Streamlit UI shows citations, collects thumbs up/down and has the 2016 vs 2026 toggle. Middleware logs latency, caches answers, limits input and redacts leaked keys.

**2. What was the hardest problem?**
The two-versions problem above. Give the 30-second version: tag every chunk with its version, prefer 2026, never mix, show differences side by side.

**3. How do you stop the model making things up?**
It may only use retrieved records, and every answer shows its citations so a reader can check it. There is a minimum coverage threshold in `app/main.py`, so weak retrieval is treated as "not found" instead of guessed. Answers carry a confidence label, and the tool says when it does not know. I also checked that all 10 of my test questions can be answered from the retrieved evidence.

**4. Why TF-IDF and not embeddings?**
The corpus is small (20 curated records, 222 clause rows) and legal language is keyword-heavy, so TF-IDF was a fast, explainable baseline I could debug by reading scores. The repo also has chunking and embedding code, so the next step is to compare both on my 10 questions and keep whichever wins. I would not claim embeddings are better without measuring.

**5. How did you evaluate quality?**
Three ways: a 10-question answerability check against the records, a prompt comparison (version 1 direct vs version 2 step-by-step) in `eval/prompt_compare.md`, and thumbs up/down saved from the UI. It is a small evaluation, and I say so. The next step is a larger labelled set.

**6. How does the agent work, and why LangGraph?**
I first wrote the loop by hand: ask the model for a tool call or a final answer, run the tool, repeat, with a step limit. Then I rebuilt it in LangGraph to get memory per thread and an approval step that pauses the run until a human approves. The hand-written version taught me what the framework does for me.

**7. How do you handle security and prompt injection?**
Three layers. The prompt treats the question and records as data, never as instructions. The middleware flags known attack phrases and can block them. Any API key that appears in a response is replaced with "[redacted]". A test simulates a model that obeys the attack and leaks a key. In my benchmark, all 3 attack prompts were flagged and no key leaked. It is a heuristic: it reduces risk, it does not remove it.

**8. What production work did you do, and what are the numbers?**
Per-request latency and token logging, a 10-minute cache of up to 256 answers, input limits (413 for bodies over 8 KB, 422 for questions over 500 characters) and a metrics page. My numbers are in `docs/benchmark.json`: fresh-answer p50 ____ ms, cached p50 ____ ms, cache hit rate ____%. My `/ask` route made no model calls in the benchmark, so it showed no token use; token counts apply to the routes that call the model.

**9. What are the limitations, and what is next?**
Limits: only 20 curated records, a hand-written 2016 vs 2026 summary, a heuristic injection check, an in-memory cache that resets on restart, and no login or rate limiting yet. Next: a shared cache (Redis), authentication and rate limits, an automated clause-by-clause diff, a larger evaluation set, and Hindi and Marathi support, because the gazette is bilingual.

**10. How did you use AI tools, and what went wrong?**
I used an AI assistant for scaffolding, tests and documentation, and I reviewed and ran everything. One problem: helper test files it generated did not match my code, overwrote some of my files and made CI fail. I found the exact commit with `git log` and `git diff`, restored my versions from the commit before it, and re-ran tests and lint before pushing. The lesson: read generated code against your own structure, and run CI locally before you push.

## Numbers to memorise

| What | Number |
|---|---|
| Pages in the gazette PDF | 144 (66 in English) |
| Clause rows extracted / curated records | 222 / 20 |
| Test questions answerable | 10 of 10 |
| Automated tests passing | ____ |
| Cached vs fresh answer speed (p50) | ____ ms vs ____ ms |
| Attack prompts flagged / keys leaked | 3 of 3 / 0 |

Print the measured ones with: `Get-Content docs\benchmark.json`

## Prove it in the repo (check before the interview)

- Where the version tag lives: `Select-String -Path app\*.py,data\*.json -Pattern "version|2016" | Select-Object -First 20`
- The toggle and its tests: `ui\compare.py` and `tests\test_ui.py` (search for "toggle")
- The coverage threshold: `Select-String -Path app\main.py -Pattern "MIN_COVERAGE"`
- Production guards: `app\prod.py` and `tests\test_prod.py`
- The live link and the CI badge work: open them in a browser
