import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from choosing.data_sources import OddsAPIClient, SportsDataIOClient, compute_schedule_context, haversine_miles
from choosing.elo import SurfaceElo, build_surface_elo, infer_surface, normalize_surface
from choosing.learner import WeightAdaptor
from choosing.prediction import compute_schedule_adjustment
from choosing.service import PredictionService
from choosing.storage import PredictionStore

from test_api import request


def _iso(days: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")


class IsolatedServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = PredictionStore(data_dir=os.path.abspath(self.temp_dir.name))
        self.learner = WeightAdaptor(model_path=os.path.join(self.temp_dir.name, "adapted_models.json"))
        import choosing.api as api_module

        self.api_module = api_module

    def tearDown(self):
        self.temp_dir.cleanup()

    def use_service(self, **clients):
        service = PredictionService(store=self.store, learner=self.learner, **clients)
        patcher = patch.object(self.api_module, "service", service)
        patcher.start()
        self.addCleanup(patcher.stop)
        return service


class TennisEloTests(IsolatedServiceTestCase):
    def test_surface_helpers(self):
        self.assertEqual(infer_surface("tennis_atp_french_open"), "clay")
        self.assertEqual(infer_surface("tennis_wta_wimbledon"), "grass")
        self.assertEqual(infer_surface("tennis_atp_us_open"), "hard")
        self.assertIsNone(normalize_surface(""))
        with self.assertRaises(ValueError):
            normalize_surface("ice")

    def test_surface_rating_diverges_from_overall(self):
        elo = SurfaceElo()
        for _ in range(10):
            elo.update("Clay Specialist", "Grass Specialist", "clay", True)
            elo.update("Clay Specialist", "Grass Specialist", "grass", False)
        clay = elo.predict("Clay Specialist", "Grass Specialist", "clay")
        grass = elo.predict("Clay Specialist", "Grass Specialist", "grass")
        self.assertGreater(clay["elo_probability"], 0.5)
        self.assertLess(grass["elo_probability"], 0.5)
        self.assertEqual(clay["player_surface_matches"], 10)
        self.assertEqual(clay["blend_weight"], 0.5)

    def test_same_match_from_both_sides_is_counted_once(self):
        created = datetime.now(timezone.utc).isoformat()
        records = [
            {"entity_type": "game", "sport_key": "tennis_*", "created_at": created, "team": "A", "actual_outcome": 1,
             "payload": {"opponent": "B", "tennis_elo": {"surface": "clay"}}},
            {"entity_type": "game", "sport_key": "tennis_*", "created_at": created, "team": "B", "actual_outcome": 0,
             "payload": {"opponent": "A", "tennis_elo": {"surface": "clay"}}},
        ]
        self.assertEqual(build_surface_elo(records).matches["a"], 1)

    def test_tennis_edge_uses_graded_history(self):
        self.use_service()
        baseline = request("/game/Jannik%20Sinner/edge?sport=tennis_*&opponent=Carlos%20Alcaraz&surface=clay&odds=-110")
        self.assertEqual(baseline["status"], "200 OK")
        self.assertEqual(baseline["body"]["opponent"], "Carlos Alcaraz")
        self.assertEqual(baseline["body"]["tennis_elo"]["blend_weight"], 0.0)
        for _ in range(4):
            response = request("/game/Jannik%20Sinner/edge?sport=tennis_*&opponent=Carlos%20Alcaraz&surface=clay&odds=-110")
            request(f"/predictions/{response['body']['meta']['prediction_id']}/outcome", method="POST", body={"actual_outcome": 1})
        after = request("/game/Jannik%20Sinner/edge?sport=tennis_*&opponent=Carlos%20Alcaraz&surface=clay&odds=-110")
        self.assertGreater(after["body"]["tennis_elo"]["elo_probability"], 0.5)
        self.assertEqual(request("/game/Jannik%20Sinner/edge?surface=ice")["status"], "400 Bad Request")


class ScheduleTests(IsolatedServiceTestCase):
    def test_compute_schedule_context_from_schedule(self):
        games = [
            {"HomeTeam": "GS", "AwayTeam": "LAL", "DateTime": _iso(-1)},
            {"HomeTeam": "BOS", "AwayTeam": "GS", "DateTime": _iso(0.5)},
        ]
        names = {"GS": "Golden State Warriors", "BOS": "Boston Celtics", "LAL": "Los Angeles Lakers"}
        context = compute_schedule_context(games, "GS", names)
        self.assertTrue(context["road_game"])
        self.assertGreater(context["travel_miles"], 2500)
        self.assertGreater(context["travel_fatigue"], 0.6)
        self.assertAlmostEqual(haversine_miles((0, 0), (0, 1)), 69.1, places=0)

    def test_live_schedule_context_feeds_game_model(self):
        def fetcher(url, headers=None, timeout=5.0):
            if "scores/json/Teams" in url:
                return [
                    {"Key": "GS", "City": "Golden State", "Name": "Warriors"},
                    {"Key": "LAL", "City": "Los Angeles", "Name": "Lakers"},
                    {"Key": "BOS", "City": "Boston", "Name": "Celtics"},
                ]
            if "Schedules" in url:
                return [
                    {"HomeTeam": "GS", "AwayTeam": "BOS", "DateTime": _iso(-3)},
                    {"HomeTeam": "BOS", "AwayTeam": "LAL", "DateTime": _iso(-1)},
                    {"HomeTeam": "GS", "AwayTeam": "LAL", "DateTime": _iso(0.3)},
                ]
            return None

        with patch.dict(os.environ, {"SPORTSDATAIO_API_KEY": "k", "UPSTREAM_CACHE_TTL_SECONDS": "0"}):
            self.use_service(sports_client=SportsDataIOClient(fetcher=fetcher))
            response = request("/game/Golden%20State%20Warriors/edge?odds=-110")
        schedule = response["body"]["schedule_context"]
        self.assertEqual(schedule["source_mode"], "live")
        self.assertGreater(schedule["rest_days"], schedule["opponent_rest_days"])
        self.assertGreater(schedule["opponent_travel_miles"], 2500)
        self.assertGreater(response["body"]["team_prediction"]["schedule_adjustment"], 0)

    def test_schedule_overrides_and_validation(self):
        self.use_service()
        neutral = request("/game/Golden%20State%20Warriors/edge?odds=-110")
        self.assertIsNone(neutral["body"]["schedule_context"])
        self.assertEqual(neutral["body"]["team_prediction"]["schedule_adjustment"], 0)
        rested = request("/game/Golden%20State%20Warriors/edge?odds=-110&rest_days=3&opponent_rest_days=0&opponent_travel_miles=2400")
        self.assertGreater(rested["body"]["team_prediction"]["win_probability"], neutral["body"]["team_prediction"]["win_probability"])
        self.assertEqual(rested["body"]["schedule_context"]["source_mode"], "override")
        self.assertEqual(request("/game/x/edge?rest_days=8")["status"], "400 Bad Request")
        self.assertEqual(request("/game/x/edge?travel_miles=-1")["status"], "400 Bad Request")
        self.assertEqual(compute_schedule_adjustment({}), 0)


class PropLineMovementTests(IsolatedServiceTestCase):
    def test_live_prop_snapshots_flag_movement_against_pick(self):
        state = {"line": 20.5}

        def fetcher(url, headers=None, timeout=5.0):
            if "/events/evt-1/odds" in url:
                return {
                    "bookmakers": [
                        {"markets": [{"key": "player_points", "outcomes": [
                            {"name": "Over", "description": "Stephen Curry", "point": state["line"], "price": -110},
                            {"name": "Under", "description": "Stephen Curry", "point": state["line"], "price": -110},
                        ]}]}
                    ]
                }
            if url.split("?")[0].endswith("/events"):
                return [{"id": "evt-1", "home_team": "Golden State Warriors", "away_team": "Los Angeles Lakers", "commence_time": _iso(0.2)}]
            return []

        with patch.dict(os.environ, {"ODDS_API_KEY": "k", "UPSTREAM_CACHE_TTL_SECONDS": "0"}):
            service = self.use_service(odds_client=OddsAPIClient(fetcher=fetcher))
            first = service.get_player_prediction("Stephen Curry", {"average_points": 30})
            self.assertEqual(first["prop_market"]["recommended_action"], "over")
            self.assertEqual(first["prop_market"]["line_history"]["snapshots"], 1)
            state["line"] = 19.0
            second = service.get_player_prediction("Stephen Curry", {"average_points": 30})
        history = second["prop_market"]["line_history"]
        self.assertEqual(history["snapshots"], 2)
        self.assertEqual(history["opening_line"], 20.5)
        self.assertEqual(history["line_change"], -1.5)
        self.assertTrue(history["movement_against_pick"])
        self.assertIsNotNone(history["warning"])


class CopyPredictionIdUiTests(IsolatedServiceTestCase):
    def test_dashboard_renders_copy_controls(self):
        self.use_service()
        html = request("/")["raw_body"]
        self.assertIn("function predictionIdMarkup", html)
        self.assertIn('data-copy-from="outcome-prediction-id"', html)
        self.assertIn("handleCopyClick", html)
        self.assertIn('id="game-surface"', html)
        self.assertIn('id="game-opponent"', html)


if __name__ == "__main__":
    unittest.main()
