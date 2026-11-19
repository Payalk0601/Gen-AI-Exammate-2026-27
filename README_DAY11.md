# Day 11 - tests, ruff, Docker

1. Remove the old script-style tests and one-time helpers (the new tests/ replaces them):
   git rm tests/test_day9.py tests/test_day10.py apply_day10.py
2. python apply_day11.py
3. pip install -r requirements-dev.txt
4. pytest        (all green)   |   ruff check .   (All checks passed)
5. docker compose up --build   -> API http://localhost:8000/docs, UI http://localhost:8501
6. Commit, push, check the README on GitHub.
