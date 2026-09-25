from __future__ import annotations

from datetime import datetime, timezone

from .data_sources import OddsAPIClient, SportsDataIOClient
from .prediction import build_game_edge, build_player_prediction, clamp


class PredictionService:
    def __init__(
        self,
        sports_client: SportsDataIOClient | None = None,
        odds_client: OddsAPIClient | None = None,
    ) -> None:
        self.sports_client = sports_client or SportsDataIOClient()
        self.odds_client = odds_client or OddsAPIClient()

    def _meta(self, entity_id: str, entity_type: str) -> dict:
        return {
            "entity_id": entity_id,
            "entity_type": entity_type,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "advisory_only": True,
        }

    def get_player_prediction(self, player_id: str, overrides: dict | None = None) -> dict:
        sports_data = self.sports_client.fetch_player_context(player_id, overrides)
        payload = build_player_prediction(player_id, sports_data)
        payload["meta"] = self._meta(player_id, "player")
        payload["source_snapshots"] = {
            "sports_data_io": {
                "recent_form": round(sports_data["recent_form"], 3),
                "workload": round(sports_data["workload"], 3),
                "injury_risk": round(sports_data["injury_risk"], 3),
                "availability": round(sports_data["availability"], 3),
            }
        }
        return payload

    def get_game_edge(self, game_id: str, sports_overrides: dict | None = None, odds_overrides: dict | None = None) -> dict:
        sports_data = self.sports_client.fetch_game_context(game_id, sports_overrides)
        odds_data = self.odds_client.fetch_game_market(game_id, odds_overrides)
        payload = build_game_edge(game_id, sports_data, odds_data)
        payload["meta"] = self._meta(game_id, "game")
        payload["team_prediction"]["expected_points"] = round(
            payload["team_prediction"]["expected_points"] + sports_data["expected_points_adjustment"],
            1,
        )
        payload["market_signals"]["sharp_money_index"] = round(odds_data["sharp_money_index"], 3)
        payload["market_signals"]["steam_move"] = odds_data["steam_move"]
        payload["market_signals"]["closing_line_value"] = round(odds_data["closing_line_value"], 3)
        payload["betting_edge"]["confidence"] = round(
            clamp(
                0.45
                + abs(payload["betting_edge"]["edge"]) * 2.5
                + odds_data["sharp_money_index"] * 0.1,
                0,
                1,
            ),
            3,
        )
        payload["betting_edge"]["recommended_stake"] = _recommended_stake(payload["betting_edge"]["edge"])
        return payload


def _recommended_stake(edge: float) -> str:
    absolute_edge = abs(edge)
    if absolute_edge < 0.03:
        return "no_play"
    if absolute_edge < 0.07:
        return "small"
    if absolute_edge < 0.12:
        return "medium"
    return "strong"
