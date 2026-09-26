import os
import unittest
from unittest.mock import patch

from choosing.mlb_props import (
    MLBLookupError,
    MLBPropModel,
    american_to_decimal,
    at_least_one_probability,
    market_comparison,
    probability_over,
    total_bases_distribution,
)
from test_api import request


class MLBMathTests(unittest.TestCase):
    def test_american_to_decimal(self):
        self.assertAlmostEqual(american_to_decimal(350), 4.5)
        self.assertAlmostEqual(american_to_decimal(-200), 1.5)
        with self.assertRaises(ValueError):
            american_to_decimal(0)

    def test_market_comparison_edge_uses_inverse_decimal_odds(self):
        result = market_comparison(0.25, 300, -450, "override", 0.5, "batter_home_runs")
        self.assertAlmostEqual(result["implied_probability"], 0.25)
        self.assertAlmostEqual(result["edge"], 0.0)
        self.assertLess(result["no_vig_probability"], 0.25)
        self.assertGreater(result["no_vig_edge"], 0)

    def test_total_bases_distribution_sums_to_one_and_matches_expectation(self):
        outcomes = {0: 0.7, 1: 0.15, 2: 0.05, 3: 0.01, 4: 0.09}
        distribution = total_bases_distribution(outcomes, 4.3)
        self.assertAlmostEqual(sum(distribution.values()), 1.0, places=9)
        expected = sum(total * prob for total, prob in distribution.items())
        per_pa = sum(bases * prob for bases, prob in outcomes.items())
        self.assertAlmostEqual(expected, per_pa * 4.3, places=9)
        self.assertAlmostEqual(probability_over(distribution, 0.5), 1 - distribution[0])

    def test_at_least_one_probability(self):
        self.assertAlmostEqual(at_least_one_probability(0.05, 4), 1 - 0.95**4)


class MLBModelTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.dict(os.environ, {"SPORTSDATAIO_API_KEY": "", "ODDS_API_KEY": ""})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.model = MLBPropModel()

    def test_layers_multiply_through_to_final_rate(self):
        result = self.model.project(
            "Aaron Judge",
            "Gerrit Cole",
            "Coors Field",
            {"wind_out_mph": 10, "temperature_f": 80, "hr_odds": 300, "tb_line": 1.5, "tb_over_odds": 110},
        )
        steps = result["steps"]
        baseline = steps["baseline_power"]
        self.assertAlmostEqual(baseline["hr_baseline"], round(58 / 704, 4))
        recent = steps["recent_form"]
        self.assertAlmostEqual(recent["hr_adj"], round(0.7 * (58 / 704) + 0.3 * (4 / 44), 4))
        self.assertAlmostEqual(steps["pitcher_matchup"]["m_pitcher"], round(0.95 / 1.20, 3))
        self.assertEqual(steps["ballpark"]["m_park"], 1.25)
        self.assertAlmostEqual(steps["weather"]["m_weather"], 1 + 10 * 0.01 + 10 * 0.005)
        expected_final = (
            (0.7 * (58 / 704) + 0.3 * (4 / 44)) * (0.95 / 1.20) * 1.25 * 1.15 * steps["pitch_type"]["m_pitchtype"]
        )
        self.assertAlmostEqual(result["home_run"]["per_pa_probability"], round(expected_final, 4), places=3)
        market = result["home_run"]["market"]
        self.assertEqual(market["source_mode"], "override")
        self.assertAlmostEqual(market["implied_probability"], 0.25)
        self.assertAlmostEqual(market["edge"], round(result["home_run"]["game_probability"] - 0.25, 4))
        self.assertEqual(result["total_bases"]["line"], 1.5)
        self.assertEqual(result["total_bases"]["market"]["source_mode"], "override")
        self.assertIn("not betting advice", result["disclaimer"])

    def test_park_and_pitcher_move_probability_in_expected_direction(self):
        hitter_friendly = self.model.project("Aaron Judge", "Gerrit Cole", "Coors Field")
        pitcher_friendly = self.model.project("Aaron Judge", "Paul Skenes", "T-Mobile Park")
        self.assertGreater(hitter_friendly["home_run"]["game_probability"], pitcher_friendly["home_run"]["game_probability"])
        self.assertGreater(hitter_friendly["total_bases"]["expected"], pitcher_friendly["total_bases"]["expected"])

    def test_dome_neutralizes_weather(self):
        result = self.model.project("Juan Soto", "Framber Valdez", "Tropicana Field", {"wind_out_mph": 20, "temperature_f": 95})
        self.assertTrue(result["steps"]["weather"]["roof_closed"])
        self.assertEqual(result["steps"]["weather"]["m_weather"], 1.0)

    def test_defaults_to_home_park_and_fallback_market(self):
        result = self.model.project("Mookie Betts")
        self.assertEqual(result["park"]["name"], "Dodger Stadium")
        self.assertEqual(result["pitcher"]["name"], "League Average Pitcher")
        self.assertEqual(result["home_run"]["market"]["source_mode"], "fallback")
        self.assertIsNotNone(result["home_run"]["market"]["edge"])
        self.assertEqual(result["sources"]["sportsdataio"]["batter"], "fallback")

    def test_unknown_player_raises_lookup_error(self):
        with self.assertRaises(MLBLookupError):
            self.model.project("Nobody Here")

    def test_live_sportsdataio_stats_replace_reference_totals(self):
        season = [
            {"PlayerID": 1, "Name": "Aaron Judge", "Team": "NYY", "Games": 100, "PlateAppearances": 400, "AtBats": 340,
             "Hits": 100, "Doubles": 20, "Triples": 0, "HomeRuns": 30},
        ]
        logs = [{"PlateAppearances": 4, "Singles": 1, "Doubles": 0, "Triples": 0, "HomeRuns": 1} for _ in range(10)]

        def fetcher(url, headers=None, timeout=5.0):
            return logs if "PlayerGameStatsBySeason" in url else season

        with patch.dict(os.environ, {"SPORTSDATAIO_API_KEY": "test"}):
            model = MLBPropModel()
            model.sports_client.fetcher = fetcher
            result = model.project("Aaron Judge")
        self.assertEqual(result["sources"]["sportsdataio"]["batter"], "live")
        self.assertAlmostEqual(result["steps"]["baseline_power"]["hr_baseline"], 0.075)
        self.assertAlmostEqual(result["steps"]["recent_form"]["hr_l10"], 0.25)
        self.assertAlmostEqual(result["steps"]["recent_form"]["tb_l10"], 5.0)


