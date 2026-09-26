from __future__ import annotations

import json
import os
from urllib.parse import parse_qs, unquote

from .elo import TENNIS_SURFACES, normalize_surface
from .grading import parse_grade_date
from .metrics import BREAKDOWN_DIMENSIONS, TIMESERIES_WINDOWS
from .service import PredictionService
from .ui import app_metadata, render_home_page


PLAYER_FLOAT_FIELDS = {
    "recent_form",
    "workload",
    "injury_risk",
    "consistency",
    "matchup_difficulty",
    "team_context",
    "availability",
    "effort_change",
    "fouls_cards",
    "team_instability",
    "media_sentiment",
    "broadcast_exposure",
    "narrative_pressure",
    "fantasy_projection",
    "fantasy_value_rating",
    "ownership_projection",
    "recent_form_l3",
    "recent_form_l5",
    "recent_form_l10",
    "home_split",
    "away_split",
    "opponent_split",
    "rest_days",
    "usage_trend",
    "source_confidence",
    "data_freshness",
    "teammate_absences",
    "lineup_support",
    "injury_days_out",
    "prop_line",
    "weather_impact",
}

PLAYER_INT_FIELDS = {"over_odds", "under_odds"}

GAME_FLOAT_FIELDS = {
    "model_probability",
    "team_form",
    "pace",
    "efficiency",
    "injury_impact",
    "market_consensus",
    "line_movement",
    "closing_line_value",
    "expected_points_adjustment",
    "broadcast_heat",
    "audience_confidence",
    "fantasy_market_support",
    "fantasy_points_total",
    "injury_leverage",
    "book_disagreement",
    "consensus_spread",
    "historical_closing_line_value",
    "market_source_confidence",
    "weather_impact",
    "rest_days",
    "opponent_rest_days",
    "travel_miles",
    "opponent_travel_miles",
}
MAX_TRAVEL_MILES = 10000
MAX_NAME_LENGTH = 100

GAME_INT_FIELDS = {"opening_odds", "current_odds", "odds"}
GAME_BOOL_FIELDS = {"steam_move"}

service = PredictionService()


def json_response(start_response, status: str, payload: dict) -> list[bytes]:
    body = json.dumps(payload).encode("utf-8")
    start_response(
        status,
        [
            ("Content-Type", "application/json"),
            ("Content-Length", str(len(body))),
        ],
    )
    return [body]


def html_response(start_response, status: str, body: str) -> list[bytes]:
    encoded = body.encode("utf-8")
    start_response(
        status,
        [
            ("Content-Type", "text/html; charset=utf-8"),
            ("Content-Length", str(len(encoded))),
        ],
    )
    return [encoded]


def csv_response(start_response, status: str, body: str, filename: str) -> list[bytes]:
    encoded = body.encode("utf-8")
    start_response(
        status,
        [
            ("Content-Type", "text/csv; charset=utf-8"),
            ("Content-Disposition", f'attachment; filename="{filename}"'),
            ("Content-Length", str(len(encoded))),
        ],
    )
    return [encoded]


def _optional_float(query: dict[str, list[str]], name: str) -> float | None:
    raw_value = query.get(name, [""])[0].strip()
    if not raw_value:
        return None
    return float(raw_value)


def _parse_bool(raw_value: str) -> bool:
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError("must be a boolean")


def _parse_overrides(query: dict[str, list[str]], fields: set[str], caster, label: str) -> tuple[dict, dict]:
    parsed = {}
    errors = {}
    for field in fields:
        if field not in query:
            continue
        try:
            parsed[field] = caster(query[field][0])
        except ValueError:
            errors[field] = f"{field} {label}"
    return parsed, errors


def resolve_server_host() -> str:
    return os.environ.get("HOST", "0.0.0.0")


