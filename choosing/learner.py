from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from .catalog import SPORT_MODEL_PROFILES
from .prediction import MODEL_VERSION
from .storage import resolve_data_dir

MIN_PLATT_SAMPLES = 30
MIN_RIDGE_SAMPLES = 8
RIDGE_LAMBDA = 1.0
MAX_WEIGHT_ADJUSTMENT = 0.2

PLAYER_FEATURE_WEIGHTS = {
    "effective_form": ("points", "recent_form"),
    "usage_trend": ("points", "usage_trend"),
    "consistency": ("performance", "consistency"),
    "lineup_support": ("minutes", "lineup_support"),
}
GAME_FEATURE_WEIGHTS = {
    "market_consensus": ("game", "market_consensus"),
    "pace": ("game", "efficiency"),
    "injury_leverage": ("game", "injury_impact"),
}


class WeightAdaptor:
    def __init__(self, model_path: Path | None = None) -> None:
        data_dir = resolve_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        self.model_path = Path(model_path) if model_path is not None else data_dir / "adapted_models.json"

    def retrain(self, records: list[dict]) -> dict:
        resolved = [record for record in records if record.get("outcome_recorded_at")]
        grouped: dict[str, list[dict]] = {}
        for record in resolved:
            if not record.get("sport_key"):
                continue
            grouped.setdefault(record["sport_key"], []).append(record)

        adapted = {}
        for sport_key, sport_records in grouped.items():
            base = SPORT_MODEL_PROFILES.get(sport_key)
            if not base:
                continue
            adapted[sport_key] = self._adapt_profile(base, sport_records)
            adapted[sport_key]["sample_size"] = len(sport_records)

        calibration = {}
        game_records = [
            record
            for record in resolved
            if record["entity_type"] == "game" and record["model_probability"] is not None and record["actual_outcome"] is not None
        ]
        global_calibrator = fit_platt_scaling(
            [record["model_probability"] for record in game_records],
            [record["actual_outcome"] for record in game_records],
        )
        if global_calibrator:
            calibration["global"] = global_calibrator
        for sport_key in sorted({record["sport_key"] for record in game_records if record["sport_key"]}):
            sport_games = [record for record in game_records if record["sport_key"] == sport_key]
            sport_calibrator = fit_platt_scaling(
                [record["model_probability"] for record in sport_games],
                [record["actual_outcome"] for record in sport_games],
            )
            if sport_calibrator:
                calibration[sport_key] = sport_calibrator

        updated_at = datetime.now(timezone.utc).isoformat()
        payload = {
            "updated_at": updated_at,
            "model_version": build_model_version(updated_at),
            "profiles": adapted,
            "calibration": calibration,
        }
        self.model_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return payload

    def load(self) -> dict:
        if not self.model_path.exists():
            return {"updated_at": None, "model_version": build_model_version(None), "profiles": {}, "calibration": {}}
        payload = json.loads(self.model_path.read_text(encoding="utf-8"))
        payload.setdefault("calibration", {})
        payload.setdefault("model_version", build_model_version(payload.get("updated_at")))
        return payload

    def calibrator_for(self, sport_key: str | None) -> dict | None:
        calibration = self.load().get("calibration", {})
        return calibration.get(sport_key or "") or calibration.get("global")

    def _adapt_profile(self, base: dict, records: list[dict]) -> dict:
        profile = {
            "form_weights": dict(base["form_weights"]),
            "minutes": dict(base["minutes"]),
            "performance": dict(base["performance"]),
            "points": dict(base["points"]),
            "risk": dict(base["risk"]),
            "game": dict(base["game"]),
        }

        player_records = [record for record in records if record["entity_type"] == "player" and record["actual_points"] is not None]
        fit_methods = {}
        if len(player_records) >= MIN_RIDGE_SAMPLES:
            residuals = [
                record["actual_points"] - ((record["payload"].get("predictions") or {}).get("expected_points") or 0.0)
                for record in player_records
            ]
            scale = max(
                _mean(player_records, lambda record: (record["payload"].get("predictions") or {}).get("expected_points")) or 1.0,
                1.0,
            )
            _apply_ridge_adjustments(profile, player_records, residuals, PLAYER_FEATURE_WEIGHTS, scale)
            fit_methods["player"] = "ridge_regression"
        elif player_records:
            feature_scores = {
                "effective_form": _mean(player_records, lambda record: record["inputs"].get("effective_form")),
                "consistency": _mean(player_records, lambda record: record["inputs"].get("consistency")),
                "usage_trend": _mean(player_records, lambda record: record["inputs"].get("usage_trend")),
                "lineup_support": _mean(player_records, lambda record: record["inputs"].get("lineup_support")),
            }
            positive_bias = _mean(
                player_records,
                lambda record: record["actual_points"] - ((record["payload"].get("predictions") or {}).get("expected_points") or 0.0),
            )
            direction = 1 if positive_bias and positive_bias > 0 else -1
            profile["points"]["recent_form"] = _nudge(profile["points"]["recent_form"], feature_scores["effective_form"], direction)
            profile["points"]["usage_trend"] = _nudge(profile["points"]["usage_trend"], abs(feature_scores["usage_trend"] or 0), direction)
            profile["performance"]["consistency"] = _nudge(profile["performance"]["consistency"], feature_scores["consistency"], direction)
            profile["minutes"]["lineup_support"] = _nudge(profile["minutes"]["lineup_support"], feature_scores["lineup_support"], direction)
            fit_methods["player"] = "nudge"

        game_records = [
            record
            for record in records
            if record["entity_type"] == "game" and record["actual_outcome"] is not None and record["model_probability"] is not None
        ]
        if len(game_records) >= MIN_RIDGE_SAMPLES:
            residuals = [record["actual_outcome"] - record["model_probability"] for record in game_records]
            _apply_ridge_adjustments(profile, game_records, residuals, GAME_FEATURE_WEIGHTS, 1.0)
            fit_methods["game"] = "ridge_regression"
        elif game_records:
            actual_wins = _mean(game_records, lambda record: record["actual_outcome"])
            predicted_wins = _mean(game_records, lambda record: record["model_probability"])
            edge_bias = (actual_wins or 0.5) - (predicted_wins or 0.5)
            direction = 1 if edge_bias > 0 else -1
            profile["game"]["market_consensus"] = _nudge(profile["game"]["market_consensus"], _mean(game_records, lambda record: record["inputs"].get("market_consensus")), direction)
            profile["game"]["efficiency"] = _nudge(profile["game"]["efficiency"], _mean(game_records, lambda record: record["inputs"].get("pace")), direction)
            profile["game"]["injury_impact"] = _nudge(profile["game"]["injury_impact"], _mean(game_records, lambda record: 1 - (record["inputs"].get("injury_leverage") or 0.5)), -direction)
            fit_methods["game"] = "nudge"
        profile["fit_methods"] = fit_methods

        return profile


