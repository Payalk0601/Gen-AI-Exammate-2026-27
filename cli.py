"""Command line interface for KachraCheck.

Usage (run from the repo root):
    python -m app.cli list
    python -m app.cli search bottle
    python -m app.cli category dry
    python -m app.cli add "Pizza box" wet --tip "Compost it."
    python -m app.cli stats
"""
import argparse
import sys

from app import records as rec


def print_table(rows):
    if not rows:
        print("No matching records.")
        return
    print(f"{'ID':<4}{'Item':<24}{'Category':<11}{'Bin':<7}{'Recycle':<8}Tip")
    print("-" * 90)
    for r in rows:
        recycle = "yes" if r["recyclable"] else "no"
        print(f"{r['id']:<4}{r['item']:<24}{r['category']:<11}{r['bin']:<7}{recycle:<8}{r['tip']}")


def cmd_list(args, data):
    print_table(data)


def cmd_search(args, data):
    print_table(rec.search_records(data, args.keyword))


def cmd_category(args, data):
    print_table(rec.filter_by_category(data, args.name))


def cmd_add(args, data):
    try:
        new = rec.add_record(data, args.item, args.category, args.tip,
                             recyclable=args.recyclable, aliases=args.alias)
    except ValueError as err:
        print(f"Could not add record: {err}")
        sys.exit(1)
    rec.save_records(data)
    print(f"Added #{new['id']}: {new['item']} -> {new['bin']} bin")


def cmd_stats(args, data):
    print(f"Total records : {len(data)}")
    for cat, n in sorted(rec.category_counts(data).items()):
        print(f"  {cat:<10}: {n}")
    print(f"Recyclable    : {rec.recyclable_share(data)}%")


def build_parser():
    p = argparse.ArgumentParser(prog="kachracheck", description="Which bin does it go in?")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="show all records").set_defaults(func=cmd_list)

    s = sub.add_parser("search", help="search by item name or alias")
    s.add_argument("keyword")
    s.set_defaults(func=cmd_search)

    c = sub.add_parser("category", help="filter by category")
    c.add_argument("name", choices=sorted(rec.BIN_BY_CATEGORY))
    c.set_defaults(func=cmd_category)

    a = sub.add_parser("add", help="add a new record")
    a.add_argument("item")
    a.add_argument("category", choices=sorted(rec.BIN_BY_CATEGORY))
    a.add_argument("--tip", required=True)
    a.add_argument("--recyclable", action="store_true")
    a.add_argument("--alias", action="append", help="repeat for multiple aliases")
    a.set_defaults(func=cmd_add)

    sub.add_parser("stats", help="summary numbers").set_defaults(func=cmd_stats)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.func(args, rec.load_records())


if __name__ == "__main__":
    main()
