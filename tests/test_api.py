import json
import os
import tempfile
import unittest
from io import BytesIO
from unittest.mock import patch

from choosing.api import app, service
from choosing.learner import WeightAdaptor
from choosing.service import PredictionService
from choosing.storage import PredictionStore


def request(path: str, method: str = "GET", body: dict | None = None):
    captured = {}
    raw_body = json.dumps(body).encode("utf-8") if body is not None else b""

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = headers

    body = b"".join(
        app(
            {
                "REQUEST_METHOD": method,
                "PATH_INFO": path.split("?", 1)[0],
                "QUERY_STRING": path.split("?", 1)[1] if "?" in path else "",
                "CONTENT_LENGTH": str(len(raw_body)),
                "wsgi.input": BytesIO(raw_body),
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
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_service = service
        isolated_store = PredictionStore(data_dir=os.path.abspath(self.temp_dir.name))
        isolated_learner = WeightAdaptor(model_path=os.path.join(self.temp_dir.name, "adapted_models.json"))
        import choosing.api as api_module

        api_module.service = PredictionService(store=isolated_store, learner=isolated_learner)
        self.api_module = api_module

    def tearDown(self):
        self.api_module.service = self.original_service
        self.temp_dir.cleanup()

    def test_root_endpoint_describes_application(self):
        response = request("/")

        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(response["headers_map"]["Content-Type"], "text/html; charset=utf-8")
        self.assertIn("Mobile friendly betting dashboard", response["raw_body"])
        self.assertIn('name="viewport"', response["raw_body"])
        self.assertIn("Player name", response["raw_body"])
        self.assertIn("Team name", response["raw_body"])
        self.assertNotIn("Jayson Tatum", response["raw_body"])
        self.assertIn('placeholder="Search player name"', response["raw_body"])
        self.assertIn('placeholder="Search team name"', response["raw_body"])
        self.assertIn('id="player-sport"', response["raw_body"])
        self.assertIn('id="top-players-sport"', response["raw_body"])
        self.assertIn("Top players by sport", response["raw_body"])
        self.assertIn("View player data", response["raw_body"])
        self.assertIn("americanfootball_nfl", response["raw_body"])
        self.assertIn("Player profile", response["raw_body"])
        self.assertIn("Injury status", response["raw_body"])
        self.assertIn("Prediction confidence", response["raw_body"])
        self.assertIn("Edge quality", response["raw_body"])
        self.assertIn("Backtesting &amp; learning", response["raw_body"])
        self.assertIn("Media &amp; Broadcast", response["raw_body"])
        self.assertIn("Fantasy Sports API", response["raw_body"])
        self.assertIn("The Odds API endpoints", response["raw_body"])
        self.assertIn("/sports/{sport}/odds", response["raw_body"])
        self.assertIn("/historical/sports/{sport}/odds", response["raw_body"])
        self.assertIn("The Odds API sports", response["raw_body"])
        self.assertIn("NFL", response["raw_body"])
        self.assertIn("Olympics", response["raw_body"])
        self.assertIn("Sport", response["raw_body"])
        self.assertIn("Sport profile", response["raw_body"])

    def test_app_metadata_endpoint_returns_machine_readable_json(self):
        response = request("/app.json")

        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(
            response["body"]["data_sources"],
            ["SportsDataIO", "Media & Broadcast", "Fantasy Sports API", "The Odds API"],
        )
        self.assertEqual(response["body"]["upstream_endpoints"]["the_odds_api"][0]["path"], "/sports")
        self.assertEqual(
            response["body"]["upstream_endpoints"]["the_odds_api"][1]["path"],
            "/sports/{sport}/odds",
        )
        self.assertEqual(response["body"]["upstream_sports"]["the_odds_api"][0]["name"], "NFL")
        self.assertEqual(response["body"]["upstream_sports"]["the_odds_api"][-1]["name"], "Olympics")
        self.assertEqual(response["body"]["endpoints"]["top_players"], "/players/top?sport={sport_key}&limit=10")
        self.assertEqual(response["body"]["endpoints"]["game_edge"], "/game/{id}/edge")
        self.assertEqual(response["body"]["endpoints"]["backtest_summary"], "/backtest/summary.json")

    def test_health_endpoint_reports_source_modes(self):
        with patch.dict(os.environ, {}, clear=True):
            self.api_module.service.sports_client._last_call_succeeded = None
            self.api_module.service.sports_client._last_error_message = None
            self.api_module.service.media_client._last_call_succeeded = None
            self.api_module.service.media_client._last_error_message = None
            self.api_module.service.fantasy_client._last_call_succeeded = None
            self.api_module.service.fantasy_client._last_error_message = None
            self.api_module.service.odds_client._last_call_succeeded = None
            self.api_module.service.odds_client._last_error_message = None
            response = request("/health")

        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(response["body"]["sources"]["sports_data_io"]["mode"], "fallback")
        self.assertEqual(response["body"]["sources"]["media_broadcast"]["mode"], "fallback")
        self.assertEqual(response["body"]["sources"]["fantasy_sports_api"]["mode"], "fallback")
        self.assertEqual(response["body"]["sources"]["odds_api"]["mode"], "fallback")
        self.assertFalse(response["body"]["sources"]["sports_data_io"]["configured"])
        self.assertFalse(response["body"]["sources"]["media_broadcast"]["configured"])
        self.assertFalse(response["body"]["sources"]["fantasy_sports_api"]["configured"])
        self.assertFalse(response["body"]["sources"]["odds_api"]["configured"])
        self.assertIsNone(response["body"]["sources"]["sports_data_io"]["last_call_succeeded"])
        self.assertEqual(
            response["body"]["sources"]["sports_data_io"]["last_error_message"],
            "API key not configured",
        )

    def test_health_endpoint_exposes_last_upstream_status(self):
        with patch.dict(
            os.environ,
            {
                "SPORTSDATAIO_API_KEY": "sports-key",
                "MEDIA_BROADCAST_API_KEY": "media-key",
                "FANTASY_SPORTS_API_KEY": "fantasy-key",
                "ODDS_API_KEY": "odds-key",
            },
            clear=True,
        ):
            self.api_module.service.sports_client._last_call_succeeded = True
            self.api_module.service.sports_client._last_error_message = None
            self.api_module.service.media_client._last_call_succeeded = True
            self.api_module.service.media_client._last_error_message = None
            self.api_module.service.fantasy_client._last_call_succeeded = False
            self.api_module.service.fantasy_client._last_error_message = "projection feed unavailable"
            self.api_module.service.odds_client._last_call_succeeded = False
            self.api_module.service.odds_client._last_error_message = "upstream timeout"
            response = request("/health")

        self.assertTrue(response["body"]["sources"]["sports_data_io"]["configured"])
        self.assertTrue(response["body"]["sources"]["sports_data_io"]["last_call_succeeded"])
        self.assertIsNone(response["body"]["sources"]["sports_data_io"]["last_error_message"])
        self.assertTrue(response["body"]["sources"]["media_broadcast"]["configured"])
        self.assertTrue(response["body"]["sources"]["media_broadcast"]["last_call_succeeded"])
        self.assertIsNone(response["body"]["sources"]["media_broadcast"]["last_error_message"])
        self.assertTrue(response["body"]["sources"]["fantasy_sports_api"]["configured"])
        self.assertFalse(response["body"]["sources"]["fantasy_sports_api"]["last_call_succeeded"])
        self.assertEqual(
            response["body"]["sources"]["fantasy_sports_api"]["last_error_message"],
            "projection feed unavailable",
        )
        self.assertTrue(response["body"]["sources"]["odds_api"]["configured"])
        self.assertFalse(response["body"]["sources"]["odds_api"]["last_call_succeeded"])
        self.assertEqual(response["body"]["sources"]["odds_api"]["last_error_message"], "upstream timeout")

    def test_player_prediction_endpoint_returns_prediction_payload(self):
        response = request("/player/42/prediction")

        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(response["body"]["player_id"], "42")
        self.assertEqual(response["body"]["sources"], ["SportsDataIO", "Media & Broadcast", "Fantasy Sports API"])
        self.assertTrue(response["body"]["meta"]["advisory_only"])
        self.assertIn("prediction_id", response["body"]["meta"])
        predictions = response["body"]["predictions"]
        self.assertGreaterEqual(predictions["expected_minutes"], 0)
        self.assertLessEqual(predictions["expected_minutes"], 48)
        self.assertIn("expected_points", predictions)
        self.assertIn("underperformance_risk", predictions)
        self.assertIn("availability_probability", predictions)
        self.assertIn("injured", predictions)
        self.assertIn("injured_label", predictions)
        self.assertIn("suggestions", predictions)
        self.assertIn("likely_to_score", predictions)
        self.assertIn("scoring_outlook", predictions)
        self.assertIn("expected_points_range", predictions)
        self.assertIn("expected_minutes_range", predictions)
        self.assertIn("expected_performance_range", predictions)
        self.assertIn("prediction_confidence", predictions)
        self.assertIn("confidence_band", predictions)
        self.assertIn("feature_tracking", predictions)
        self.assertIn("player_profile", response["body"])
        self.assertIn("computation_data", response["body"]["player_profile"])
        self.assertIn("injury_status", response["body"])
        self.assertIn("injury_status", response["body"]["player_profile"])
        self.assertIn("injured", response["body"]["player_profile"])
        self.assertIn("injured_label", response["body"]["player_profile"])
        self.assertIn("suggestions", response["body"]["player_profile"])
        self.assertIn("player_name", response["body"])
        self.assertIn("team", response["body"])
        self.assertEqual(response["body"]["sport"]["name"], "Basketball")
        self.assertEqual(response["body"]["sport"]["league"], "NBA")
        self.assertIn("media_broadcast_signals", response["body"])
        self.assertIn("fantasy_sports_signals", response["body"])
        self.assertIn("media_broadcast", response["body"]["source_snapshots"])
        self.assertIn("fantasy_sports_api", response["body"]["source_snapshots"])
        self.assertIn("odds_api", response["body"]["source_snapshots"])
        self.assertEqual(response["body"]["odds_api_catalog"]["provider"], "The Odds API")
        self.assertEqual(response["body"]["odds_api_catalog"]["sports"][0]["name"], "NFL")
        self.assertEqual(response["body"]["predictions"]["odds_api_endpoints"][0]["path"], "/sports")
        self.assertEqual(response["body"]["player_profile"]["sport"]["league"], "NBA")
        self.assertEqual(response["body"]["player_profile"]["odds_api_coverage"]["sports"][-1]["name"], "Olympics")
        self.assertEqual(
            response["body"]["player_profile"]["computation_data"]["odds_api_endpoints"][1]["path"],
            "/sports/{sport}/odds",
        )
        self.assertIn("recent_form_l3", response["body"]["player_profile"]["computation_data"])
        self.assertIn("prediction_confidence", response["body"]["player_profile"])
        self.assertIn("feature_tracking", response["body"]["player_profile"])

    def test_player_prediction_endpoint_supports_player_name_and_team_lookup(self):
        response = request("/player/Stephen%20Curry/prediction?team=Golden%20State%20Warriors")

        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(response["body"]["player_id"], "30")
        self.assertEqual(response["body"]["player_name"], "Stephen Curry")
        self.assertEqual(response["body"]["team"], "Golden State Warriors")
        self.assertIn(response["body"]["player_profile"]["risk_level"], {"Low", "Moderate", "High"})
        self.assertIn(response["body"]["injury_status"], {"Available", "Probable", "Limited", "Questionable", "Out"})

    def test_player_prediction_endpoint_supports_selected_sport(self):
        response = request("/player/Stephen%20Curry/prediction?team=Golden%20State%20Warriors&sport=americanfootball_nfl")

        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(response["body"]["sport"]["name"], "American Football")
        self.assertEqual(response["body"]["sport"]["league"], "NFL")
        self.assertEqual(response["body"]["sport"]["odds_api_key"], "americanfootball_nfl")
        self.assertEqual(response["body"]["player_profile"]["sport"]["league"], "NFL")

    def test_player_prediction_endpoint_applies_overrides(self):
        response = request(
            "/player/42/prediction?recent_form=0.9&workload=0.1&injury_risk=0.2&availability=0.95"
        )

        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(response["body"]["player_signals"]["recent_form"], 0.9)
        self.assertEqual(response["body"]["source_snapshots"]["sports_data_io"]["availability"], 0.95)
        self.assertGreater(response["body"]["predictions"]["expected_points"], 0)
        self.assertEqual(response["body"]["predictions"]["injured_label"], "No")
        self.assertGreaterEqual(len(response["body"]["predictions"]["suggestions"]), 1)
        self.assertGreaterEqual(response["body"]["predictions"]["prediction_confidence"], 0)

    def test_top_players_endpoint_returns_ranked_players_for_selected_sport(self):
        response = request("/players/top?sport=basketball_nba&limit=10")

        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(response["body"]["sport"]["league"], "NBA")
        self.assertEqual(response["body"]["summary"]["returned"], 10)
        self.assertEqual(len(response["body"]["top_players"]), 10)
        self.assertIn("/player/", response["body"]["top_players"][0]["player_prediction_path"])
        self.assertIn("injured_label", response["body"]["top_players"][0])
        self.assertIn("suggestions", response["body"]["top_players"][0])
        self.assertIn("prediction_confidence", response["body"]["top_players"][0])
        self.assertIn("expected_points_range", response["body"]["top_players"][0])
        self.assertGreaterEqual(
            response["body"]["top_players"][0]["expected_performance"],
            response["body"]["top_players"][-1]["expected_performance"],
        )

    def test_top_players_endpoint_rejects_invalid_limit(self):
        response = request("/players/top?limit=abc")

        self.assertEqual(response["status"], "400 Bad Request")
        self.assertEqual(response["body"]["error"], "limit must be an integer")

    def test_game_edge_endpoint_uses_model_probability_and_odds_query_params(self):
        response = request("/game/Golden%20State%20Warriors/edge?model_probability=0.61&odds=-110")

        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(response["body"]["game_id"], "warriors-lakers")
        self.assertEqual(response["body"]["team"], "Golden State Warriors")
        self.assertEqual(response["body"]["opponent"], "Los Angeles Lakers")
        self.assertEqual(response["body"]["market_signals"]["current_odds"], -110)
        self.assertEqual(response["body"]["team_prediction"]["win_probability"], 0.61)
        self.assertEqual(response["body"]["market_signals"]["implied_probability"], 0.524)
        self.assertEqual(response["body"]["betting_edge"]["edge"], 0.086)
        self.assertEqual(response["body"]["betting_edge"]["recommended_action"], "bet")
        self.assertEqual(response["body"]["betting_edge"]["recommended_stake"], "medium")
        self.assertIn("confidence", response["body"]["betting_edge"])
        self.assertIn("edge_quality", response["body"]["betting_edge"])
        self.assertIn("win_probability_range", response["body"]["team_prediction"])
        self.assertIn("prediction_id", response["body"]["meta"])
        self.assertIn("context_signals", response["body"])
        self.assertIn("media_broadcast", response["body"]["source_snapshots"])
        self.assertIn("fantasy_sports_api", response["body"]["source_snapshots"])

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
        self.assertIn("book_disagreement", response["body"]["market_signals"])
        self.assertIn("market_stability", response["body"]["market_signals"])
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
        player_response = request("/lookup/players?query=curry")
        sport_filtered_player_response = request("/lookup/players?query=mahomes&sport=americanfootball_nfl")
        team_response = request("/lookup/teams?query=warriors")

        self.assertEqual(player_response["status"], "200 OK")
        self.assertEqual(player_response["body"]["players"][0]["name"], "Stephen Curry")
        self.assertEqual(sport_filtered_player_response["status"], "200 OK")
        self.assertEqual(sport_filtered_player_response["body"]["players"][0]["name"], "Patrick Mahomes")
        self.assertEqual(team_response["status"], "200 OK")
        self.assertEqual(team_response["body"]["teams"][0]["team"], "Golden State Warriors")

    def test_backtest_summary_and_outcome_recording_endpoints(self):
        prediction = request("/game/Golden%20State%20Warriors/edge?model_probability=0.61&odds=-110")
        prediction_id = prediction["body"]["meta"]["prediction_id"]

        outcome_response = request(
            f"/predictions/{prediction_id}/outcome",
            method="POST",
            body={"actual_outcome": 1, "actual_odds": -110},
        )
        self.assertEqual(outcome_response["status"], "200 OK")
        self.assertEqual(outcome_response["body"]["prediction"]["prediction_id"], prediction_id)
        self.assertIn("backtest_summary", outcome_response["body"])

        summary = request("/backtest/summary.json")
        self.assertEqual(summary["status"], "200 OK")
        self.assertEqual(summary["body"]["resolved_games"], 1)
        self.assertIsNotNone(summary["body"]["roi"])
        self.assertIsNotNone(summary["body"]["brier_score"])


if __name__ == "__main__":
    unittest.main()
