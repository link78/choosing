import os
import unittest
from unittest.mock import patch

from choosing.api import app
from choosing.data_sources import OddsAPIClient, SportsDataIOClient
from choosing.service import PredictionService


def fake_sports_fetcher(url: str, headers=None, timeout=5.0):
    if "scores/json/Players" in url:
        return [
            {"PlayerID": 42, "Name": "Jayson Tatum", "Team": "Boston Celtics"},
            {"PlayerID": 15, "Name": "Nikola Jokic", "Team": "Denver Nuggets"},
        ]
    if "PlayerSeasonStatsByPlayer" in url:
        return {"Points": 2100, "Games": 82, "Minutes": 36}
    if "PlayerGameStatsByPlayerID" in url:
        return [
            {"Points": 32, "Minutes": 37, "PersonalFouls": 2},
            {"Points": 30, "Minutes": 36, "PersonalFouls": 1},
            {"Points": 28, "Minutes": 35, "PersonalFouls": 3},
        ]
    if "scores/json/Injuries" in url:
        return [{"PlayerID": 42, "Status": "Probable"}]
    if "TeamSeasonStats" in url:
        return [
            {
                "Name": "Boston Celtics",
                "Key": "BOS",
                "Possessions": 101,
                "PointsPerGame": 118,
                "OffensiveRating": 119,
                "DefensiveRating": 109,
                "Percentage": 0.72,
            }
        ]
    raise AssertionError(f"Unexpected SportsDataIO URL: {url}")


def fake_odds_fetcher(url: str, headers=None, timeout=5.0):
    if "sports/basketball_nba/odds" in url:
        return [
            {
                "home_team": "Boston Celtics",
                "away_team": "Dallas Mavericks",
                "bookmakers": [
                    {
                        "markets": [
                            {
                                "key": "h2h",
                                "outcomes": [
                                    {"name": "Boston Celtics", "price": -115},
                                    {"name": "Dallas Mavericks", "price": 105},
                                ],
                            }
                        ]
                    }
                ],
            }
        ]
    raise AssertionError(f"Unexpected Odds API URL: {url}")


class LiveDataSourceTests(unittest.TestCase):
    def test_sportsdataio_client_uses_live_data_when_configured(self):
        with patch.dict(os.environ, {"SPORTSDATAIO_API_KEY": "test-key"}, clear=False):
            client = SportsDataIOClient(fetcher=fake_sports_fetcher)
            payload = client.fetch_player_context("Jayson Tatum", {"team": "Boston Celtics"})

        self.assertEqual(payload["player_id"], "42")
        self.assertEqual(payload["player_name"], "Jayson Tatum")
        self.assertEqual(payload["source_mode"], "live")
        self.assertGreater(payload["recent_form"], 0)
        self.assertLess(payload["injury_risk"], 0.5)

    def test_odds_api_client_uses_live_market_when_configured(self):
        with patch.dict(os.environ, {"ODDS_API_KEY": "test-key"}, clear=False):
            client = OddsAPIClient(fetcher=fake_odds_fetcher)
            payload = client.fetch_game_market("Boston Celtics")

        self.assertEqual(payload["team"], "Boston Celtics")
        self.assertEqual(payload["opponent"], "Dallas Mavericks")
        self.assertEqual(payload["source_mode"], "live")
        self.assertEqual(payload["current_odds"], -115)
        self.assertIn("implied_probability", payload)

    def test_service_source_status_reflects_configured_env_vars(self):
        with patch.dict(
            os.environ,
            {"SPORTSDATAIO_API_KEY": "sports-key", "ODDS_API_KEY": "odds-key"},
            clear=False,
        ):
            service = PredictionService(
                sports_client=SportsDataIOClient(fetcher=fake_sports_fetcher),
                odds_client=OddsAPIClient(fetcher=fake_odds_fetcher),
            )
            status = service.source_status()

        self.assertTrue(status["sports_data_io"]["configured"])
        self.assertTrue(status["odds_api"]["configured"])
        self.assertEqual(status["sports_data_io"]["mode"], "live")
        self.assertEqual(status["odds_api"]["mode"], "live")


if __name__ == "__main__":
    unittest.main()
