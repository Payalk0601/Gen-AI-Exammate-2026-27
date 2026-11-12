# KachraCheck user questions

Ten questions real users would ask. **Q1 to Q6 are on the project card**; Q7 to Q10 came from thinking about
other users (an analyst, a resident, an officer). `data/questions.json` holds the same list, and
`python analysis/check_questions.py` tests every one against the search engine.

| # | Who asks | Question | Record(s) that answer it | Answerable from data? |
|---|----------|----------|--------------------------|-----------------------|
| 1 | Household member | Who has to separate waste at home, and into which streams? | #1 Rule 5(1)(ख) | Yes |
| 2 | Housing society secretary | Is my housing society a bulk waste generator and what must it do? | #4 Rule 5(2), #5 Rule 6(क) | Yes |
| 3 | Compost plant operator | By when must a processing facility file its annual return? | #8 Rule 7(ग) | Yes |
| 4 | Resident | What bin colours must my municipality use? | #15 Rule 39(51) | Yes |
| 5 | Student | How did the 2026 rules change sanitary waste wrapping compared with 2016? | #2 Rule 5(1)(ग) | Yes |
| **6** | **Resident** | **What is the exact fine in rupees for a household that burns waste?** | **none** | **No** |
| 7 | Compliance analyst | Which duties have a 30 June deadline? | #6, #8, #9, #11, #12 | Yes |
| 8 | Resident | Does my municipality have to collect waste from my door every day? | #13 Rule 39(4) | Yes |
| 9 | Resident | Who checks whether my municipality is following the rules? | #18 Rule 37(ii), #19 Rule 41(1)(i) | Yes |
| 10 | Municipal officer | When must urban local bodies make their bye-laws? | #14 Rule 39(5) | Yes |

## Why Q6 cannot be answered
My 20 records cover *who must do what, and by when*. None says what the **penalty** is, and none covers the
rule against **burning** waste. Fines under the Rules are set through a separate environmental-compensation
mechanism, and I did not put it in the data. So the honest reply is "this dataset cannot tell you".

## What I learned from testing
- **Plain TF-IDF got Q6 wrong.** It still returned Rule 6(ज) (bulk generator annual return) with a score of 0.25,
  higher than the *correct* matches for Q1 (0.17) and Q7 (0.13). So a minimum-score cut-off cannot separate
  "no answer" from "weak answer".
- **Fix:** a coverage check. For each meaningful word in the question I test whether it appears in the data
  (directly or through my synonym list). Q6 scores 0.33 because *exact, fine, rupees, burns* appear nowhere,
  while real questions score 0.6 or more. Below 0.4 the API says `"answerable": false` and returns no answers.
- **Q9 failed first.** I asked "who *checks*", but the records say "*review*" and "*enforce*". I added
  `check` and `following` to the synonym list afterwards, so Q9 passing is partly tuned to my own test set.
  The check is a rule of thumb, not a guarantee.

Result: `python analysis/check_questions.py` gives **10 of 10** handled correctly on these ten questions.
Ten questions is a very small test, so a different set could fail.