class MLBLiveOddsTests(unittest.TestCase):
    def test_live_odds_api_home_run_and_total_bases_markets(self):
        events = [{"id": "evt1", "home_team": "New York Yankees", "away_team": "Boston Red Sox", "commence_time": "2026-09-27T23:05:00Z"}]

        def odds_payload(market):
            if market == "batter_home_runs":
                outcomes = [{"name": "Over", "description": "Aaron Judge", "point": 0.5, "price": 280}]
            else:
                outcomes = [
                    {"name": "Over", "description": "Aaron Judge", "point": 1.5, "price": 105},
                    {"name": "Under", "description": "Aaron Judge", "point": 1.5, "price": -135},
                ]
            return {"bookmakers": [{"markets": [{"key": market, "outcomes": outcomes}]}]}

        def fetcher(url, headers=None, timeout=5.0):
            if "/events/evt1/odds" in url:
                return odds_payload("batter_home_runs" if "batter_home_runs" in url else "batter_total_bases")
            return events

        with patch.dict(os.environ, {"SPORTSDATAIO_API_KEY": "", "ODDS_API_KEY": "test"}):
            model = MLBPropModel()
            model.odds_client.fetcher = fetcher
            result = model.project("Aaron Judge", "Gerrit Cole")
        hr_market = result["home_run"]["market"]
        self.assertEqual(hr_market["source_mode"], "live")
        self.assertEqual(hr_market["over_odds"], 280)
        self.assertIsNone(hr_market["no_vig_probability"])
        tb_market = result["total_bases"]["market"]
        self.assertEqual(tb_market["source_mode"], "live")
        self.assertEqual(tb_market["line"], 1.5)
        self.assertEqual(tb_market["under_odds"], -135)
        self.assertIsNotNone(tb_market["no_vig_edge"])


class MLBApiTests(unittest.TestCase):
    def test_props_endpoint_returns_projection(self):
        response = request("/mlb/props?player=Aaron%20Judge&pitcher=Gerrit%20Cole&park=Yankee%20Stadium&hr_odds=320&roof_closed=false")
        self.assertEqual(response["status"], "200 OK")
        body = response["body"]
        self.assertEqual(body["sport"], "baseball_mlb")
        self.assertIn("pitch_type", body["steps"])
        self.assertEqual(body["home_run"]["market"]["over_odds"], 320)

    def test_props_endpoint_validation(self):
        self.assertEqual(request("/mlb/props")["status"], "400 Bad Request")
        self.assertEqual(request("/mlb/props?player=Aaron%20Judge&wind_out_mph=abc")["status"], "400 Bad Request")
        self.assertEqual(request("/mlb/props?player=Aaron%20Judge&temperature_f=500")["status"], "400 Bad Request")
        self.assertEqual(request("/mlb/props?player=Aaron%20Judge&hr_odds=50")["status"], "400 Bad Request")
        self.assertEqual(request("/mlb/props?player=Aaron%20Judge&tb_under_odds=-110")["status"], "400 Bad Request")
        self.assertEqual(request("/mlb/props?player=Aaron%20Judge&park=Nowhere")["status"], "404 Not Found")

    def test_reference_endpoint_and_dashboard(self):
        response = request("/mlb/reference")
        self.assertEqual(response["status"], "200 OK")
        self.assertTrue(response["body"]["batters"])
        self.assertIn("mlb-props-form", request("/")["raw_body"])
        self.assertEqual(request("/app.json")["body"]["endpoints"]["mlb_reference"], "/mlb/reference")


if __name__ == "__main__":
    unittest.main()
