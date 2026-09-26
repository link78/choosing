import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from choosing import jobs
from choosing.data_sources import OddsAPIClient, SportsDataIOClient, TTLCache, WeatherClient, compute_weather_impact
from choosing.learner import MIN_PLATT_SAMPLES, WeightAdaptor, fit_platt_scaling, ridge_regression
from choosing.metrics import build_breakdown, build_timeseries, compute_max_drawdown
from choosing.prediction import KELLY_CAPS, build_prop_edge, kelly_stake
from choosing.service import PredictionService
from choosing.storage import PredictionStore, compute_clv

from test_api import request


def _now_iso(offset_hours: float = 0.0) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=offset_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def fake_odds_fetcher(url: str, headers=None, timeout=5.0):
    if "/scores" in url:
        return [
            {
                "id": "evt-1",
                "home_team": "Golden State Warriors",
                "away_team": "Los Angeles Lakers",
                "commence_time": _now_iso(1),
                "completed": True,
                "scores": [
                    {"name": "Golden State Warriors", "score": "118"},
                    {"name": "Los Angeles Lakers", "score": "110"},
                ],
            }
        ]
    if "/historical/" in url:
        return {
            "data": [
                {
                    "home_team": "Golden State Warriors",
                    "away_team": "Los Angeles Lakers",
                    "bookmakers": [
                        {"markets": [{"key": "h2h", "outcomes": [{"name": "Golden State Warriors", "price": -150}]}]}
                    ],
                }
            ]
        }
    return []


def fake_sports_fetcher(url: str, headers=None, timeout=5.0):
    if "PlayerGameStatsByDate" in url:
        return [{"PlayerID": 30, "Name": "Stephen Curry", "Team": "GS", "Points": 31, "Minutes": 35}]
    return None


class PerformanceTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = PredictionStore(data_dir=os.path.abspath(self.temp_dir.name))
        self.learner = WeightAdaptor(model_path=os.path.join(self.temp_dir.name, "adapted_models.json"))

    def tearDown(self):
        self.temp_dir.cleanup()

    def build_service(self, **clients) -> PredictionService:
        return PredictionService(store=self.store, learner=self.learner, **clients)


class GradingTests(PerformanceTestCase):
    def test_grade_endpoint_grades_games_and_players_with_clv(self):
        with patch.dict(os.environ, {"ODDS_API_KEY": "k", "SPORTSDATAIO_API_KEY": "k", "UPSTREAM_CACHE_TTL_SECONDS": "0"}):
            service = self.build_service(
                odds_client=OddsAPIClient(fetcher=fake_odds_fetcher),
                sports_client=SportsDataIOClient(fetcher=fake_sports_fetcher),
            )
            import choosing.api as api_module

            with patch.object(api_module, "service", service):
                game = request("/game/Golden%20State%20Warriors/edge?model_probability=0.61&odds=-110")
                player = request("/player/Stephen%20Curry/prediction?average_points=28&minutes_played=34")
                self.assertEqual(game["status"], "200 OK")
                self.assertEqual(player["status"], "200 OK")

                bad = request("/backtest/grade?date=not-a-date", method="POST")
                self.assertEqual(bad["status"], "400 Bad Request")

                graded = request("/backtest/grade", method="POST")
                self.assertEqual(graded["status"], "200 OK")
                self.assertEqual(graded["body"]["graded_count"], 2)
                self.assertEqual(graded["body"]["pending"], 0)

                summary = request("/backtest/summary.json")["body"]
                self.assertEqual(summary["pending_predictions"], 0)
                self.assertEqual(summary["closing_line_value"]["samples"], 1)
                self.assertGreater(summary["closing_line_value"]["average_clv"], 0)
                self.assertEqual(summary["closing_line_value"]["beat_close_rate"], 1.0)

        game_record = self.store.get_prediction(game["body"]["meta"]["prediction_id"])
        self.assertEqual(game_record["closing_odds"], -150)
        self.assertEqual(game_record["graded_by"], "auto:the_odds_api")

    def test_manual_outcome_with_closing_odds_computes_clv(self):
        self.assertGreater(compute_clv(-110, -150), 0)
        self.assertLess(compute_clv(-150, -110), 0)


class TimeseriesAndBreakdownTests(PerformanceTestCase):
    def setUp(self):
        super().setUp()
        import choosing.api as api_module

        self.service = self.build_service()
        self.patcher = patch.object(api_module, "service", self.service)
        self.patcher.start()
        for index, outcome in enumerate([1, 0, 1, 1, 0]):
            response = request(f"/game/Golden%20State%20Warriors/edge?model_probability=0.{60 + index}&odds=-110")
            request(
                f"/predictions/{response['body']['meta']['prediction_id']}/outcome",
                method="POST",
                body={"actual_outcome": outcome, "closing_odds": -120},
            )

    def tearDown(self):
        self.patcher.stop()
        super().tearDown()

    def test_timeseries_endpoint_returns_curves_and_validates_window(self):
        response = request("/backtest/timeseries?window=all&rolling=3")
        self.assertEqual(response["status"], "200 OK")
        body = response["body"]
        self.assertEqual(len(body["points"]), 5)
        self.assertIn("max_drawdown", body["summary"])
        self.assertIn("rolling_brier_score", body["points"][-1])
        self.assertEqual(request("/backtest/timeseries?window=1y")["status"], "400 Bad Request")

    def test_breakdown_endpoint_groups_and_validates_dimension(self):
        for dimension in ["sport", "market", "confidence_band", "edge_bucket", "model_version"]:
            response = request(f"/backtest/breakdown?by={dimension}")
            self.assertEqual(response["status"], "200 OK", dimension)
            self.assertTrue(response["body"]["segments"])
        self.assertEqual(request("/backtest/breakdown?by=weather")["status"], "400 Bad Request")

    def test_csv_export_and_slate(self):
        csv_response = request("/predictions.csv")
        self.assertEqual(csv_response["status"], "200 OK")
        self.assertTrue(csv_response["headers_map"]["Content-Type"].startswith("text/csv"))
        self.assertIn("attachment", csv_response["headers_map"]["Content-Disposition"])
        lines = csv_response["raw_body"].strip().splitlines()
        self.assertEqual(len(lines), 6)
        self.assertIn("prediction_id", lines[0])

        slate = request("/slate?sport=basketball_nba&limit=5")
        self.assertEqual(slate["status"], "200 OK")
        edges = [entry["edge"] for entry in slate["body"]["games"]]
        self.assertEqual(edges, sorted(edges, reverse=True))
        filtered = request("/slate?sport=basketball_nba&min_edge=0.99")
        self.assertEqual(filtered["body"]["games"], [])
        self.assertEqual(request("/slate?min_confidence=2")["status"], "400 Bad Request")

    def test_root_page_includes_new_dashboard_sections(self):
        html = request("/")["raw_body"]
        for marker in ["health-banner", "grade-form", "slate-form", "performance-charts", "watchlist-result", "/predictions.csv"]:
            self.assertIn(marker, html)


