"""MLB home run and total bases prop model.

Combines SportsDataIO player performance, Statcast-style batted-ball metrics, pitcher matchup,
park, weather and pitch-type fit into a per-plate-appearance outcome distribution, converts it to
per-game probabilities, and compares them with The Odds API implied probabilities.
Informational only, not betting advice.
"""

from __future__ import annotations

import math

from .data_sources import OddsAPIClient, SportsDataIOClient, _normalize
from .prediction import american_to_implied_probability, clamp, stable_float

SPORT_KEY = "baseball_mlb"
HR_MARKET = "batter_home_runs"
TB_MARKET = "batter_total_bases"
DISCLAIMER = "Informational only, not betting advice."

LEAGUE = {
    "hr_per_pa": 0.029,
    "hr_per_9": 1.20,
    "batting_average_against": 0.243,
    "single_per_pa": 0.140,
    "double_per_pa": 0.043,
    "triple_per_pa": 0.0035,
    "pitch_slg": {"FF": 0.420, "SI": 0.445, "FC": 0.425, "SL": 0.375, "CU": 0.370, "CH": 0.395},
}

LEAGUE_PITCH_MIX = {"FF": 0.33, "SI": 0.15, "SL": 0.19, "CH": 0.11, "CU": 0.10, "FC": 0.12}

PITCH_NAMES = {"FF": "4-seam fastball", "SI": "sinker", "FC": "cutter", "SL": "slider", "CU": "curveball", "CH": "changeup"}

BASELINE_WEIGHT = 0.7
RECENT_WEIGHT = 0.3
DEFAULT_EXPECTED_PA = 4.2
LINEUP_SLOT_PA = [4.65, 4.55, 4.45, 4.35, 4.25, 4.15, 4.05, 3.95, 3.85]
DEFAULT_WEATHER = {"wind_out_mph": 0.0, "temperature_f": 70.0, "humidity": 50.0}
WEATHER_BASE_TEMPERATURE_F = 70.0

MLB_TEAMS = {
    "ARI": "Arizona Diamondbacks", "ATL": "Atlanta Braves", "BAL": "Baltimore Orioles", "BOS": "Boston Red Sox",
    "CHC": "Chicago Cubs", "CHW": "Chicago White Sox", "CIN": "Cincinnati Reds", "CLE": "Cleveland Guardians",
    "COL": "Colorado Rockies", "DET": "Detroit Tigers", "HOU": "Houston Astros", "KC": "Kansas City Royals",
    "LAA": "Los Angeles Angels", "LAD": "Los Angeles Dodgers", "MIA": "Miami Marlins", "MIL": "Milwaukee Brewers",
    "MIN": "Minnesota Twins", "NYM": "New York Mets", "NYY": "New York Yankees", "OAK": "Oakland Athletics",
    "PHI": "Philadelphia Phillies", "PIT": "Pittsburgh Pirates", "SD": "San Diego Padres", "SEA": "Seattle Mariners",
    "SF": "San Francisco Giants", "STL": "St. Louis Cardinals", "TB": "Tampa Bay Rays", "TEX": "Texas Rangers",
    "TOR": "Toronto Blue Jays", "WSH": "Washington Nationals",
}
TEAM_ALIASES = {"CWS": "CHW", "KCR": "KC", "SDP": "SD", "SFG": "SF", "TBR": "TB", "WSN": "WSH", "WAS": "WSH", "ATH": "OAK"}

