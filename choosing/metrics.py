from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from statistics import mean

BET_ACTIONS = {"bet", "over", "under"}
BREAKDOWN_DIMENSIONS = ("sport", "market", "confidence_band", "edge_bucket", "model_version")
TIMESERIES_WINDOWS = {"7d": 7, "30d": 30, "90d": 90, "all": None}


def build_backtest_summary(records: list[dict]) -> dict:
    game_records = [record for record in records if record["entity_type"] == "game"]
    resolved_games = [record for record in game_records if record["actual_outcome"] is not None]
    player_records = [record for record in records if record["entity_type"] == "player"]
    resolved_players = [
        record
        for record in player_records
        if record["actual_points"] is not None or record["actual_minutes"] is not None or record["actual_available"] is not None
    ]
    resolved_markets = [
        record
        for record in records
        if record["actual_outcome"] is not None and record["model_probability"] is not None
    ]
    calibration_curve = compute_calibration_curve(resolved_markets)
    by_sport = {}
    for sport_key in sorted({record["sport_key"] for record in resolved_markets if record["sport_key"]}):
        sport_records = [record for record in resolved_markets if record["sport_key"] == sport_key]
        by_sport[sport_key] = {
            "resolved_predictions": len(sport_records),
            "brier_score": compute_brier_score(sport_records),
            "hit_rate": compute_hit_rate(sport_records),
            "roi": compute_roi(sport_records),
        }
    return {
        "total_predictions": len(records),
        "resolved_predictions": len([record for record in records if record["outcome_recorded_at"]]),
        "game_predictions": len(game_records),
        "resolved_games": len(resolved_games),
        "player_predictions": len(player_records),
        "resolved_players": len(resolved_players),
        "pending_predictions": len([record for record in records if not record["outcome_recorded_at"]]),
        "brier_score": compute_brier_score(resolved_markets),
        "log_loss": compute_log_loss(resolved_markets),
        "hit_rate": compute_hit_rate(resolved_markets),
        "roi": compute_roi(resolved_markets),
        "max_drawdown": compute_max_drawdown(_sorted_bets(resolved_markets)),
        "average_edge": _average([record["edge"] for record in resolved_markets]),
        "average_confidence": _average([record["confidence"] for record in resolved_markets]),
        "calibration_curve": calibration_curve,
        "closing_line_value": build_clv_summary(records),
        "player_mean_absolute_error": compute_player_mae(resolved_players),
        "player_minutes_mae": compute_player_minutes_mae(resolved_players),
        "by_sport": by_sport,
        "recent_results": [_result_card(record) for record in records[:10]],
    }


def compute_brier_score(records: list[dict]) -> float | None:
    values = [
        (record["model_probability"] - record["actual_outcome"]) ** 2
        for record in records
        if record["model_probability"] is not None and record["actual_outcome"] is not None
    ]
    return round(mean(values), 4) if values else None


def compute_log_loss(records: list[dict]) -> float | None:
    values = []
    for record in records:
        if record["model_probability"] is None or record["actual_outcome"] is None:
            continue
        probability = min(max(record["model_probability"], 1e-6), 1 - 1e-6)
        outcome = 1.0 if record["actual_outcome"] >= 1 else 0.0
        values.append(-(outcome * math.log(probability) + (1 - outcome) * math.log(1 - probability)))
    return round(mean(values), 4) if values else None


def compute_hit_rate(records: list[dict]) -> float | None:
    graded = [
        1.0 if (record["actual_outcome"] or 0) >= 1 else 0.0
        for record in records
        if record["recommended_action"] in BET_ACTIONS and record["actual_outcome"] is not None
    ]
    return round(mean(graded), 4) if graded else None


def compute_roi(records: list[dict]) -> float | None:
    profits = [
        record["profit_units"]
        for record in records
        if record["recommended_action"] in BET_ACTIONS and record["profit_units"] is not None
    ]
    if not profits:
        return None
    return round(sum(profits) / len(profits), 4)


