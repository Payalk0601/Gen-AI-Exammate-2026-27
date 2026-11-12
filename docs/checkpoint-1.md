# Checkpoint 1: KachraCheck FastAPI

## 1. Run it
```powershell
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Open **http://127.0.0.1:8000/docs**. This is the page FastAPI builds by itself from my code. Every
endpoint can be tried from the browser with **Try it out → Execute**.

<!-- After taking your screenshot of /docs, save it as docs/img/fastapi_docs.png and delete this line and the arrows:
![FastAPI /docs page](img/fastapi_docs.png)
-->

| Endpoint | What it does |
|---|---|
| `GET /health` | status, number of records, which search engine is active |
| `GET /records?limit=` | list records |
| `GET /records/{id}` | one record, `404` if missing |
| `GET /search?q=` | ranked records with score, coverage and `answerable` |
| `POST /questions` | a user question in, closest clauses out (or "not answerable") |

## 2. Demo (about 2 minutes)
1. **/health** → Execute → shows `"records": 20`.
2. **POST /questions** with `{"question": "What bin colours must my municipality use?", "name": "Payal"}`:
   ```json
   { "answerable": true, "missing_terms": [],
     "answers": [ { "score": 0.351, "record": { "id": 15, "rule_reference": "Rule 39(51)",
                    "stakeholder": "Urban local bodies", "timeline": "Ongoing" } } ] }
   ```
3. **POST /questions** with Q6, `"What is the exact fine in rupees for a household that burns waste?"`:
   ```json
   { "answerable": false, "missing_terms": ["exact", "fine", "rupees", "burns"], "answers": [],
     "note": "The KachraCheck data has no clause about: exact, fine, rupees, burns." }
   ```
   The API refuses to guess, because the data holds no clause about fines.
4. **GET /records/999** → `404 Record 999 not found`.

## 3. One function explained: `SmartSearch.rank` (`app/smart_search.py`)
```python
def rank(self, query, limit=5):
    query = (query or "").strip()
    if not query or not self.records:
        return []
    scores = cosine_similarity(self.vectorizer.transform([expand_query(query)]), self.matrix).ravel()
    order = scores.argsort()[::-1][:limit]
    return [(self.records[i], round(float(scores[i]), 4)) for i in order if scores[i] > 0]
```
**What it does:** takes a user's question and returns the records that fit it best, with a score.

**How, step by step**
1. If the question is empty, return nothing.
2. `expand_query` adds the Rules' own words for everyday ones: "municipality" gets "urban local bodies" added.
3. `vectorizer.transform` turns the question into a row of numbers, one per word, where rare words count more
   than common ones (that is the TF-IDF idea). `self.matrix` already holds the same kind of row for each of the
   20 records, built once when the server starts.
4. `cosine_similarity` measures the angle between the question's row and every record's row. Records that share
   important words point the same way and score near 1; unrelated records score 0.
5. `argsort()[::-1][:limit]` sorts the scores from highest to lowest and keeps the top few.
6. Records with a score of 0 are dropped, and each result is returned as `(record, score)`.

**Its weakness:** it counts words, not meaning. A question with no matching words can still return a weak match
(Q6 got 0.25). That is why `coverage()` exists next to it, to say when the data has no answer.

## 4. Tag
```powershell
git tag -a checkpoint-1 -m "Checkpoint 1: FastAPI demo, LLM notes, user questions"
git push origin checkpoint-1
```
