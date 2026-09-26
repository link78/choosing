import json
import os
from pathlib import Path

PLAYER_SPORT = {
    "name": "Basketball",
    "league": "NBA",
    "odds_api_key": "basketball_nba",
}


ODDS_API_ENDPOINTS = [
    {"name": "Sports list", "path": "/sports"},
    {"name": "Current odds", "path": "/sports/{sport}/odds"},
    {"name": "Event list", "path": "/sports/{sport}/events"},
    {"name": "Event odds", "path": "/sports/{sport}/events/{eventId}/odds"},
    {"name": "Scores", "path": "/sports/{sport}/scores"},
    {"name": "Historical odds", "path": "/historical/sports/{sport}/odds"},
]


ODDS_API_SPORTS = [
    {"name": "NFL", "key": "americanfootball_nfl"},
    {"name": "MLB", "key": "baseball_mlb"},
    {"name": "NBA", "key": "basketball_nba"},
    {"name": "NHL", "key": "icehockey_nhl"},
    {"name": "College Football", "key": "americanfootball_ncaaf"},
    {"name": "College Basketball", "key": "basketball_ncaab"},
    {"name": "PGA / Golf", "key": "golf_pga"},
    {"name": "NASCAR", "key": "motorsports_nascar"},
    {"name": "Soccer", "key": "soccer_*"},
    {"name": "UFC / MMA", "key": "mma_mixed_martial_arts"},
    {"name": "Tennis", "key": "tennis_*"},
    {"name": "Olympics", "key": "olympics_*"},
]


DEFAULT_SPORT_MODEL = {
    "form_weights": {"l3": 0.5, "l5": 0.3, "l10": 0.2},
    "minutes": {
        "base": 18.0,
        "recent_form": 12.0,
        "team_context": 8.0,
        "workload": -4.0,
        "injury_risk": -6.0,
        "broadcast_exposure": 2.0,
        "narrative_pressure": -1.5,
        "rest_days": 0.6,
        "usage_trend": 4.0,
        "role": 3.0,
        "lineup_support": 3.0,
        "teammate_absences": 0.4,
    },
    "performance": {
        "base": 12.0,
        "effective_form": 18.0,
        "consistency": 10.0,
        "team_context": 6.0,
        "matchup_difficulty": -7.0,
        "media_sentiment": 4.0,
        "fantasy_value_rating": 6.0,
        "narrative_pressure": -4.0,
        "usage_trend": 8.0,
        "lineup_support": 4.0,
    },
    "points": {
        "recent_form": 14.0,
        "consistency": 5.0,
        "team_context": 4.0,
        "matchup_difficulty": -5.0,
        "fantasy_projection_blend": 0.32,
        "broadcast_exposure": 1.2,
        "media_sentiment": 1.4,
        "narrative_pressure": -1.5,
        "usage_trend": 6.0,
        "lineup_support": 2.4,
    },
    "risk": {
        "consistency": 0.35,
        "workload": 0.25,
        "matchup_difficulty": 0.2,
        "injury_risk": 0.2,
        "narrative_pressure": 0.12,
        "fantasy_value_rating": -0.06,
        "ownership_projection": -0.03,
        "rest_days": -0.03,
        "usage_trend": -0.04,
    },
    "game": {
        "recent_form": 0.18,
        "efficiency": 0.14,
        "pace": 0.05,
        "injury_impact": -0.08,
        "market_consensus": 0.05,
        "broadcast_heat": 0.03,
        "audience_confidence": 0.02,
        "fantasy_market_support": 0.04,
        "narrative_pressure": -0.02,
        "injury_leverage": -0.01,
    },
}


