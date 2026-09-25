from __future__ import annotations

import json
import os
import re
from statistics import mean, pstdev
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .prediction import clamp, stable_float


PLAYER_DIRECTORY = [
    {"id": "42", "name": "Luka Doncic", "team": "Dallas Mavericks", "aliases": ["luka", "doncic"]},
    {"id": "7", "name": "Kevin Durant", "team": "Phoenix Suns", "aliases": ["durant", "kd"]},
    {"id": "15", "name": "Nikola Jokic", "team": "Denver Nuggets", "aliases": ["jokic", "nikola"]},
    {"id": "30", "name": "Stephen Curry", "team": "Golden State Warriors", "aliases": ["curry", "steph"]},
]

TEAM_DIRECTORY = [
    {
        "game_id": "suns-mavericks",
        "team": "Phoenix Suns",
        "opponent": "Dallas Mavericks",
        "aliases": ["phoenix", "suns"],
    },
    {
        "game_id": "nuggets-suns",
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


def _safe_float(value, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default: int | None = None) -> int | None:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _status_to_risk(status: str | None) -> float | None:
    if not status:
        return None
    normalized = _normalize(status)
    if any(token in normalized for token in {"out", "suspended", "inactive"}):
        return 0.9
    if any(token in normalized for token in {"doubtful", "questionable"}):
        return 0.65
    if any(token in normalized for token in {"probable", "day to day"}):
        return 0.35
    return 0.15


def _risk_to_status(injury_risk: float) -> str:
    if injury_risk >= 0.8:
        return "Out"
    if injury_risk >= 0.6:
        return "Questionable"
    if injury_risk >= 0.35:
        return "Monitor"
    return "Available"


def _http_get_json(url: str, headers: dict[str, str] | None = None, timeout: float = 5.0):
    request = Request(url, headers=headers or {})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


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


def _resolve_local_player(player_reference: str, team: str | None = None) -> dict:
    matches = search_players(player_reference, team)
    if matches:
        return matches[0]
    return {
        "id": _slugify(player_reference),
        "name": _titleize(player_reference),
        "team": _titleize(team) if team else "Open Market",
    }


def _resolve_local_team(team_reference: str) -> dict:
    matches = search_teams(team_reference)
    if matches:
        return matches[0]
    title = _titleize(team_reference)
    return {"game_id": _slugify(team_reference), "team": title, "opponent": "Market Average"}


class SportsDataIOClient:
    source_name = "SportsDataIO"

    def __init__(self, fetcher=None) -> None:
        self.fetcher = fetcher or _http_get_json
        self._last_call_succeeded = None
        self._last_error_message = None

    @property
    def api_key(self) -> str:
        return os.environ.get("SPORTSDATAIO_API_KEY", "").strip()

    @property
    def base_url(self) -> str:
        return os.environ.get("SPORTSDATAIO_BASE_URL", "https://api.sportsdata.io/v3/nba").rstrip("/")

    @property
    def season(self) -> str:
        return os.environ.get("SPORTSDATAIO_SEASON", "2024")

    def source_status(self) -> dict:
        configured = bool(self.api_key)
        return {
            "configured": configured,
            "mode": "live" if configured else "fallback",
            "last_call_succeeded": self._last_call_succeeded,
            "last_error_message": self._last_error_message if configured else "API key not configured",
        }

    def fetch_player_context(self, player_id: str, overrides: dict | None = None) -> dict:
        overrides = overrides or {}
        player = self.resolve_player(player_id, overrides.get("team"))
        injury_risk = overrides.get("injury_risk", stable_float(f"{player['id']}:injury", 0.05, 0.55))
        payload = {
            "player_id": player["id"],
            "player_name": player["name"],
            "team": player["team"],
            "recent_form": overrides.get("recent_form", stable_float(f"{player['id']}:form", 0.4, 0.95)),
            "workload": overrides.get("workload", stable_float(f"{player['id']}:workload", 0.2, 0.9)),
            "injury_risk": injury_risk,
            "injury_status": overrides.get("injury_status", _risk_to_status(injury_risk)),
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
        live_payload = self._fetch_live_player_context(player)
        if live_payload:
            payload.update({key: value for key, value in live_payload.items() if value is not None})
            payload["source_mode"] = "live"
        else:
            payload["source_mode"] = "fallback"
        return payload

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
        live_payload = self._fetch_live_team_context(game)
        if live_payload:
            payload.update({key: value for key, value in live_payload.items() if value is not None})
            payload["source_mode"] = "live"
        else:
            payload["source_mode"] = "fallback"
        return payload

    def resolve_player(self, player_reference: str, team: str | None = None) -> dict:
        if self.api_key:
            live_match = self._resolve_live_player(player_reference, team)
            if live_match:
                return live_match
        return _resolve_local_player(player_reference, team)

    def resolve_team(self, team_reference: str) -> dict:
        if self.api_key:
            live_match = self._resolve_live_team(team_reference)
            if live_match:
                return live_match
        return _resolve_local_team(team_reference)

    def _request(self, path: str, params: dict | None = None):
        if not self.api_key:
            self._last_call_succeeded = None
            self._last_error_message = "API key not configured"
            return None
        query = dict(params or {})
        query["key"] = self.api_key
        url = f"{self.base_url}/{path.lstrip('/')}"
        if query:
            url = f"{url}?{urlencode(query)}"
        try:
            payload = self.fetcher(url, headers={"Accept": "application/json"})
            self._last_call_succeeded = True
            self._last_error_message = None
            return payload
        except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
            self._last_call_succeeded = False
            self._last_error_message = str(exc)
            return None

    def _resolve_live_player(self, player_reference: str, team: str | None = None) -> dict | None:
        normalized_query = _normalize(player_reference)
        normalized_team = _normalize(team or "")
        for path in ("scores/json/Players", "scores/json/PlayersBasic"):
            players = self._request(path)
            if not isinstance(players, list):
                continue
            for entry in players:
                name = entry.get("Name") or " ".join(
                    part for part in [entry.get("FirstName"), entry.get("LastName")] if part
                )
                team_name = entry.get("Team") or entry.get("TeamName") or entry.get("TeamKey") or ""
                searchable = [_normalize(str(entry.get("PlayerID", ""))), _normalize(name), _normalize(team_name)]
                if normalized_query and not any(normalized_query in candidate for candidate in searchable):
                    continue
                if normalized_team and normalized_team not in _normalize(team_name):
                    continue
                return {
                    "id": str(entry.get("PlayerID") or _slugify(name)),
                    "name": name or _titleize(player_reference),
                    "team": team_name or (_titleize(team) if team else "Open Market"),
                }
        return None

    def _resolve_live_team(self, team_reference: str) -> dict | None:
        normalized_query = _normalize(team_reference)
        for path in (f"stats/json/TeamSeasonStats/{self.season}", f"scores/json/Standings/{self.season}"):
            teams = self._request(path)
            if not isinstance(teams, list):
                continue
            for entry in teams:
                name = entry.get("Name") or entry.get("City") or entry.get("Team") or entry.get("Key") or ""
                key = entry.get("Key") or entry.get("Team") or entry.get("Name") or name
                if normalized_query and normalized_query not in _normalize(f"{name} {key}"):
                    continue
                return {
                    "game_id": _slugify(name or key),
                    "team": name or _titleize(team_reference),
                    "opponent": "Market Average",
                    "team_key": entry.get("Key") or entry.get("Team"),
                }
        return None

    def _fetch_live_player_context(self, player: dict) -> dict | None:
        player_id = player.get("id")
        if not self.api_key or not player_id:
            return None

        season_stats = self._request(f"stats/json/PlayerSeasonStatsByPlayer/{self.season}/{player_id}")
        recent_games = self._request(f"stats/json/PlayerGameStatsByPlayerID/{player_id}/5")
        injuries = self._request("scores/json/Injuries")

        if not isinstance(recent_games, list) and not isinstance(season_stats, dict):
            return None

        recent_games = recent_games if isinstance(recent_games, list) else []
        season_stats = season_stats if isinstance(season_stats, dict) else {}
        points = [_safe_float(game.get("Points")) for game in recent_games]
        points = [value for value in points if value is not None]
        minutes = [_safe_float(game.get("Minutes")) for game in recent_games]
        minutes = [value for value in minutes if value is not None]
        fouls = [_safe_float(game.get("PersonalFouls")) for game in recent_games]
        fouls = [value for value in fouls if value is not None]

        season_points = _safe_float(season_stats.get("Points"), 0.0)
        season_games = _safe_float(season_stats.get("Games"), max(len(recent_games), 1)) or 1
        baseline_points = season_points / max(season_games, 1)
        recent_points = mean(points) if points else baseline_points
        recent_form = clamp(0.5 + ((recent_points - baseline_points) / max(baseline_points, 8)) * 0.3, 0.05, 0.99)

        workload = clamp((mean(minutes) if minutes else _safe_float(season_stats.get("Minutes"), 30.0)) / 40, 0.05, 0.99)
        consistency = clamp(
            1 - ((pstdev(points) if len(points) > 1 else baseline_points * 0.1) / max(recent_points or baseline_points or 1, 1)),
            0.05,
            0.99,
        )
        injury_status = None
        if isinstance(injuries, list):
            for injury in injuries:
                if str(injury.get("PlayerID")) == str(player_id):
                    injury_status = injury.get("Status") or injury.get("InjuryStatus")
                    break
        injury_risk = _status_to_risk(injury_status)
        if injury_risk is None:
            injury_risk = clamp((1 - consistency) * 0.45 + workload * 0.2, 0.05, 0.8)
        return {
            "recent_form": recent_form,
            "expected_points": recent_points,
            "workload": workload,
            "injury_risk": injury_risk,
            "injury_status": injury_status or _risk_to_status(injury_risk),
            "consistency": consistency,
            "availability": clamp(1 - injury_risk * 0.8, 0.05, 0.99),
            "fouls_cards": clamp((mean(fouls) if fouls else 2.0) / 6, 0, 0.99),
        }

    def _fetch_live_team_context(self, game: dict) -> dict | None:
        if not self.api_key:
            return None
        team_stats = self._request(f"stats/json/TeamSeasonStats/{self.season}")
        if not isinstance(team_stats, list):
            return None
        match = None
        normalized_team = _normalize(game["team"])
        for entry in team_stats:
            name = entry.get("Name") or entry.get("City") or entry.get("Team") or entry.get("Key") or ""
            key = entry.get("Key") or entry.get("Team") or ""
            if normalized_team in _normalize(f"{name} {key}"):
                match = entry
                break
        if not match:
            return None
        pace = _safe_float(match.get("Possessions"), 98.0) / 120
        points_per_game = _safe_float(match.get("PointsPerGame"), 108.0)
        offensive_rating = _safe_float(match.get("OffensiveRating"), points_per_game)
        defensive_rating = _safe_float(match.get("DefensiveRating"), 108.0)
        win_pct = _safe_float(match.get("Percentage"), 0.5)
        if win_pct is None:
            wins = _safe_float(match.get("Wins"), 0.0) or 0.0
            losses = _safe_float(match.get("Losses"), 0.0) or 0.0
            total = max(wins + losses, 1)
            win_pct = wins / total
        return {
            "team_form": clamp(win_pct, 0.05, 0.99),
            "pace": clamp(pace, 0.05, 0.99),
            "efficiency": clamp((offensive_rating or 108.0) / max((offensive_rating or 108.0) + (defensive_rating or 108.0), 1), 0.05, 0.99),
            "injury_impact": clamp(max((defensive_rating or 108.0) - (offensive_rating or 108.0), 0) / 40, 0.02, 0.8),
            "expected_points_adjustment": clamp(((points_per_game or 108.0) - 108) / 2, -8, 8),
        }


class OddsAPIClient:
    source_name = "The Odds API"

    def __init__(self, fetcher=None) -> None:
        self.fetcher = fetcher or _http_get_json
        self._last_call_succeeded = None
        self._last_error_message = None

    @property
    def api_key(self) -> str:
        return os.environ.get("ODDS_API_KEY", "").strip()

    @property
    def base_url(self) -> str:
        return os.environ.get("ODDS_API_BASE_URL", "https://api.the-odds-api.com/v4").rstrip("/")

    @property
    def sport(self) -> str:
        return os.environ.get("ODDS_API_SPORT", "basketball_nba")

    def source_status(self) -> dict:
        configured = bool(self.api_key)
        return {
            "configured": configured,
            "mode": "live" if configured else "fallback",
            "last_call_succeeded": self._last_call_succeeded,
            "last_error_message": self._last_error_message if configured else "API key not configured",
        }

    def fetch_game_market(self, game_id: str, overrides: dict | None = None) -> dict:
        overrides = overrides or {}
        game = SportsDataIOClient().resolve_team(game_id)
        opening_odds = int(overrides.get("opening_odds", -108))
        current_odds = int(overrides.get("current_odds", opening_odds))
        line_movement = overrides.get("line_movement")
        if line_movement is None:
            line_movement = round(current_odds - opening_odds, 3)
        payload = {
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
        live_payload = self._fetch_live_market(game)
        if live_payload:
            payload.update({key: value for key, value in live_payload.items() if value is not None})
            payload["source_mode"] = "live"
        else:
            payload["source_mode"] = "fallback"
        return payload

    def _request(self, path: str, params: dict | None = None):
        if not self.api_key:
            self._last_call_succeeded = None
            self._last_error_message = "API key not configured"
            return None
        query = {
            "apiKey": self.api_key,
            "regions": os.environ.get("ODDS_API_REGIONS", "us"),
            "markets": os.environ.get("ODDS_API_MARKETS", "h2h"),
            "oddsFormat": os.environ.get("ODDS_API_ODDS_FORMAT", "american"),
        }
        query.update(params or {})
        url = f"{self.base_url}/{path.lstrip('/')}"
        url = f"{url}?{urlencode(query)}"
        try:
            payload = self.fetcher(url, headers={"Accept": "application/json"})
            self._last_call_succeeded = True
            self._last_error_message = None
            return payload
        except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
            self._last_call_succeeded = False
            self._last_error_message = str(exc)
            return None

    def _fetch_live_market(self, game: dict) -> dict | None:
        odds_payload = self._request(f"sports/{self.sport}/odds")
        if not isinstance(odds_payload, list):
            return None
        normalized_team = _normalize(game["team"])
        for event in odds_payload:
            home = event.get("home_team") or ""
            away = event.get("away_team") or ""
            if normalized_team not in _normalize(f"{home} {away}"):
                continue
            prices = []
            for bookmaker in event.get("bookmakers", []):
                for market in bookmaker.get("markets", []):
                    if market.get("key") != "h2h":
                        continue
                    for outcome in market.get("outcomes", []):
                        if normalized_team not in _normalize(outcome.get("name", "")):
                            continue
                        price = _safe_int(outcome.get("price"))
                        if price:
                            prices.append(price)
            if not prices:
                return None
            implied_probabilities = []
            for price in prices:
                if price > 0:
                    implied_probabilities.append(100 / (price + 100))
                else:
                    implied_probabilities.append(abs(price) / (abs(price) + 100))
            current_odds = prices[0]
            consensus_probability = clamp(mean(implied_probabilities), 0.02, 0.98)
            sharp_money_index = clamp(0.5 + (consensus_probability - 0.5) * 1.2, 0.05, 0.99)
            return {
                "game_id": _slugify(f"{home}-vs-{away}"),
                "team": home if normalized_team in _normalize(home) else away,
                "opponent": away if normalized_team in _normalize(home) else home,
                "opening_odds": current_odds,
                "current_odds": current_odds,
                "market_consensus": consensus_probability,
                "line_movement": 0,
                "sharp_money_index": sharp_money_index,
                "steam_move": len(set(prices)) > 1,
                "closing_line_value": 0.0,
                "implied_probability": consensus_probability,
            }
        return None


class MediaBroadcastClient:
    source_name = "Media & Broadcast"

    def __init__(self, fetcher=None) -> None:
        self.fetcher = fetcher or _http_get_json
        self._last_call_succeeded = None
        self._last_error_message = None

    @property
    def api_key(self) -> str:
        return os.environ.get("MEDIA_BROADCAST_API_KEY", "").strip() or os.environ.get(
            "SPORTSDATAIO_API_KEY", ""
        ).strip()

    @property
    def base_url(self) -> str:
        return os.environ.get("MEDIA_BROADCAST_BASE_URL", "").strip().rstrip("/") or os.environ.get(
            "SPORTSDATAIO_BASE_URL", "https://api.sportsdata.io/v3/nba"
        ).rstrip("/")

    @property
    def season(self) -> str:
        return os.environ.get("SPORTSDATAIO_SEASON", "2024")

    def source_status(self) -> dict:
        configured = bool(self.api_key)
        return {
            "configured": configured,
            "mode": "live" if configured else "fallback",
            "last_call_succeeded": self._last_call_succeeded,
            "last_error_message": self._last_error_message if configured else "API key not configured",
        }

    def fetch_player_context(self, player_id: str, overrides: dict | None = None) -> dict:
        overrides = overrides or {}
        player = _resolve_local_player(player_id, overrides.get("team"))
        payload = {
            "player_id": player["id"],
            "player_name": player["name"],
            "team": player["team"],
            "media_sentiment": overrides.get("media_sentiment", stable_float(f"{player['id']}:media", 0.35, 0.88)),
            "broadcast_exposure": overrides.get(
                "broadcast_exposure",
                stable_float(f"{player['id']}:broadcast", 0.25, 0.95),
            ),
            "narrative_pressure": overrides.get(
                "narrative_pressure",
                stable_float(f"{player['id']}:narrative", 0.08, 0.72),
            ),
        }
        live_payload = self._fetch_live_player_context(player)
        if live_payload:
            payload.update({key: value for key, value in live_payload.items() if value is not None})
            payload["source_mode"] = "live"
        else:
            payload["source_mode"] = "fallback"
        return payload

    def fetch_game_context(self, game_id: str, overrides: dict | None = None) -> dict:
        overrides = overrides or {}
        game = _resolve_local_team(game_id)
        payload = {
            "game_id": game["game_id"],
            "team": game["team"],
            "opponent": game["opponent"],
            "broadcast_heat": overrides.get("broadcast_heat", stable_float(f"{game['game_id']}:heat", 0.3, 0.92)),
            "audience_confidence": overrides.get(
                "audience_confidence",
                stable_float(f"{game['game_id']}:audience", 0.35, 0.84),
            ),
            "narrative_pressure": overrides.get(
                "narrative_pressure",
                stable_float(f"{game['game_id']}:narrative", 0.08, 0.7),
            ),
        }
        live_payload = self._fetch_live_game_context(game)
        if live_payload:
            payload.update({key: value for key, value in live_payload.items() if value is not None})
            payload["source_mode"] = "live"
        else:
            payload["source_mode"] = "fallback"
        return payload

    def _request(self, path: str):
        if not self.api_key:
            self._last_call_succeeded = None
            self._last_error_message = "API key not configured"
            return None
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            payload = self.fetcher(f"{url}?{urlencode({'key': self.api_key})}", headers={"Accept": "application/json"})
            self._last_call_succeeded = True
            self._last_error_message = None
            return payload
        except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
            self._last_call_succeeded = False
            self._last_error_message = str(exc)
            return None

    def _fetch_live_player_context(self, player: dict) -> dict | None:
        season_stats = self._request(f"stats/json/PlayerSeasonStatsByPlayer/{self.season}/{player['id']}")
        recent_games = self._request(f"stats/json/PlayerGameStatsByPlayerID/{player['id']}/5")
        if not isinstance(season_stats, dict) and not isinstance(recent_games, list):
            return None
        season_stats = season_stats if isinstance(season_stats, dict) else {}
        recent_games = recent_games if isinstance(recent_games, list) else []
        points = [_safe_float(game.get("Points")) for game in recent_games]
        points = [value for value in points if value is not None]
        minutes = [_safe_float(game.get("Minutes")) for game in recent_games]
        minutes = [value for value in minutes if value is not None]
        baseline_points = (_safe_float(season_stats.get("Points"), 0.0) or 0.0) / max(
            _safe_float(season_stats.get("Games"), max(len(recent_games), 1)) or 1,
            1,
        )
        recent_points = mean(points) if points else baseline_points
        recent_minutes = mean(minutes) if minutes else _safe_float(season_stats.get("Minutes"), 34.0) or 34.0
        return {
            "media_sentiment": clamp(0.45 + recent_points / 50, 0.1, 0.99),
            "broadcast_exposure": clamp(recent_minutes / 42, 0.1, 0.99),
            "narrative_pressure": clamp(abs(recent_points - baseline_points) / max(baseline_points or 12, 12), 0.05, 0.9),
        }

    def _fetch_live_game_context(self, game: dict) -> dict | None:
        team_stats = self._request(f"stats/json/TeamSeasonStats/{self.season}")
        if not isinstance(team_stats, list):
            return None
        match = None
        normalized_team = _normalize(game["team"])
        for entry in team_stats:
            name = entry.get("Name") or entry.get("City") or entry.get("Team") or entry.get("Key") or ""
            key = entry.get("Key") or entry.get("Team") or ""
            if normalized_team in _normalize(f"{name} {key}"):
                match = entry
                break
        if not match:
            return None
        points_per_game = _safe_float(match.get("PointsPerGame"), 108.0) or 108.0
        win_pct = _safe_float(match.get("Percentage"), 0.5)
        if win_pct is None:
            wins = _safe_float(match.get("Wins"), 0.0) or 0.0
            losses = _safe_float(match.get("Losses"), 0.0) or 0.0
            win_pct = wins / max(wins + losses, 1)
        return {
            "broadcast_heat": clamp(points_per_game / 135, 0.1, 0.99),
            "audience_confidence": clamp(win_pct, 0.05, 0.99),
            "narrative_pressure": clamp(abs(points_per_game - 112) / 35, 0.05, 0.9),
        }


class FantasySportsAPIClient:
    source_name = "Fantasy Sports API"

    def __init__(self, fetcher=None) -> None:
        self.fetcher = fetcher or _http_get_json
        self._last_call_succeeded = None
        self._last_error_message = None

    @property
    def api_key(self) -> str:
        return os.environ.get("FANTASY_SPORTS_API_KEY", "").strip() or os.environ.get(
            "SPORTSDATAIO_API_KEY", ""
        ).strip()

    @property
    def base_url(self) -> str:
        return os.environ.get("FANTASY_SPORTS_BASE_URL", "").strip().rstrip("/") or os.environ.get(
            "SPORTSDATAIO_BASE_URL", "https://api.sportsdata.io/v3/nba"
        ).rstrip("/")

    @property
    def season(self) -> str:
        return os.environ.get("SPORTSDATAIO_SEASON", "2024")

    def source_status(self) -> dict:
        configured = bool(self.api_key)
        return {
            "configured": configured,
            "mode": "live" if configured else "fallback",
            "last_call_succeeded": self._last_call_succeeded,
            "last_error_message": self._last_error_message if configured else "API key not configured",
        }

    def fetch_player_context(self, player_id: str, overrides: dict | None = None) -> dict:
        overrides = overrides or {}
        player = _resolve_local_player(player_id, overrides.get("team"))
        payload = {
            "player_id": player["id"],
            "player_name": player["name"],
            "team": player["team"],
            "fantasy_projection": overrides.get(
                "fantasy_projection",
                stable_float(f"{player['id']}:fantasy_projection", 14, 42),
            ),
            "fantasy_value_rating": overrides.get(
                "fantasy_value_rating",
                stable_float(f"{player['id']}:fantasy_value", 0.28, 0.94),
            ),
            "ownership_projection": overrides.get(
                "ownership_projection",
                stable_float(f"{player['id']}:ownership", 0.1, 0.65),
            ),
        }
        live_payload = self._fetch_live_player_context(player)
        if live_payload:
            payload.update({key: value for key, value in live_payload.items() if value is not None})
            payload["source_mode"] = "live"
        else:
            payload["source_mode"] = "fallback"
        return payload

    def fetch_game_context(self, game_id: str, overrides: dict | None = None) -> dict:
        overrides = overrides or {}
        game = _resolve_local_team(game_id)
        payload = {
            "game_id": game["game_id"],
            "team": game["team"],
            "opponent": game["opponent"],
            "fantasy_market_support": overrides.get(
                "fantasy_market_support",
                stable_float(f"{game['game_id']}:fantasy_support", 0.3, 0.88),
            ),
            "fantasy_points_total": overrides.get(
                "fantasy_points_total",
                stable_float(f"{game['game_id']}:fantasy_total", 198, 244),
            ),
            "injury_leverage": overrides.get(
                "injury_leverage",
                stable_float(f"{game['game_id']}:injury_leverage", 0.05, 0.7),
            ),
        }
        live_payload = self._fetch_live_game_context(game)
        if live_payload:
            payload.update({key: value for key, value in live_payload.items() if value is not None})
            payload["source_mode"] = "live"
        else:
            payload["source_mode"] = "fallback"
        return payload

    def _request(self, path: str):
        if not self.api_key:
            self._last_call_succeeded = None
            self._last_error_message = "API key not configured"
            return None
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            payload = self.fetcher(f"{url}?{urlencode({'key': self.api_key})}", headers={"Accept": "application/json"})
            self._last_call_succeeded = True
            self._last_error_message = None
            return payload
        except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
            self._last_call_succeeded = False
            self._last_error_message = str(exc)
            return None

    def _fetch_live_player_context(self, player: dict) -> dict | None:
        season_stats = self._request(f"stats/json/PlayerSeasonStatsByPlayer/{self.season}/{player['id']}")
        recent_games = self._request(f"stats/json/PlayerGameStatsByPlayerID/{player['id']}/5")
        if not isinstance(season_stats, dict) and not isinstance(recent_games, list):
            return None
        season_stats = season_stats if isinstance(season_stats, dict) else {}
        recent_games = recent_games if isinstance(recent_games, list) else []
        points = [_safe_float(game.get("Points")) for game in recent_games]
        points = [value for value in points if value is not None]
        minutes = [_safe_float(game.get("Minutes")) for game in recent_games]
        minutes = [value for value in minutes if value is not None]
        recent_points = mean(points) if points else _safe_float(season_stats.get("Points"), 20.0) or 20.0
        recent_minutes = mean(minutes) if minutes else _safe_float(season_stats.get("Minutes"), 34.0) or 34.0
        return {
            "fantasy_projection": round(recent_points * 1.2 + recent_minutes * 0.45, 1),
            "fantasy_value_rating": clamp(recent_points / 35, 0.1, 0.99),
            "ownership_projection": clamp(recent_minutes / 60, 0.05, 0.85),
        }

    def _fetch_live_game_context(self, game: dict) -> dict | None:
        team_stats = self._request(f"stats/json/TeamSeasonStats/{self.season}")
        if not isinstance(team_stats, list):
            return None
        match = None
        normalized_team = _normalize(game["team"])
        for entry in team_stats:
            name = entry.get("Name") or entry.get("City") or entry.get("Team") or entry.get("Key") or ""
            key = entry.get("Key") or entry.get("Team") or ""
            if normalized_team in _normalize(f"{name} {key}"):
                match = entry
                break
        if not match:
            return None
        points_per_game = _safe_float(match.get("PointsPerGame"), 108.0) or 108.0
        possessions = _safe_float(match.get("Possessions"), 98.0) or 98.0
        offensive_rating = _safe_float(match.get("OffensiveRating"), points_per_game) or points_per_game
        defensive_rating = _safe_float(match.get("DefensiveRating"), 108.0) or 108.0
        return {
            "fantasy_market_support": clamp(offensive_rating / 130, 0.1, 0.99),
            "fantasy_points_total": round(points_per_game + possessions + 20, 1),
            "injury_leverage": clamp(max(defensive_rating - offensive_rating, 0) / 40, 0.02, 0.85),
        }
