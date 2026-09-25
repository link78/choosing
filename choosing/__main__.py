from __future__ import annotations

import argparse

from .application import BettingApplication, render_text_report, report_to_json


def parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sports betting application powered by existing APIs.")
    parser.add_argument("--players", default="7,42", help="Comma-separated player ids")
    parser.add_argument("--games", default="finals,demo", help="Comma-separated game ids")
    parser.add_argument("--bankroll", type=float, default=1000.0, help="Bankroll amount")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of text")
    args = parser.parse_args(argv)

    application = BettingApplication()
    report = application.build_report(
        player_ids=parse_csv(args.players),
        game_ids=parse_csv(args.games),
        bankroll=args.bankroll,
    )

    if args.json:
        print(report_to_json(report))
    else:
        print(render_text_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
