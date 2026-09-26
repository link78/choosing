import os
import unittest
from urllib.error import URLError
from unittest.mock import patch

from choosing.api import app
from choosing.data_sources import (
    FantasySportsAPIClient,
    MediaBroadcastClient,
    OddsAPIClient,
    SportsDataIOClient,
)
from choosing.service import PredictionService


def fake_sports_fetcher(url: str, headers=None, timeout=5.0):
    if "/nfl/" in url and "scores/json/Players" in url:
        return [
            {"PlayerID": 101, "Name": "Patrick Mahomes", "Team": "Kansas City Chiefs"},
            {"PlayerID": 102, "Name": "Josh Allen", "Team": "Buffalo Bills"},
            {"PlayerID": 103, "Name": "Christian McCaffrey", "Team": "San Francisco 49ers"},
            {"PlayerID": 104, "Name": "Lamar Jackson", "Team": "Baltimore Ravens"},
            {"PlayerID": 105, "Name": "Tyreek Hill", "Team": "Miami Dolphins"},
            {"PlayerID": 106, "Name": "CeeDee Lamb", "Team": "Dallas Cowboys"},
            {"PlayerID": 107, "Name": "Jalen Hurts", "Team": "Philadelphia Eagles"},
            {"PlayerID": 108, "Name": "Joe Burrow", "Team": "Cincinnati Bengals"},
            {"PlayerID": 109, "Name": "Justin Jefferson", "Team": "Minnesota Vikings"},
            {"PlayerID": 110, "Name": "Saquon Barkley", "Team": "Philadelphia Eagles"},
        ]
    if "/nfl/" in url and "stats/json/PlayerSeasonStats/2024" in url:
        return [
            {"PlayerID": 101, "FantasyPoints": 410},
            {"PlayerID": 102, "FantasyPoints": 385},
            {"PlayerID": 103, "FantasyPoints": 360},
            {"PlayerID": 104, "FantasyPoints": 352},
            {"PlayerID": 105, "FantasyPoints": 348},
            {"PlayerID": 106, "FantasyPoints": 344},
            {"PlayerID": 107, "FantasyPoints": 340},
            {"PlayerID": 108, "FantasyPoints": 338},
            {"PlayerID": 109, "FantasyPoints": 332},
            {"PlayerID": 110, "FantasyPoints": 328},
        ]
    if "/nfl/" in url and "PlayerSeasonStatsByPlayer" in url:
        player_id = url.split("/")[-1].split("?")[0]
        return {"PlayerID": int(player_id), "FantasyPoints": 300, "Games": 17, "Points": 280, "Minutes": 60}
    if "/nfl/" in url and "PlayerGameStatsByPlayerID" in url:
        return [
            {"Points": 24, "Minutes": 60, "PersonalFouls": 0},
            {"Points": 22, "Minutes": 60, "PersonalFouls": 0},
            {"Points": 26, "Minutes": 60, "PersonalFouls": 0},
        ]
    if "/nfl/" in url and "scores/json/Injuries" in url:
        return []
    if "scores/json/Players" in url:
        return [
            {"PlayerID": 30, "Name": "Stephen Curry", "Team": "Golden State Warriors"},
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
                "Name": "Golden State Warriors",
                "Key": "GSW",
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
                "home_team": "Golden State Warriors",
                "away_team": "Los Angeles Lakers",
                "bookmakers": [
                    {
                        "markets": [
                            {
                                "key": "h2h",
                                "outcomes": [
                                    {"name": "Golden State Warriors", "price": -115},
                                    {"name": "Los Angeles Lakers", "price": 105},
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
            payload = client.fetch_player_context("Stephen Curry", {"team": "Golden State Warriors"})

        self.assertEqual(payload["player_id"], "30")
        self.assertEqual(payload["player_name"], "Stephen Curry")
        self.assertEqual(payload["source_mode"], "live")
        self.assertGreater(payload["recent_form"], 0)
        self.assertLess(payload["injury_risk"], 0.5)
        self.assertIn("recent_form_l3", payload)
        self.assertIn("source_confidence", payload)

    def test_odds_api_client_uses_live_market_when_configured(self):
        with patch.dict(os.environ, {"ODDS_API_KEY": "test-key"}, clear=False):
            client = OddsAPIClient(fetcher=fake_odds_fetcher)
            payload = client.fetch_game_market("Golden State Warriors")

        self.assertEqual(payload["team"], "Golden State Warriors")
        self.assertEqual(payload["opponent"], "Los Angeles Lakers")
        self.assertEqual(payload["source_mode"], "live")
        self.assertEqual(payload["current_odds"], -115)
        self.assertIn("implied_probability", payload)
        self.assertIn("book_disagreement", payload)
        self.assertIn("market_source_confidence", payload)

    def test_media_client_uses_live_context_when_configured(self):
        with patch.dict(os.environ, {"MEDIA_BROADCAST_API_KEY": "test-key"}, clear=False):
            client = MediaBroadcastClient(fetcher=fake_sports_fetcher)
            payload = client.fetch_player_context("Stephen Curry", {"team": "Golden State Warriors"})

        self.assertEqual(payload["player_id"], "30")
        self.assertEqual(payload["source_mode"], "live")
        self.assertGreater(payload["broadcast_exposure"], 0)

    def test_fantasy_client_uses_live_context_when_configured(self):
        with patch.dict(os.environ, {"FANTASY_SPORTS_API_KEY": "test-key"}, clear=False):
            client = FantasySportsAPIClient(fetcher=fake_sports_fetcher)
            payload = client.fetch_player_context("Stephen Curry", {"team": "Golden State Warriors"})

        self.assertEqual(payload["player_id"], "30")
        self.assertEqual(payload["source_mode"], "live")
        self.assertGreater(payload["fantasy_projection"], 0)

    def test_media_and_fantasy_clients_can_fall_back_to_sportsdata_config(self):
        with patch.dict(
            os.environ,
            {
                "SPORTSDATAIO_API_KEY": "shared-key",
                "SPORTSDATAIO_BASE_URL": "https://api.sportsdata.io/v3/nba",
            },
            clear=False,
        ):
            media_client = MediaBroadcastClient(fetcher=fake_sports_fetcher)
            fantasy_client = FantasySportsAPIClient(fetcher=fake_sports_fetcher)

            self.assertEqual(media_client.api_key, "shared-key")
            self.assertEqual(fantasy_client.api_key, "shared-key")
            self.assertEqual(media_client.base_url, "https://api.sportsdata.io/v3/nba")
            self.assertEqual(fantasy_client.base_url, "https://api.sportsdata.io/v3/nba")

    def test_service_source_status_reflects_configured_env_vars(self):
        with patch.dict(
            os.environ,
            {
                "SPORTSDATAIO_API_KEY": "sports-key",
                "MEDIA_BROADCAST_API_KEY": "media-key",
                "FANTASY_SPORTS_API_KEY": "fantasy-key",
                "ODDS_API_KEY": "odds-key",
            },
            clear=False,
        ):
            service = PredictionService(
                sports_client=SportsDataIOClient(fetcher=fake_sports_fetcher),
                media_client=MediaBroadcastClient(fetcher=fake_sports_fetcher),
                fantasy_client=FantasySportsAPIClient(fetcher=fake_sports_fetcher),
                odds_client=OddsAPIClient(fetcher=fake_odds_fetcher),
            )
            status = service.source_status()

        self.assertTrue(status["sports_data_io"]["configured"])
        self.assertTrue(status["media_broadcast"]["configured"])
        self.assertTrue(status["fantasy_sports_api"]["configured"])
        self.assertTrue(status["odds_api"]["configured"])
        self.assertEqual(status["sports_data_io"]["mode"], "live")
        self.assertEqual(status["media_broadcast"]["mode"], "live")
        self.assertEqual(status["fantasy_sports_api"]["mode"], "live")
        self.assertEqual(status["odds_api"]["mode"], "live")
        self.assertIsNone(status["sports_data_io"]["last_call_succeeded"])
        self.assertIsNone(status["media_broadcast"]["last_call_succeeded"])
        self.assertIsNone(status["fantasy_sports_api"]["last_call_succeeded"])
        self.assertIsNone(status["odds_api"]["last_call_succeeded"])
        self.assertIsNone(status["sports_data_io"]["last_error_message"])
        self.assertIsNone(status["media_broadcast"]["last_error_message"])
        self.assertIsNone(status["fantasy_sports_api"]["last_error_message"])
        self.assertIsNone(status["odds_api"]["last_error_message"])

    def test_service_uses_live_nfl_players_for_top_summary(self):
        with patch.dict(os.environ, {"SPORTSDATAIO_API_KEY": "sports-key"}, clear=False):
            service = PredictionService(
                sports_client=SportsDataIOClient(fetcher=fake_sports_fetcher),
                media_client=MediaBroadcastClient(fetcher=fake_sports_fetcher),
                fantasy_client=FantasySportsAPIClient(fetcher=fake_sports_fetcher),
            )
            summary = service.get_top_players_summary("americanfootball_nfl", limit=10)

        self.assertEqual(summary["sport"]["league"], "NFL")
        self.assertEqual(len(summary["top_players"]), 10)
        player_names = [entry["player_name"] for entry in summary["top_players"]]
        self.assertIn("Patrick Mahomes", player_names)
        self.assertIn("Saquon Barkley", player_names)
        self.assertTrue(all("Featured Player" not in name for name in player_names))

    def test_source_status_tracks_last_upstream_success_and_error(self):
        def failing_fetcher(url: str, headers=None, timeout=5.0):
            raise URLError("provider unavailable")

        with patch.dict(
            os.environ,
            {
                "SPORTSDATAIO_API_KEY": "sports-key",
                "MEDIA_BROADCAST_API_KEY": "media-key",
                "FANTASY_SPORTS_API_KEY": "fantasy-key",
                "ODDS_API_KEY": "odds-key",
            },
            clear=False,
        ):
            sports_client = SportsDataIOClient(fetcher=fake_sports_fetcher)
            media_client = MediaBroadcastClient(fetcher=fake_sports_fetcher)
            fantasy_client = FantasySportsAPIClient(fetcher=failing_fetcher)
            odds_client = OddsAPIClient(fetcher=failing_fetcher)
            sports_client.fetch_player_context("Stephen Curry", {"team": "Golden State Warriors"})
            media_client.fetch_player_context("Stephen Curry", {"team": "Golden State Warriors"})
            fantasy_client.fetch_player_context("Stephen Curry", {"team": "Golden State Warriors"})
            odds_client.fetch_game_market("Golden State Warriors")
            sports_status = sports_client.source_status()
            media_status = media_client.source_status()
            fantasy_status = fantasy_client.source_status()
            odds_status = odds_client.source_status()

            self.assertTrue(sports_status["last_call_succeeded"])
            self.assertTrue(media_status["last_call_succeeded"])
            self.assertIsNone(media_status["last_error_message"])
            self.assertFalse(fantasy_status["last_call_succeeded"])
            self.assertIn("provider unavailable", fantasy_status["last_error_message"])
            self.assertIsNone(sports_status["last_error_message"])
            self.assertFalse(odds_status["last_call_succeeded"])
            self.assertIn("provider unavailable", odds_status["last_error_message"])


if __name__ == "__main__":
    unittest.main()