# Illustrative reference sample used when SportsDataIO/Statcast data is unavailable.
BATTERS = [
    {
        "name": "Aaron Judge", "team": "New York Yankees", "bats": "R",
        "season": {"games": 158, "pa": 704, "ab": 559, "hits": 180, "doubles": 36, "triples": 1, "hr": 58},
        "statcast": {"hard_hit_pct": 60.1, "barrel_pct": 26.9, "avg_exit_velocity": 96.2, "xba": 0.302, "xslg": 0.698,
                     "batting_average": 0.322, "launch_angle": {"ground_ball": 31.0, "line_drive": 22.0, "fly_ball": 41.0, "popup": 6.0}},
        "recent": {"games": 10, "pa": 44, "hr": 4, "tb": 24},
        "slg_vs_pitch": {"FF": 0.720, "SI": 0.640, "FC": 0.600, "SL": 0.560, "CU": 0.520, "CH": 0.610},
    },
    {
        "name": "Shohei Ohtani", "team": "Los Angeles Dodgers", "bats": "L",
        "season": {"games": 159, "pa": 731, "ab": 636, "hits": 197, "doubles": 38, "triples": 7, "hr": 54},
        "statcast": {"hard_hit_pct": 60.2, "barrel_pct": 21.5, "avg_exit_velocity": 95.8, "xba": 0.306, "xslg": 0.630,
                     "batting_average": 0.310, "launch_angle": {"ground_ball": 38.0, "line_drive": 21.0, "fly_ball": 36.0, "popup": 5.0}},
        "recent": {"games": 10, "pa": 46, "hr": 3, "tb": 22},
        "slg_vs_pitch": {"FF": 0.680, "SI": 0.610, "FC": 0.570, "SL": 0.540, "CU": 0.500, "CH": 0.590},
    },
    {
        "name": "Juan Soto", "team": "New York Yankees", "bats": "L",
        "season": {"games": 157, "pa": 713, "ab": 576, "hits": 166, "doubles": 31, "triples": 4, "hr": 41},
        "statcast": {"hard_hit_pct": 57.2, "barrel_pct": 19.1, "avg_exit_velocity": 95.0, "xba": 0.296, "xslg": 0.577,
                     "batting_average": 0.288, "launch_angle": {"ground_ball": 40.0, "line_drive": 23.0, "fly_ball": 32.0, "popup": 5.0}},
        "recent": {"games": 10, "pa": 45, "hr": 2, "tb": 17},
        "slg_vs_pitch": {"FF": 0.600, "SI": 0.580, "FC": 0.520, "SL": 0.500, "CU": 0.470, "CH": 0.540},
    },
    {
        "name": "Mookie Betts", "team": "Los Angeles Dodgers", "bats": "R",
        "season": {"games": 116, "pa": 516, "ab": 450, "hits": 130, "doubles": 24, "triples": 2, "hr": 19},
        "statcast": {"hard_hit_pct": 39.5, "barrel_pct": 8.2, "avg_exit_velocity": 90.0, "xba": 0.277, "xslg": 0.456,
                     "batting_average": 0.289, "launch_angle": {"ground_ball": 36.0, "line_drive": 22.0, "fly_ball": 33.0, "popup": 9.0}},
        "recent": {"games": 10, "pa": 43, "hr": 1, "tb": 14},
        "slg_vs_pitch": {"FF": 0.500, "SI": 0.470, "FC": 0.430, "SL": 0.400, "CU": 0.380, "CH": 0.420},
    },
    {
        "name": "Ronald Acuna Jr.", "team": "Atlanta Braves", "bats": "R",
        "season": {"games": 159, "pa": 735, "ab": 643, "hits": 217, "doubles": 35, "triples": 4, "hr": 41},
        "statcast": {"hard_hit_pct": 54.1, "barrel_pct": 15.5, "avg_exit_velocity": 94.7, "xba": 0.320, "xslg": 0.598,
                     "batting_average": 0.337, "launch_angle": {"ground_ball": 42.0, "line_drive": 22.0, "fly_ball": 31.0, "popup": 5.0}},
        "recent": {"games": 10, "pa": 45, "hr": 2, "tb": 19},
        "slg_vs_pitch": {"FF": 0.640, "SI": 0.590, "FC": 0.540, "SL": 0.500, "CU": 0.480, "CH": 0.550},
    },
    {
        "name": "Freddie Freeman", "team": "Los Angeles Dodgers", "bats": "L",
        "season": {"games": 147, "pa": 638, "ab": 542, "hits": 153, "doubles": 35, "triples": 2, "hr": 22},
        "statcast": {"hard_hit_pct": 45.0, "barrel_pct": 10.4, "avg_exit_velocity": 91.2, "xba": 0.286, "xslg": 0.479,
                     "batting_average": 0.282, "launch_angle": {"ground_ball": 37.0, "line_drive": 26.0, "fly_ball": 31.0, "popup": 6.0}},
        "recent": {"games": 10, "pa": 42, "hr": 1, "tb": 15},
        "slg_vs_pitch": {"FF": 0.520, "SI": 0.500, "FC": 0.450, "SL": 0.420, "CU": 0.400, "CH": 0.460},
    },
    {
        "name": "Bobby Witt Jr.", "team": "Kansas City Royals", "bats": "R",
        "season": {"games": 161, "pa": 709, "ab": 636, "hits": 211, "doubles": 45, "triples": 11, "hr": 32},
        "statcast": {"hard_hit_pct": 49.4, "barrel_pct": 12.1, "avg_exit_velocity": 92.4, "xba": 0.313, "xslg": 0.554,
                     "batting_average": 0.332, "launch_angle": {"ground_ball": 38.0, "line_drive": 23.0, "fly_ball": 32.0, "popup": 7.0}},
        "recent": {"games": 10, "pa": 44, "hr": 2, "tb": 20},
        "slg_vs_pitch": {"FF": 0.600, "SI": 0.570, "FC": 0.520, "SL": 0.480, "CU": 0.450, "CH": 0.500},
    },
]

# Season-only reference lines (no Statcast splits): pitch-type fit is neutral and recent form defaults to baseline.
BATTERS += [
    {"name": "Giancarlo Stanton", "team": "New York Yankees", "bats": "R",
     "season": {"games": 114, "pa": 459, "ab": 417, "hits": 97, "doubles": 15, "triples": 0, "hr": 27}},
    {"name": "Kyle Schwarber", "team": "Philadelphia Phillies", "bats": "L",
     "season": {"games": 162, "pa": 700, "ab": 573, "hits": 142, "doubles": 22, "triples": 0, "hr": 38}},
    {"name": "Bryce Harper", "team": "Philadelphia Phillies", "bats": "L",
     "season": {"games": 145, "pa": 631, "ab": 550, "hits": 157, "doubles": 42, "triples": 0, "hr": 30}},
    {"name": "Yordan Alvarez", "team": "Houston Astros", "bats": "L",
     "season": {"games": 147, "pa": 635, "ab": 552, "hits": 170, "doubles": 34, "triples": 2, "hr": 35}},
    {"name": "Jose Altuve", "team": "Houston Astros", "bats": "R",
     "season": {"games": 153, "pa": 682, "ab": 628, "hits": 185, "doubles": 31, "triples": 0, "hr": 20}},
    {"name": "Gunnar Henderson", "team": "Baltimore Orioles", "bats": "L",
     "season": {"games": 159, "pa": 719, "ab": 630, "hits": 177, "doubles": 31, "triples": 7, "hr": 37}},
    {"name": "Anthony Santander", "team": "Baltimore Orioles", "bats": "S",
     "season": {"games": 155, "pa": 665, "ab": 595, "hits": 140, "doubles": 25, "triples": 2, "hr": 44}},
    {"name": "Marcell Ozuna", "team": "Atlanta Braves", "bats": "R",
     "season": {"games": 162, "pa": 688, "ab": 606, "hits": 184, "doubles": 31, "triples": 0, "hr": 39}},
    {"name": "Matt Olson", "team": "Atlanta Braves", "bats": "L",
     "season": {"games": 162, "pa": 685, "ab": 600, "hits": 148, "doubles": 37, "triples": 0, "hr": 29}},
    {"name": "Pete Alonso", "team": "New York Mets", "bats": "R",
     "season": {"games": 162, "pa": 695, "ab": 608, "hits": 146, "doubles": 31, "triples": 0, "hr": 34}},
    {"name": "Francisco Lindor", "team": "New York Mets", "bats": "S",
     "season": {"games": 152, "pa": 689, "ab": 626, "hits": 171, "doubles": 39, "triples": 1, "hr": 33}},
    {"name": "Jose Ramirez", "team": "Cleveland Guardians", "bats": "S",
     "season": {"games": 158, "pa": 682, "ab": 620, "hits": 173, "doubles": 39, "triples": 2, "hr": 39}},
    {"name": "Cal Raleigh", "team": "Seattle Mariners", "bats": "S",
     "season": {"games": 153, "pa": 628, "ab": 546, "hits": 120, "doubles": 21, "triples": 0, "hr": 34}},
    {"name": "Brent Rooker", "team": "Oakland Athletics", "bats": "R",
     "season": {"games": 150, "pa": 614, "ab": 532, "hits": 156, "doubles": 30, "triples": 1, "hr": 39}},
    {"name": "Rafael Devers", "team": "Boston Red Sox", "bats": "L",
     "season": {"games": 138, "pa": 601, "ab": 525, "hits": 142, "doubles": 34, "triples": 1, "hr": 28}},
    {"name": "Salvador Perez", "team": "Kansas City Royals", "bats": "R",
     "season": {"games": 158, "pa": 652, "ab": 594, "hits": 161, "doubles": 28, "triples": 0, "hr": 27}},
    {"name": "Riley Greene", "team": "Detroit Tigers", "bats": "L",
     "season": {"games": 137, "pa": 584, "ab": 507, "hits": 133, "doubles": 29, "triples": 3, "hr": 24}},
    {"name": "Elly De La Cruz", "team": "Cincinnati Reds", "bats": "S",
     "season": {"games": 160, "pa": 696, "ab": 618, "hits": 150, "doubles": 36, "triples": 10, "hr": 25}},
]