def _mean(records: list[dict], getter) -> float | None:
    values = [getter(record) for record in records]
    values = [value for value in values if value is not None]
    if not values:
        return None
    return sum(values) / len(values)


def _nudge(current: float, signal: float | None, direction: int) -> float:
    if signal is None:
        return current
    adjustment = (signal - 0.5) * 0.2 * direction
    return round(current * (1 + max(min(adjustment, 0.2), -0.2)), 4)


def build_model_version(updated_at: str | None) -> str:
    if not updated_at:
        return f"{MODEL_VERSION}+base"
    return f"{MODEL_VERSION}+{hashlib.sha256(updated_at.encode('utf-8')).hexdigest()[:8]}"


def fit_platt_scaling(probabilities: list[float], outcomes: list[float], iterations: int = 50, l2: float = 2.0) -> dict | None:
    """Fit p' = sigmoid(a * logit(p) + b) with Newton's method and light L2 regularisation."""
    pairs = [
        (math.log(min(max(p, 1e-4), 1 - 1e-4) / (1 - min(max(p, 1e-4), 1 - 1e-4))), 1.0 if y >= 1 else 0.0)
        for p, y in zip(probabilities, outcomes)
        if p is not None and y is not None and y != 0.5
    ]
    if len(pairs) < MIN_PLATT_SAMPLES or len({y for _, y in pairs}) < 2:
        return None
    a, b = 1.0, 0.0
    for _ in range(iterations):
        grad_a = l2 * (a - 1.0)
        grad_b = l2 * b
        h_aa = l2
        h_ab = 0.0
        h_bb = l2
        for x, y in pairs:
            prediction = 1 / (1 + math.exp(-(a * x + b)))
            error = prediction - y
            weight = prediction * (1 - prediction)
            grad_a += error * x
            grad_b += error
            h_aa += weight * x * x
            h_ab += weight * x
            h_bb += weight
        determinant = h_aa * h_bb - h_ab * h_ab
        if abs(determinant) < 1e-12:
            break
        step_a = (h_bb * grad_a - h_ab * grad_b) / determinant
        step_b = (h_aa * grad_b - h_ab * grad_a) / determinant
        a -= step_a
        b -= step_b
        if abs(step_a) < 1e-6 and abs(step_b) < 1e-6:
            break
    a = max(min(a, 5.0), 0.05)
    b = max(min(b, 3.0), -3.0)
    return {"method": "platt_scaling", "a": round(a, 6), "b": round(b, 6), "samples": len(pairs)}


