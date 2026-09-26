from __future__ import annotations

import json
import math
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from statistics import mean, pstdev
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .prediction import clamp, stable_float

SPORTSDATAIO_SPORT_PATHS = {
    "basketball_nba": "nba",
    "americanfootball_nfl": "nfl",
    "baseball_mlb": "mlb",
    "basketball_ncaab": "cbb",
    "tennis_*": "tennis",
}


PLAYER_DIRECTORY = [
    {"id": "42", "name": "Luka Doncic", "team": "Dallas Mavericks", "sport_key": "basketball_nba", "aliases": ["luka", "doncic"]},
    {"id": "7", "name": "Kevin Durant", "team": "Phoenix Suns", "sport_key": "basketball_nba", "aliases": ["durant", "kd"]},
    {"id": "15", "name": "Nikola Jokic", "team": "Denver Nuggets", "sport_key": "basketball_nba", "aliases": ["jokic", "nikola"]},
    {"id": "30", "name": "Stephen Curry", "team": "Golden State Warriors", "sport_key": "basketball_nba", "aliases": ["curry", "steph"]},
    {"id": "34", "name": "Giannis Antetokounmpo", "team": "Milwaukee Bucks", "sport_key": "basketball_nba", "aliases": ["giannis", "antetokounmpo"]},
    {"id": "35", "name": "Jayson Brunson", "team": "New York Knicks", "sport_key": "basketball_nba", "aliases": ["brunson", "jalen"]},
    {"id": "36", "name": "Shai Gilgeous-Alexander", "team": "Oklahoma City Thunder", "sport_key": "basketball_nba", "aliases": ["shai", "gilgeous"]},
    {"id": "37", "name": "Anthony Edwards", "team": "Minnesota Timberwolves", "sport_key": "basketball_nba", "aliases": ["edwards", "ant"]},
    {"id": "38", "name": "LeBron James", "team": "Los Angeles Lakers", "sport_key": "basketball_nba", "aliases": ["lebron", "james"]},
    {"id": "39", "name": "Devin Booker", "team": "Phoenix Suns", "sport_key": "basketball_nba", "aliases": ["booker", "devin"]},
    {"id": "101", "name": "Patrick Mahomes", "team": "Kansas City Chiefs", "sport_key": "americanfootball_nfl", "aliases": ["mahomes", "patrick"]},
    {"id": "102", "name": "Josh Allen", "team": "Buffalo Bills", "sport_key": "americanfootball_nfl", "aliases": ["allen", "josh"]},
    {"id": "103", "name": "Christian McCaffrey", "team": "San Francisco 49ers", "sport_key": "americanfootball_nfl", "aliases": ["mccaffrey", "christian"]},
    {"id": "401", "name": "Cooper Flagg", "team": "Duke Blue Devils", "sport_key": "basketball_ncaab", "aliases": ["flagg", "cooper"]},
    {"id": "402", "name": "Johni Broome", "team": "Auburn Tigers", "sport_key": "basketball_ncaab", "aliases": ["broome", "johni"]},
    {"id": "403", "name": "Hunter Dickinson", "team": "Kansas Jayhawks", "sport_key": "basketball_ncaab", "aliases": ["dickinson", "hunter"]},
    {"id": "404", "name": "Mark Sears", "team": "Alabama Crimson Tide", "sport_key": "basketball_ncaab", "aliases": ["sears", "mark"]},
    {"id": "405", "name": "Alex Karaban", "team": "UConn Huskies", "sport_key": "basketball_ncaab", "aliases": ["karaban", "alex"]},
    {"id": "201", "name": "Shohei Ohtani", "team": "Los Angeles Dodgers", "sport_key": "baseball_mlb", "aliases": ["ohtani", "shohei"]},
    {"id": "202", "name": "Aaron Judge", "team": "New York Yankees", "sport_key": "baseball_mlb", "aliases": ["judge", "aaron"]},
    {"id": "203", "name": "Juan Soto", "team": "New York Yankees", "sport_key": "baseball_mlb", "aliases": ["soto", "juan"]},
    {"id": "204", "name": "Mookie Betts", "team": "Los Angeles Dodgers", "sport_key": "baseball_mlb", "aliases": ["betts", "mookie"]},
    {"id": "205", "name": "Ronald Acuna Jr.", "team": "Atlanta Braves", "sport_key": "baseball_mlb", "aliases": ["acuna", "ronald"]},
    {"id": "206", "name": "Freddie Freeman", "team": "Los Angeles Dodgers", "sport_key": "baseball_mlb", "aliases": ["freeman", "freddie"]},
    {"id": "207", "name": "Bobby Witt Jr.", "team": "Kansas City Royals", "sport_key": "baseball_mlb", "aliases": ["witt", "bobby"]},
    {"id": "208", "name": "Gunnar Henderson", "team": "Baltimore Orioles", "sport_key": "baseball_mlb", "aliases": ["gunnar", "henderson"]},
    {"id": "209", "name": "Corey Seager", "team": "Texas Rangers", "sport_key": "baseball_mlb", "aliases": ["seager", "corey"]},
    {"id": "210", "name": "Bryce Harper", "team": "Philadelphia Phillies", "sport_key": "baseball_mlb", "aliases": ["harper", "bryce"]},
    {"id": "501", "name": "Jannik Sinner", "team": "ATP Tour", "sport_key": "tennis_*", "aliases": ["sinner", "jannik"]},
    {"id": "502", "name": "Carlos Alcaraz", "team": "ATP Tour", "sport_key": "tennis_*", "aliases": ["alcaraz", "carlos"]},
    {"id": "503", "name": "Novak Djokovic", "team": "ATP Tour", "sport_key": "tennis_*", "aliases": ["djokovic", "novak"]},
    {"id": "504", "name": "Iga Swiatek", "team": "WTA Tour", "sport_key": "tennis_*", "aliases": ["swiatek", "iga"]},
    {"id": "505", "name": "Coco Gauff", "team": "WTA Tour", "sport_key": "tennis_*", "aliases": ["gauff", "coco"]},
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
    if any(token in normalized for token in {"limited", "minutes restriction", "game time"}):
        return 0.5
    if any(token in normalized for token in {"doubtful", "questionable"}):
        return 0.65
    if any(token in normalized for token in {"probable", "day to day"}):
        return 0.3
    return 0.15


def _risk_to_status(injury_risk: float) -> str:
    if injury_risk >= 0.8:
        return "Out"
    if injury_risk >= 0.5:
        return "Questionable"
    if injury_risk >= 0.35:
        return "Limited"
    if injury_risk >= 0.2:
        return "Probable"
    return "Available"


def _form_score(recent_average: float, baseline_average: float) -> float:
    return clamp(0.5 + ((recent_average - baseline_average) / max(baseline_average, 8)) * 0.3, 0.05, 0.99)


def _window_average(values: list[float], window: int, default: float) -> float:
    sample = values[:window]
    return mean(sample) if sample else default


def _build_recent_form_windows(player_id: str, recent_form: float, points: list[float] | None = None, baseline_points: float | None = None) -> dict:
    if points and baseline_points is not None:
        form_l3 = _form_score(_window_average(points, 3, baseline_points), baseline_points)
        form_l5 = _form_score(_window_average(points, 5, baseline_points), baseline_points)
        form_l10 = _form_score(_window_average(points, 10, baseline_points), baseline_points)
    else:
        form_l3 = clamp(recent_form + stable_float(f"{player_id}:form_l3", -0.08, 0.12), 0.05, 0.99)
        form_l5 = clamp(recent_form + stable_float(f"{player_id}:form_l5", -0.05, 0.08), 0.05, 0.99)
        form_l10 = clamp(recent_form + stable_float(f"{player_id}:form_l10", -0.04, 0.05), 0.05, 0.99)
    return {
        "recent_form_l3": round(form_l3, 3),
        "recent_form_l5": round(form_l5, 3),
        "recent_form_l10": round(form_l10, 3),
    }


def _infer_projected_role(team_context: float, fantasy_projection: float, usage_trend: float) -> str:
    if fantasy_projection >= 30 or (team_context >= 0.7 and usage_trend >= 0.08):
        return "Primary option"
    if fantasy_projection >= 22 or team_context >= 0.58:
        return "Starter"
    if fantasy_projection >= 16:
        return "Rotation"
    return "Bench spark"


def _extract_rest_days(recent_games: list[dict], fallback: float) -> float:
    for field in ("DaysRest", "RestDays"):
        values = [_safe_float(game.get(field)) for game in recent_games]
        values = [value for value in values if value is not None]
        if values:
            return clamp(values[0], 0, 7)
    dates = []
    for game in recent_games:
        parsed = _parse_iso_datetime(game.get("Day") or game.get("DateTime") or game.get("Date"))
        if parsed:
            dates.append(parsed)
    if len(dates) >= 2:
        dates.sort(reverse=True)
        return clamp((dates[0] - dates[1]).days - 1, 0, 7)
    return clamp(fallback, 0, 7)


def _finalize_player_payload(payload: dict) -> dict:
    payload["source_confidence"] = round(clamp(payload.get("source_confidence", 0.66), 0.05, 0.99), 3)
    payload["data_freshness"] = round(clamp(payload.get("data_freshness", 0.78), 0.05, 0.99), 3)
    payload["rest_days"] = round(clamp(payload.get("rest_days", 1.0), 0, 7), 2)
    payload["usage_trend"] = round(clamp(payload.get("usage_trend", 0.0), -1, 1), 3)
    payload["home_split"] = round(clamp(payload.get("home_split", payload.get("recent_form", 0.5)), 0.05, 0.99), 3)
    payload["away_split"] = round(clamp(payload.get("away_split", payload.get("recent_form", 0.5)), 0.05, 0.99), 3)
    payload["opponent_split"] = round(clamp(payload.get("opponent_split", payload.get("recent_form", 0.5)), 0.05, 0.99), 3)
    payload["lineup_support"] = round(clamp(payload.get("lineup_support", 0.6), 0.05, 0.99), 3)
    payload["teammate_absences"] = round(max(payload.get("teammate_absences", 0.0), 0.0), 2)
    payload["injury_days_out"] = round(max(payload.get("injury_days_out", 0.0), 0.0), 2)
    if not payload.get("projected_role"):
        payload["projected_role"] = _infer_projected_role(
            payload.get("team_context", 0.5),
            payload.get("fantasy_projection", 20.0),
            payload.get("usage_trend", 0.0),
        )
    if "recent_form_l3" not in payload or "recent_form_l5" not in payload or "recent_form_l10" not in payload:
        payload.update(_build_recent_form_windows(payload["player_id"], payload.get("recent_form", 0.5)))
    return payload


def _finalize_market_payload(payload: dict) -> dict:
    payload["book_disagreement"] = round(clamp(payload.get("book_disagreement", 0.05), 0, 1), 3)
    payload["market_source_confidence"] = round(clamp(payload.get("market_source_confidence", 0.72), 0.05, 0.99), 3)
    payload["consensus_spread"] = round(payload.get("consensus_spread", 0.0), 3)
    payload["historical_closing_line_value"] = round(payload.get("historical_closing_line_value", payload.get("closing_line_value", 0.0)), 3)
    return payload


def _season_value_score(stats: dict) -> float:
    fantasy_points = _safe_float(stats.get("FantasyPoints"))
    if fantasy_points is not None:
        return fantasy_points
    points = _safe_float(stats.get("Points"), 0.0) or 0.0
    passing_yards = _safe_float(stats.get("PassingYards"), 0.0) or 0.0
    rushing_yards = _safe_float(stats.get("RushingYards"), 0.0) or 0.0
    receiving_yards = _safe_float(stats.get("ReceivingYards"), 0.0) or 0.0
    touchdowns = (
        (_safe_float(stats.get("PassingTouchdowns"), 0.0) or 0.0) * 4
        + ((_safe_float(stats.get("RushingTouchdowns"), 0.0) or 0.0) * 6)
        + ((_safe_float(stats.get("ReceivingTouchdowns"), 0.0) or 0.0) * 6)
    )
    return points + passing_yards * 0.04 + rushing_yards * 0.1 + receiving_yards * 0.1 + touchdowns


def _http_get_json(url: str, headers: dict[str, str] | None = None, timeout: float = 5.0):
    request = Request(url, headers=headers or {})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _http_get_json_with_headers(url: str, headers: dict[str, str] | None = None, timeout: float = 5.0):
    request = Request(url, headers=headers or {})
    with urlopen(request, timeout=timeout) as response:
        response_headers = {key.lower(): value for key, value in response.headers.items()}
        return json.loads(response.read().decode("utf-8")), response_headers


def resolve_cache_ttl() -> float:
    raw_value = os.environ.get("UPSTREAM_CACHE_TTL_SECONDS", "120")
    try:
        return max(float(raw_value), 0.0)
    except ValueError:
        return 120.0


class TTLCache:
    """Small thread-safe time-based cache for upstream JSON responses."""

    def __init__(self, ttl_seconds: float | None = None, max_entries: int = 256) -> None:
        self._ttl_override = ttl_seconds
        self.max_entries = max_entries
        self._entries: dict[str, tuple[float, object]] = {}
        self._lock = threading.Lock()

    @property
    def ttl_seconds(self) -> float:
        return resolve_cache_ttl() if self._ttl_override is None else self._ttl_override

    def get(self, key: str):
        ttl = self.ttl_seconds
        if ttl <= 0:
            return None
        with self._lock:
            entry = self._entries.get(key)
            if not entry:
                return None
            stored_at, value = entry
            if time.monotonic() - stored_at > ttl:
                self._entries.pop(key, None)
                return None
            return value

    def set(self, key: str, value) -> None:
        if self.ttl_seconds <= 0 or value is None:
            return
        with self._lock:
            if len(self._entries) >= self.max_entries:
                oldest = min(self._entries, key=lambda item: self._entries[item][0])
                self._entries.pop(oldest, None)
            self._entries[key] = (time.monotonic(), value)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


def _cached_fetch(client, url: str, headers: dict[str, str]):
    cached = client._cache.get(url)
    if cached is not None:
        return cached
    payload = client.fetcher(url, headers=headers)
    client._cache.set(url, payload)
    return payload


def _format_sportsdata_date(value: str) -> str:
    parsed = datetime.strptime(value, "%Y-%m-%d")
    return parsed.strftime("%Y-%b-%d").upper()


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _team_matches(reference: str, candidate: str) -> bool:
    normalized_reference = _normalize(reference)
    normalized_candidate = _normalize(candidate)
    if not normalized_reference or not normalized_candidate:
        return False
    return normalized_reference in normalized_candidate or normalized_candidate in normalized_reference


def _american_to_probability(price: int) -> float:
    if price > 0:
        return 100 / (price + 100)
    return abs(price) / (abs(price) + 100)


def _extract_team_prices(event: dict, team: str, market_key: str = "h2h") -> list[int]:
    prices = []
    for bookmaker in event.get("bookmakers", []):
        for market in bookmaker.get("markets", []):
            if market.get("key") != market_key:
                continue
            for outcome in market.get("outcomes", []):
                if not _team_matches(team, outcome.get("name", "")):
                    continue
                price = _safe_int(outcome.get("price"))
                if price:
                    prices.append(price)
    return prices


def _consensus_price(prices: list[int]) -> int | None:
    if not prices:
        return None
    probability = mean(_american_to_probability(price) for price in prices)
    probability = clamp(probability, 0.01, 0.99)
    if probability >= 0.5:
        return int(round(-100 * probability / (1 - probability)))
    return int(round(100 * (1 - probability) / probability))


def search_players(query: str = "", team: str | None = None, sport: str | None = None) -> list[dict]:
    normalized_query = _normalize(query)
    normalized_team = _normalize(team or "")
    normalized_sport = _normalize(sport or "")
    results = []
    for entry in PLAYER_DIRECTORY:
        searchable = [_normalize(entry["id"]), _normalize(entry["name"]), _normalize(entry["team"])]
        searchable.extend(_normalize(alias) for alias in entry["aliases"])
        if normalized_query and not any(normalized_query in candidate for candidate in searchable):
            continue
        if normalized_team and normalized_team not in _normalize(entry["team"]):
            continue
        if normalized_sport and normalized_sport not in _normalize(entry.get("sport_key", "")):
            continue
        results.append(
            {
                "id": entry["id"],
                "name": entry["name"],
                "team": entry["team"],
                "sport_key": entry.get("sport_key", "basketball_nba"),
            }
        )
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


def _resolve_local_player(player_reference: str, team: str | None = None, sport: str | None = None) -> dict:
    matches = search_players(player_reference, team, sport)
    if matches:
        return matches[0]
    return {
        "id": _slugify(player_reference),
        "name": _titleize(player_reference),
        "team": _titleize(team) if team else "Open Market",
        "sport_key": sport or "basketball_nba",
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
        self._cache = TTLCache()

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

    def base_url_for_sport(self, sport: str | None = None) -> str:
        if not sport:
            return self.base_url
        mapped = SPORTSDATAIO_SPORT_PATHS.get(sport)
        if not mapped:
            return self.base_url
        for candidate in SPORTSDATAIO_SPORT_PATHS.values():
            suffix = f"/{candidate}"
            if self.base_url.endswith(suffix):
                return f"{self.base_url[:-len(suffix)]}/{mapped}"
        return f"{self.base_url.rstrip('/')}/{mapped}"

    def fetch_player_context(self, player_id: str, overrides: dict | None = None) -> dict:
        overrides = overrides or {}
        sport = overrides.get("sport")
        player = self.resolve_player(player_id, overrides.get("team"), sport)
        injury_risk = overrides.get("injury_risk", stable_float(f"{player['id']}:injury", 0.05, 0.55))
        recent_form = overrides.get("recent_form", stable_float(f"{player['id']}:form", 0.4, 0.95))
        payload = {
            "player_id": player["id"],
            "player_name": player["name"],
            "team": player["team"],
            "recent_form": recent_form,
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
            "rest_days": overrides.get("rest_days", stable_float(f"{player['id']}:rest", 0, 4)),
            "usage_trend": overrides.get("usage_trend", stable_float(f"{player['id']}:usage", -0.15, 0.18)),
            "home_split": overrides.get("home_split", clamp(recent_form + stable_float(f"{player['id']}:home", -0.06, 0.1), 0.05, 0.99)),
            "away_split": overrides.get("away_split", clamp(recent_form + stable_float(f"{player['id']}:away", -0.08, 0.08), 0.05, 0.99)),
            "opponent_split": overrides.get("opponent_split", clamp(recent_form + stable_float(f"{player['id']}:opponent", -0.07, 0.07), 0.05, 0.99)),
            "source_confidence": overrides.get("source_confidence", stable_float(f"{player['id']}:source", 0.58, 0.86)),
            "data_freshness": overrides.get("data_freshness", stable_float(f"{player['id']}:freshness", 0.6, 0.92)),
            "teammate_absences": overrides.get("teammate_absences", round(stable_float(f"{player['id']}:absences", 0, 3), 2)),
            "lineup_support": overrides.get("lineup_support", stable_float(f"{player['id']}:lineup", 0.35, 0.92)),
            "injury_days_out": overrides.get("injury_days_out", 0.0),
            "projected_role": overrides.get("projected_role"),
        }
        payload.update(_build_recent_form_windows(player["id"], recent_form))
        live_payload = self._fetch_live_player_context(player, sport or player.get("sport_key"))
        if live_payload:
            payload.update({key: value for key, value in live_payload.items() if value is not None})
            payload["source_mode"] = "live"
        else:
            payload["source_mode"] = "fallback"
        return _finalize_player_payload(payload)

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

    def resolve_player(self, player_reference: str, team: str | None = None, sport: str | None = None) -> dict:
        if self.api_key:
            live_match = self._resolve_live_player(player_reference, team, sport)
            if live_match:
                return live_match
        return _resolve_local_player(player_reference, team, sport)

    def resolve_team(self, team_reference: str) -> dict:
        if self.api_key:
            live_match = self._resolve_live_team(team_reference)
            if live_match:
                return live_match
        return _resolve_local_team(team_reference)

    def _request(self, path: str, params: dict | None = None, sport: str | None = None):
        if not self.api_key:
            self._last_call_succeeded = None
            self._last_error_message = "API key not configured"
            return None
        query = dict(params or {})
        query["key"] = self.api_key
        url = f"{self.base_url_for_sport(sport)}/{path.lstrip('/')}"
        if query:
            url = f"{url}?{urlencode(query)}"
        try:
            payload = _cached_fetch(self, url, {"Accept": "application/json"})
            self._last_call_succeeded = True
            self._last_error_message = None
            return payload
        except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
            self._last_call_succeeded = False
            self._last_error_message = str(exc)
            return None

    def _resolve_live_player(self, player_reference: str, team: str | None = None, sport: str | None = None) -> dict | None:
        normalized_query = _normalize(player_reference)
        normalized_team = _normalize(team or "")
        for path in ("scores/json/Players", "scores/json/PlayersBasic"):
            players = self._request(path, sport=sport)
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
                    "sport_key": sport or "basketball_nba",
                }
        return None

    def fetch_top_players(self, sport: str, limit: int = 10) -> list[dict]:
        if not self.api_key:
            return []
        players = self._request("scores/json/Players", sport=sport)
        if not isinstance(players, list):
            players = self._request("scores/json/PlayersBasic", sport=sport)
        season_stats = self._request(f"stats/json/PlayerSeasonStats/{self.season}", sport=sport)
        if not isinstance(players, list) or not isinstance(season_stats, list):
            return []
        stats_by_id = {
            str(entry.get("PlayerID")): entry
            for entry in season_stats
            if entry.get("PlayerID") is not None
        }
        ranked = []
        for player in players:
            player_id = str(player.get("PlayerID") or "")
            stats = stats_by_id.get(player_id)
            name = player.get("Name") or " ".join(
                part for part in [player.get("FirstName"), player.get("LastName")] if part
            )
            if not player_id or not name or not stats:
                continue
            score = _season_value_score(stats)
            if score <= 0:
                continue
            ranked.append(
                {
                    "id": player_id,
                    "name": name,
                    "team": player.get("Team") or player.get("TeamName") or player.get("TeamKey") or "Open Market",
                    "sport_key": sport,
                    "season_value_score": round(score, 3),
                }
            )
        ranked.sort(key=lambda item: item["season_value_score"], reverse=True)
        return ranked[:limit]

    def fetch_player_game_stats_by_date(self, date: str, sport: str | None = None) -> list[dict]:
        """Final box-score lines for a YYYY-MM-DD date, used to grade player predictions."""
        stats = self._request(f"stats/json/PlayerGameStatsByDate/{_format_sportsdata_date(date)}", sport=sport)
        if not isinstance(stats, list):
            return []
        results = []
        for entry in stats:
            name = entry.get("Name") or " ".join(part for part in [entry.get("FirstName"), entry.get("LastName")] if part)
            points = _safe_float(entry.get("Points"))
            if points is None:
                points = _safe_float(entry.get("FantasyPoints"))
            results.append(
                {
                    "player_id": str(entry.get("PlayerID") or ""),
                    "name": name,
                    "team": entry.get("Team") or "",
                    "points": points,
                    "minutes": _safe_float(entry.get("Minutes")),
                    "played": (_safe_float(entry.get("Minutes"), 0.0) or 0.0) > 0 or bool(entry.get("Started")),
                }
            )
        return results

    def fetch_scores_by_date(self, date: str, sport: str | None = None) -> list[dict]:
        """Final game scores for a YYYY-MM-DD date in the shared score format used by the grader."""
        formatted = _format_sportsdata_date(date)
        games = self._request(f"scores/json/ScoresByDate/{formatted}", sport=sport)
        if not isinstance(games, list):
            games = self._request(f"scores/json/GamesByDate/{formatted}", sport=sport)
        if not isinstance(games, list):
            return []
        results = []
        for game in games:
            status = str(game.get("Status") or "")
            home_score = _safe_float(game.get("HomeTeamScore") if game.get("HomeTeamScore") is not None else game.get("HomeScore"))
            away_score = _safe_float(game.get("AwayTeamScore") if game.get("AwayTeamScore") is not None else game.get("AwayScore"))
            results.append(
                {
                    "home_team": game.get("HomeTeamName") or game.get("HomeTeam") or "",
                    "away_team": game.get("AwayTeamName") or game.get("AwayTeam") or "",
                    "home_score": home_score,
                    "away_score": away_score,
                    "completed": status.startswith("F") and home_score is not None and away_score is not None,
                    "commence_time": game.get("DateTime") or game.get("Day") or date,
                    "source": "sportsdataio",
                }
            )
        return results

    def fetch_schedule_context(self, team: str, sport: str | None = None) -> dict | None:
        """Rest, back-to-back and travel from SportsDataIO `Schedules`/`Games` for the team's next game."""
        if not self.api_key or not team:
            return None
        teams = self._request("scores/json/Teams", sport=sport)
        team_names: dict[str, str] = {}
        team_key = team
        if isinstance(teams, list):
            for entry in teams:
                key = str(entry.get("Key") or "")
                full_name = " ".join(part for part in [entry.get("City"), entry.get("Name")] if part) or key
                if key:
                    team_names[key] = full_name
                if _normalize(team) in {_normalize(key), _normalize(full_name)} or (
                    entry.get("Name") and _normalize(entry["Name"]) in _normalize(team)
                ):
                    team_key = key or team_key
        for path in (f"scores/json/Schedules/{self.season}", f"scores/json/Games/{self.season}"):
            games = self._request(path, sport=sport)
            if isinstance(games, list) and games:
                context = compute_schedule_context(games, team_key, team_names)
                if context:
                    return {**context, "team_key": team_key, "source_mode": "live"}
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

    def _fetch_live_player_context(self, player: dict, sport: str | None = None) -> dict | None:
        player_id = player.get("id")
        if not self.api_key or not player_id:
            return None

        season_stats = self._request(f"stats/json/PlayerSeasonStatsByPlayer/{self.season}/{player_id}", sport=sport)
        if not isinstance(season_stats, dict):
            season_stats_list = self._request(f"stats/json/PlayerSeasonStats/{self.season}", sport=sport)
            if isinstance(season_stats_list, list):
                season_stats = next(
                    (entry for entry in season_stats_list if str(entry.get("PlayerID")) == str(player_id)),
                    None,
                )
        recent_games = self._request(f"stats/json/PlayerGameStatsByPlayerID/{player_id}/5", sport=sport)
        injuries = self._request("scores/json/Injuries", sport=sport)

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
        recent_form = _form_score(recent_points, baseline_points)

        workload = clamp((mean(minutes) if minutes else _safe_float(season_stats.get("Minutes"), 30.0)) / 40, 0.05, 0.99)
        consistency = clamp(
            1 - ((pstdev(points) if len(points) > 1 else baseline_points * 0.1) / max(recent_points or baseline_points or 1, 1)),
            0.05,
            0.99,
        )
        injury_status = None
        teammate_absences = 0.0
        if isinstance(injuries, list):
            for injury in injuries:
                status = injury.get("Status") or injury.get("InjuryStatus")
                if str(injury.get("PlayerID")) == str(player_id):
                    injury_status = status
                    continue
                injury_team = injury.get("Team") or injury.get("TeamName") or ""
                if _team_matches(player.get("team", ""), injury_team) and (_status_to_risk(status) or 0) >= 0.6:
                    teammate_absences += 1
        injury_risk = _status_to_risk(injury_status)
        if injury_risk is None:
            injury_risk = clamp((1 - consistency) * 0.45 + workload * 0.2, 0.05, 0.8)
        rest_days = _extract_rest_days(recent_games, stable_float(f"{player['id']}:rest_live", 0, 3))
        usage_trend = clamp((_window_average(points, 3, recent_points) - baseline_points) / max(baseline_points or 12, 12), -1, 1)
        form_windows = _build_recent_form_windows(player["id"], recent_form, points, baseline_points)
        return {
            "recent_form": recent_form,
            "expected_points": recent_points,
            "workload": workload,
            "injury_risk": injury_risk,
            "injury_status": injury_status or _risk_to_status(injury_risk),
            "consistency": consistency,
            "availability": clamp(1 - injury_risk * 0.8, 0.05, 0.99),
            "fouls_cards": clamp((mean(fouls) if fouls else 2.0) / 6, 0, 0.99),
            "rest_days": rest_days,
            "usage_trend": usage_trend,
            "home_split": clamp(form_windows["recent_form_l5"] + 0.03, 0.05, 0.99),
            "away_split": clamp(form_windows["recent_form_l10"] - 0.02, 0.05, 0.99),
            "opponent_split": clamp((form_windows["recent_form_l3"] + form_windows["recent_form_l10"]) / 2, 0.05, 0.99),
            "source_confidence": clamp(0.62 + min(len(recent_games), 5) * 0.06, 0.05, 0.99),
            "data_freshness": clamp(0.65 + min(len(recent_games), 5) * 0.05, 0.05, 0.99),
            "teammate_absences": min(teammate_absences, 10.0),
            "lineup_support": clamp(consistency * 0.55 + recent_form * 0.45 - min(teammate_absences, 5) * 0.04, 0.05, 0.99),
            "injury_days_out": 3.0 if injury_risk >= 0.8 else (1.0 if injury_risk >= 0.5 else 0.0),
            "projected_role": _infer_projected_role(
                clamp(0.4 + recent_form * 0.3 + consistency * 0.3, 0.05, 0.99),
                recent_points * 1.15,
                usage_trend,
            ),
            **form_windows,
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
        self.fetcher = fetcher or self._fetch_with_quota
        self._last_call_succeeded = None
        self._last_error_message = None
        self._cache = TTLCache()
        self.requests_remaining = None
        self.requests_used = None

    def _fetch_with_quota(self, url: str, headers: dict[str, str] | None = None, timeout: float = 5.0):
        payload, response_headers = _http_get_json_with_headers(url, headers=headers, timeout=timeout)
        remaining = _safe_int(response_headers.get("x-requests-remaining"))
        used = _safe_int(response_headers.get("x-requests-used"))
        if remaining is not None:
            self.requests_remaining = remaining
        if used is not None:
            self.requests_used = used
        return payload

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
            "requests_remaining": self.requests_remaining,
            "requests_used": self.requests_used,
        }

    def fetch_game_market(self, game_id: str, overrides: dict | None = None, sport: str | None = None) -> dict:
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
            "book_disagreement": overrides.get(
                "book_disagreement",
                stable_float(f"{game['game_id']}:disagreement", 0.01, 0.18),
            ),
            "consensus_spread": overrides.get(
                "consensus_spread",
                stable_float(f"{game['game_id']}:spread", -6, 6),
            ),
            "historical_closing_line_value": overrides.get(
                "historical_closing_line_value",
                clamp(stable_float(f"{game['game_id']}:history_clv", -0.06, 0.09), -0.15, 0.15),
            ),
            "market_source_confidence": overrides.get(
                "market_source_confidence",
                stable_float(f"{game['game_id']}:market_source", 0.6, 0.9),
            ),
        }
        live_payload = self._fetch_live_market(game, sport or self.sport)
        if live_payload:
            payload.update({key: value for key, value in live_payload.items() if value is not None})
            payload["source_mode"] = "live"
        else:
            payload["source_mode"] = "fallback"
        return _finalize_market_payload(payload)

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
            payload = _cached_fetch(self, url, {"Accept": "application/json"})
            self._last_call_succeeded = True
            self._last_error_message = None
            return payload
        except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
            self._last_call_succeeded = False
            self._last_error_message = str(exc)
            return None

    def fetch_events(self, sport: str | None = None) -> list[dict]:
        events = self._request(f"sports/{sport or self.sport}/events")
        if not isinstance(events, list):
            return []
        return [
            {
                "event_id": event.get("id"),
                "home_team": event.get("home_team") or "",
                "away_team": event.get("away_team") or "",
                "commence_time": event.get("commence_time"),
            }
            for event in events
            if event.get("home_team") and event.get("away_team")
        ]

    def fetch_scores(self, sport: str | None = None, days_from: int = 3) -> list[dict]:
        """Recent completed scores from `/sports/{sport}/scores` in the shared grader format."""
        events = self._request(f"sports/{sport or self.sport}/scores", {"daysFrom": str(max(1, min(days_from, 3)))})
        if not isinstance(events, list):
            return []
        results = []
        for event in events:
            home = event.get("home_team") or ""
            away = event.get("away_team") or ""
            scores = {entry.get("name"): _safe_float(entry.get("score")) for entry in (event.get("scores") or [])}
            results.append(
                {
                    "event_id": event.get("id"),
                    "home_team": home,
                    "away_team": away,
                    "home_score": scores.get(home),
                    "away_score": scores.get(away),
                    "completed": bool(event.get("completed")) and scores.get(home) is not None and scores.get(away) is not None,
                    "commence_time": event.get("commence_time"),
                    "source": "the_odds_api",
                }
            )
        return results

    def fetch_closing_odds(self, team: str, commence_time: str | None, sport: str | None = None) -> int | None:
        """Consensus h2h price shortly before tip-off from `/historical/sports/{sport}/odds`."""
        kickoff = _parse_iso_datetime(commence_time)
        if not kickoff:
            return None
        snapshot_time = (kickoff - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        payload = self._request(f"historical/sports/{sport or self.sport}/odds", {"date": snapshot_time})
        events = payload.get("data") if isinstance(payload, dict) else payload
        if not isinstance(events, list):
            return None
        for event in events:
            if not (_team_matches(team, event.get("home_team", "")) or _team_matches(team, event.get("away_team", ""))):
                continue
            return _consensus_price(_extract_team_prices(event, team))
        return None

    def fetch_player_prop(
        self,
        player_name: str,
        team: str,
        sport: str | None = None,
        market: str = "player_points",
    ) -> dict | None:
        """Consensus over/under line for a player from `/sports/{sport}/events/{eventId}/odds`."""
        sport_key = sport or self.sport
        for event in self.fetch_events(sport_key):
            if not (_team_matches(team, event["home_team"]) or _team_matches(team, event["away_team"])):
                continue
            payload = self._request(f"sports/{sport_key}/events/{event['event_id']}/odds", {"markets": market})
            if not isinstance(payload, dict):
                return None
            lines = []
            over_prices = []
            under_prices = []
            for bookmaker in payload.get("bookmakers", []):
                for book_market in bookmaker.get("markets", []):
                    if book_market.get("key") != market:
                        continue
                    for outcome in book_market.get("outcomes", []):
                        if _normalize(outcome.get("description", "")) != _normalize(player_name):
                            continue
                        point = _safe_float(outcome.get("point"))
                        price = _safe_int(outcome.get("price"))
                        if point is None or not price:
                            continue
                        lines.append(point)
                        if str(outcome.get("name", "")).lower() == "over":
                            over_prices.append(price)
                        elif str(outcome.get("name", "")).lower() == "under":
                            under_prices.append(price)
            if not lines or not over_prices or not under_prices:
                return None
            return {
                "market": market,
                "line": round(mean(lines), 1),
                "over_odds": _consensus_price(over_prices),
                "under_odds": _consensus_price(under_prices),
                "bookmakers": len(over_prices),
                "event_id": event["event_id"],
                "commence_time": event["commence_time"],
                "source_mode": "live",
            }
        return None

    def _fetch_live_market(self, game: dict, sport: str | None = None) -> dict | None:
        odds_payload = self._request(f"sports/{sport or self.sport}/odds")
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
            book_disagreement = clamp((max(implied_probabilities) - min(implied_probabilities)) * 2.4, 0, 1)
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
                "book_disagreement": book_disagreement,
                "consensus_spread": 0.0,
                "historical_closing_line_value": 0.0,
                "market_source_confidence": clamp(0.62 + min(len(prices), 4) * 0.08 - book_disagreement * 0.3, 0.05, 0.99),
                "implied_probability": consensus_probability,
            }
        return None


