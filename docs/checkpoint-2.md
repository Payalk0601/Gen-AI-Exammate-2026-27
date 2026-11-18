# Checkpoint 2: live demo script

**Tag:** `checkpoint-2` · **What is shown:** the KachraCheck chat (Streamlit) on top of the FastAPI service, with citations,
an "I don't know" for the unanswerable question, an agent that sorts household items, thumbs up/down, and the
**2016 vs 2026 toggle**.

## Before you start (5 minutes)
Terminal 1: `uvicorn app.main:app` · Terminal 2: `streamlit run ui/app.py` · Terminal 3: `python ui/preflight.py`

Preflight must say `8 of 8 checks passed`. If a line says FAIL, its message tells you the fix, for example
`python -m app.vectorstore --rebuild`. Open `http://localhost:8501`, keep `http://127.0.0.1:8000/docs` in a second tab, and
start with **New conversation** so the screen is clean.

**If the internet or the LLM provider is down:** answers and planning still work offline. Set
`KACHRACHECK_GENERATOR=extractive` and `KACHRACHECK_PLANNER=rules` before starting `uvicorn`, and say so.

## The demo (about 6 minutes)
| # | Do this | Say this |
|---|---|---|
| 1 | Show `/docs` for 10 seconds, then the chat. | "One API (`/ask`, `/agent`, `/search/semantic`), one chat on top of it." |
| 2 | **Ask the Rules**, click the sample "What bin colours must my municipality use?". Open **Sources**. | "The answer comes only from retrieved chunks. Each one shows its rule, file and page, so I can check it." |
| 3 | Flip **Compare with the 2016 Rules** on that answer. | "My own feature: the old rule next to the new one. Red is only in 2016, green is only in 2026. White became blue, black became red." Open **Full 2026 text** to show the clause from the PDF. |
| 4 | Click the sample "What is the exact fine in rupees for a household that burns waste?". Flip the toggle. | "It says I don't know, because my documents contain no rupee amount. A similarity score alone could not catch this: this question scored higher than some correct ones, so the code checks what the question asks for." The toggle explains why there is no comparison. |
| 5 | Switch to **Agent**, send `batery`. | "The item table had to guess a spelling, so the graph pauses and asks me. A wrong guess means the wrong bin." Click **Yes**. |
| 6 | Flip the toggle on the battery answer, then ask `why?` | "Memory: it remembers the last item, so `why?` searches the rule for special care waste." |
| 7 | Press 👍 on one answer and 👎 on another. Show the counter in the sidebar. | "Feedback is saved in a local SQLite file, one row per answer." |
| 8 | Show `eval/` in the README: the winner table. | "Two configurations, 15 questions: 11 of 15 correct, both refusals right." |

## Questions you may get
- **How does the toggle work?** `data/rule_changes.json` pairs each 2026 duty with the 2016 duty it replaces (12 pairs). Both sides are
  short summaries in matching wording, and `difflib` compares them word by word. An answer is linked to a pair through the rule
  the sorter named, or through the rule number of the cited chunk plus shared words. No match means no comparison.
- **Why summaries and not the legal text side by side?** The two Rules are worded differently, so a diff of the raw text would
  highlight phrasing, not changes. The raw 2026 clause is one click away under **Full 2026 text**.
- **How do you know the 2016 side is right?** It comes from published summaries of the 2016 Rules (NIUA/ICLEI slides, the NPC toolkit, the CAG summary), not
  from the gazette text. I mark the pairs where I could not confirm a detail (for example the large-premises deadline).
- **What does your agent do that a plain search doesn't?** It chooses between two tools, uses both when asked for both, falls back to
  the Rules search when the item table does not know an item, and stops after four steps.
- **Where does it fail?** [fill in from `eval/eval_results.md`: name the 4 questions that failed and why]. The comparison covers only 12 duties.
  The item table has 60 hand-built items, and 40 of them are my reading of the stream definitions, not items the Rules name; the answer says so.

## Screenshot for the README
1. With the toggle on the bins answer, take a screenshot that shows the question, the answer, the **Sources** line and the
   2016 / 2026 columns with the red and green words.
2. Save it as `docs/img/ui_toggle.png`.
3. In `README.md`, find the `<!-- screenshot -->` block under "Chat UI" and delete the two comment lines around the image.

## Tag
```powershell
git tag -a checkpoint-2 -m "Checkpoint 2: chat UI with 2016 vs 2026 toggle, agent, feedback"
git push origin checkpoint-2
```