def compute_max_drawdown(bet_records: list[dict]) -> float | None:
    if not bet_records:
        return None
    peak = 0.0
    cumulative = 0.0
    drawdown = 0.0
    for record in bet_records:
        cumulative += record["profit_units"] or 0.0
        peak = max(peak, cumulative)
        drawdown = max(drawdown, peak - cumulative)
    return round(drawdown, 3)


def build_clv_summary(records: list[dict]) -> dict:
    tracked = [record for record in records if record.get("clv") is not None]

    def _stats(subset: list[dict]) -> dict:
        return {
            "samples": len(subset),
            "average_clv": _average([record["clv"] for record in subset]),
            "beat_close_rate": round(mean(1.0 if record["clv"] > 0 else 0.0 for record in subset), 4) if subset else None,
        }

    by_sport = {}
    for sport_key in sorted({record["sport_key"] for record in tracked if record["sport_key"]}):
        by_sport[sport_key] = _stats([record for record in tracked if record["sport_key"] == sport_key])
    by_market = {}
    for market in sorted({record.get("market") for record in tracked if record.get("market")}):
        by_market[market] = _stats([record for record in tracked if record.get("market") == market])
    return {**_stats(tracked), "by_sport": by_sport, "by_market": by_market}


def build_timeseries(records: list[dict], window: str = "30d", sport: str | None = None, rolling: int = 20) -> dict:
    if window not in TIMESERIES_WINDOWS:
        raise ValueError(f"window must be one of {', '.join(TIMESERIES_WINDOWS)}")
    if rolling < 1:
        raise ValueError("rolling must be positive")
    days = TIMESERIES_WINDOWS[window]
    cutoff = datetime.now(timezone.utc) - timedelta(days=days) if days else None
    selected = [
        record
        for record in records
        if record["actual_outcome"] is not None
        and (not sport or record["sport_key"] == sport)
        and (cutoff is None or _parse_time(record["created_at"]) >= cutoff)
    ]
    selected.sort(key=lambda record: record["created_at"])
    points = []
    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for index, record in enumerate(selected):
        is_bet = record["recommended_action"] in BET_ACTIONS and record["profit_units"] is not None
        if is_bet:
            cumulative += record["profit_units"]
            peak = max(peak, cumulative)
            max_drawdown = max(max_drawdown, peak - cumulative)
        trailing = selected[max(0, index - rolling + 1) : index + 1]
        points.append(
            {
                "index": index + 1,
                "created_at": record["created_at"],
                "prediction_id": record["prediction_id"],
                "sport_key": record["sport_key"],
                "is_bet": is_bet,
                "profit_units": record["profit_units"],
                "cumulative_profit": round(cumulative, 3),
                "drawdown": round(peak - cumulative, 3),
                "rolling_hit_rate": compute_hit_rate(trailing),
                "rolling_brier_score": compute_brier_score(trailing),
                "rolling_log_loss": compute_log_loss(trailing),
            }
        )
    return {
        "window": window,
        "sport": sport,
        "rolling": rolling,
        "points": points,
        "summary": {
            "graded": len(selected),
            "bets": len([point for point in points if point["is_bet"]]),
            "total_profit": round(cumulative, 3),
            "max_drawdown": round(max_drawdown, 3) if points else None,
            "hit_rate": compute_hit_rate(selected),
            "brier_score": compute_brier_score(selected),
            "log_loss": compute_log_loss(selected),
        },
    }


def build_breakdown(records: list[dict], by: str = "sport") -> dict:
    if by not in BREAKDOWN_DIMENSIONS:
        raise ValueError(f"by must be one of {', '.join(BREAKDOWN_DIMENSIONS)}")
    resolved = [record for record in records if record["actual_outcome"] is not None]
    groups: dict[str, list[dict]] = {}
    for record in resolved:
        groups.setdefault(_segment(record, by), []).append(record)
    order = _segment_order(by)
    segments = []
    for key in sorted(groups, key=lambda value: (order.index(value) if value in order else len(order), value)):
        subset = groups[key]
        bets = [record for record in subset if record["recommended_action"] in BET_ACTIONS and record["profit_units"] is not None]
        segments.append(
            {
                "segment": key,
                "graded": len(subset),
                "bets": len(bets),
                "hit_rate": compute_hit_rate(subset),
                "roi": compute_roi(subset),
                "total_profit": round(sum(record["profit_units"] for record in bets), 3) if bets else 0.0,
                "brier_score": compute_brier_score(subset),
                "average_edge": _average([record["edge"] for record in subset]),
                "average_clv": _average([record.get("clv") for record in subset]),
            }
        )
    return {"by": by, "segments": segments}


