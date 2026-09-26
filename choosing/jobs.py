from __future__ import annotations

import argparse
import json
import sys
import time

from .catalog import ODDS_API_SPORTS
from .service import PredictionService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Background jobs for grading predictions and refreshing odds snapshots.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    grade = subparsers.add_parser("grade", help="Grade pending predictions from upstream final scores and box scores.")
    grade.add_argument("--date", default=None, help="Grade only results for this YYYY-MM-DD date.")

    refresh = subparsers.add_parser("refresh", help="Refresh the slate and store odds snapshots for line movement.")
    refresh.add_argument(
        "--sport",
        action="append",
        default=None,
        help="Odds API sport key to refresh (repeatable). Defaults to every supported sport.",
    )

    for subparser in (grade, refresh):
        subparser.add_argument("--loop", action="store_true", help="Keep running on an interval.")
        subparser.add_argument("--interval", type=int, default=3600, help="Seconds between runs when --loop is set.")
    return parser


def run_job(service: PredictionService, args: argparse.Namespace) -> dict:
    if args.command == "grade":
        return service.grade_outcomes(args.date)
    sports = args.sport or [entry["key"] for entry in ODDS_API_SPORTS]
    refreshed = {}
    for sport in sports:
        slate = service.get_slate(sport, record_snapshot=True, limit=25)
        refreshed[sport] = {"source_mode": slate["source_mode"], "evaluated": slate["evaluated"]}
    return {"refreshed": refreshed}


def main(argv: list[str] | None = None, service: PredictionService | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.interval < 60:
        print("--interval must be at least 60 seconds", file=sys.stderr)
        return 2
    service = service or PredictionService()
    while True:
        result = run_job(service, args)
        print(json.dumps(result, sort_keys=True), flush=True)
        if not args.loop:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