SPORT_MODEL_PROFILES = {
    "basketball_nba": DEFAULT_SPORT_MODEL,
    "americanfootball_nfl": {
        **DEFAULT_SPORT_MODEL,
        "minutes": {**DEFAULT_SPORT_MODEL["minutes"], "recent_form": 10.0, "usage_trend": 5.0, "lineup_support": 4.0},
        "performance": {**DEFAULT_SPORT_MODEL["performance"], "effective_form": 16.0, "matchup_difficulty": -8.0},
        "points": {**DEFAULT_SPORT_MODEL["points"], "recent_form": 12.0, "usage_trend": 7.0},
        "risk": {**DEFAULT_SPORT_MODEL["risk"], "workload": 0.18, "matchup_difficulty": 0.24, "injury_risk": 0.24},
        "game": {**DEFAULT_SPORT_MODEL["game"], "pace": 0.02, "injury_impact": -0.1, "market_consensus": 0.06},
    },
    "baseball_mlb": {
        **DEFAULT_SPORT_MODEL,
        "minutes": {**DEFAULT_SPORT_MODEL["minutes"], "base": 14.0, "workload": -2.5, "rest_days": 0.35},
        "performance": {**DEFAULT_SPORT_MODEL["performance"], "effective_form": 14.0, "consistency": 12.0, "usage_trend": 5.0},
        "points": {**DEFAULT_SPORT_MODEL["points"], "recent_form": 10.0, "consistency": 6.0, "fantasy_projection_blend": 0.26},
        "risk": {**DEFAULT_SPORT_MODEL["risk"], "consistency": 0.42, "workload": 0.14, "injury_risk": 0.16},
        "game": {**DEFAULT_SPORT_MODEL["game"], "pace": 0.01, "injury_impact": -0.05, "market_consensus": 0.07},
    },
    "icehockey_nhl": {
        **DEFAULT_SPORT_MODEL,
        "minutes": {**DEFAULT_SPORT_MODEL["minutes"], "base": 16.0, "broadcast_exposure": 1.5, "teammate_absences": 0.5},
        "performance": {**DEFAULT_SPORT_MODEL["performance"], "effective_form": 15.0, "consistency": 11.0, "team_context": 5.0},
        "points": {**DEFAULT_SPORT_MODEL["points"], "recent_form": 11.0, "lineup_support": 2.0},
        "risk": {**DEFAULT_SPORT_MODEL["risk"], "workload": 0.2, "matchup_difficulty": 0.22},
        "game": {**DEFAULT_SPORT_MODEL["game"], "pace": 0.03, "efficiency": 0.12},
    },
}


def resolve_player_sport(selection: str | None = None) -> dict:
    normalized = (selection or "").strip().lower()
    if normalized:
        for sport in ODDS_API_SPORTS:
            if normalized in {sport["name"].lower(), sport["key"].lower()}:
                return _sport_profile(sport)
    return dict(PLAYER_SPORT)


def resolve_sport_model(selection: str | None = None) -> dict:
    sport = resolve_player_sport(selection)
    model = SPORT_MODEL_PROFILES.get(sport["odds_api_key"], DEFAULT_SPORT_MODEL)
    adapted_profiles = _load_adapted_profiles()
    adapted = adapted_profiles.get(sport["odds_api_key"], {})
    return {
        "form_weights": dict(model["form_weights"]),
        "minutes": {**dict(model["minutes"]), **dict(adapted.get("minutes", {}))},
        "performance": {**dict(model["performance"]), **dict(adapted.get("performance", {}))},
        "points": {**dict(model["points"]), **dict(adapted.get("points", {}))},
        "risk": {**dict(model["risk"]), **dict(adapted.get("risk", {}))},
        "game": {**dict(model["game"]), **dict(adapted.get("game", {}))},
    }


def _sport_profile(sport: dict) -> dict:
    name = sport["name"]
    if name == "NFL":
        sport_name = "American Football"
        league = "NFL"
    elif name == "MLB":
        sport_name = "Baseball"
        league = "MLB"
    elif name == "NBA":
        sport_name = "Basketball"
        league = "NBA"
    elif name == "NHL":
        sport_name = "Ice Hockey"
        league = "NHL"
    else:
        sport_name = name
        league = name
    return {
        "name": sport_name,
        "league": league,
        "odds_api_key": sport["key"],
    }


def _load_adapted_profiles() -> dict:
    configured = os.environ.get("CHOOSING_DATA_DIR", "").strip()
    data_dir = Path(configured).expanduser() if configured else Path.home() / ".choosing"
    model_path = data_dir / "adapted_models.json"
    if not model_path.exists():
        return {}
    try:
        payload = json.loads(model_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return payload.get("profiles", {})
