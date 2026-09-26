from __future__ import annotations

import math
from hashlib import sha256


DEFAULT_SPORT_PROFILE = {
    "form_weights": {"l3": 0.5, "l5": 0.3, "l10": 0.2},
    "minutes": {
        "base": 18.0,
        "recent_form": 12.0,
        "team_context": 8.0,
        "workload": -4.0,
        "injury_risk": -6.0,
        "broadcast_exposure": 2.0,
        "narrative_pressure": -1.5,
        "rest_days": 0.6,
        "usage_trend": 4.0,
        "role": 3.0,
        "lineup_support": 3.0,
        "teammate_absences": 0.4,
    },
    "performance": {
        "base": 12.0,
        "effective_form": 18.0,
        "consistency": 10.0,
        "team_context": 6.0,
        "matchup_difficulty": -7.0,
        "media_sentiment": 4.0,
        "fantasy_value_rating": 6.0,
        "narrative_pressure": -4.0,
        "usage_trend": 8.0,
        "lineup_support": 4.0,
    },
    "points": {
        "recent_form": 14.0,
        "consistency": 5.0,
        "team_context": 4.0,
        "matchup_difficulty": -5.0,
        "fantasy_projection_blend": 0.32,
        "broadcast_exposure": 1.2,
        "media_sentiment": 1.4,
        "narrative_pressure": -1.5,
        "usage_trend": 6.0,
        "lineup_support": 2.4,
    },
    "risk": {
        "consistency": 0.35,
        "workload": 0.25,
        "matchup_difficulty": 0.2,
        "injury_risk": 0.2,
        "narrative_pressure": 0.12,
        "fantasy_value_rating": -0.06,
        "ownership_projection": -0.03,
        "rest_days": -0.03,
        "usage_trend": -0.04,
    },
    "game": {
        "recent_form": 0.18,
        "efficiency": 0.14,
        "pace": 0.05,
        "injury_impact": -0.08,
        "market_consensus": 0.05,
        "broadcast_heat": 0.03,
        "audience_confidence": 0.02,
        "fantasy_market_support": 0.04,
        "narrative_pressure": -0.02,
        "injury_leverage": -0.01,
    },
}


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(value, maximum))


def stable_float(seed: str, minimum: float, maximum: float) -> float:
    digest = sha256(seed.encode("utf-8")).hexdigest()
    ratio = int(digest[:8], 16) / 0xFFFFFFFF
    return minimum + (maximum - minimum) * ratio


MODEL_VERSION = "2026.09-platt-kelly"
KELLY_FRACTION = 0.25
KELLY_CAPS = {"Low": 0.01, "Moderate": 0.02, "High": 0.03}
BET_EDGE_THRESHOLD = 0.03
BET_QUALITY_THRESHOLD = 0.38


def kelly_stake(probability: float | None, american_odds: int | None, confidence_band: str, bankroll_units: float = 100.0) -> dict:
    """Fractional Kelly stake capped by confidence band (fractions are of bankroll)."""
    cap = KELLY_CAPS.get(confidence_band, KELLY_CAPS["Low"])
    if probability is None or not american_odds:
        full_kelly = 0.0
    else:
        net_odds = american_odds / 100 if american_odds > 0 else 100 / abs(american_odds)
        full_kelly = max((net_odds * probability - (1 - probability)) / net_odds, 0.0)
    fractional = full_kelly * KELLY_FRACTION
    stake_fraction = min(fractional, cap)
    return {
        "full_kelly": round(full_kelly, 4),
        "fraction": KELLY_FRACTION,
        "fractional_kelly": round(fractional, 4),
        "confidence_cap": cap,
        "stake_fraction": round(stake_fraction, 4),
        "stake_units": round(stake_fraction * bankroll_units, 2),
        "bankroll_units": bankroll_units,
    }


def _normal_cdf(value: float) -> float:
    return 0.5 * (1 + math.erf(value / math.sqrt(2)))


