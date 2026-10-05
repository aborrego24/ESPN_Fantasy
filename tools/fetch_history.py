"""Fetch every accessible season of a league and save it as one JSON file.

Kept out of `run_scenarios.sh` on purpose. A history is one League fetch per
season and each of those is several HTTP requests, so it is slow, it needs
`ESPN_S2` / `SWID` for anything older than last year, and none of it changes
between runs -- a finished season is finished. Writing it once to a file means the
all-time tables can be re-rendered, and the rating re-weighted, with no network at
all.

    tools/fetch_history.py --out history.json
    ./run_scenarios.sh --irl 14 --html report.html --history history.json

Re-run it when a season finishes, or with --force to overwrite.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scenario_engine"))

import config  # noqa: E402
import history_data  # noqa: E402


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="fetch_history.py",
        description="Save every accessible season of a league as one JSON file.",
    )
    parser.add_argument(
        "-o",
        "--out",
        metavar="PATH",
        default="history.json",
        help="where to write (default: history.json)",
    )
    parser.add_argument(
        "--league-id",
        type=int,
        default=config.default_league_id(),
        help="ESPN league id (falls back to ESPN_LEAGUE_ID, then local_config.py)",
    )
    parser.add_argument(
        "--year",
        type=int,
        action="append",
        dest="years",
        help="fetch only this season; repeatable (default: every season found)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite an existing file instead of refusing",
    )
    return parser.parse_args(argv), parser


def main(argv=None):
    args, parser = parse_args(sys.argv[1:] if argv is None else argv)

    if args.league_id is None:
        parser.error(
            "no league configured: pass --league-id, set ESPN_LEAGUE_ID, or copy "
            "scenario_engine/local_config.example.py to local_config.py"
        )
    if os.path.exists(args.out) and not args.force:
        parser.error(f"{args.out} already exists; pass --force to overwrite")

    espn_s2, swid = config.espn_s2(), config.swid()
    if not (espn_s2 and swid):
        print(
            "No ESPN_S2 / SWID set: only the current and previous season are "
            "readable without them, so older years will be skipped.",
            file=sys.stderr,
        )

    history = history_data.build_history(
        args.league_id,
        espn_s2=espn_s2,
        swid=swid,
        years=args.years,
        on_season=lambda year: print(f"  fetching {year} ...", file=sys.stderr),
    )

    if not history["seasons"]:
        parser.error(
            f"no season of league {args.league_id} could be read: "
            + "; ".join(f"{s['year']}: {s['reason']}" for s in history["skipped"])
        )

    with open(args.out, "w") as handle:
        json.dump(history, handle, indent=2)

    years = ", ".join(str(s["year"]) for s in history["seasons"])
    print(f"Wrote {args.out}: {len(history['seasons'])} season(s) -- {years}", file=sys.stderr)
    for skip in history["skipped"]:
        print(f"  skipped {skip['year']}: {skip['reason']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