def ridge_regression(rows: list[list[float]], targets: list[float], alpha: float = RIDGE_LAMBDA) -> list[float]:
    """Closed-form ridge regression on centred features (no intercept penalty)."""
    if not rows:
        return []
    feature_count = len(rows[0])
    means = [sum(row[index] for row in rows) / len(rows) for index in range(feature_count)]
    target_mean = sum(targets) / len(targets)
    centred = [[row[index] - means[index] for index in range(feature_count)] for row in rows]
    centred_targets = [target - target_mean for target in targets]
    matrix = [
        [sum(row[i] * row[j] for row in centred) + (alpha if i == j else 0.0) for j in range(feature_count)]
        for i in range(feature_count)
    ]
    vector = [sum(row[i] * target for row, target in zip(centred, centred_targets)) for i in range(feature_count)]
    return _solve_linear_system(matrix, vector)


def _solve_linear_system(matrix: list[list[float]], vector: list[float]) -> list[float]:
    size = len(vector)
    augmented = [list(matrix[index]) + [vector[index]] for index in range(size)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-12:
            return [0.0] * size
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column] / augmented[column][column]
            for index in range(column, size + 1):
                augmented[row][index] -= factor * augmented[column][index]
    return [augmented[index][size] / augmented[index][index] for index in range(size)]


def _apply_ridge_adjustments(profile: dict, records: list[dict], residuals: list[float], feature_map: dict, scale: float) -> None:
    features = list(feature_map)
    rows = []
    targets = []
    for record, residual in zip(records, residuals):
        values = [record["inputs"].get(feature) for feature in features]
        if any(value is None for value in values):
            continue
        rows.append([float(value) for value in values])
        targets.append(residual)
    if len(rows) < MIN_RIDGE_SAMPLES:
        return
    coefficients = ridge_regression(rows, targets)
    for feature, coefficient in zip(features, coefficients):
        section, weight_name = feature_map[feature]
        if weight_name not in profile[section]:
            continue
        adjustment = max(min(coefficient / scale, MAX_WEIGHT_ADJUSTMENT), -MAX_WEIGHT_ADJUSTMENT)
        profile[section][weight_name] = round(profile[section][weight_name] * (1 + adjustment), 4)