def build_prop_edge(expected_points: float, points_range: dict, prop: dict, confidence_band: str) -> dict:
    """Compare a player projection with a real over/under line."""
    line = float(prop["line"])
    over_odds = int(prop["over_odds"])
    under_odds = int(prop["under_odds"])
    sigma = max((points_range["high"] - points_range["low"]) / 2.56, expected_points * 0.12, 0.5)
    probability_over = clamp(1 - _normal_cdf((line - expected_points) / sigma), 0.01, 0.99)
    implied_over = american_to_implied_probability(over_odds)
    implied_under = american_to_implied_probability(under_odds)
    edge_over = probability_over - implied_over
    edge_under = (1 - probability_over) - implied_under
    if edge_over >= BET_EDGE_THRESHOLD and edge_over >= edge_under:
        action, probability, implied, edge, odds = "over", probability_over, implied_over, edge_over, over_odds
    elif edge_under >= BET_EDGE_THRESHOLD:
        action, probability, implied, edge, odds = "under", 1 - probability_over, implied_under, edge_under, under_odds
    else:
        best_is_over = edge_over >= edge_under
        action = "pass"
        probability = probability_over if best_is_over else 1 - probability_over
        implied = implied_over if best_is_over else implied_under
        edge = edge_over if best_is_over else edge_under
        odds = over_odds if best_is_over else under_odds
    kelly = kelly_stake(probability if action != "pass" else None, odds, confidence_band)
    return {
        "market": prop.get("market", "player_points"),
        "line": round(line, 1),
        "over_odds": over_odds,
        "under_odds": under_odds,
        "projection": round(expected_points, 1),
        "projection_sigma": round(sigma, 2),
        "probability_over": round(probability_over, 3),
        "probability_under": round(1 - probability_over, 3),
        "edge_over": round(edge_over, 3),
        "edge_under": round(edge_under, 3),
        "recommended_action": action,
        "model_probability": round(probability, 3),
        "implied_probability": round(implied, 3),
        "edge": round(edge, 3),
        "bet_odds": odds,
        "kelly": kelly,
        "bookmakers": prop.get("bookmakers"),
        "event_id": prop.get("event_id"),
        "source_mode": prop.get("source_mode", "override"),
    }


def platt_calibrate(probability: float, calibrator: dict) -> float:
    probability = clamp(probability, 1e-4, 1 - 1e-4)
    logit = math.log(probability / (1 - probability))
    return clamp(1 / (1 + math.exp(-(calibrator["a"] * logit + calibrator["b"]))), 0.02, 0.98)


def apply_probability_calibration(payload: dict, calibrator: dict | None) -> dict:
    """Recalibrate the game win probability and re-derive edge, action, and Kelly stake."""
    betting_edge = payload["betting_edge"]
    raw_probability = payload["team_prediction"]["win_probability"]
    implied_probability = payload["market_signals"]["implied_probability"]
    if calibrator:
        calibrated_probability = platt_calibrate(raw_probability, calibrator)
        edge = calibrated_probability - implied_probability
        if edge >= BET_EDGE_THRESHOLD and betting_edge["edge_quality_score"] >= BET_QUALITY_THRESHOLD:
            action = "bet"
        elif edge <= -BET_EDGE_THRESHOLD:
            action = "avoid"
        else:
            action = "hold"
        betting_edge["raw_edge"] = betting_edge["edge"]
        betting_edge["edge"] = round(edge, 3)
        betting_edge["recommended_action"] = action
        betting_edge["recommended_stake"] = _recommended_stake(edge, betting_edge["edge_quality_score"])
        betting_edge["calibration"] = {
            **betting_edge["calibration"],
            "mode": "platt_scaling",
            "a": round(calibrator["a"], 4),
            "b": round(calibrator["b"], 4),
            "samples": calibrator.get("samples"),
            "raw_probability": raw_probability,
        }
    else:
        calibrated_probability = raw_probability
    betting_edge["calibrated_probability"] = round(calibrated_probability, 3)
    betting_edge["kelly"] = kelly_stake(
        calibrated_probability if betting_edge["recommended_action"] == "bet" else None,
        payload["market_signals"]["current_odds"],
        payload["team_prediction"]["confidence_band"],
    )
    return payload


