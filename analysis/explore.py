"""Print three facts about the KachraCheck records using pandas.

  python analysis/explore.py
"""
import json
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"
path = DATA / "records.json" if (DATA / "records.json").exists() else DATA / "sample_records.json"
df = pd.DataFrame(json.loads(path.read_text(encoding="utf-8")))
total = len(df)
print(f"Loaded {total} records from {path.name}\n")

# Fact 1: which kind of duty dominates?
cats = df["category"].value_counts()
top, n = cats.index[0], int(cats.iloc[0])
print(f"1. '{top}' is the most common duty type: {n} of {total} records ({n / total:.0%}).")
print("   " + ", ".join(f"{c} {k}" for c, k in cats.items()))

# Fact 2: how many deadlines sit on 30 June?
june = df["timeline"].str.contains("30 June", case=False, regex=False)
print(f"\n2. {int(june.sum())} of {total} records ({june.mean():.0%}) have a 30 June deadline,"
      f" held by: {', '.join(df.loc[june, 'stakeholder'].str.split(' \\(').str[0].unique())}.")

# Fact 3: what is new compared with 2016?
new = df["rule_2016_match"].isna()
print(f"\n3. {int(new.sum())} of {total} records ({new.mean():.0%}) have no direct 2016 clause: "
      f"{', '.join(df.loc[new, 'rule_reference'])}.")
print(f"   Most of the new duties are '{df.loc[new, 'category'].value_counts().index[0]}' duties.")
