from __future__ import annotations

from datetime import datetime, timezone

from .data_sources import OddsAPIClient, SportsDataIOClient, search_players, search_teams
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
        payload = build_player_prediction(sports_data["player_id"], sports_data)
        payload["meta"] = self._meta(sports_data["player_id"], "player")
        payload["player_name"] = sports_data["player_name"]
        payload["team"] = sports_data["team"]
        payload["source_snapshots"] = {
            "sports_data_io": {
                "mode": sports_data.get("source_mode", "fallback"),
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
        payload = build_game_edge(sports_data["game_id"], sports_data, odds_data)
        payload["meta"] = self._meta(sports_data["game_id"], "game")
        payload["team"] = sports_data["team"]
        payload["opponent"] = sports_data["opponent"]
        payload["team_prediction"]["expected_points"] = round(
            payload["team_prediction"]["expected_points"] + sports_data["expected_points_adjustment"],
            1,
        )
        payload["team_prediction"]["source_mode"] = sports_data.get("source_mode", "fallback")
        payload["market_signals"]["sharp_money_index"] = round(odds_data["sharp_money_index"], 3)
        payload["market_signals"]["steam_move"] = odds_data["steam_move"]
        payload["market_signals"]["closing_line_value"] = round(odds_data["closing_line_value"], 3)
        payload["market_signals"]["source_mode"] = odds_data.get("source_mode", "fallback")
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

    def search_players(self, query: str = "", team: str | None = None) -> list[dict]:
        return search_players(query, team)

    def search_teams(self, query: str = "") -> list[dict]:
        return search_teams(query)

    def source_status(self) -> dict:
        return {
            "sports_data_io": self.sports_client.source_status(),
            "odds_api": self.odds_client.source_status(),
        }


def _recommended_stake(edge: float) -> str:
    absolute_edge = abs(edge)
    if absolute_edge < 0.03:
        return "no_play"
    if absolute_edge < 0.07:
        return "small"
    if absolute_edge < 0.12:
        return "medium"
    return "strong"