def american_to_implied_probability(american_odds: int) -> float:
    if american_odds == 0:
        raise ValueError("American odds cannot be zero.")
    if american_odds > 0:
        return 100 / (american_odds + 100)
    return abs(american_odds) / (abs(american_odds) + 100)


def _sport_profile(sports_data: dict) -> dict:
    profile = sports_data.get("sport_profile") or DEFAULT_SPORT_PROFILE
    return {
        "form_weights": dict(profile.get("form_weights", DEFAULT_SPORT_PROFILE["form_weights"])),
        "minutes": dict(profile.get("minutes", DEFAULT_SPORT_PROFILE["minutes"])),
        "performance": dict(profile.get("performance", DEFAULT_SPORT_PROFILE["performance"])),
        "points": dict(profile.get("points", DEFAULT_SPORT_PROFILE["points"])),
        "risk": dict(profile.get("risk", DEFAULT_SPORT_PROFILE["risk"])),
        "game": dict(profile.get("game", DEFAULT_SPORT_PROFILE["game"])),
    }


def _role_factor(projected_role: str) -> float:
    normalized = (projected_role or "").strip().lower()
    if "primary" in normalized or "featured" in normalized:
        return 1.0
    if "starter" in normalized:
        return 0.78
    if "rotation" in normalized:
        return 0.55
    if "bench" in normalized:
        return 0.35
    return 0.5


def _range(low: float, center: float, high: float, floor: float = 0.0, ceiling: float | None = None) -> dict:
    lower = max(floor, low)
    upper = high if ceiling is None else min(ceiling, high)
    return {
        "low": round(min(lower, center), 1),
        "mid": round(center, 1),
        "high": round(max(upper, center), 1),
    }


def _confidence_band(confidence: float) -> str:
    if confidence >= 0.75:
        return "High"
    if confidence >= 0.55:
        return "Moderate"
    return "Low"


def _availability_tier(availability_probability: float, injury_status: str, injury_days_out: float) -> str:
    if injury_status == "Out" or injury_days_out >= 5:
        return "Unavailable"
    if availability_probability >= 0.8:
        return "Clear"
    if availability_probability >= 0.62:
        return "Watch"
    return "Fragile"


def _feature_tracking(features: dict[str, float], positive_cutoff: float = 0.62, negative_cutoff: float = 0.38) -> dict:
    helping = [name for name, value in features.items() if value >= positive_cutoff]
    hurting = [name for name, value in features.items() if value <= negative_cutoff]
    return {
        "helping": helping[:5],
        "hurting": hurting[:5],
    }


def _calibration_proxy(confidence: float, variability: float, quality_signal: float) -> dict:
    projected_hit_rate = clamp(0.44 + confidence * 0.32 + quality_signal * 0.14 - variability * 0.18, 0.35, 0.84)
    return {
        "mode": "heuristic_proxy",
        "confidence_band": _confidence_band(confidence),
        "projected_hit_rate": round(projected_hit_rate, 3),
    }


