from __future__ import annotations

from hashlib import sha256


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(value, maximum))


def stable_float(seed: str, minimum: float, maximum: float) -> float:
    digest = sha256(seed.encode("utf-8")).hexdigest()
    ratio = int(digest[:8], 16) / 0xFFFFFFFF
    return minimum + (maximum - minimum) * ratio


def american_to_implied_probability(american_odds: int) -> float:
    if american_odds == 0:
        raise ValueError("American odds cannot be zero.")
    if american_odds > 0:
        return 100 / (american_odds + 100)
    return abs(american_odds) / (abs(american_odds) + 100)


def build_player_prediction(player_id: str, sports_data: dict | None = None) -> dict:
    sports_data = sports_data or {}
    recent_form = sports_data.get("recent_form", stable_float(f"{player_id}:form", 0.4, 0.95))
    workload = sports_data.get("workload", stable_float(f"{player_id}:workload", 0.2, 0.9))
    injury_risk = sports_data.get("injury_risk", stable_float(f"{player_id}:injury", 0.05, 0.55))
    consistency = sports_data.get("consistency", stable_float(f"{player_id}:consistency", 0.35, 0.95))
    matchup_difficulty = sports_data.get(
        "matchup_difficulty",
        stable_float(f"{player_id}:matchup", 0.2, 0.9),
    )
    team_context = sports_data.get("team_context", stable_float(f"{player_id}:team", 0.3, 0.85))
    availability = sports_data.get("availability", clamp(1 - injury_risk * 0.9, 0.05, 0.99))
    effort_change = sports_data.get("effort_change", stable_float(f"{player_id}:effort", -0.2, 0.2))
    fouls_cards = sports_data.get("fouls_cards", stable_float(f"{player_id}:discipline", 0.0, 0.7))
    team_instability = sports_data.get(
        "team_instability",
        stable_float(f"{player_id}:instability", 0.05, 0.6),
    )
    media_sentiment = sports_data.get("media_sentiment", stable_float(f"{player_id}:media", 0.3, 0.8))

    expected_minutes = clamp(
        18 + recent_form * 12 + team_context * 8 - workload * 4 - injury_risk * 6,
        0,
        48,
    )
    expected_performance = max(
        0,
        12 + recent_form * 18 + consistency * 10 + team_context * 6 - matchup_difficulty * 7,
    )
    expected_points = max(
        0,
        sports_data.get(
            "expected_points",
            8 + recent_form * 14 + consistency * 5 + team_context * 4 - matchup_difficulty * 5,
        ),
    )
    underperformance_risk = clamp(
        (1 - consistency) * 0.35
        + workload * 0.25
        + matchup_difficulty * 0.2
        + injury_risk * 0.2,
        0,
        1,
    )
    availability_probability = clamp((1 - injury_risk) * 0.75 + availability * 0.25, 0, 1)
    likely_to_score = (
        expected_points >= 20
        and availability_probability >= 0.6
        and underperformance_risk <= 0.55
    )

    return {
        "player_id": player_id,
        "sources": ["SportsDataIO"],
        "player_signals": {
            "recent_form": round(recent_form, 3),
            "workload_fatigue": round(workload, 3),
            "injury_risk": round(injury_risk, 3),
            "consistency": round(consistency, 3),
            "matchup_difficulty": round(matchup_difficulty, 3),
            "team_context": round(team_context, 3),
        },
        "psychological_proxies": {
            "effort_change": round(effort_change, 3),
            "fouls_cards": round(fouls_cards, 3),
            "team_instability": round(team_instability, 3),
            "media_sentiment": round(media_sentiment, 3),
        },
        "predictions": {
            "expected_minutes": round(expected_minutes, 1),
            "expected_points": round(expected_points, 1),
            "expected_performance": round(expected_performance, 1),
            "underperformance_risk": round(underperformance_risk, 3),
            "availability_probability": round(availability_probability, 3),
            "likely_to_score": likely_to_score,
            "scoring_outlook": "Likely to score" if likely_to_score else "Not likely to score",
        },
    }


def build_game_edge(
    game_id: str,
    sports_data: dict | None = None,
    odds_data: dict | None = None,
) -> dict:
    sports_data = sports_data or {}
    odds_data = odds_data or {}
    opening_odds = int(odds_data.get("opening_odds", -108))
    current_odds = int(odds_data.get("current_odds", opening_odds))
    implied_probability = odds_data.get("implied_probability")
    if implied_probability is None:
        implied_probability = american_to_implied_probability(current_odds)

    recent_form = sports_data.get("team_form", stable_float(f"{game_id}:team_form", 0.35, 0.9))
    pace = sports_data.get("pace", stable_float(f"{game_id}:pace", 0.35, 0.8))
    efficiency = sports_data.get("efficiency", stable_float(f"{game_id}:efficiency", 0.4, 0.9))
    injury_impact = sports_data.get("injury_impact", stable_float(f"{game_id}:injury_impact", 0.05, 0.5))
    market_consensus = odds_data.get(
        "market_consensus",
        stable_float(f"{game_id}:consensus", 0.35, 0.7),
    )
    line_movement = odds_data.get("line_movement", round(current_odds - opening_odds, 3))

    model_probability = sports_data.get(
        "model_probability",
        clamp(
            0.5
            + (recent_form - 0.5) * 0.18
            + (efficiency - 0.5) * 0.14
            + (pace - 0.5) * 0.05
            - injury_impact * 0.08
            + (market_consensus - 0.5) * 0.05,
            0.02,
            0.98,
        ),
    )
    edge = model_probability - implied_probability
    if edge >= 0.03:
        recommended_action = "bet"
    elif edge <= -0.03:
        recommended_action = "avoid"
    else:
        recommended_action = "hold"

    return {
        "game_id": game_id,
        "sources": ["SportsDataIO", "The Odds API"],
        "team_prediction": {
            "win_probability": round(model_probability, 3),
            "expected_points": round(95 + pace * 15 + efficiency * 12 - injury_impact * 5, 1),
            "pace": round(pace, 3),
            "efficiency": round(efficiency, 3),
        },
        "market_signals": {
            "opening_odds": opening_odds,
            "current_odds": current_odds,
            "line_movement": line_movement,
            "implied_probability": round(implied_probability, 3),
            "market_consensus": round(market_consensus, 3),
        },
        "betting_edge": {
            "edge": round(edge, 3),
            "recommended_action": recommended_action,
        },
    }