PITCHERS = [
    {
        "name": "League Average Pitcher", "team": "", "throws": "R",
        "hr_per_9": 1.20, "hr_per_9_vs_lhb": 1.20, "hr_per_9_vs_rhb": 1.20,
        "barrel_pct_allowed": 7.8, "hard_hit_pct_allowed": 39.0, "fastball_ev_allowed": 89.8, "batting_average_against": 0.243,
        "pitch_mix": LEAGUE_PITCH_MIX,
    },
    {
        "name": "Gerrit Cole", "team": "New York Yankees", "throws": "R",
        "hr_per_9": 1.13, "hr_per_9_vs_lhb": 1.30, "hr_per_9_vs_rhb": 0.95,
        "barrel_pct_allowed": 8.2, "hard_hit_pct_allowed": 38.5, "fastball_ev_allowed": 89.8, "batting_average_against": 0.220,
        "pitch_mix": {"FF": 0.52, "SL": 0.18, "FC": 0.12, "CU": 0.12, "CH": 0.06},
    },
    {
        "name": "Paul Skenes", "team": "Pittsburgh Pirates", "throws": "R",
        "hr_per_9": 0.51, "hr_per_9_vs_lhb": 0.55, "hr_per_9_vs_rhb": 0.47,
        "barrel_pct_allowed": 5.1, "hard_hit_pct_allowed": 33.0, "fastball_ev_allowed": 88.9, "batting_average_against": 0.198,
        "pitch_mix": {"FF": 0.40, "SI": 0.20, "SL": 0.18, "CH": 0.12, "CU": 0.10},
    },
    {
        "name": "Zack Wheeler", "team": "Philadelphia Phillies", "throws": "R",
        "hr_per_9": 0.80, "hr_per_9_vs_lhb": 0.95, "hr_per_9_vs_rhb": 0.66,
        "barrel_pct_allowed": 6.1, "hard_hit_pct_allowed": 34.8, "fastball_ev_allowed": 88.5, "batting_average_against": 0.190,
        "pitch_mix": {"FF": 0.38, "SI": 0.18, "FC": 0.15, "SL": 0.12, "CU": 0.10, "CH": 0.07},
    },
    {
        "name": "Logan Webb", "team": "San Francisco Giants", "throws": "R",
        "hr_per_9": 0.73, "hr_per_9_vs_lhb": 0.80, "hr_per_9_vs_rhb": 0.66,
        "barrel_pct_allowed": 5.8, "hard_hit_pct_allowed": 38.0, "fastball_ev_allowed": 89.9, "batting_average_against": 0.245,
        "pitch_mix": {"SI": 0.36, "CH": 0.30, "SL": 0.26, "FF": 0.05, "FC": 0.03},
    },
    {
        "name": "Framber Valdez", "team": "Houston Astros", "throws": "L",
        "hr_per_9": 0.74, "hr_per_9_vs_lhb": 0.60, "hr_per_9_vs_rhb": 0.80,
        "barrel_pct_allowed": 6.4, "hard_hit_pct_allowed": 36.1, "fastball_ev_allowed": 89.4, "batting_average_against": 0.222,
        "pitch_mix": {"SI": 0.45, "CU": 0.30, "CH": 0.15, "FC": 0.10},
    },
    {
        "name": "Tarik Skubal", "team": "Detroit Tigers", "throws": "L",
        "hr_per_9": 0.79, "hr_per_9_vs_lhb": 0.70, "hr_per_9_vs_rhb": 0.82,
        "barrel_pct_allowed": 6.0, "hard_hit_pct_allowed": 33.9, "fastball_ev_allowed": 89.0, "batting_average_against": 0.199,
        "pitch_mix": {"FF": 0.32, "CH": 0.28, "SI": 0.22, "SL": 0.12, "CU": 0.06},
    },
]