class MediaBroadcastClient:
    source_name = "Media & Broadcast"

    def __init__(self, fetcher=None) -> None:
        self.fetcher = fetcher or _http_get_json
        self._last_call_succeeded = None
        self._last_error_message = None
        self._cache = TTLCache()

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
        player = _resolve_local_player(player_id, overrides.get("team"), overrides.get("sport"))
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
            payload = _cached_fetch(self, f"{url}?{urlencode({'key': self.api_key})}", {"Accept": "application/json"})
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
        self._cache = TTLCache()

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
        player = _resolve_local_player(player_id, overrides.get("team"), overrides.get("sport"))
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
            payload = _cached_fetch(self, f"{url}?{urlencode({'key': self.api_key})}", {"Accept": "application/json"})
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


WEATHER_SPORTS = {"americanfootball_nfl", "baseball_mlb"}

# Approximate venue coordinates (latitude, longitude, indoor) for NFL and MLB teams.
VENUE_COORDINATES = {
    "arizona cardinals": (33.528, -112.263, True),
    "atlanta falcons": (33.755, -84.401, True),
    "baltimore ravens": (39.278, -76.623, False),
    "buffalo bills": (42.774, -78.787, False),
    "carolina panthers": (35.226, -80.853, False),
    "chicago bears": (41.862, -87.617, False),
    "cincinnati bengals": (39.095, -84.516, False),
    "cleveland browns": (41.506, -81.700, False),
    "dallas cowboys": (32.748, -97.093, True),
    "denver broncos": (39.744, -105.020, False),
    "detroit lions": (42.340, -83.046, True),
    "green bay packers": (44.501, -88.062, False),
    "houston texans": (29.685, -95.411, True),
    "indianapolis colts": (39.760, -86.164, True),
    "jacksonville jaguars": (30.324, -81.637, False),
    "kansas city chiefs": (39.049, -94.484, False),
    "las vegas raiders": (36.091, -115.184, True),
    "los angeles chargers": (33.953, -118.339, True),
    "los angeles rams": (33.953, -118.339, True),
    "miami dolphins": (25.958, -80.239, False),
    "minnesota vikings": (44.974, -93.258, True),
    "new england patriots": (42.091, -71.264, False),
    "new orleans saints": (29.951, -90.081, True),
    "new york giants": (40.813, -74.074, False),
    "new york jets": (40.813, -74.074, False),
    "philadelphia eagles": (39.901, -75.168, False),
    "pittsburgh steelers": (40.447, -80.016, False),
    "san francisco 49ers": (37.403, -121.970, False),
    "seattle seahawks": (47.595, -122.332, False),
    "tampa bay buccaneers": (27.976, -82.503, False),
    "tennessee titans": (36.166, -86.771, False),
    "washington commanders": (38.908, -76.864, False),
    "arizona diamondbacks": (33.445, -112.067, True),
    "atlanta braves": (33.891, -84.468, False),
    "baltimore orioles": (39.284, -76.622, False),
    "boston red sox": (42.346, -71.097, False),
    "chicago cubs": (41.948, -87.656, False),
    "chicago white sox": (41.830, -87.634, False),
    "cincinnati reds": (39.097, -84.507, False),
    "cleveland guardians": (41.496, -81.685, False),
    "colorado rockies": (39.756, -104.994, False),
    "detroit tigers": (42.339, -83.049, False),
    "houston astros": (29.757, -95.355, True),
    "kansas city royals": (39.051, -94.480, False),
    "los angeles angels": (33.800, -117.883, False),
    "los angeles dodgers": (34.074, -118.240, False),
    "miami marlins": (25.778, -80.220, True),
    "milwaukee brewers": (43.028, -87.971, True),
    "minnesota twins": (44.982, -93.278, False),
    "new york mets": (40.757, -73.846, False),
    "new york yankees": (40.829, -73.926, False),
    "oakland athletics": (38.580, -121.514, False),
    "athletics": (38.580, -121.514, False),
    "philadelphia phillies": (39.906, -75.166, False),
    "pittsburgh pirates": (40.447, -80.006, False),
    "san diego padres": (32.707, -117.157, False),
    "san francisco giants": (37.778, -122.389, False),
    "seattle mariners": (47.591, -122.332, True),
    "st louis cardinals": (38.623, -90.193, False),
    "tampa bay rays": (27.768, -82.653, True),
    "texas rangers": (32.747, -97.084, True),
    "toronto blue jays": (43.641, -79.389, True),
    "washington nationals": (38.873, -77.007, False),
}


