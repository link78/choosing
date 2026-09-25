from __future__ import annotations

from datetime import datetime, timezone

from .data_sources import (
    FantasySportsAPIClient,
    MediaBroadcastClient,
    OddsAPIClient,
    SportsDataIOClient,
    search_players,
    search_teams,
)
from .prediction import build_game_edge, build_player_prediction, clamp


class PredictionService:
    def __init__(
        self,
        sports_client: SportsDataIOClient | None = None,
        odds_client: OddsAPIClient | None = None,
        media_client: MediaBroadcastClient | None = None,
        fantasy_client: FantasySportsAPIClient | None = None,
    ) -> None:
        self.sports_client = sports_client or SportsDataIOClient()
        self.odds_client = odds_client or OddsAPIClient()
        self.media_client = media_client or MediaBroadcastClient()
        self.fantasy_client = fantasy_client or FantasySportsAPIClient()

    def _meta(self, entity_id: str, entity_type: str) -> dict:
        return {
            "entity_id": entity_id,
            "entity_type": entity_type,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "advisory_only": True,
        }

    def get_player_prediction(self, player_id: str, overrides: dict | None = None) -> dict:
        sports_data = self.sports_client.fetch_player_context(player_id, overrides)
        media_data = self.media_client.fetch_player_context(player_id, overrides)
        fantasy_data = self.fantasy_client.fetch_player_context(player_id, overrides)
        player_inputs = dict(sports_data)
        player_inputs.update({key: value for key, value in media_data.items() if key != "source_mode"})
        player_inputs.update({key: value for key, value in fantasy_data.items() if key != "source_mode"})
        payload = build_player_prediction(sports_data["player_id"], player_inputs)
        payload["meta"] = self._meta(sports_data["player_id"], "player")
        payload["player_name"] = sports_data["player_name"]
        payload["team"] = sports_data["team"]
        payload["injury_status"] = sports_data.get("injury_status", "Unknown")
        payload["player_profile"] = _build_player_profile(payload, player_inputs)
        payload["source_snapshots"] = {
            "sports_data_io": {
                "mode": sports_data.get("source_mode", "fallback"),
                "recent_form": round(sports_data["recent_form"], 3),
                "workload": round(sports_data["workload"], 3),
                "injury_risk": round(sports_data["injury_risk"], 3),
                "injury_status": sports_data.get("injury_status", "Unknown"),
                "availability": round(sports_data["availability"], 3),
            },
            "media_broadcast": {
                "mode": media_data.get("source_mode", "fallback"),
                "media_sentiment": round(media_data["media_sentiment"], 3),
                "broadcast_exposure": round(media_data["broadcast_exposure"], 3),
                "narrative_pressure": round(media_data["narrative_pressure"], 3),
            },
            "fantasy_sports_api": {
                "mode": fantasy_data.get("source_mode", "fallback"),
                "fantasy_projection": round(fantasy_data["fantasy_projection"], 1),
                "fantasy_value_rating": round(fantasy_data["fantasy_value_rating"], 3),
                "ownership_projection": round(fantasy_data["ownership_projection"], 3),
            },
        }
        return payload

    def get_game_edge(self, game_id: str, sports_overrides: dict | None = None, odds_overrides: dict | None = None) -> dict:
        sports_data = self.sports_client.fetch_game_context(game_id, sports_overrides)
        odds_data = self.odds_client.fetch_game_market(game_id, odds_overrides)
        media_data = self.media_client.fetch_game_context(game_id, sports_overrides)
        fantasy_data = self.fantasy_client.fetch_game_context(game_id, sports_overrides)
        game_inputs = dict(sports_data)
        game_inputs.update({key: value for key, value in media_data.items() if key != "source_mode"})
        game_inputs.update({key: value for key, value in fantasy_data.items() if key != "source_mode"})
        payload = build_game_edge(sports_data["game_id"], game_inputs, odds_data)
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
        payload["source_snapshots"] = {
            "sports_data_io": {
                "mode": sports_data.get("source_mode", "fallback"),
                "team_form": round(sports_data["team_form"], 3),
                "pace": round(sports_data["pace"], 3),
                "efficiency": round(sports_data["efficiency"], 3),
                "injury_impact": round(sports_data["injury_impact"], 3),
            },
            "media_broadcast": {
                "mode": media_data.get("source_mode", "fallback"),
                "broadcast_heat": round(media_data["broadcast_heat"], 3),
                "audience_confidence": round(media_data["audience_confidence"], 3),
                "narrative_pressure": round(media_data["narrative_pressure"], 3),
            },
            "fantasy_sports_api": {
                "mode": fantasy_data.get("source_mode", "fallback"),
                "fantasy_market_support": round(fantasy_data["fantasy_market_support"], 3),
                "fantasy_points_total": round(fantasy_data["fantasy_points_total"], 1),
                "injury_leverage": round(fantasy_data["injury_leverage"], 3),
            },
            "odds_api": {
                "mode": odds_data.get("source_mode", "fallback"),
                "opening_odds": odds_data["opening_odds"],
                "current_odds": odds_data["current_odds"],
                "market_consensus": round(odds_data["market_consensus"], 3),
            },
        }
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
            "media_broadcast": self.media_client.source_status(),
            "fantasy_sports_api": self.fantasy_client.source_status(),
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