PARKS = [
    {"name": "Neutral Park", "team": "", "hr_factor": 1.00, "tb_factor": 1.00, "roof": "open"},
    {"name": "Coors Field", "team": "Colorado Rockies", "hr_factor": 1.25, "tb_factor": 1.15, "roof": "open"},
    {"name": "Great American Ball Park", "team": "Cincinnati Reds", "hr_factor": 1.20, "tb_factor": 1.05, "roof": "open"},
    {"name": "Yankee Stadium", "team": "New York Yankees", "hr_factor": 1.15, "tb_factor": 1.02, "roof": "open"},
    {"name": "Citizens Bank Park", "team": "Philadelphia Phillies", "hr_factor": 1.10, "tb_factor": 1.03, "roof": "open"},
    {"name": "Dodger Stadium", "team": "Los Angeles Dodgers", "hr_factor": 1.08, "tb_factor": 1.00, "roof": "open"},
    {"name": "Minute Maid Park", "team": "Houston Astros", "hr_factor": 1.05, "tb_factor": 1.00, "roof": "retractable"},
    {"name": "Truist Park", "team": "Atlanta Braves", "hr_factor": 1.02, "tb_factor": 1.01, "roof": "open"},
    {"name": "Oriole Park at Camden Yards", "team": "Baltimore Orioles", "hr_factor": 1.00, "tb_factor": 1.00, "roof": "open"},
    {"name": "Wrigley Field", "team": "Chicago Cubs", "hr_factor": 1.00, "tb_factor": 1.00, "roof": "open"},
    {"name": "Progressive Field", "team": "Cleveland Guardians", "hr_factor": 0.97, "tb_factor": 0.98, "roof": "open"},
    {"name": "Citi Field", "team": "New York Mets", "hr_factor": 0.95, "tb_factor": 0.96, "roof": "open"},
    {"name": "Fenway Park", "team": "Boston Red Sox", "hr_factor": 0.98, "tb_factor": 1.08, "roof": "open"},
    {"name": "Tropicana Field", "team": "Tampa Bay Rays", "hr_factor": 0.92, "tb_factor": 0.95, "roof": "dome"},
    {"name": "Comerica Park", "team": "Detroit Tigers", "hr_factor": 0.90, "tb_factor": 0.98, "roof": "open"},
    {"name": "PNC Park", "team": "Pittsburgh Pirates", "hr_factor": 0.90, "tb_factor": 0.97, "roof": "open"},
    {"name": "Kauffman Stadium", "team": "Kansas City Royals", "hr_factor": 0.88, "tb_factor": 1.02, "roof": "open"},
    {"name": "Oakland Coliseum", "team": "Oakland Athletics", "hr_factor": 0.88, "tb_factor": 0.93, "roof": "open"},
    {"name": "T-Mobile Park", "team": "Seattle Mariners", "hr_factor": 0.85, "tb_factor": 0.92, "roof": "retractable"},
    {"name": "Oracle Park", "team": "San Francisco Giants", "hr_factor": 0.82, "tb_factor": 0.94, "roof": "open"},
]


class MLBLookupError(LookupError):
    """Raised when a batter, pitcher, or park cannot be resolved."""


def _find(entries: list[dict], reference: str | None, allow_team: bool = True) -> dict | None:
    target = _normalize(reference or "")
    if not target:
        return None
    for entry in entries:
        if _normalize(entry["name"]) == target:
            return entry
    for entry in entries:
        if allow_team and entry["team"] and _normalize(entry["team"]) == target:
            return entry
    for entry in entries:
        if target in _normalize(entry["name"]):
            return entry
    return None


def team_full_name(reference: str | None) -> str:
    """Map an MLB abbreviation (e.g. `NYY`) or full/partial team name to the full team name; '' when unknown."""
    raw = (reference or "").strip()
    if not raw:
        return ""
    code = TEAM_ALIASES.get(raw.upper(), raw.upper())
    if code in MLB_TEAMS:
        return MLB_TEAMS[code]
    target = _normalize(raw)
    for full in MLB_TEAMS.values():
        if _normalize(full) == target:
            return full
    partial = [full for full in MLB_TEAMS.values() if target and target in _normalize(full)]
    return partial[0] if len(partial) == 1 else ""


def reference_data() -> dict:
    return {
        "sport": SPORT_KEY,
        "batters": [{"name": b["name"], "team": b["team"], "bats": b["bats"]} for b in BATTERS],
        "pitchers": [{"name": p["name"], "team": p["team"], "throws": p["throws"]} for p in PITCHERS],
        "parks": [{"name": p["name"], "team": p["team"], "hr_factor": p["hr_factor"], "tb_factor": p["tb_factor"], "roof": p["roof"]} for p in PARKS],
        "teams": sorted({b["team"] for b in BATTERS}),
        "league": LEAGUE,
        "markets": {"home_run": HR_MARKET, "total_bases": TB_MARKET},
        "disclaimer": DISCLAIMER,
    }


def american_to_decimal(american_odds: int) -> float:
    if american_odds == 0:
        raise ValueError("American odds cannot be zero.")
    if american_odds > 0:
        return 1 + american_odds / 100
    return 1 + 100 / abs(american_odds)


def probability_to_american(probability: float) -> int:
    probability = clamp(probability, 0.01, 0.99)
    if probability >= 0.5:
        return -int(round(probability / (1 - probability) * 100))
    return int(round((1 - probability) / probability * 100))


def expected_plate_appearances(lineup_slot: int | None = None) -> float:
    if lineup_slot is None:
        return DEFAULT_EXPECTED_PA
    return LINEUP_SLOT_PA[int(lineup_slot) - 1]


def at_least_one_probability(per_pa: float, expected_pa: float) -> float:
    return 1 - (1 - per_pa) ** expected_pa


def total_bases_distribution(outcomes: dict[int, float], expected_pa: float) -> dict[int, float]:
    """Exact per-game total-bases distribution from a per-PA outcome distribution.

    Fractional plate appearances are handled as a mixture of floor/ceil PA counts.
    """

    def convolve(count: int) -> dict[int, float]:
        distribution = {0: 1.0}
        for _ in range(count):
            nxt: dict[int, float] = {}
            for total, prob in distribution.items():
                for bases, outcome_prob in outcomes.items():
                    nxt[total + bases] = nxt.get(total + bases, 0.0) + prob * outcome_prob
            distribution = nxt
        return distribution

    low = math.floor(expected_pa)
    weight_high = expected_pa - low
    mixed: dict[int, float] = {}
    for count, weight in ((low, 1 - weight_high), (low + 1, weight_high)):
        if weight <= 0:
            continue
        for total, prob in convolve(count).items():
            mixed[total] = mixed.get(total, 0.0) + weight * prob
    return dict(sorted(mixed.items()))


