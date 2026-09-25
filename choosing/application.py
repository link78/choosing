from __future__ import annotations

import json
from datetime import datetime, timezone

from .service import PredictionService


STAKE_RATES = {
    "no_play": 0.0,
    "small": 0.01,
    "medium": 0.02,
    "strong": 0.03,
}


class BettingApplication:
    def __init__(self, service: PredictionService | None = None) -> None:
        self.service = service or PredictionService()

    def build_report(
        self,
        player_ids: list[str],
        game_ids: list[str],
        bankroll: float = 1000.0,
        player_overrides: dict[str, dict] | None = None,
        game_overrides: dict[str, dict] | None = None,
    ) -> dict:
        player_overrides = player_overrides or {}
        game_overrides = game_overrides or {}

        player_cards = [
            self._build_player_card(player_id, player_overrides.get(player_id))
            for player_id in player_ids
        ]
        game_cards = [
            self._build_game_card(game_id, bankroll, game_overrides.get(game_id))
            for game_id in game_ids
        ]

        active_bets = [card for card in game_cards if card["recommendation"]["action"] == "bet"]
        total_stake = round(sum(card["recommendation"]["stake_amount"] for card in active_bets), 2)
        highest_edge = max(game_cards, key=lambda card: abs(card["betting_edge"]["edge"]), default=None)

        return {
            "meta": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "bankroll": round(bankroll, 2),
                "advisory_only": True,
                "data_sources": ["SportsDataIO", "The Odds API"],
            },
            "player_cards": player_cards,
            "game_cards": game_cards,
            "portfolio_summary": {
                "recommended_bets": len(active_bets),
                "total_recommended_stake": total_stake,
                "highest_edge_game": highest_edge["game_id"] if highest_edge else None,
                "watchlist_players": [
                    card["player_id"] for card in player_cards if "availability_risk" in card["flags"]
                ],
            },
        }

    def _build_player_card(self, player_id: str, overrides: dict | None = None) -> dict:
        prediction = self.service.get_player_prediction(player_id, overrides)
        flags = []
        if prediction["predictions"]["availability_probability"] < 0.7:
            flags.append("availability_risk")
        if prediction["predictions"]["underperformance_risk"] > 0.45:
            flags.append("underperformance_risk")
        if prediction["predictions"]["expected_minutes"] >= 34:
            flags.append("high_minutes_projection")
        return {
            "player_id": prediction["player_id"],
            "expected_minutes": prediction["predictions"]["expected_minutes"],
            "expected_performance": prediction["predictions"]["expected_performance"],
            "availability_probability": prediction["predictions"]["availability_probability"],
            "underperformance_risk": prediction["predictions"]["underperformance_risk"],
            "flags": flags,
        }

    def _build_game_card(self, game_id: str, bankroll: float, overrides: dict | None = None) -> dict:
        overrides = overrides or {}
        sports_overrides = overrides.get("sports")
        odds_overrides = overrides.get("odds")
        edge = self.service.get_game_edge(game_id, sports_overrides, odds_overrides)
        stake_rate = STAKE_RATES[edge["betting_edge"]["recommended_stake"]]
        stake_amount = round(bankroll * stake_rate, 2)
        return {
            "game_id": edge["game_id"],
            "team_prediction": edge["team_prediction"],
            "market_signals": edge["market_signals"],
            "betting_edge": edge["betting_edge"],
            "recommendation": {
                "action": edge["betting_edge"]["recommended_action"],
                "stake_label": edge["betting_edge"]["recommended_stake"],
                "stake_amount": stake_amount,
                "confidence": edge["betting_edge"]["confidence"],
            },
        }


def render_text_report(report: dict) -> str:
    lines = [
        "CHOOSING SPORTS BETTING REPORT",
        f"Bankroll: ${report['meta']['bankroll']:.2f}",
        "",
        "PLAYER WATCHLIST",
    ]
    for player in report["player_cards"]:
        flags = ", ".join(player["flags"]) if player["flags"] else "stable"
        lines.append(
            f"- Player {player['player_id']}: minutes {player['expected_minutes']}, "
            f"performance {player['expected_performance']}, flags {flags}"
        )

    lines.extend(["", "BETTING OPPORTUNITIES"])
    for game in report["game_cards"]:
        recommendation = game["recommendation"]
        lines.append(
            f"- Game {game['game_id']}: {recommendation['action']} / {recommendation['stake_label']} "
            f"(${recommendation['stake_amount']:.2f}), edge {game['betting_edge']['edge']}"
        )

    summary = report["portfolio_summary"]
    lines.extend(
        [
            "",
            "PORTFOLIO SUMMARY",
            f"- Recommended bets: {summary['recommended_bets']}",
            f"- Total stake: ${summary['total_recommended_stake']:.2f}",
            f"- Highest edge game: {summary['highest_edge_game']}",
        ]
    )
    return "\n".join(lines)


def report_to_json(report: dict) -> str:
    return json.dumps(report, indent=2, sort_keys=True)