def _build_player_profile(prediction: dict, sports_data: dict) -> dict:
    expected_points = prediction["predictions"]["expected_points"]
    expected_minutes = prediction["predictions"]["expected_minutes"]
    availability_probability = prediction["predictions"]["availability_probability"]
    underperformance_risk = prediction["predictions"]["underperformance_risk"]
    readiness_score = clamp(
        availability_probability * 0.4
        + prediction["player_signals"]["recent_form"] * 0.25
        + prediction["player_signals"]["team_context"] * 0.2
        + prediction["player_signals"]["consistency"] * 0.15,
        0,
        1,
    )
    scoring_index = clamp(expected_points / 35, 0, 1)
    if expected_points >= 26:
        scoring_band = "High-volume scorer"
    elif expected_points >= 18:
        scoring_band = "Reliable scorer"
    else:
        scoring_band = "Low-volume scorer"

    if underperformance_risk >= 0.55:
        risk_level = "High"
    elif underperformance_risk >= 0.35:
        risk_level = "Moderate"
    else:
        risk_level = "Low"

    return {
        "readiness_score": round(readiness_score, 3),
        "scoring_index": round(scoring_index, 3),
        "scoring_band": scoring_band,
        "risk_level": risk_level,
        "projected_role": "Featured scorer" if expected_minutes >= 32 or expected_points >= 24 else "Rotation scorer",
        "injury_status": sports_data.get("injury_status", "Unknown"),
        "computation_data": {
            "recent_form": prediction["player_signals"]["recent_form"],
            "consistency": prediction["player_signals"]["consistency"],
            "team_context": prediction["player_signals"]["team_context"],
            "workload_fatigue": prediction["player_signals"]["workload_fatigue"],
            "matchup_difficulty": prediction["player_signals"]["matchup_difficulty"],
            "injury_risk": prediction["player_signals"]["injury_risk"],
            "broadcast_exposure": prediction["media_broadcast_signals"]["broadcast_exposure"],
            "narrative_pressure": prediction["media_broadcast_signals"]["narrative_pressure"],
            "fantasy_projection": prediction["fantasy_sports_signals"]["fantasy_projection"],
            "fantasy_value_rating": prediction["fantasy_sports_signals"]["fantasy_value_rating"],
            "injury_status": sports_data.get("injury_status", "Unknown"),
            "availability_probability": availability_probability,
            "expected_minutes": expected_minutes,
            "expected_points": expected_points,
            "source_mode": sports_data.get("source_mode", "fallback"),
        },
    }