def resolve_server_port() -> int:
    raw_port = os.environ.get("PORT", "8000")
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise ValueError("PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise ValueError("PORT must be between 1 and 65535")
    return port


def run_server() -> None:
    from wsgiref.simple_server import make_server

    host = resolve_server_host()
    port = resolve_server_port()
    with make_server(host, port, app) as server:
        print(f"Serving on http://{host}:{port}")
        server.serve_forever()


def app(environ, start_response):
    method = environ.get("REQUEST_METHOD", "GET")
    path = environ.get("PATH_INFO", "")
    query = parse_qs(environ.get("QUERY_STRING", ""))

    if method == "POST" and path.startswith("/predictions/") and path.endswith("/outcome"):
        prediction_id = unquote(path[len("/predictions/") : -len("/outcome")].strip("/"))
        if not prediction_id:
            return json_response(start_response, "404 Not Found", {"error": "Not found"})
        try:
            body_length = int(environ.get("CONTENT_LENGTH") or "0")
        except ValueError:
            body_length = 0
        raw_body = environ.get("wsgi.input").read(body_length) if body_length else b""
        try:
            payload = json.loads(raw_body.decode("utf-8") or "{}")
        except ValueError:
            return json_response(start_response, "400 Bad Request", {"error": "invalid JSON body"})
        try:
            result = service.record_prediction_outcome(prediction_id, payload)
        except ValueError:
            return json_response(start_response, "400 Bad Request", {"error": "invalid outcome payload"})
        except Exception:
            return json_response(start_response, "500 Internal Server Error", {"error": "unable to record outcome"})
        if not result:
            return json_response(start_response, "404 Not Found", {"error": "prediction not found"})
        return json_response(start_response, "200 OK", result)

    if method == "POST" and path == "/backtest/grade":
        try:
            date = parse_grade_date(query.get("date", [""])[0].strip())
        except ValueError:
            return json_response(start_response, "400 Bad Request", {"error": "date must use YYYY-MM-DD"})
        try:
            result = service.grade_outcomes(date)
        except Exception:
            return json_response(start_response, "500 Internal Server Error", {"error": "unable to grade predictions"})
        return json_response(start_response, "200 OK", result)

    if method != "GET":
        return json_response(start_response, "405 Method Not Allowed", {"error": "Method not allowed"})

    if path == "/":
        return html_response(start_response, "200 OK", render_home_page())

    if path == "/app.json":
        return json_response(start_response, "200 OK", app_metadata())

    if path == "/backtest/summary.json":
        return json_response(start_response, "200 OK", service.get_backtest_summary())

    if path == "/backtest/timeseries":
        window = query.get("window", ["30d"])[0].strip() or "30d"
        if window not in TIMESERIES_WINDOWS:
            return json_response(
                start_response,
                "400 Bad Request",
                {"error": f"window must be one of {', '.join(TIMESERIES_WINDOWS)}"},
            )
        try:
            rolling = int(query.get("rolling", ["20"])[0])
        except ValueError:
            return json_response(start_response, "400 Bad Request", {"error": "rolling must be an integer"})
        if not 1 <= rolling <= 200:
            return json_response(start_response, "400 Bad Request", {"error": "rolling must be between 1 and 200"})
        sport = query.get("sport", [""])[0].strip() or None
        return json_response(start_response, "200 OK", service.get_backtest_timeseries(window, sport, rolling))

    if path == "/backtest/breakdown":
        by = query.get("by", ["sport"])[0].strip() or "sport"
        if by not in BREAKDOWN_DIMENSIONS:
            return json_response(
                start_response,
                "400 Bad Request",
                {"error": f"by must be one of {', '.join(BREAKDOWN_DIMENSIONS)}"},
            )
        return json_response(start_response, "200 OK", service.get_backtest_breakdown(by))

    if path == "/predictions.csv":
        return csv_response(start_response, "200 OK", service.export_predictions_csv(), "predictions.csv")

    if path == "/slate":
        try:
            min_edge = _optional_float(query, "min_edge")
            min_confidence = _optional_float(query, "min_confidence")
            limit = int(query.get("limit", ["10"])[0])
        except ValueError:
            return json_response(
                start_response,
                "400 Bad Request",
                {"error": "min_edge and min_confidence must be numeric and limit must be an integer"},
            )
        if not 1 <= limit <= 25:
            return json_response(start_response, "400 Bad Request", {"error": "limit must be between 1 and 25"})
        if min_confidence is not None and not 0 <= min_confidence <= 1:
            return json_response(start_response, "400 Bad Request", {"error": "min_confidence must be between 0 and 1"})
        sport = query.get("sport", [""])[0].strip() or None
        try:
            payload = service.get_slate(sport, min_edge, min_confidence, limit)
        except Exception:
            return json_response(start_response, "500 Internal Server Error", {"error": "unable to build slate"})
        return json_response(start_response, "200 OK", payload)

    if path == "/lookup/players":
        return json_response(
            start_response,
            "200 OK",
            {
                "players": service.search_players(
                    query.get("query", [""])[0],
                    query.get("team", [None])[0],
                    query.get("sport", [None])[0],
                )
            },
        )

    if path == "/lookup/teams":
        return json_response(
            start_response,
            "200 OK",
            {"teams": service.search_teams(query.get("query", [""])[0])},
        )

    if path == "/health":
        return json_response(
            start_response,
            "200 OK",
            {"status": "ok", "sources": service.source_status()},
        )

    if path == "/players/top":
        sport = query.get("sport", [None])[0]
        raw_limit = query.get("limit", ["10"])[0]
        try:
            limit = int(raw_limit)
        except ValueError:
            return json_response(start_response, "400 Bad Request", {"error": "limit must be an integer"})
        if not 1 <= limit <= 25:
            return json_response(start_response, "400 Bad Request", {"error": "limit must be between 1 and 25"})
        return json_response(start_response, "200 OK", service.get_top_players_summary(sport, limit))

    if path.startswith("/player/") and path.endswith("/prediction"):
        player_id = unquote(path[len("/player/") : -len("/prediction")].strip("/"))
        if not player_id:
            return json_response(start_response, "404 Not Found", {"error": "Not found"})
        overrides, errors = _parse_overrides(query, PLAYER_FLOAT_FIELDS, float, "must be numeric")
        int_overrides, int_errors = _parse_overrides(query, PLAYER_INT_FIELDS, int, "must be an integer American line")
        errors.update(int_errors)
        if errors:
            return json_response(start_response, "400 Bad Request", {"errors": errors})
        for odds_field in PLAYER_INT_FIELDS:
            if int_overrides.get(odds_field) == 0:
                return json_response(start_response, "400 Bad Request", {"error": f"{odds_field} cannot be zero"})
        overrides.update(int_overrides)
        if "prop_line" in overrides and overrides["prop_line"] < 0:
            return json_response(start_response, "400 Bad Request", {"error": "prop_line must be zero or greater"})
        if "prop_market" in query and query["prop_market"][0].strip():
            overrides["prop_market"] = query["prop_market"][0].strip()[:40]
        if "team" in query and query["team"][0].strip():
            overrides["team"] = query["team"][0].strip()
        if "sport" in query and query["sport"][0].strip():
            overrides["sport"] = query["sport"][0].strip()
        for bounded_field in {
            "recent_form",
            "recent_form_l3",
            "recent_form_l5",
            "recent_form_l10",
            "workload",
            "injury_risk",
            "consistency",
            "matchup_difficulty",
            "team_context",
            "availability",
            "home_split",
            "away_split",
            "opponent_split",
            "fouls_cards",
            "team_instability",
            "media_sentiment",
            "source_confidence",
            "data_freshness",
            "lineup_support",
            "weather_impact",
        }:
            if bounded_field in overrides and not 0 <= overrides[bounded_field] <= 1:
                return json_response(
                    start_response,
                    "400 Bad Request",
                    {"error": f"{bounded_field} must be between 0 and 1"},
                )
        if "effort_change" in overrides and not -1 <= overrides["effort_change"] <= 1:
            return json_response(
                start_response,
                "400 Bad Request",
                {"error": "effort_change must be between -1 and 1"},
            )
        if "usage_trend" in overrides and not -1 <= overrides["usage_trend"] <= 1:
            return json_response(
                start_response,
                "400 Bad Request",
                {"error": "usage_trend must be between -1 and 1"},
            )
        if "rest_days" in overrides and not 0 <= overrides["rest_days"] <= 7:
            return json_response(
                start_response,
                "400 Bad Request",
                {"error": "rest_days must be between 0 and 7"},
            )
        if "teammate_absences" in overrides and not 0 <= overrides["teammate_absences"] <= 10:
            return json_response(
                start_response,
                "400 Bad Request",
                {"error": "teammate_absences must be between 0 and 10"},
            )
        if "injury_days_out" in overrides and overrides["injury_days_out"] < 0:
            return json_response(
                start_response,
                "400 Bad Request",
                {"error": "injury_days_out must be zero or greater"},
            )
        try:
            payload = service.get_player_prediction(player_id, overrides)
        except ValueError:
            return json_response(start_response, "400 Bad Request", {"error": "invalid player prediction request"})
        except Exception:
            return json_response(start_response, "500 Internal Server Error", {"error": "unable to generate player prediction"})
        return json_response(start_response, "200 OK", payload)

    if path.startswith("/game/") and path.endswith("/edge"):
        game_id = unquote(path[len("/game/") : -len("/edge")].strip("/"))
        if not game_id:
            return json_response(start_response, "404 Not Found", {"error": "Not found"})
        sports_overrides, float_errors = _parse_overrides(query, GAME_FLOAT_FIELDS, float, "must be numeric")
        int_overrides, int_errors = _parse_overrides(query, GAME_INT_FIELDS, int, "must be an integer American line")
        bool_overrides, bool_errors = _parse_overrides(query, GAME_BOOL_FIELDS, _parse_bool, "must be a boolean")
        errors = {}
        errors.update(float_errors)
        errors.update(int_errors)
        errors.update(bool_errors)
        if errors:
            return json_response(start_response, "400 Bad Request", {"errors": errors})

        if "model_probability" in sports_overrides and not 0 <= sports_overrides["model_probability"] <= 1:
            return json_response(
                start_response,
                "400 Bad Request",
                {"error": "model_probability must be between 0 and 1"},
            )
        for bounded_field in {
            "team_form",
            "pace",
            "efficiency",
            "injury_impact",
            "market_consensus",
            "book_disagreement",
            "market_source_confidence",
            "weather_impact",
        }:
            if bounded_field in sports_overrides and not 0 <= sports_overrides[bounded_field] <= 1:
                return json_response(
                    start_response,
                    "400 Bad Request",
                    {"error": f"{bounded_field} must be between 0 and 1"},
                )
        odds_overrides = dict(bool_overrides)
        odds_overrides.update(
            {
                key: value
                for key, value in sports_overrides.items()
                if key
                in {
                    "market_consensus",
                    "line_movement",
                    "closing_line_value",
                    "book_disagreement",
                    "consensus_spread",
                    "historical_closing_line_value",
                    "market_source_confidence",
                }
            }
        )
        sports_overrides = {
            key: value
            for key, value in sports_overrides.items()
            if key
            not in {
                "market_consensus",
                "line_movement",
                "closing_line_value",
                "book_disagreement",
                "consensus_spread",
                "historical_closing_line_value",
                "market_source_confidence",
            }
        }

        if "odds" in int_overrides:
            odds_overrides["current_odds"] = int_overrides["odds"]
        for key in {"opening_odds", "current_odds"}:
            if key in int_overrides:
                odds_overrides[key] = int_overrides[key]
        for odds_field in {"opening_odds", "current_odds"}:
            if odds_overrides.get(odds_field) == 0:
                return json_response(
                    start_response,
                    "400 Bad Request",
                    {"error": f"{odds_field} cannot be zero"},
                )
        for rest_field in ("rest_days", "opponent_rest_days"):
            if rest_field in sports_overrides and not 0 <= sports_overrides[rest_field] <= 7:
                return json_response(start_response, "400 Bad Request", {"error": f"{rest_field} must be between 0 and 7"})
        for travel_field in ("travel_miles", "opponent_travel_miles"):
            if travel_field in sports_overrides and not 0 <= sports_overrides[travel_field] <= MAX_TRAVEL_MILES:
                return json_response(
                    start_response,
                    "400 Bad Request",
                    {"error": f"{travel_field} must be between 0 and {MAX_TRAVEL_MILES}"},
                )
        game_sport = query.get("sport", [""])[0].strip() or None
        opponent = query.get("opponent", [""])[0].strip() or None
        if opponent and len(opponent) > MAX_NAME_LENGTH:
            return json_response(start_response, "400 Bad Request", {"error": f"opponent must be at most {MAX_NAME_LENGTH} characters"})
        try:
            surface = normalize_surface(query.get("surface", [""])[0])
        except ValueError:
            return json_response(
                start_response, "400 Bad Request", {"error": f"surface must be one of {', '.join(TENNIS_SURFACES)}"}
            )
        try:
            payload = service.get_game_edge(
                game_id, sports_overrides, odds_overrides, sport=game_sport, opponent=opponent, surface=surface
            )
        except ValueError:
            return json_response(start_response, "400 Bad Request", {"error": "invalid game edge request"})
        except Exception:
            return json_response(start_response, "500 Internal Server Error", {"error": "unable to generate game edge"})
        return json_response(start_response, "200 OK", payload)

    return json_response(start_response, "404 Not Found", {"error": "Not found"})


if __name__ == "__main__":
    run_server()
