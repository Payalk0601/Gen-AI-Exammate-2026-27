"""S1 - work with the records as a plain list of dicts: print all, search by keyword,
count per category. (Refactored into app/records.py + app/cli.py in S2.)"""
import json
from collections import Counter
from pathlib import Path

DATA = Path(__file__).parent / "data" / "sample_records.json"

with DATA.open(encoding="utf-8") as f:
    records = json.load(f)


def print_all(rows):
    for r in rows:
        print(f"#{r['id']:<2} {r['rule_reference']:<14} {r['stakeholder'][:45]:<45} | {r['timeline']}")


def search(rows, keyword):
    kw = keyword.lower()
    return [r for r in rows if any(kw in str(v).lower() for v in r.values())]


def count_per_category(rows):
    return Counter(r["category"] for r in rows)


print(f"{len(records)} records loaded\n")
print_all(records)

print("\nSearch 'annual return':")
print_all(search(records, "annual return"))

print("\nCount per category:")
for cat, n in count_per_category(records).most_common():
    print(f"  {cat:<18}{n}")