def compute_weather_impact(temperature_f: float | None, wind_mph: float | None, precipitation_mm: float | None) -> float:
    """0 = neutral conditions, 1 = severe scoring-suppressing weather."""
    wind_component = clamp(((wind_mph or 0.0) - 10) / 20, 0, 1) * 0.5
    precipitation_component = clamp((precipitation_mm or 0.0) / 2.0, 0, 1) * 0.3
    temperature = 60.0 if temperature_f is None else temperature_f
    cold_component = clamp((32 - temperature) / 30, 0, 1) * 0.2
    heat_component = clamp((temperature - 95) / 15, 0, 1) * 0.1
    return round(clamp(wind_component + precipitation_component + cold_component + heat_component, 0, 1), 3)


class WeatherClient:
    """Optional Open-Meteo integration (no API key) for outdoor NFL and MLB venues."""

    source_name = "Open-Meteo"

    def __init__(self, fetcher=None) -> None:
        self.fetcher = fetcher or _http_get_json
        self._last_call_succeeded = None
        self._last_error_message = None
        self._cache = TTLCache()

    @property
    def enabled(self) -> bool:
        return os.environ.get("OPEN_METEO_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}

    @property
    def base_url(self) -> str:
        return os.environ.get("OPEN_METEO_BASE_URL", "https://api.open-meteo.com/v1").rstrip("/")

    def source_status(self) -> dict:
        return {
            "configured": self.enabled,
            "mode": "live" if self.enabled else "disabled",
            "last_call_succeeded": self._last_call_succeeded,
            "last_error_message": self._last_error_message if self.enabled else "OPEN_METEO_ENABLED not set",
        }

    def fetch_venue_weather(self, team: str, sport: str | None, overrides: dict | None = None) -> dict | None:
        overrides = overrides or {}
        if "weather_impact" in overrides:
            return {
                "mode": "override",
                "indoor": False,
                "weather_impact": round(clamp(float(overrides["weather_impact"]), 0, 1), 3),
            }
        if sport not in WEATHER_SPORTS:
            return None
        venue = VENUE_COORDINATES.get(_normalize(team))
        if not venue:
            return None
        latitude, longitude, indoor = venue
        if indoor:
            return {"mode": "indoor", "indoor": True, "weather_impact": 0.0}
        if not self.enabled:
            return None
        query = urlencode(
            {
                "latitude": latitude,
                "longitude": longitude,
                "current": "temperature_2m,precipitation,wind_speed_10m",
                "temperature_unit": "fahrenheit",
                "wind_speed_unit": "mph",
            }
        )
        try:
            payload = _cached_fetch(self, f"{self.base_url}/forecast?{query}", {"Accept": "application/json"})
            self._last_call_succeeded = True
            self._last_error_message = None
        except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
            self._last_call_succeeded = False
            self._last_error_message = str(exc)
            return None
        current = (payload or {}).get("current") or {}
        temperature = _safe_float(current.get("temperature_2m"))
        wind = _safe_float(current.get("wind_speed_10m"))
        precipitation = _safe_float(current.get("precipitation"))
        return {
            "mode": "live",
            "indoor": False,
            "temperature_f": temperature,
            "wind_mph": wind,
            "precipitation_mm": precipitation,
            "weather_impact": compute_weather_impact(temperature, wind, precipitation),
        }


# Approximate NBA arena coordinates (latitude, longitude, indoor) used for travel distance only.
NBA_ARENA_COORDINATES = {
    "atlanta hawks": (33.757, -84.396, True),
    "boston celtics": (42.366, -71.062, True),
    "brooklyn nets": (40.683, -73.975, True),
    "charlotte hornets": (35.225, -80.839, True),
    "chicago bulls": (41.881, -87.674, True),
    "cleveland cavaliers": (41.496, -81.688, True),
    "dallas mavericks": (32.790, -96.810, True),
    "denver nuggets": (39.749, -105.008, True),
    "detroit pistons": (42.341, -83.055, True),
    "golden state warriors": (37.768, -122.388, True),
    "houston rockets": (29.751, -95.362, True),
    "indiana pacers": (39.764, -86.155, True),
    "los angeles clippers": (33.945, -118.341, True),
    "los angeles lakers": (34.043, -118.267, True),
    "memphis grizzlies": (35.138, -90.051, True),
    "miami heat": (25.781, -80.188, True),
    "milwaukee bucks": (43.045, -87.917, True),
    "minnesota timberwolves": (44.979, -93.276, True),
    "new orleans pelicans": (29.949, -90.082, True),
    "new york knicks": (40.751, -73.993, True),
    "oklahoma city thunder": (35.463, -97.515, True),
    "orlando magic": (28.539, -81.384, True),
    "philadelphia 76ers": (39.901, -75.172, True),
    "phoenix suns": (33.446, -112.071, True),
    "portland trail blazers": (45.532, -122.667, True),
    "sacramento kings": (38.580, -121.500, True),
    "san antonio spurs": (29.427, -98.438, True),
    "toronto raptors": (43.643, -79.379, True),
    "utah jazz": (40.768, -111.901, True),
    "washington wizards": (38.898, -77.021, True),
}
MAX_TRAVEL_FATIGUE_MILES = 2500.0


def _venue_coordinates(team_name: str) -> tuple[float, float, bool] | None:
    normalized = _normalize(team_name or "")
    return VENUE_COORDINATES.get(normalized) or NBA_ARENA_COORDINATES.get(normalized)


def haversine_miles(origin: tuple[float, float], destination: tuple[float, float]) -> float:
    lat1, lon1 = math.radians(origin[0]), math.radians(origin[1])
    lat2, lon2 = math.radians(destination[0]), math.radians(destination[1])
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(a))


