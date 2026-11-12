"""KachraCheck command line.

  python -m app.cli list
  python -m app.cli search "annual return"
  python -m app.cli count --by stakeholder
  python -m app.cli show 14
"""
import argparse
import sys
import textwrap

from app import records as rec


def print_rows(rows):
    if not rows:
        print("No matching records.")
        return
    for r in rows:
        print(f"#{r.id:<3}{r.rule_reference:<15}{r.stakeholder[:48]:<48}  {r.timeline[:50]}")
    print(f"\n{len(rows)} record(s)")


def cmd_list(args, data):
    print_rows(data)


def cmd_search(args, data):
    print_rows(rec.search(data, args.keyword))


def cmd_count(args, data):
    try:
        counts = rec.count_by(data, args.by)
    except ValueError as err:
        sys.exit(str(err))
    for key, n in counts.items():
        print(f"{n:>3}  {key}")


def cmd_show(args, data):
    r = rec.get_by_id(data, args.id)
    if r is None:
        sys.exit(f"No record with id {args.id}")
    print(f"{r.rules_version} | {r.rule_reference} | {r.category}")
    print(f"Stakeholder : {r.stakeholder}")
    print("Obligation  :\n" + textwrap.indent(textwrap.fill(r.obligation, 78), "  "))
    print(f"Timeline    : {r.timeline}")
    print(f"2016 match  : {r.rule_2016_match or 'no direct 2016 clause identified'}")
    print(f"Source      : {r.source_url}")


def build_parser():
    p = argparse.ArgumentParser(prog="kachracheck", description="SWM Rules 2026 duty lookup")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="list all records").set_defaults(func=cmd_list)
    s = sub.add_parser("search", help="keyword search")
    s.add_argument("keyword")
    s.set_defaults(func=cmd_search)
    c = sub.add_parser("count", help="count records per field")
    c.add_argument("--by", default="category")
    c.set_defaults(func=cmd_count)
    sh = sub.add_parser("show", help="show one record in full")
    sh.add_argument("id", type=int)
    sh.set_defaults(func=cmd_show)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.func(args, rec.load_records())


if __name__ == "__main__":
    main()
