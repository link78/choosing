import json
import unittest
from contextlib import redirect_stdout
from io import StringIO

from choosing.__main__ import main
from choosing.application import BettingApplication, render_text_report


class BettingApplicationTests(unittest.TestCase):
    def test_build_report_creates_betting_summary(self):
        application = BettingApplication()

        report = application.build_report(
            player_ids=["7"],
            game_ids=["finals"],
            bankroll=500,
            player_overrides={"7": {"availability": 0.6, "injury_risk": 0.45}},
            game_overrides={
                "finals": {
                    "sports": {"model_probability": 0.61},
                    "odds": {"current_odds": -110, "steam_move": True},
                }
            },
        )

        self.assertEqual(report["meta"]["bankroll"], 500)
        self.assertEqual(report["portfolio_summary"]["recommended_bets"], 1)
        self.assertEqual(report["portfolio_summary"]["total_recommended_stake"], 10.0)
        self.assertEqual(report["game_cards"][0]["recommendation"]["stake_label"], "medium")
        self.assertGreater(report["player_cards"][0]["expected_points"], 0)
        self.assertIn("availability_risk", report["player_cards"][0]["flags"])

    def test_build_report_supports_player_names_and_team_names(self):
        application = BettingApplication()

        report = application.build_report(
            player_ids=["Stephen Curry"],
            game_ids=["Golden State Warriors"],
        )

        self.assertEqual(report["player_cards"][0]["player_id"], "30")
        self.assertEqual(report["player_cards"][0]["player_name"], "Stephen Curry")
        self.assertIn(report["player_cards"][0]["scoring_outlook"], {"Likely to score", "Not likely to score"})
        self.assertEqual(report["game_cards"][0]["game_id"], "warriors-lakers")
        self.assertEqual(report["portfolio_summary"]["highest_edge_game"], "warriors-lakers")

    def test_render_text_report_contains_sections(self):
        application = BettingApplication()
        report = application.build_report(player_ids=["7"], game_ids=["finals"])

        rendered = render_text_report(report)

        self.assertIn("CHOOSING SPORTS BETTING REPORT", rendered)
        self.assertIn("PLAYER WATCHLIST", rendered)
        self.assertIn("points", rendered)
        self.assertRegex(rendered, r"likely to score|not likely to score")
        self.assertIn("BETTING OPPORTUNITIES", rendered)
        self.assertIn("PORTFOLIO SUMMARY", rendered)

    def test_main_can_emit_json(self):
        output = StringIO()

        with redirect_stdout(output):
            exit_code = main(["--players", "7", "--games", "finals", "--bankroll", "250", "--json"])

        self.assertEqual(exit_code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["meta"]["bankroll"], 250)
        self.assertEqual(payload["player_cards"][0]["player_id"], "7")


if __name__ == "__main__":
    unittest.main()
