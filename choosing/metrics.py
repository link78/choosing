from __future__ import annotations

from statistics import mean


def build_backtest_summary(records: list[dict]) -> dict:
    game_records = [record for record in records if record["entity_type"] == "game"]
    resolved_games = [record for record in game_records if record["actual_outcome"] is not None]
    player_records = [record for record in records if record["entity_type"] == "player"]
    resolved_players = [
        record
        for record in player_records
        if record["actual_points"] is not None or record["actual_minutes"] is not None or record["actual_available"] is not None
    ]
    calibration_curve = compute_calibration_curve(resolved_games)
    by_sport = {}
    for sport_key in sorted({record["sport_key"] for record in resolved_games if record["sport_key"]}):
        sport_records = [record for record in resolved_games if record["sport_key"] == sport_key]
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
        "brier_score": compute_brier_score(resolved_games),
        "hit_rate": compute_hit_rate(resolved_games),
        "roi": compute_roi(resolved_games),
        "average_edge": _average([record["edge"] for record in resolved_games]),
        "average_confidence": _average([record["confidence"] for record in resolved_games]),
        "calibration_curve": calibration_curve,
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


def compute_hit_rate(records: list[dict]) -> float | None:
    graded = [
        1.0 if (record["recommended_action"] == "bet" and (record["actual_outcome"] or 0) >= 1) else 0.0
        for record in records
        if record["recommended_action"] == "bet" and record["actual_outcome"] is not None
    ]
    return round(mean(graded), 4) if graded else None


def compute_roi(records: list[dict]) -> float | None:
    profits = [
        record["profit_units"]
        for record in records
        if record["recommended_action"] == "bet" and record["profit_units"] is not None
    ]
    if not profits:
        return None
    return round(sum(profits) / len(profits), 4)


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
    }
