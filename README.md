# KachraCheck ♻️

> Type in any piece of household waste and find out which bin it belongs in, in under five seconds.

**Author:** Payal · Final-year B.Tech (AI & ML), Sanjivani University, Kopargaon
**Programme:** Gen AI Exammate 2026-27
**Status:** In progress (Day 1 to Day 2 done)

## Problem
In most Indian households, waste ends up mixed in a single bin. Wet, dry, hazardous and sanitary waste
all get combined, which makes recycling and composting hard for municipal workers. People don't
segregate mostly because they are unsure *where* an item goes, not because they don't care.

## Solution
KachraCheck is a small assistant that answers one question: **"Where does this go?"**
It keeps a growing knowledge base of everyday waste items, each with a category, a bin colour,
a recyclability flag and a short disposal tip. Later days will add an LLM layer that handles items
not yet in the knowledge base.

## Bin colour guide used in this project
| Colour | Category | Examples |
|--------|----------|----------|
| Green  | Wet (biodegradable) | Vegetable peels, tea leaves |
| Blue   | Dry (recyclable/non-biodegradable) | Paper, plastic bottles, glass |
| Red    | Hazardous and e-waste | Batteries, CFL bulbs, old chargers |
| Black  | Sanitary / reject | Diapers, sanitary pads, used masks |

## Tech stack
Python 3 · JSON for storage · argparse for the CLI · (planned) LLM API for unknown items

## Project layout
```
.
├── README.md
├── day01_intro.py          # project banner + greeting
├── day01_menu.py           # interactive menu
├── data/
│   └── sample_records.json # 18 KachraCheck records
└── app/
    ├── __init__.py
    ├── records.py          # load / validate / search / add records
    └── cli.py              # command line interface
```

## How to run
```bash
python day01_intro.py
python day01_menu.py

python -m app.cli list
python -m app.cli search bottle
python -m app.cli category hazardous
python -m app.cli add "Pizza box (oily)" wet --tip "Greasy cardboard can't be recycled; compost it."
python -m app.cli stats
```

## Roadmap
- [x] D1: Project card, intro and menu scripts
- [x] D2: Records dataset, record functions, CLI
- [ ] D3+: Fuzzy matching, LLM fallback for unknown items, simple web UI
