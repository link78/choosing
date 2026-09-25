from __future__ import annotations

import re

from .prediction import clamp, stable_float


PLAYER_DIRECTORY = [
    {"id": "42", "name": "Jayson Tatum", "team": "Boston Celtics", "aliases": ["tatum", "jayson"]},
    {"id": "7", "name": "Kevin Durant", "team": "Phoenix Suns", "aliases": ["durant", "kd"]},
    {"id": "15", "name": "Nikola Jokic", "team": "Denver Nuggets", "aliases": ["jokic", "nikola"]},
    {"id": "30", "name": "Stephen Curry", "team": "Golden State Warriors", "aliases": ["curry", "steph"]},
]

TEAM_DIRECTORY = [
    {
        "game_id": "finals",
        "team": "Boston Celtics",
        "opponent": "Dallas Mavericks",
        "aliases": ["boston", "celtics"],
    },
    {
        "game_id": "demo",
        "team": "Denver Nuggets",
        "opponent": "Phoenix Suns",
        "aliases": ["denver", "nuggets"],
    },
    {
        "game_id": "warriors-lakers",
        "team": "Golden State Warriors",
        "opponent": "Los Angeles Lakers",
        "aliases": ["golden state", "warriors"],
    },
]


def _normalize(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "unknown"


def _titleize(value: str) -> str:
    return " ".join(part.capitalize() for part in value.split())


def search_players(query: str = "", team: str | None = None) -> list[dict]:
    normalized_query = _normalize(query)
    normalized_team = _normalize(team or "")
    results = []
    for entry in PLAYER_DIRECTORY:
        searchable = [_normalize(entry["id"]), _normalize(entry["name"]), _normalize(entry["team"])]
        searchable.extend(_normalize(alias) for alias in entry["aliases"])
        if normalized_query and not any(normalized_query in candidate for candidate in searchable):
            continue
        if normalized_team and normalized_team not in _normalize(entry["team"]):
            continue
        results.append({"id": entry["id"], "name": entry["name"], "team": entry["team"]})
    return results


def search_teams(query: str = "") -> list[dict]:
    normalized_query = _normalize(query)
    results = []
    for entry in TEAM_DIRECTORY:
        searchable = [_normalize(entry["game_id"]), _normalize(entry["team"]), _normalize(entry["opponent"])]
        searchable.extend(_normalize(alias) for alias in entry["aliases"])
        if normalized_query and not any(normalized_query in candidate for candidate in searchable):
            continue
        results.append(
            {
                "game_id": entry["game_id"],
                "team": entry["team"],
                "opponent": entry["opponent"],
            }
        )
    return results


class SportsDataIOClient:
    source_name = "SportsDataIO"

    def fetch_player_context(self, player_id: str, overrides: dict | None = None) -> dict:
        overrides = overrides or {}
        player = self.resolve_player(player_id, overrides.get("team"))
        return {
            "player_id": player["id"],
            "player_name": player["name"],
            "team": player["team"],
            "recent_form": overrides.get("recent_form", stable_float(f"{player['id']}:form", 0.4, 0.95)),
            "workload": overrides.get("workload", stable_float(f"{player['id']}:workload", 0.2, 0.9)),
            "injury_risk": overrides.get("injury_risk", stable_float(f"{player['id']}:injury", 0.05, 0.55)),
            "consistency": overrides.get("consistency", stable_float(f"{player['id']}:consistency", 0.35, 0.95)),
            "matchup_difficulty": overrides.get(
                "matchup_difficulty",
                stable_float(f"{player['id']}:matchup", 0.2, 0.9),
            ),
            "team_context": overrides.get("team_context", stable_float(f"{player['id']}:team", 0.3, 0.85)),
            "availability": overrides.get("availability", stable_float(f"{player['id']}:availability", 0.55, 0.99)),
            "effort_change": overrides.get("effort_change", stable_float(f"{player['id']}:effort", -0.2, 0.2)),
            "fouls_cards": overrides.get("fouls_cards", stable_float(f"{player['id']}:discipline", 0.0, 0.7)),
            "team_instability": overrides.get(
                "team_instability",
                stable_float(f"{player['id']}:instability", 0.05, 0.6),
            ),
            "media_sentiment": overrides.get("media_sentiment", stable_float(f"{player['id']}:media", 0.3, 0.8)),
        }

    def fetch_game_context(self, game_id: str, overrides: dict | None = None) -> dict:
        overrides = overrides or {}
        game = self.resolve_team(game_id)
        payload = {
            "game_id": game["game_id"],
            "team": game["team"],
            "opponent": game["opponent"],
            "team_form": overrides.get("team_form", stable_float(f"{game['game_id']}:team_form", 0.35, 0.9)),
            "pace": overrides.get("pace", stable_float(f"{game['game_id']}:pace", 0.35, 0.8)),
            "efficiency": overrides.get("efficiency", stable_float(f"{game['game_id']}:efficiency", 0.4, 0.9)),
            "injury_impact": overrides.get("injury_impact", stable_float(f"{game['game_id']}:injury_impact", 0.05, 0.5)),
            "expected_points_adjustment": overrides.get(
                "expected_points_adjustment",
                stable_float(f"{game['game_id']}:points_adj", -6, 6),
            ),
        }
        if "model_probability" in overrides:
            payload["model_probability"] = overrides["model_probability"]
        return payload

    def resolve_player(self, player_reference: str, team: str | None = None) -> dict:
        matches = search_players(player_reference, team)
        if matches:
            return matches[0]
        return {
            "id": _slugify(player_reference),
            "name": _titleize(player_reference),
            "team": _titleize(team) if team else "Open Market",
        }

    def resolve_team(self, team_reference: str) -> dict:
        matches = search_teams(team_reference)
        if matches:
            return matches[0]
        title = _titleize(team_reference)
        return {"game_id": _slugify(team_reference), "team": title, "opponent": "Market Average"}


class OddsAPIClient:
    source_name = "The Odds API"

    def fetch_game_market(self, game_id: str, overrides: dict | None = None) -> dict:
        overrides = overrides or {}
        game = SportsDataIOClient().resolve_team(game_id)
        opening_odds = int(overrides.get("opening_odds", -108))
        current_odds = int(overrides.get("current_odds", opening_odds))
        line_movement = overrides.get("line_movement")
        if line_movement is None:
            line_movement = round(current_odds - opening_odds, 3)
        return {
            "game_id": game["game_id"],
            "team": game["team"],
            "opponent": game["opponent"],
            "opening_odds": opening_odds,
            "current_odds": current_odds,
            "market_consensus": overrides.get(
                "market_consensus",
                stable_float(f"{game['game_id']}:consensus", 0.35, 0.7),
            ),
            "line_movement": line_movement,
            "sharp_money_index": overrides.get(
                "sharp_money_index",
                stable_float(f"{game['game_id']}:sharp", 0.2, 0.95),
            ),
            "steam_move": overrides.get("steam_move", stable_float(f"{game['game_id']}:steam", 0.0, 1.0) > 0.7),
            "closing_line_value": overrides.get(
                "closing_line_value",
                clamp(stable_float(f"{game['game_id']}:clv", -0.08, 0.08), -0.15, 0.15),
            ),
        }