def edge_bucket(edge: float | None) -> str:
    if edge is None:
        return "unknown"
    if edge < 0:
        return "negative"
    if edge < 0.02:
        return "0-2%"
    if edge < 0.05:
        return "2-5%"
    if edge < 0.10:
        return "5-10%"
    return "10%+"


def confidence_band(confidence: float | None) -> str:
    if confidence is None:
        return "unknown"
    if confidence >= 0.75:
        return "High"
    if confidence >= 0.55:
        return "Moderate"
    return "Low"


def _segment(record: dict, by: str) -> str:
    if by == "sport":
        return record["sport_key"] or "unknown"
    if by == "market":
        return record.get("market") or record["entity_type"]
    if by == "confidence_band":
        return confidence_band(record["confidence"])
    if by == "edge_bucket":
        return edge_bucket(record["edge"])
    return record.get("model_version") or "unversioned"


def _segment_order(by: str) -> list[str]:
    if by == "edge_bucket":
        return ["negative", "0-2%", "2-5%", "5-10%", "10%+", "unknown"]
    if by == "confidence_band":
        return ["Low", "Moderate", "High", "unknown"]
    return []


def _sorted_bets(records: list[dict]) -> list[dict]:
    bets = [record for record in records if record["recommended_action"] in BET_ACTIONS and record["profit_units"] is not None]
    return sorted(bets, key=lambda record: record["created_at"])


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def compute_calibration_curve(records: list[dict], bins: int = 5) -> list[dict]:
    curve = []
    if not records:
        return curve
    for index in range(bins):
        lower = index / bins
        upper = (index + 1) / bins
        bucket = [
            record
            for record in records
            if record["model_probability"] is not None
            and lower <= record["model_probability"] < upper + (0.0001 if index == bins - 1 else 0)
        ]
        if not bucket:
            continue
        curve.append(
            {
                "range": f"{lower:.1f}-{upper:.1f}",
                "count": len(bucket),
                "predicted": round(mean(record["model_probability"] for record in bucket), 3),
                "actual": round(mean(record["actual_outcome"] for record in bucket if record["actual_outcome"] is not None), 3),
            }
        )
    return curve


def compute_player_mae(records: list[dict]) -> float | None:
    errors = []
    for record in records:
        if record["actual_points"] is None:
            continue
        predicted = ((record["payload"].get("predictions") or {}).get("expected_points"))
        if predicted is None:
            continue
        errors.append(abs(predicted - record["actual_points"]))
    return round(mean(errors), 3) if errors else None


def compute_player_minutes_mae(records: list[dict]) -> float | None:
    errors = []
    for record in records:
        if record["actual_minutes"] is None:
            continue
        predicted = ((record["payload"].get("predictions") or {}).get("expected_minutes"))
        if predicted is None:
            continue
        errors.append(abs(predicted - record["actual_minutes"]))
    return round(mean(errors), 3) if errors else None


def _average(values: list[float | None]) -> float | None:
    filtered = [value for value in values if value is not None]
    return round(mean(filtered), 4) if filtered else None


def _result_card(record: dict) -> dict:
    payload = record["payload"]
    return {
        "prediction_id": record["prediction_id"],
        "entity_type": record["entity_type"],
        "sport_key": record["sport_key"],
        "created_at": record["created_at"],
        "team": record["team"],
        "subject": payload.get("player_name") or payload.get("game_id"),
        "recommended_action": record["recommended_action"],
        "confidence": record["confidence"],
        "actual_outcome": record["actual_outcome"],
        "actual_points": record["actual_points"],
        "profit_units": record["profit_units"],
        "clv": record.get("clv"),
        "market": record.get("market"),
        "model_version": record.get("model_version"),
        "graded_by": record.get("graded_by"),
    }
