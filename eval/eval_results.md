# RAG evaluation: per-question results

| Config | Chunk size | Top-k | Chunks | Accuracy | Retrieval hit | Refusals right | Wrong answers | Winner |
|---|---|---|---|---|---|---|---|---|
| A | 800 | 3 | 426 | 11/15 (73%) | 77% | 2/2 | 3 | **yes** |
| B | 500 | 5 | 648 | 11/15 (73%) | 69% | 2/2 | 3 |  |

Generator: `llm:groq/llama-3.3-70b-versatile` · Embedder: `all-MiniLM-L6-v2` · 15 questions (13 answerable, 2 must say "I don't know") · run 16 November 2026

## A: chunk size 800, top-k 3 (winner)

| Q | Question | Expected rule | Retrieved rules | Answered | Reason | Result |
|---|---|---|---|---|---|---|
| 1 | Who has to separate waste at home, and into which streams? | 5 | 5, 8 | yes | ok | OK |
| 2 | Is my housing society a bulk waste generator and what must it do? | 5, 6 | 3, 6, 39 | yes | ok | OK |
| 3 | By when must a processing facility file its annual return? | 7 | 4, 7, 8 | yes | ok | OK |
| 4 | What bin colours must my municipality use? | 39 | 39, 41 | yes | ok | OK |
| 5 | How did the 2026 rules change sanitary waste wrapping compared with 2016? | 5 | 1, 3, 5 | yes | ok | OK |
| 6 | What is the exact fine in rupees for a household that burns waste? | none (refuse) | 5, 14 | no | no_amount_in_sources | OK |
| 7 | Which duties have a 30 June deadline? | 6, 7, 8, 11, 14 | 1, 31, 41 | no | no_supporting_sentence | FAIL |
| 8 | Does my municipality have to collect waste from my door every day? | 39 | 39, 41 | yes | ok | OK |
| 9 | Who checks whether my municipality is following the rules? | 37, 41 | 4, 39 | yes | ok | FAIL |
| 10 | When must urban local bodies make their bye-laws? | 39 | 12, 34, 39 | yes | ok | FAIL |
| 11 | Who has to file quarterly returns, and by when? | 7, 8, 9 | 4, 7, 14 | yes | ok | OK |
| 12 | What must industrial units that use solid fuel do about refuse derived fuel? | 11 | 11, 15 | yes | ok | OK |
| 13 | What must a district panchayat prepare for waste in villages? | 40 | 3, 40 | yes | ok | OK |
| 14 | What must the Central Pollution Control Board set up and by when? | 16 | 20, 38 | yes | ok | FAIL |
| 15 | Can I get a refund on my income tax? | none (refuse) | 7, 11, 31 | no | low_similarity | OK |

## B: chunk size 500, top-k 5

| Q | Question | Expected rule | Retrieved rules | Answered | Reason | Result |
|---|---|---|---|---|---|---|
| 1 | Who has to separate waste at home, and into which streams? | 5 | 5, 39 | yes | ok | OK |
| 2 | Is my housing society a bulk waste generator and what must it do? | 5, 6 | 3, 6, 39 | yes | ok | OK |
| 3 | By when must a processing facility file its annual return? | 7 | 4, 7, 8, 14 | yes | ok | OK |
| 4 | What bin colours must my municipality use? | 39 | 39, 41 | yes | ok | OK |
| 5 | How did the 2026 rules change sanitary waste wrapping compared with 2016? | 5 | 1, 3, 5, 39 | yes | ok | OK |
| 6 | What is the exact fine in rupees for a household that burns waste? | none (refuse) | 3, 5, 39, 40 | no | no_amount_in_sources | OK |
| 7 | Which duties have a 30 June deadline? | 6, 7, 8, 11, 14 | 1, 4, 41, 44 | no | low_coverage | FAIL |
| 8 | Does my municipality have to collect waste from my door every day? | 39 | 5, 39, 41 | yes | ok | OK |
| 9 | Who checks whether my municipality is following the rules? | 37, 41 | 4, 22, 23, 35 | yes | ok | FAIL |
| 10 | When must urban local bodies make their bye-laws? | 39 | 3, 12, 34, 41 | yes | ok | FAIL |
| 11 | Who has to file quarterly returns, and by when? | 7, 8, 9 | 4, 7, 8, 14, 23 | yes | ok | OK |
| 12 | What must industrial units that use solid fuel do about refuse derived fuel? | 11 | 11, 15, 39 | yes | ok | OK |
| 13 | What must a district panchayat prepare for waste in villages? | 40 | 3, 40 | yes | ok | OK |
| 14 | What must the Central Pollution Control Board set up and by when? | 16 | 3, 20, 38 | yes | ok | FAIL |
| 15 | Can I get a refund on my income tax? | none (refuse) | 6, 7, 8, 11, 31 | no | low_similarity | OK |
