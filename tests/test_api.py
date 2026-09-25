import json
import os
import unittest
from io import BytesIO
from unittest.mock import patch

from choosing.api import app


def request(path: str):
    captured = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = headers

    body = b"".join(
        app(
            {
                "REQUEST_METHOD": "GET",
                "PATH_INFO": path.split("?", 1)[0],
                "QUERY_STRING": path.split("?", 1)[1] if "?" in path else "",
                "wsgi.input": BytesIO(),
            },
            start_response,
        )
    )
    captured["headers_map"] = {name: value for name, value in captured["headers"]}
    captured["raw_body"] = body.decode("utf-8")
    if captured["headers_map"]["Content-Type"].startswith("application/json"):
        captured["body"] = json.loads(captured["raw_body"])
    return captured


class PredictionApiTests(unittest.TestCase):
    def test_root_endpoint_describes_application(self):
        response = request("/")

        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(response["headers_map"]["Content-Type"], "text/html; charset=utf-8")
        self.assertIn("Mobile friendly betting dashboard", response["raw_body"])
        self.assertIn('name="viewport"', response["raw_body"])
        self.assertIn("Player name", response["raw_body"])
        self.assertIn("Team name", response["raw_body"])

    def test_app_metadata_endpoint_returns_machine_readable_json(self):
        response = request("/app.json")

        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(response["body"]["data_sources"], ["SportsDataIO", "The Odds API"])
        self.assertEqual(response["body"]["endpoints"]["game_edge"], "/game/{id}/edge")

    def test_health_endpoint_reports_source_modes(self):
        with patch.dict(os.environ, {}, clear=True):
            response = request("/health")

        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(response["body"]["sources"]["sports_data_io"]["mode"], "fallback")
        self.assertEqual(response["body"]["sources"]["odds_api"]["mode"], "fallback")

    def test_player_prediction_endpoint_returns_prediction_payload(self):
        response = request("/player/42/prediction")

        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(response["body"]["player_id"], "42")
        self.assertEqual(response["body"]["sources"], ["SportsDataIO"])
        self.assertTrue(response["body"]["meta"]["advisory_only"])
        predictions = response["body"]["predictions"]
        self.assertGreaterEqual(predictions["expected_minutes"], 0)
        self.assertLessEqual(predictions["expected_minutes"], 48)
        self.assertIn("underperformance_risk", predictions)
        self.assertIn("availability_probability", predictions)
        self.assertIn("player_name", response["body"])
        self.assertIn("team", response["body"])

    def test_player_prediction_endpoint_supports_player_name_and_team_lookup(self):
        response = request("/player/Jayson%20Tatum/prediction?team=Boston%20Celtics")

        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(response["body"]["player_id"], "42")
        self.assertEqual(response["body"]["player_name"], "Jayson Tatum")
        self.assertEqual(response["body"]["team"], "Boston Celtics")

    def test_player_prediction_endpoint_applies_overrides(self):
        response = request(
            "/player/42/prediction?recent_form=0.9&workload=0.1&injury_risk=0.2&availability=0.95"
        )

        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(response["body"]["player_signals"]["recent_form"], 0.9)
        self.assertEqual(response["body"]["source_snapshots"]["sports_data_io"]["availability"], 0.95)

    def test_game_edge_endpoint_uses_model_probability_and_odds_query_params(self):
        response = request("/game/Boston%20Celtics/edge?model_probability=0.61&odds=-110")

        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(response["body"]["game_id"], "finals")
        self.assertEqual(response["body"]["team"], "Boston Celtics")
        self.assertEqual(response["body"]["opponent"], "Dallas Mavericks")
        self.assertEqual(response["body"]["market_signals"]["current_odds"], -110)
        self.assertEqual(response["body"]["team_prediction"]["win_probability"], 0.61)
        self.assertEqual(response["body"]["market_signals"]["implied_probability"], 0.524)
        self.assertEqual(response["body"]["betting_edge"]["edge"], 0.086)
        self.assertEqual(response["body"]["betting_edge"]["recommended_action"], "bet")
        self.assertEqual(response["body"]["betting_edge"]["recommended_stake"], "medium")
        self.assertIn("confidence", response["body"]["betting_edge"])

    def test_game_edge_endpoint_supports_extended_market_inputs(self):
        response = request(
            "/game/finals/edge?opening_odds=-120&current_odds=105&steam_move=true"
            "&market_consensus=0.64&closing_line_value=0.05&expected_points_adjustment=4"
        )

        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(response["body"]["market_signals"]["opening_odds"], -120)
        self.assertEqual(response["body"]["market_signals"]["current_odds"], 105)
        self.assertTrue(response["body"]["market_signals"]["steam_move"])
        self.assertEqual(response["body"]["market_signals"]["closing_line_value"], 0.05)
        self.assertIn("expected_points", response["body"]["team_prediction"])

    def test_game_edge_endpoint_rejects_invalid_odds(self):
        response = request("/game/finals/edge?odds=abc")

        self.assertEqual(response["status"], "400 Bad Request")
        self.assertEqual(response["body"]["errors"]["odds"], "odds must be an integer American line")

    def test_game_edge_endpoint_rejects_zero_odds(self):
        response = request("/game/finals/edge?odds=0")

        self.assertEqual(response["status"], "400 Bad Request")
        self.assertEqual(response["body"]["error"], "current_odds cannot be zero")

    def test_game_edge_endpoint_rejects_out_of_range_model_probability(self):
        response = request("/game/finals/edge?model_probability=1.4")

        self.assertEqual(response["status"], "400 Bad Request")
        self.assertEqual(response["body"]["error"], "model_probability must be between 0 and 1")

    def test_player_prediction_rejects_out_of_range_effort_change(self):
        response = request("/player/42/prediction?effort_change=4")

        self.assertEqual(response["status"], "400 Bad Request")
        self.assertEqual(response["body"]["error"], "effort_change must be between -1 and 1")

    def test_lookup_endpoints_return_player_and_team_matches(self):
        player_response = request("/lookup/players?query=tatum")
        team_response = request("/lookup/teams?query=warriors")

        self.assertEqual(player_response["status"], "200 OK")
        self.assertEqual(player_response["body"]["players"][0]["name"], "Jayson Tatum")
        self.assertEqual(team_response["status"], "200 OK")
        self.assertEqual(team_response["body"]["teams"][0]["team"], "Golden State Warriors")


if __name__ == "__main__":
    unittest.main()
