import json
import unittest
from io import BytesIO

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
    captured["body"] = json.loads(body.decode("utf-8"))
    return captured


class PredictionApiTests(unittest.TestCase):
    def test_player_prediction_endpoint_returns_prediction_payload(self):
        response = request("/player/42/prediction")

        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(response["body"]["player_id"], "42")
        self.assertEqual(response["body"]["sources"], ["SportsDataIO"])
        predictions = response["body"]["predictions"]
        self.assertGreaterEqual(predictions["expected_minutes"], 0)
        self.assertLessEqual(predictions["expected_minutes"], 48)
        self.assertIn("underperformance_risk", predictions)
        self.assertIn("availability_probability", predictions)

    def test_game_edge_endpoint_uses_model_probability_and_odds_query_params(self):
        response = request("/game/finals/edge?model_probability=0.61&odds=-110")

        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(response["body"]["game_id"], "finals")
        self.assertEqual(response["body"]["market_signals"]["current_odds"], -110)
        self.assertEqual(response["body"]["team_prediction"]["win_probability"], 0.61)
        self.assertEqual(response["body"]["market_signals"]["implied_probability"], 0.524)
        self.assertEqual(response["body"]["betting_edge"]["edge"], 0.086)
        self.assertEqual(response["body"]["betting_edge"]["recommended_action"], "bet")

    def test_game_edge_endpoint_rejects_invalid_odds(self):
        response = request("/game/finals/edge?odds=abc")

        self.assertEqual(response["status"], "400 Bad Request")
        self.assertEqual(response["body"]["error"], "odds must be an integer American line")

    def test_game_edge_endpoint_rejects_zero_odds(self):
        response = request("/game/finals/edge?odds=0")

        self.assertEqual(response["status"], "400 Bad Request")
        self.assertEqual(response["body"]["error"], "odds cannot be zero")

    def test_game_edge_endpoint_rejects_out_of_range_model_probability(self):
        response = request("/game/finals/edge?model_probability=1.4")

        self.assertEqual(response["status"], "400 Bad Request")
        self.assertEqual(response["body"]["error"], "model_probability must be between 0 and 1")


if __name__ == "__main__":
    unittest.main()