def build_player_prediction(player_id: str, sports_data: dict | None = None) -> dict:
    sports_data = sports_data or {}
    profile = _sport_profile(sports_data)
    form_weights = profile["form_weights"]
    recent_form = sports_data.get("recent_form", stable_float(f"{player_id}:form", 0.4, 0.95))
    recent_form_l3 = sports_data.get("recent_form_l3", recent_form)
    recent_form_l5 = sports_data.get("recent_form_l5", recent_form)
    recent_form_l10 = sports_data.get("recent_form_l10", recent_form)
    effective_form = clamp(
        recent_form_l3 * form_weights["l3"] + recent_form_l5 * form_weights["l5"] + recent_form_l10 * form_weights["l10"],
        0.05,
        0.99,
    )
    workload = sports_data.get("workload", stable_float(f"{player_id}:workload", 0.2, 0.9))
    injury_risk = sports_data.get("injury_risk", stable_float(f"{player_id}:injury", 0.05, 0.55))
    consistency = sports_data.get("consistency", stable_float(f"{player_id}:consistency", 0.35, 0.95))
    matchup_difficulty = sports_data.get("matchup_difficulty", stable_float(f"{player_id}:matchup", 0.2, 0.9))
    team_context = sports_data.get("team_context", stable_float(f"{player_id}:team", 0.3, 0.85))
    availability = sports_data.get("availability", clamp(1 - injury_risk * 0.9, 0.05, 0.99))
    effort_change = sports_data.get("effort_change", stable_float(f"{player_id}:effort", -0.2, 0.2))
    fouls_cards = sports_data.get("fouls_cards", stable_float(f"{player_id}:discipline", 0.0, 0.7))
    team_instability = sports_data.get("team_instability", stable_float(f"{player_id}:instability", 0.05, 0.6))
    media_sentiment = sports_data.get("media_sentiment", stable_float(f"{player_id}:media", 0.3, 0.8))
    broadcast_exposure = sports_data.get("broadcast_exposure", stable_float(f"{player_id}:broadcast", 0.25, 0.95))
    narrative_pressure = sports_data.get("narrative_pressure", stable_float(f"{player_id}:narrative", 0.08, 0.72))
    fantasy_projection = sports_data.get("fantasy_projection", stable_float(f"{player_id}:fantasy_projection", 14, 42))
    fantasy_value_rating = sports_data.get("fantasy_value_rating", stable_float(f"{player_id}:fantasy_value", 0.28, 0.94))
    ownership_projection = sports_data.get("ownership_projection", stable_float(f"{player_id}:ownership", 0.1, 0.65))
    rest_days = sports_data.get("rest_days", stable_float(f"{player_id}:rest", 0, 4))
    usage_trend = sports_data.get("usage_trend", stable_float(f"{player_id}:usage", -0.15, 0.18))
    home_split = sports_data.get("home_split", recent_form)
    away_split = sports_data.get("away_split", recent_form)
    opponent_split = sports_data.get("opponent_split", recent_form)
    source_confidence = sports_data.get("source_confidence", 0.66)
    data_freshness = sports_data.get("data_freshness", 0.78)
    teammate_absences = sports_data.get("teammate_absences", 0.0)
    lineup_support = sports_data.get("lineup_support", 0.6)
    injury_days_out = sports_data.get("injury_days_out", 0.0)
    projected_role = sports_data.get("projected_role", "Rotation")
    injury_status = sports_data.get("injury_status", "Available")

    home_away_balance = 1 - min(abs(home_split - away_split), 1)
    role_factor = _role_factor(projected_role)
    lineup_context = clamp(lineup_support + teammate_absences * 0.08, 0.05, 0.99)

    minutes_weights = profile["minutes"]
    expected_minutes = clamp(
        minutes_weights["base"]
        + effective_form * minutes_weights["recent_form"]
        + team_context * minutes_weights["team_context"]
        + workload * minutes_weights["workload"]
        + injury_risk * minutes_weights["injury_risk"]
        + broadcast_exposure * minutes_weights["broadcast_exposure"]
        + narrative_pressure * minutes_weights["narrative_pressure"]
        + min(rest_days, 3) * minutes_weights["rest_days"]
        + usage_trend * minutes_weights["usage_trend"]
        + role_factor * minutes_weights["role"]
        + lineup_support * minutes_weights["lineup_support"]
        + teammate_absences * minutes_weights["teammate_absences"]
        + source_confidence * 1.8
        + data_freshness * 1.4,
        0,
        48,
    )

    performance_weights = profile["performance"]
    expected_performance = max(
        0,
        performance_weights["base"]
        + effective_form * performance_weights["effective_form"]
        + consistency * performance_weights["consistency"]
        + team_context * performance_weights["team_context"]
        + matchup_difficulty * performance_weights["matchup_difficulty"]
        + media_sentiment * performance_weights["media_sentiment"]
        + fantasy_value_rating * performance_weights["fantasy_value_rating"]
        + narrative_pressure * performance_weights["narrative_pressure"]
        + usage_trend * performance_weights["usage_trend"]
        + lineup_context * performance_weights["lineup_support"]
        + home_away_balance * 3.0
        + opponent_split * 2.5
        + source_confidence * 2.4,
    )

    points_weights = profile["points"]
    base_expected_points = sports_data.get(
        "expected_points",
        8
        + effective_form * points_weights["recent_form"]
        + consistency * points_weights["consistency"]
        + team_context * points_weights["team_context"]
        + matchup_difficulty * points_weights["matchup_difficulty"]
        + usage_trend * points_weights["usage_trend"]
        + lineup_context * points_weights["lineup_support"]
        + opponent_split * 2.0,
    )
    fantasy_blend = clamp(points_weights["fantasy_projection_blend"] * source_confidence, 0.12, 0.5)
    expected_points = max(
        0,
        base_expected_points * (1 - fantasy_blend)
        + fantasy_projection * fantasy_blend
        + broadcast_exposure * points_weights["broadcast_exposure"]
        + media_sentiment * points_weights["media_sentiment"]
        + narrative_pressure * points_weights["narrative_pressure"]
        + min(rest_days, 4) * 0.35
        + home_away_balance * 1.4,
    )

    risk_weights = profile["risk"]
    underperformance_risk = clamp(
        (1 - consistency) * risk_weights["consistency"]
        + workload * risk_weights["workload"]
        + matchup_difficulty * risk_weights["matchup_difficulty"]
        + injury_risk * risk_weights["injury_risk"]
        + narrative_pressure * risk_weights["narrative_pressure"]
        + fantasy_value_rating * risk_weights["fantasy_value_rating"]
        + ownership_projection * risk_weights["ownership_projection"]
        + min(rest_days, 4) * risk_weights["rest_days"]
        + usage_trend * risk_weights["usage_trend"]
        + (1 - source_confidence) * 0.08
        + (1 - data_freshness) * 0.06
        + (1 - home_away_balance) * 0.06
        + max(injury_days_out, 0) * 0.01,
        0,
        1,
    )
    availability_probability = clamp(
        (1 - injury_risk) * 0.5
        + availability * 0.2
        + source_confidence * 0.12
        + data_freshness * 0.08
        + min(rest_days, 4) / 4 * 0.08
        - min(injury_days_out, 14) / 14 * 0.1,
        0,
        1,
    )
    likely_to_score = expected_points >= 20 and availability_probability >= 0.6 and underperformance_risk <= 0.55
    injured = injury_risk >= 0.35 or injury_status in {"Limited", "Questionable", "Out"}

    variability = clamp(
        (1 - consistency) * 0.28
        + underperformance_risk * 0.26
        + (1 - source_confidence) * 0.2
        + (1 - data_freshness) * 0.16
        + (1 - home_away_balance) * 0.1,
        0.08,
        0.45,
    )
    prediction_confidence = clamp(
        source_confidence * 0.28
        + data_freshness * 0.18
        + consistency * 0.2
        + availability_probability * 0.12
        + effective_form * 0.12
        + lineup_support * 0.1
        - underperformance_risk * 0.12
        - (1 - home_away_balance) * 0.08,
        0.05,
        0.99,
    )
    minutes_range = _range(expected_minutes * (1 - variability * 0.55), expected_minutes, expected_minutes * (1 + variability * 0.42), 0.0, 48.0)
    points_range = _range(expected_points * (1 - variability * 0.5), expected_points, expected_points * (1 + variability * 0.5), 0.0)
    performance_range = _range(
        expected_performance * (1 - variability * 0.42),
        expected_performance,
        expected_performance * (1 + variability * 0.42),
        0.0,
    )
    tracked_features = _feature_tracking(
        {
            "effective_form": effective_form,
            "consistency": consistency,
            "availability": availability_probability,
            "lineup_support": lineup_support,
            "rest_days": clamp(rest_days / 4, 0, 1),
            "matchup_difficulty": 1 - matchup_difficulty,
            "injury_risk": 1 - injury_risk,
            "source_confidence": source_confidence,
            "data_freshness": data_freshness,
        }
    )
    calibration = _calibration_proxy(prediction_confidence, variability, availability_probability)

    return {
        "player_id": player_id,
        "sources": ["SportsDataIO", "Media & Broadcast", "Fantasy Sports API"],
        "player_signals": {
            "recent_form": round(recent_form, 3),
            "recent_form_l3": round(recent_form_l3, 3),
            "recent_form_l5": round(recent_form_l5, 3),
            "recent_form_l10": round(recent_form_l10, 3),
            "effective_form": round(effective_form, 3),
            "workload_fatigue": round(workload, 3),
            "injury_risk": round(injury_risk, 3),
            "consistency": round(consistency, 3),
            "matchup_difficulty": round(matchup_difficulty, 3),
            "team_context": round(team_context, 3),
            "rest_days": round(rest_days, 2),
            "usage_trend": round(usage_trend, 3),
            "home_split": round(home_split, 3),
            "away_split": round(away_split, 3),
            "opponent_split": round(opponent_split, 3),
            "source_confidence": round(source_confidence, 3),
            "data_freshness": round(data_freshness, 3),
            "teammate_absences": round(teammate_absences, 2),
            "lineup_support": round(lineup_support, 3),
        },
        "psychological_proxies": {
            "effort_change": round(effort_change, 3),
            "fouls_cards": round(fouls_cards, 3),
            "team_instability": round(team_instability, 3),
            "media_sentiment": round(media_sentiment, 3),
        },
        "media_broadcast_signals": {
            "broadcast_exposure": round(broadcast_exposure, 3),
            "narrative_pressure": round(narrative_pressure, 3),
            "media_sentiment": round(media_sentiment, 3),
        },
        "fantasy_sports_signals": {
            "fantasy_projection": round(fantasy_projection, 1),
            "fantasy_value_rating": round(fantasy_value_rating, 3),
            "ownership_projection": round(ownership_projection, 3),
        },
        "predictions": {
            "expected_minutes": round(expected_minutes, 1),
            "expected_minutes_range": minutes_range,
            "expected_points": round(expected_points, 1),
            "expected_points_range": points_range,
            "expected_performance": round(expected_performance, 1),
            "expected_performance_range": performance_range,
            "underperformance_risk": round(underperformance_risk, 3),
            "availability_probability": round(availability_probability, 3),
            "availability_tier": _availability_tier(availability_probability, injury_status, injury_days_out),
            "injured": injured,
            "injured_label": "Yes" if injured else "No",
            "likely_to_score": likely_to_score,
            "scoring_outlook": "Likely to score" if likely_to_score else "Not likely to score",
            "prediction_confidence": round(prediction_confidence, 3),
            "confidence_band": calibration["confidence_band"],
            "calibration": calibration,
            "feature_tracking": tracked_features,
        },
    }


