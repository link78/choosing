from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .catalog import SPORT_MODEL_PROFILES
from .storage import resolve_data_dir


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

        payload = {"updated_at": datetime.now(timezone.utc).isoformat(), "profiles": adapted}
        self.model_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return payload

    def load(self) -> dict:
        if not self.model_path.exists():
            return {"updated_at": None, "profiles": {}}
        return json.loads(self.model_path.read_text(encoding="utf-8"))

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
        if player_records:
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

        game_records = [record for record in records if record["entity_type"] == "game" and record["actual_outcome"] is not None]
        if game_records:
            actual_wins = _mean(game_records, lambda record: record["actual_outcome"])
            predicted_wins = _mean(game_records, lambda record: record["model_probability"])
            edge_bias = (actual_wins or 0.5) - (predicted_wins or 0.5)
            direction = 1 if edge_bias > 0 else -1
            profile["game"]["market_consensus"] = _nudge(profile["game"]["market_consensus"], _mean(game_records, lambda record: record["inputs"].get("market_consensus")), direction)
            profile["game"]["efficiency"] = _nudge(profile["game"]["efficiency"], _mean(game_records, lambda record: record["inputs"].get("pace")), direction)
            profile["game"]["injury_impact"] = _nudge(profile["game"]["injury_impact"], _mean(game_records, lambda record: 1 - (record["inputs"].get("injury_leverage") or 0.5)), -direction)

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
