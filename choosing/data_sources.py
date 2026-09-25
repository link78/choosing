from __future__ import annotations

from .prediction import clamp, stable_float


class SportsDataIOClient:
    source_name = "SportsDataIO"

    def fetch_player_context(self, player_id: str, overrides: dict | None = None) -> dict:
        overrides = overrides or {}
        return {
            "player_id": player_id,
            "recent_form": overrides.get("recent_form", stable_float(f"{player_id}:form", 0.4, 0.95)),
            "workload": overrides.get("workload", stable_float(f"{player_id}:workload", 0.2, 0.9)),
            "injury_risk": overrides.get("injury_risk", stable_float(f"{player_id}:injury", 0.05, 0.55)),
            "consistency": overrides.get("consistency", stable_float(f"{player_id}:consistency", 0.35, 0.95)),
            "matchup_difficulty": overrides.get(
                "matchup_difficulty",
                stable_float(f"{player_id}:matchup", 0.2, 0.9),
            ),
            "team_context": overrides.get("team_context", stable_float(f"{player_id}:team", 0.3, 0.85)),
            "availability": overrides.get("availability", stable_float(f"{player_id}:availability", 0.55, 0.99)),
            "effort_change": overrides.get("effort_change", stable_float(f"{player_id}:effort", -0.2, 0.2)),
            "fouls_cards": overrides.get("fouls_cards", stable_float(f"{player_id}:discipline", 0.0, 0.7)),
            "team_instability": overrides.get(
                "team_instability",
                stable_float(f"{player_id}:instability", 0.05, 0.6),
            ),
            "media_sentiment": overrides.get("media_sentiment", stable_float(f"{player_id}:media", 0.3, 0.8)),
        }

    def fetch_game_context(self, game_id: str, overrides: dict | None = None) -> dict:
        overrides = overrides or {}
        payload = {
            "game_id": game_id,
            "team_form": overrides.get("team_form", stable_float(f"{game_id}:team_form", 0.35, 0.9)),
            "pace": overrides.get("pace", stable_float(f"{game_id}:pace", 0.35, 0.8)),
            "efficiency": overrides.get("efficiency", stable_float(f"{game_id}:efficiency", 0.4, 0.9)),
            "injury_impact": overrides.get("injury_impact", stable_float(f"{game_id}:injury_impact", 0.05, 0.5)),
            "expected_points_adjustment": overrides.get(
                "expected_points_adjustment",
                stable_float(f"{game_id}:points_adj", -6, 6),
            ),
        }
        if "model_probability" in overrides:
            payload["model_probability"] = overrides["model_probability"]
        return payload


class OddsAPIClient:
    source_name = "The Odds API"

    def fetch_game_market(self, game_id: str, overrides: dict | None = None) -> dict:
        overrides = overrides or {}
        opening_odds = int(overrides.get("opening_odds", -108))
        current_odds = int(overrides.get("current_odds", opening_odds))
        line_movement = overrides.get("line_movement")
        if line_movement is None:
            line_movement = round(current_odds - opening_odds, 3)
        return {
            "game_id": game_id,
            "opening_odds": opening_odds,
            "current_odds": current_odds,
            "market_consensus": overrides.get(
                "market_consensus",
                stable_float(f"{game_id}:consensus", 0.35, 0.7),
            ),
            "line_movement": line_movement,
            "sharp_money_index": overrides.get(
                "sharp_money_index",
                stable_float(f"{game_id}:sharp", 0.2, 0.95),
            ),
            "steam_move": overrides.get("steam_move", stable_float(f"{game_id}:steam", 0.0, 1.0) > 0.7),
            "closing_line_value": overrides.get(
                "closing_line_value",
                clamp(stable_float(f"{game_id}:clv", -0.08, 0.08), -0.15, 0.15),
            ),
        }
