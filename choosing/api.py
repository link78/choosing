from __future__ import annotations

import json
from urllib.parse import parse_qs

from .prediction import build_game_edge, build_player_prediction


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


def app(environ, start_response):
    method = environ.get("REQUEST_METHOD", "GET")
    path = environ.get("PATH_INFO", "")
    query = parse_qs(environ.get("QUERY_STRING", ""))

    if method != "GET":
        return json_response(start_response, "405 Method Not Allowed", {"error": "Method not allowed"})

    if path == "/health":
        return json_response(start_response, "200 OK", {"status": "ok"})

    if path.startswith("/player/") and path.endswith("/prediction"):
        player_id = path[len("/player/") : -len("/prediction")].strip("/")
        if not player_id:
            return json_response(start_response, "404 Not Found", {"error": "Not found"})
        return json_response(start_response, "200 OK", build_player_prediction(player_id))

    if path.startswith("/game/") and path.endswith("/edge"):
        game_id = path[len("/game/") : -len("/edge")].strip("/")
        if not game_id:
            return json_response(start_response, "404 Not Found", {"error": "Not found"})
        sports_data = {}
        odds_data = {}
        if "model_probability" in query:
            try:
                sports_data["model_probability"] = float(query["model_probability"][0])
            except ValueError:
                return json_response(
                    start_response,
                    "400 Bad Request",
                    {"error": "model_probability must be numeric"},
                )
            if not 0 <= sports_data["model_probability"] <= 1:
                return json_response(
                    start_response,
                    "400 Bad Request",
                    {"error": "model_probability must be between 0 and 1"},
                )
        if "odds" in query:
            try:
                odds_data["current_odds"] = int(query["odds"][0])
            except ValueError:
                return json_response(
                    start_response,
                    "400 Bad Request",
                    {"error": "odds must be an integer American line"},
                )
            if odds_data["current_odds"] == 0:
                return json_response(
                    start_response,
                    "400 Bad Request",
                    {"error": "odds cannot be zero"},
                )
        return json_response(start_response, "200 OK", build_game_edge(game_id, sports_data, odds_data))

    return json_response(start_response, "404 Not Found", {"error": "Not found"})


if __name__ == "__main__":
    from wsgiref.simple_server import make_server

    with make_server("127.0.0.1", 8000, app) as server:
        print("Serving on http://127.0.0.1:8000")
        server.serve_forever()