def probability_over(distribution: dict[int, float], line: float) -> float:
    return sum(prob for total, prob in distribution.items() if total > line)


def market_comparison(model_probability: float, over_odds: int | None, under_odds: int | None, source_mode: str, line=None, market: str = "") -> dict:
    """Step 8: P_implied = 1 / decimal odds; Edge = P_model - P_implied (plus a no-vig view when both sides exist)."""
    result = {
        "market": market,
        "line": line,
        "over_odds": over_odds,
        "under_odds": under_odds,
        "source_mode": source_mode,
        "model_probability": round(model_probability, 4),
        "decimal_odds": None,
        "implied_probability": None,
        "no_vig_probability": None,
        "edge": None,
        "no_vig_edge": None,
    }
    if over_odds is None:
        return result
    decimal = american_to_decimal(over_odds)
    implied = 1 / decimal
    result["decimal_odds"] = round(decimal, 3)
    result["implied_probability"] = round(implied, 4)
    result["edge"] = round(model_probability - implied, 4)
    if under_odds is not None:
        implied_under = american_to_implied_probability(under_odds)
        fair = implied / (implied + implied_under)
        result["no_vig_probability"] = round(fair, 4)
        result["no_vig_edge"] = round(model_probability - fair, 4)
    return result


class MLBPropModel:
    def __init__(self, sports_client: SportsDataIOClient | None = None, odds_client: OddsAPIClient | None = None) -> None:
        self.sports_client = sports_client or SportsDataIOClient()
        self.odds_client = odds_client or OddsAPIClient()

    # ----- data resolution -------------------------------------------------
    @staticmethod
    def _batter_from_local(local: dict | None, name: str = "") -> dict:
        return {
            "name": local["name"] if local else name.strip(),
            "team": local["team"] if local else "",
            "bats": local["bats"] if local else "R",
            "season": dict(local["season"]) if local else None,
            "statcast": dict(local["statcast"]) if local and local.get("statcast") else None,
            "recent": dict(local["recent"]) if local and local.get("recent") else None,
            "slg_vs_pitch": dict(local.get("slg_vs_pitch") or {}) if local else {},
        }

    @staticmethod
    def _finalize_batter(batter: dict) -> dict:
        if batter["season"] is None:
            raise MLBLookupError("batter not found")
        if batter["statcast"] is None:
            season = batter["season"]
            average = season["hits"] / season["ab"] if season["ab"] else LEAGUE["batting_average_against"]
            batter["statcast"] = {
                "hard_hit_pct": None, "barrel_pct": None, "avg_exit_velocity": None, "launch_angle": None,
                "xba": average, "xslg": None, "batting_average": average,
            }
        if batter["recent"] is None:
            batter["recent"] = {"games": 0, "pa": 0, "hr": 0, "tb": 0}
        return batter

    def _resolve_batter(self, reference: str) -> tuple[dict, str]:
        local = _find(BATTERS, reference, allow_team=False)
        batter = self._batter_from_local(local, reference)
        mode = "fallback"
        live = self.sports_client.fetch_mlb_player_stats(batter["name"]) if self.sports_client.api_key else None
        if live and live["season"]["pa"] > 0:
            mode = "live"
            batter["name"] = live["name"]
            batter["team"] = batter["team"] or team_full_name(live["team"])
            batter["season"] = live["season"]
            if live.get("recent") and live["recent"]["pa"] > 0:
                batter["recent"] = live["recent"]
        return self._finalize_batter(batter), mode

    def _resolve_pitcher(self, reference: str | None) -> tuple[dict, str]:
        local = _find(PITCHERS, reference) if reference else PITCHERS[0]
        if local is None:
            pitcher = dict(PITCHERS[0], name=reference.strip(), team="")
        else:
            pitcher = dict(local)
        pitcher["pitch_mix"] = dict(pitcher["pitch_mix"])
        mode = "fallback"
        if reference and self.sports_client.api_key:
            live = self.sports_client.fetch_mlb_player_stats(pitcher["name"])
            pitching = (live or {}).get("pitching")
            if pitching and pitching["innings"] > 0:
                mode = "live"
                pitcher["hr_per_9"] = round(pitching["hr_allowed"] * 9 / pitching["innings"], 3)
                if local is None:
                    pitcher["hr_per_9_vs_lhb"] = pitcher["hr_per_9_vs_rhb"] = pitcher["hr_per_9"]
        if local is None and mode == "fallback":
            raise MLBLookupError("pitcher not found")
        return pitcher, mode

    def _resolve_park(self, reference: str | None, batter_team: str) -> dict:
        park = _find(PARKS, reference) if reference else (_find(PARKS, batter_team) or PARKS[0])
        if park is None:
            raise MLBLookupError("park not found")
        return dict(park)

    def _live_market(self, batter: dict, market: str) -> dict | None:
        if not self.odds_client.api_key or not batter["team"]:
            return None
        return self.odds_client.fetch_player_prop_market(batter["name"], batter["team"], market, SPORT_KEY)

    # ----- model -----------------------------------------------------------
    def project(self, player: str, pitcher: str | None = None, park: str | None = None, overrides: dict | None = None) -> dict:
        overrides = overrides or {}
        batter, batter_mode = self._resolve_batter(player)
        opponent, pitcher_mode = self._resolve_pitcher(pitcher)
        venue = self._resolve_park(park, batter["team"])
        return self._score(batter, batter_mode, opponent, pitcher_mode, venue, overrides)

    def _score(
        self,
        batter: dict,
        batter_mode: str,
        opponent: dict,
        pitcher_mode: str,
        venue: dict,
        overrides: dict,
        live_markets: bool = True,
    ) -> dict:

        season = batter["season"]
        for key, field in (("season_hr", "hr"), ("season_pa", "pa")):
            if key in overrides:
                season[field] = int(overrides[key])
        recent = batter["recent"]
        for key, field in (("l10_hr", "hr"), ("l10_pa", "pa"), ("l10_tb", "tb")):
            if key in overrides:
                recent[field] = int(overrides[key])
                recent["games"] = recent.get("games") or 10
        if season["pa"] <= 0:
            raise ValueError("season plate appearances must be positive")

        # 1. Baseline power
        singles = season["hits"] - season["doubles"] - season["triples"] - season["hr"]
        season_tb = max(singles, 0) + 2 * season["doubles"] + 3 * season["triples"] + 4 * season["hr"]
        average = season["hits"] / season["ab"] if season["ab"] else 0.0
        slg = season_tb / season["ab"] if season["ab"] else 0.0
        hr_baseline = season["hr"] / season["pa"]
        statcast = batter["statcast"]
        baseline = {
            "formula": "HR_baseline = Season HR / Season PA",
            "season_hr": season["hr"],
            "season_pa": season["pa"],
            "hr_baseline": round(hr_baseline, 4),
            "batting_average": round(average, 3),
            "slg": round(slg, 3),
            "iso": round(slg - average, 3),
            "hard_hit_pct": statcast.get("hard_hit_pct"),
            "barrel_pct": statcast.get("barrel_pct"),
            "avg_exit_velocity": statcast.get("avg_exit_velocity"),
            "launch_angle_distribution": statcast.get("launch_angle"),
        }

        # 2. Recent form
        hr_l10 = recent["hr"] / recent["pa"] if recent["pa"] > 0 else hr_baseline
        games_l10 = recent.get("games") or 0
        season_tb_per_game = season_tb / season["games"] if season["games"] else 0.0
        tb_l10 = recent["tb"] / games_l10 if games_l10 else season_tb_per_game
        hr_adj = BASELINE_WEIGHT * hr_baseline + RECENT_WEIGHT * hr_l10
        blended_tb_per_game = BASELINE_WEIGHT * season_tb_per_game + RECENT_WEIGHT * tb_l10
        tb_form_factor = clamp(blended_tb_per_game / season_tb_per_game, 0.75, 1.25) if season_tb_per_game else 1.0
        recent_form = {
            "formula": "HR_adj = 0.7 * HR_baseline + 0.3 * HR_L10",
            "games": games_l10,
            "hr_l10": round(hr_l10, 4),
            "tb_l10": round(tb_l10, 3),
            "hr_adj": round(hr_adj, 4),
            "tb_form_factor": round(tb_form_factor, 3),
            "trend": "hot" if hr_l10 > hr_baseline * 1.15 else "cold" if hr_l10 < hr_baseline * 0.85 else "steady",
        }

        # 3. Pitcher matchup (platoon split vs batter handedness; switch hitters bat opposite the pitcher)
        batter_side = batter["bats"]
        if batter_side == "S":
            batter_side = "L" if opponent["throws"] == "R" else "R"
        split_key = "hr_per_9_vs_lhb" if batter_side == "L" else "hr_per_9_vs_rhb"
        pitcher_hr9 = overrides.get("pitcher_hr9", opponent.get(split_key, opponent["hr_per_9"]))
        league_hr9 = overrides.get("league_hr9", LEAGUE["hr_per_9"])
        m_pitcher = clamp(pitcher_hr9 / league_hr9, 0.4, 2.0)
        hr_matchup = hr_adj * m_pitcher
        pitcher_step = {
            "formula": "M_pitcher = Pitcher HR/9 / League HR/9; HR_matchup = HR_adj * M_pitcher",
            "pitcher_hr9": round(pitcher_hr9, 3),
            "platoon_split": f"vs {batter_side}HB",
            "league_hr9": league_hr9,
            "m_pitcher": round(m_pitcher, 3),
            "hr_matchup": round(hr_matchup, 4),
            "barrel_pct_allowed": opponent.get("barrel_pct_allowed"),
            "hard_hit_pct_allowed": opponent.get("hard_hit_pct_allowed"),
            "fastball_ev_allowed": opponent.get("fastball_ev_allowed"),
            "pitch_mix": opponent["pitch_mix"],
        }

        # 4. Ballpark
        m_park = overrides.get("park_hr_factor", venue["hr_factor"])
        tb_park = overrides.get("park_tb_factor", venue["tb_factor"])
        hr_park = hr_matchup * m_park
        park_step = {
            "formula": "M_park = HR Park Factor; HR_park = HR_matchup * M_park",
            "m_park": m_park,
            "tb_factor": tb_park,
            "hr_park": round(hr_park, 4),
        }

        # 5. Weather
        weather = {key: overrides.get(key, default) for key, default in DEFAULT_WEATHER.items()}
        roof_closed = venue["roof"] == "dome" or bool(overrides.get("roof_closed"))
        temp_boost = weather["temperature_f"] - WEATHER_BASE_TEMPERATURE_F
        if roof_closed:
            m_weather = 1.0
        else:
            m_weather = clamp(1 + weather["wind_out_mph"] * 0.01 + temp_boost * 0.005, 0.7, 1.4)
        hr_env = hr_park * m_weather
        weather_step = {
            "formula": "M_weather = 1 + WindOut_mph * 0.01 + TempBoost * 0.005 (TempBoost = temp_f - 70)",
            **weather,
            "temp_boost": round(temp_boost, 1),
            "roof_closed": roof_closed,
            "m_weather": round(m_weather, 3),
            "hr_env": round(hr_env, 4),
        }

        # 6. Pitch-type vulnerability
        mix = opponent["pitch_mix"]
        mix_total = sum(mix.values()) or 1.0
        player_weighted = 0.0
        league_weighted = 0.0
        breakdown = []
        for pitch, usage in mix.items():
            share = usage / mix_total
            league_slg = LEAGUE["pitch_slg"].get(pitch, 0.400)
            player_slg = batter["slg_vs_pitch"].get(pitch, league_slg)
            player_weighted += share * player_slg
            league_weighted += share * league_slg
            breakdown.append({"pitch": pitch, "name": PITCH_NAMES.get(pitch, pitch), "usage": round(share, 3),
                              "player_slg": player_slg, "league_slg": league_slg})
        # Raw player SLG already reflects overall power (captured by HR_baseline), so normalize against the
        # player's SLG versus a league-average pitch mix to isolate how this pitcher's mix fits the hitter.
        profile = batter["slg_vs_pitch"]
        league_mix = LEAGUE_PITCH_MIX
        league_mix_total = sum(league_mix.values())
        player_vs_league_mix = sum(
            usage / league_mix_total * profile.get(pitch, LEAGUE["pitch_slg"][pitch]) for pitch, usage in league_mix.items()
        )
        relative_league = player_weighted / league_weighted if league_weighted else 1.0
        m_pitchtype = clamp(player_weighted / player_vs_league_mix, 0.7, 1.4) if profile else 1.0
        hr_final = clamp(hr_env * m_pitchtype, 0.001, 0.25)
        pitch_step = {
            "formula": "M_pitchtype = sum(PitcherUsage_i * PlayerSLGvsPitch_i) / sum(LeagueUsage_i * PlayerSLGvsPitch_i)",
            "weighted_player_slg": round(player_weighted, 3),
            "weighted_league_slg": round(league_weighted, 3),
            "player_slg_vs_league_mix": round(player_vs_league_mix, 3),
            "vs_league_ratio": round(relative_league, 3),
            "m_pitchtype": round(m_pitchtype, 3),
            "hr_final": round(hr_final, 4),
            "breakdown": sorted(breakdown, key=lambda item: -item["usage"]),
        }

        # 7. Total bases distribution
        lineup_slot = overrides.get("lineup_slot")
        expected_pa = overrides.get("expected_pa", expected_plate_appearances(int(lineup_slot) if lineup_slot else None))
        contact_factor = clamp(statcast["xba"] / statcast["batting_average"], 0.85, 1.15) if statcast.get("batting_average") else 1.0
        pitcher_hit_factor = clamp(opponent["batting_average_against"] / LEAGUE["batting_average_against"], 0.7, 1.3)
        non_hr_multiplier = contact_factor * pitcher_hit_factor * tb_park * tb_form_factor
        p1 = max(singles, 0) / season["pa"] * non_hr_multiplier
        p2 = season["doubles"] / season["pa"] * non_hr_multiplier
        p3 = season["triples"] / season["pa"] * non_hr_multiplier
        hit_total = p1 + p2 + p3 + hr_final
        if hit_total > 0.6:
            scale = (0.6 - hr_final) / (p1 + p2 + p3)
            p1, p2, p3 = p1 * scale, p2 * scale, p3 * scale
        p0 = 1 - (p1 + p2 + p3 + hr_final)
        per_pa = {0: p0, 1: p1, 2: p2, 3: p3, 4: hr_final}
        tb_per_pa = p1 + 2 * p2 + 3 * p3 + 4 * hr_final
        expected_tb = tb_per_pa * expected_pa
        distribution = total_bases_distribution(per_pa, expected_pa)
        hr_game_probability = at_least_one_probability(hr_final, expected_pa)

        tb_line = overrides.get("tb_line")
        tb_market_live = None if tb_line is not None or "tb_over_odds" in overrides else (self._live_market(batter, TB_MARKET) if live_markets else None)
        if tb_line is None:
            tb_line = tb_market_live["line"] if tb_market_live and tb_market_live.get("line") is not None else (1.5 if expected_tb >= 1.3 else 0.5)
        tb_over_probability = probability_over(distribution, tb_line)
        tb_step = {
            "formula": "E[TB] = 1*P(1B) + 2*P(2B) + 3*P(3B) + 4*P(HR) per PA, times expected PA",
            "expected_pa": round(expected_pa, 2),
            "contact_factor_xba": round(contact_factor, 3),
            "pitcher_hit_factor": round(pitcher_hit_factor, 3),
            "per_pa_probabilities": {"out": round(p0, 4), "single": round(p1, 4), "double": round(p2, 4),
                                     "triple": round(p3, 4), "home_run": round(hr_final, 4)},
            "expected_tb_per_pa": round(tb_per_pa, 4),
            "expected_total_bases": round(expected_tb, 3),
            "distribution": {str(total): round(prob, 4) for total, prob in distribution.items() if prob >= 0.0005},
        }

        # 8. Market comparison
        hr_market_live = None if "hr_odds" in overrides else (self._live_market(batter, HR_MARKET) if live_markets else None)
        naive_hr = at_least_one_probability(hr_baseline, DEFAULT_EXPECTED_PA)
        seed = f"{batter['name']}:{opponent['name']}:{venue['name']}"
        if "hr_odds" in overrides:
            hr_over, hr_under, hr_mode = overrides["hr_odds"], overrides.get("hr_no_odds"), "override"
        elif hr_market_live:
            hr_over, hr_under, hr_mode = hr_market_live["over_odds"], hr_market_live["under_odds"], "live"
        else:
            fair = clamp(naive_hr * stable_float(f"{seed}:hr", 0.92, 1.08), 0.02, 0.6)
            hr_over, hr_under, hr_mode = probability_to_american(fair * 1.05), probability_to_american((1 - fair) * 1.05), "fallback"
        hr_comparison = market_comparison(hr_game_probability, hr_over, hr_under, hr_mode, 0.5, HR_MARKET)

        if "tb_over_odds" in overrides:
            tb_over, tb_under, tb_mode = overrides["tb_over_odds"], overrides.get("tb_under_odds"), "override"
        elif tb_market_live and overrides.get("tb_line") is None:
            tb_over, tb_under, tb_mode = tb_market_live["over_odds"], tb_market_live["under_odds"], "live"
        else:
            naive_per_pa = {0: 0.0, 1: max(singles, 0) / season["pa"], 2: season["doubles"] / season["pa"],
                            3: season["triples"] / season["pa"], 4: hr_baseline}
            naive_per_pa[0] = 1 - sum(naive_per_pa.values())
            naive_fair = probability_over(total_bases_distribution(naive_per_pa, DEFAULT_EXPECTED_PA), tb_line)
            fair = clamp(naive_fair * stable_float(f"{seed}:tb", 0.95, 1.05), 0.03, 0.97)
            tb_over, tb_under, tb_mode = probability_to_american(fair * 1.045), probability_to_american((1 - fair) * 1.045), "fallback"
        tb_comparison = market_comparison(tb_over_probability, tb_over, tb_under, tb_mode, tb_line, TB_MARKET)

        return {
            "sport": SPORT_KEY,
            "player": {"name": batter["name"], "team": batter["team"], "bats": batter["bats"]},
            "pitcher": {"name": opponent["name"], "team": opponent["team"], "throws": opponent["throws"]},
            "park": venue,
            "home_run": {
                "per_pa_probability": round(hr_final, 4),
                "expected_pa": round(expected_pa, 2),
                "game_probability": round(hr_game_probability, 4),
                "fair_american_odds": probability_to_american(hr_game_probability),
                "market": hr_comparison,
            },
            "total_bases": {
                "expected": round(expected_tb, 3),
                "line": tb_line,
                "probability_over": round(tb_over_probability, 4),
                "probability_under": round(1 - tb_over_probability, 4),
                "fair_american_odds": probability_to_american(tb_over_probability),
                "market": tb_comparison,
            },
            "steps": {
                "baseline_power": baseline,
                "recent_form": recent_form,
                "pitcher_matchup": pitcher_step,
                "ballpark": park_step,
                "weather": weather_step,
                "pitch_type": pitch_step,
                "total_bases": tb_step,
            },
            "sources": {
                "sportsdataio": {"batter": batter_mode, "pitcher": pitcher_mode},
                "odds_api": {"home_run": hr_mode, "total_bases": tb_mode},
                "statcast": "reference",
            },
            "notes": [
                "Market probability is compared against the per-game probability P(HR >= 1) = 1 - (1 - HR_final)^PA, "
                "since sportsbook HR props are priced per game, not per plate appearance.",
            ],
            "disclaimer": DISCLAIMER,
        }

    # ----- per-team home run leaders ----------------------------------------
    def _team_candidates(self, min_plate_appearances: int) -> tuple[list[dict], str]:
        """Batters grouped later by team: live SportsDataIO season lines (enriched with reference Statcast) or the reference sample."""
        local_by_name = {_normalize(entry["name"]): entry for entry in BATTERS}
        if self.sports_client.api_key:
            live = self.sports_client.fetch_mlb_season_batters(min_plate_appearances)
            if live:
                candidates = []
                for row in live:
                    team = team_full_name(row["team"])
                    if not team:
                        continue
                    batter = self._batter_from_local(local_by_name.get(_normalize(row["name"])), row["name"])
                    batter["name"] = row["name"]
                    batter["team"] = team
                    batter["season"] = dict(row["season"])
                    candidates.append(self._finalize_batter(batter))
                return candidates, "live"
        candidates = [
            self._finalize_batter(self._batter_from_local(entry))
            for entry in BATTERS
            if entry["season"]["pa"] >= min_plate_appearances
        ]
        return candidates, "fallback"

    def team_home_run_leaders(
        self,
        team: str | None = None,
        limit: int = 5,
        pitcher: str | None = None,
        park: str | None = None,
        overrides: dict | None = None,
        min_plate_appearances: int = 100,
    ) -> dict:
        """Rank each team's batters by model P(HR >= 1) for the game, using the full layered prop model."""
        overrides = dict(overrides or {})
        team_filter = None
        if team:
            team_filter = team_full_name(team)
            if not team_filter:
                raise MLBLookupError("team not found")
        opponent, pitcher_mode = self._resolve_pitcher(pitcher)
        fixed_venue = self._resolve_park(park, "") if park else None
        candidates, batter_mode = self._team_candidates(min_plate_appearances)

        by_team: dict[str, list[dict]] = {}
        for batter in candidates:
            if team_filter and batter["team"] != team_filter:
                continue
            by_team.setdefault(batter["team"], []).append(batter)

        teams = []
        for team_name in sorted(by_team):
            venue = fixed_venue or self._resolve_park(None, team_name)
            rows = []
            for batter in by_team[team_name]:
                result = self._score(
                    batter, batter_mode, opponent, pitcher_mode, venue, overrides, live_markets=team_filter is not None
                )
                hr = result["home_run"]
                steps = result["steps"]
                rows.append(
                    {
                        "name": batter["name"],
                        "bats": batter["bats"],
                        "season_hr": batter["season"]["hr"],
                        "season_pa": batter["season"]["pa"],
                        "hr_baseline": steps["baseline_power"]["hr_baseline"],
                        "recent_trend": steps["recent_form"]["trend"],
                        "per_pa_probability": hr["per_pa_probability"],
                        "game_probability": hr["game_probability"],
                        "fair_american_odds": hr["fair_american_odds"],
                        "market_odds": hr["market"]["over_odds"],
                        "implied_probability": hr["market"]["implied_probability"],
                        "edge": hr["market"]["edge"],
                        "market_source": hr["market"]["source_mode"],
                        "expected_total_bases": result["total_bases"]["expected"],
                    }
                )
            rows.sort(key=lambda row: (-row["game_probability"], row["name"]))
            for rank, row in enumerate(rows[:limit], start=1):
                row["rank"] = rank
            teams.append(
                {
                    "team": team_name,
                    "park": {"name": venue["name"], "hr_factor": venue["hr_factor"]},
                    "players": rows[:limit],
                }
            )

        return {
            "sport": SPORT_KEY,
            "team": team_filter,
            "limit": limit,
            "pitcher": {"name": opponent["name"], "team": opponent["team"], "throws": opponent["throws"]},
            "park": fixed_venue["name"] if fixed_venue else "home park",
            "teams": teams,
            "sources": {
                "sportsdataio": {"batters": batter_mode, "pitcher": pitcher_mode},
                "odds_api": "live when a single team is requested and ODDS_API_KEY is set, otherwise fallback",
            },
            "notes": [
                "Players are ranked by the model's per-game probability of at least one home run.",
                "The same opposing pitcher, park, and weather inputs are applied to every listed batter.",
            ],
            "disclaimer": DISCLAIMER,
        }