class ModelTests(unittest.TestCase):
    def test_kelly_stake_respects_confidence_caps(self):
        for band, cap in KELLY_CAPS.items():
            stake = kelly_stake(0.9, 100, band)
            self.assertLessEqual(stake["stake_fraction"], cap)
        self.assertEqual(kelly_stake(0.4, -110, "High")["stake_fraction"], 0.0)

    def test_prop_edge_recommends_over_when_projection_beats_line(self):
        edge = build_prop_edge(30.0, {"low": 26.0, "high": 34.0}, {"line": 25.5, "over_odds": -110, "under_odds": -110}, "Moderate")
        self.assertEqual(edge["recommended_action"], "over")
        self.assertGreater(edge["edge"], 0)

    def test_player_prop_overrides_are_graded(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = PredictionStore(data_dir=temp_dir)
            service = PredictionService(store=store, learner=WeightAdaptor(model_path=os.path.join(temp_dir, "m.json")))
            payload = service.get_player_prediction(
                "Stephen Curry",
                {"average_points": 30, "prop_line": 20.5, "over_odds": -110, "under_odds": -110},
            )
            prediction_id = payload["meta"]["prediction_id"]
            record = store.record_outcome(prediction_id, {"actual_points": 28, "actual_minutes": 34})
            self.assertEqual(record["market"], "player_points")
            self.assertEqual(record["actual_outcome"], 1)
            self.assertGreater(record["profit_units"], 0)

    def test_platt_scaling_requires_minimum_samples_and_corrects_overconfidence(self):
        self.assertIsNone(fit_platt_scaling([0.7] * (MIN_PLATT_SAMPLES - 1), [1, 0] * MIN_PLATT_SAMPLES))
        probabilities = [0.8] * 60
        outcomes = [1] * 30 + [0] * 30
        calibrator = fit_platt_scaling(probabilities, outcomes)
        self.assertIsNotNone(calibrator)
        from choosing.prediction import platt_calibrate

        self.assertLess(platt_calibrate(0.8, calibrator), 0.8)

    def test_ridge_regression_recovers_linear_signal(self):
        rows = [[float(x)] for x in range(10)]
        targets = [2.0 * x for x in range(10)]
        coefficients = ridge_regression(rows, targets, alpha=0.001)
        self.assertAlmostEqual(coefficients[0], 2.0, places=2)

    def test_max_drawdown(self):
        records = [{"profit_units": value} for value in [1, -2, 1, -1]]
        self.assertEqual(compute_max_drawdown(records), 2)
        self.assertIsNone(compute_max_drawdown([]))

    def test_metrics_helpers_accept_empty_history(self):
        self.assertEqual(build_timeseries([], window="all")["points"], [])
        self.assertEqual(build_breakdown([], "sport")["segments"], [])


class ReliabilityTests(unittest.TestCase):
    def test_ttl_cache_avoids_repeated_upstream_calls(self):
        calls = []

        def fetcher(url, headers=None, timeout=5.0):
            calls.append(url)
            return []

        with patch.dict(os.environ, {"ODDS_API_KEY": "k", "UPSTREAM_CACHE_TTL_SECONDS": "60"}):
            client = OddsAPIClient(fetcher=fetcher)
            client.fetch_events("basketball_nba")
            client.fetch_events("basketball_nba")
        self.assertEqual(len(calls), 1)
        cache = TTLCache(ttl_seconds=0)
        cache.set("a", 1)
        self.assertIsNone(cache.get("a"))

    def test_weather_is_opt_in_and_ignores_indoor_venues(self):
        with patch.dict(os.environ, {"OPEN_METEO_ENABLED": ""}):
            self.assertEqual(WeatherClient().source_status()["mode"], "disabled")
        self.assertEqual(compute_weather_impact(65, 3, 0), 0.0)
        self.assertGreater(compute_weather_impact(20, 30, 5), 0.5)

    def test_jobs_grade_command_uses_injected_service(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service = PredictionService(
                store=PredictionStore(data_dir=temp_dir),
                learner=WeightAdaptor(model_path=os.path.join(temp_dir, "m.json")),
            )
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = jobs.main(["grade"], service=service)
            self.assertEqual(exit_code, 0)
            self.assertIn("graded_count", output.getvalue())


if __name__ == "__main__":
    unittest.main()