def build_game_edge(game_id: str, sports_data: dict | None = None, odds_data: dict | None = None) -> dict:
    sports_data = sports_data or {}
    odds_data = odds_data or {}
    profile = _sport_profile(sports_data)
    game_weights = profile["game"]
    opening_odds = int(odds_data.get("opening_odds", -108))
    current_odds = int(odds_data.get("current_odds", opening_odds))
    implied_probability = odds_data.get("implied_probability")
    if implied_probability is None:
        implied_probability = american_to_implied_probability(current_odds)

    recent_form = sports_data.get("team_form", stable_float(f"{game_id}:team_form", 0.35, 0.9))
    pace = sports_data.get("pace", stable_float(f"{game_id}:pace", 0.35, 0.8))
    efficiency = sports_data.get("efficiency", stable_float(f"{game_id}:efficiency", 0.4, 0.9))
    injury_impact = sports_data.get("injury_impact", stable_float(f"{game_id}:injury_impact", 0.05, 0.5))
    broadcast_heat = sports_data.get("broadcast_heat", stable_float(f"{game_id}:heat", 0.3, 0.92))
    audience_confidence = sports_data.get("audience_confidence", stable_float(f"{game_id}:audience", 0.35, 0.84))
    narrative_pressure = sports_data.get("narrative_pressure", stable_float(f"{game_id}:narrative", 0.08, 0.7))
    fantasy_market_support = sports_data.get("fantasy_market_support", stable_float(f"{game_id}:fantasy_support", 0.3, 0.88))
    fantasy_points_total = sports_data.get("fantasy_points_total", stable_float(f"{game_id}:fantasy_total", 198, 244))
    injury_leverage = sports_data.get("injury_leverage", stable_float(f"{game_id}:injury_leverage", 0.05, 0.7))
    market_consensus = odds_data.get("market_consensus", stable_float(f"{game_id}:consensus", 0.35, 0.7))
    line_movement = odds_data.get("line_movement", round(current_odds - opening_odds, 3))
    sharp_money_index = odds_data.get("sharp_money_index", stable_float(f"{game_id}:sharp", 0.2, 0.95))
    steam_move = bool(odds_data.get("steam_move", stable_float(f"{game_id}:steam", 0.0, 1.0) > 0.7))
    closing_line_value = odds_data.get("closing_line_value", stable_float(f"{game_id}:clv", -0.08, 0.08))
    book_disagreement = odds_data.get("book_disagreement", stable_float(f"{game_id}:disagreement", 0.01, 0.18))
    market_source_confidence = odds_data.get("market_source_confidence", 0.72)
    consensus_spread = odds_data.get("consensus_spread", 0.0)
    historical_closing_line_value = odds_data.get("historical_closing_line_value", closing_line_value)

    if "model_probability" in sports_data:
        model_probability = clamp(sports_data["model_probability"], 0.02, 0.98)
    else:
        model_probability = clamp(
            0.5
            + (recent_form - 0.5) * game_weights["recent_form"]
            + (efficiency - 0.5) * game_weights["efficiency"]
            + (pace - 0.5) * game_weights["pace"]
            + injury_impact * game_weights["injury_impact"]
            + (market_consensus - 0.5) * game_weights["market_consensus"]
            + (broadcast_heat - 0.5) * game_weights["broadcast_heat"]
            + (audience_confidence - 0.5) * game_weights["audience_confidence"]
            + (fantasy_market_support - 0.5) * game_weights["fantasy_market_support"]
            + narrative_pressure * game_weights["narrative_pressure"]
            + injury_leverage * game_weights["injury_leverage"],
            0.02,
            0.98,
        )
    edge = model_probability - implied_probability
    market_stability = clamp(
        1
        - min(abs(line_movement) / 25, 0.65)
        - book_disagreement * 0.75
        - (0.1 if steam_move else 0),
        0.05,
        0.99,
    )
    source_agreement = clamp((1 - abs(model_probability - market_consensus)) * 0.55 + market_source_confidence * 0.45, 0.05, 0.99)
    model_confidence = clamp(
        0.38
        + abs(edge) * 2.3
        + sharp_money_index * 0.12
        + max(closing_line_value, 0) * 0.55
        + max(historical_closing_line_value, 0) * 0.25
        + market_stability * 0.12
        + source_agreement * 0.15
        - book_disagreement * 0.25
        - (0.05 if steam_move else 0),
        0,
        1,
    )
    edge_quality_score = clamp(
        abs(edge) * 2.1
        + model_confidence * 0.35
        + market_stability * 0.15
        + source_agreement * 0.15
        + max(closing_line_value, 0) * 0.4
        - max(-closing_line_value, 0) * 0.25,
        0,
        1,
    )
    if edge >= 0.03 and edge_quality_score >= 0.38:
        recommended_action = "bet"
    elif edge <= -0.03:
        recommended_action = "avoid"
    else:
        recommended_action = "hold"

    variance = clamp((1 - market_stability) * 0.28 + (1 - source_agreement) * 0.22 + book_disagreement * 0.2 + injury_impact * 0.15, 0.06, 0.32)
    win_probability_range = _range(model_probability - variance * 0.45, model_probability, model_probability + variance * 0.45, 0.02, 0.98)
    expected_points = (
        95
        + pace * 15
        + efficiency * 12
        - injury_impact * 5
        + broadcast_heat * 2
        + (fantasy_points_total - 220) * 0.08
    )
    expected_points_range = _range(expected_points * (1 - variance * 0.25), expected_points, expected_points * (1 + variance * 0.25), 0.0)
    calibration = _calibration_proxy(model_confidence, variance, edge_quality_score)

    return apply_probability_calibration({
        "game_id": game_id,
        "sources": ["SportsDataIO", "Media & Broadcast", "Fantasy Sports API", "The Odds API"],
        "team_prediction": {
            "win_probability": round(model_probability, 3),
            "win_probability_range": {
                "low": round(win_probability_range["low"], 3),
                "mid": round(win_probability_range["mid"], 3),
                "high": round(win_probability_range["high"], 3),
            },
            "expected_points": round(expected_points, 1),
            "expected_points_range": expected_points_range,
            "pace": round(pace, 3),
            "efficiency": round(efficiency, 3),
            "confidence": round(model_confidence, 3),
            "confidence_band": calibration["confidence_band"],
        },
        "context_signals": {
            "broadcast_heat": round(broadcast_heat, 3),
            "audience_confidence": round(audience_confidence, 3),
            "narrative_pressure": round(narrative_pressure, 3),
            "fantasy_market_support": round(fantasy_market_support, 3),
            "fantasy_points_total": round(fantasy_points_total, 1),
            "injury_leverage": round(injury_leverage, 3),
        },
        "market_signals": {
            "opening_odds": opening_odds,
            "current_odds": current_odds,
            "implied_probability": round(implied_probability, 3),
            "market_consensus": round(market_consensus, 3),
            "line_movement": round(line_movement, 3),
            "sharp_money_index": round(sharp_money_index, 3),
            "steam_move": steam_move,
            "closing_line_value": round(closing_line_value, 3),
            "book_disagreement": round(book_disagreement, 3),
            "consensus_spread": round(consensus_spread, 3),
            "historical_closing_line_value": round(historical_closing_line_value, 3),
            "market_source_confidence": round(market_source_confidence, 3),
            "market_stability": round(market_stability, 3),
            "source_agreement": round(source_agreement, 3),
        },
        "betting_edge": {
            "edge": round(edge, 3),
            "recommended_action": recommended_action,
            "confidence": round(model_confidence, 3),
            "recommended_stake": _recommended_stake(edge, edge_quality_score),
            "edge_quality": _confidence_band(edge_quality_score),
            "edge_quality_score": round(edge_quality_score, 3),
            "calibration": calibration,
            "feature_tracking": _feature_tracking(
                {
                    "edge": clamp(abs(edge) * 8, 0, 1),
                    "market_stability": market_stability,
                    "source_agreement": source_agreement,
                    "sharp_money": sharp_money_index,
                    "closing_line_value": clamp((closing_line_value + 0.15) / 0.3, 0, 1),
                    "book_disagreement": 1 - book_disagreement,
                }
            ),
        },
    }, None)


def _recommended_stake(edge: float, edge_quality_score: float) -> str:
    absolute_edge = abs(edge)
    if absolute_edge < 0.03:
        return "no_play"
    if edge_quality_score < 0.4:
        return "small"
    if absolute_edge < 0.07:
        return "small"
    if absolute_edge < 0.12:
        return "medium"
    return "strong"