def travel_fatigue(travel_miles: float | None, back_to_back: bool) -> float:
    """0 = fresh, 1 = long trip on a back-to-back."""
    distance_component = clamp((travel_miles or 0.0) / MAX_TRAVEL_FATIGUE_MILES, 0, 1) * 0.7
    return round(clamp(distance_component + (0.3 if back_to_back else 0.0), 0, 1), 3)


def compute_schedule_context(games: list[dict], team_key: str, team_names: dict[str, str] | None = None, now: datetime | None = None) -> dict | None:
    """Rest days, back-to-back flag and travel miles for a team from a SportsDataIO schedule list.

    `games` entries use SportsDataIO fields (HomeTeam, AwayTeam, DateTime/Day). `team_names` maps team keys to full
    names so venue coordinates can be resolved.
    """
    now = now or datetime.now(timezone.utc)
    team_names = team_names or {}
    normalized_key = _normalize(team_key)
    team_games = []
    for game in games:
        home = str(game.get("HomeTeam") or "")
        away = str(game.get("AwayTeam") or "")
        if normalized_key not in {_normalize(home), _normalize(away)}:
            continue
        kickoff = _parse_iso_datetime(game.get("DateTime") or game.get("Day") or game.get("Date"))
        if not kickoff:
            continue
        team_games.append((kickoff, home, away))
    if not team_games:
        return None
    team_games.sort(key=lambda item: item[0])
    previous = [entry for entry in team_games if entry[0] < now - timedelta(hours=4)]
    upcoming = [entry for entry in team_games if entry[0] >= now - timedelta(hours=4)]
    if not previous or not upcoming:
        return None
    last_game, next_game = previous[-1], upcoming[0]
    rest_days = clamp((next_game[0].date() - last_game[0].date()).days - 1, 0, 7)
    back_to_back = rest_days == 0
    origin = _venue_coordinates(team_names.get(last_game[1], last_game[1]))
    destination = _venue_coordinates(team_names.get(next_game[1], next_game[1]))
    travel_miles = round(haversine_miles(origin[:2], destination[:2]), 1) if origin and destination else None
    return {
        "rest_days": rest_days,
        "back_to_back": back_to_back,
        "travel_miles": travel_miles,
        "road_game": _normalize(next_game[2]) == normalized_key,
        "last_game_at": last_game[0].isoformat(),
        "next_game_at": next_game[0].isoformat(),
        "travel_fatigue": travel_fatigue(travel_miles, back_to_back),
    }
