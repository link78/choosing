from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


def resolve_data_dir() -> Path:
    configured = os.environ.get("CHOOSING_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".choosing"


class PredictionStore:
    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = Path(data_dir) if data_dir is not None else resolve_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "history.sqlite3"
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS predictions (
                    prediction_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    sport_key TEXT,
                    subject_id TEXT,
                    team TEXT,
                    recommended_action TEXT,
                    confidence REAL,
                    model_probability REAL,
                    implied_probability REAL,
                    edge REAL,
                    payload_json TEXT NOT NULL,
                    inputs_json TEXT NOT NULL,
                    outcome_json TEXT,
                    actual_outcome REAL,
                    actual_points REAL,
                    actual_minutes REAL,
                    actual_available REAL,
                    actual_odds INTEGER,
                    profit_units REAL,
                    outcome_recorded_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_predictions_created_at ON predictions(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_predictions_entity ON predictions(entity_type, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_predictions_sport ON predictions(sport_key, created_at DESC);
                """
            )

    def append_prediction(self, entity_type: str, payload: dict) -> str:
        prediction_id = uuid.uuid4().hex
        created_at = datetime.now(timezone.utc).isoformat()
        sport_key = None
        subject_id = None
        team = payload.get("team")
        recommended_action = None
        confidence = None
        model_probability = None
        implied_probability = None
        edge = None

        if entity_type == "player":
            subject_id = payload.get("player_id")
            sport_key = (payload.get("sport") or {}).get("odds_api_key")
            confidence = (payload.get("predictions") or {}).get("prediction_confidence")
        elif entity_type == "game":
            subject_id = payload.get("game_id")
            sport_key = (payload.get("sport") or {}).get("odds_api_key")
            recommended_action = (payload.get("betting_edge") or {}).get("recommended_action")
            confidence = (payload.get("betting_edge") or {}).get("confidence")
            model_probability = (payload.get("team_prediction") or {}).get("win_probability")
            implied_probability = (payload.get("market_signals") or {}).get("implied_probability")
            edge = (payload.get("betting_edge") or {}).get("edge")
        inputs = self._extract_inputs(entity_type, payload)

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO predictions (
                    prediction_id, created_at, entity_type, sport_key, subject_id, team,
                    recommended_action, confidence, model_probability, implied_probability, edge,
                    payload_json, inputs_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    prediction_id,
                    created_at,
                    entity_type,
                    sport_key,
                    subject_id,
                    team,
                    recommended_action,
                    confidence,
                    model_probability,
                    implied_probability,
                    edge,
                    json.dumps(payload, sort_keys=True),
                    json.dumps(inputs, sort_keys=True),
                ),
            )
        return prediction_id

    def record_outcome(self, prediction_id: str, outcome: dict) -> dict | None:
        record = self.get_prediction(prediction_id)
        if not record:
            return None
        entity_type = record["entity_type"]
        payload = record["payload"]
        outcome_recorded_at = datetime.now(timezone.utc).isoformat()
        actual_outcome = _coerce_float(outcome.get("actual_outcome"))
        actual_points = _coerce_float(outcome.get("actual_points"))
        actual_minutes = _coerce_float(outcome.get("actual_minutes"))
        actual_available = _coerce_float(outcome.get("actual_available"))
        actual_odds = _coerce_int(outcome.get("actual_odds"))
        profit_units = None

        if entity_type == "game":
            if actual_outcome is None:
                raise ValueError("actual_outcome is required for game predictions")
            if actual_odds is None:
                actual_odds = (payload.get("market_signals") or {}).get("current_odds")
            recommended_action = (payload.get("betting_edge") or {}).get("recommended_action")
            profit_units = _profit_units(recommended_action, actual_outcome, actual_odds)

        with self._connect() as connection:
            connection.execute(
                """
                UPDATE predictions
                SET outcome_json = ?, actual_outcome = ?, actual_points = ?, actual_minutes = ?,
                    actual_available = ?, actual_odds = ?, profit_units = ?, outcome_recorded_at = ?
                WHERE prediction_id = ?
                """,
                (
                    json.dumps(outcome, sort_keys=True),
                    actual_outcome,
                    actual_points,
                    actual_minutes,
                    actual_available,
                    actual_odds,
                    profit_units,
                    outcome_recorded_at,
                    prediction_id,
                ),
            )
        return self.get_prediction(prediction_id)

    def get_prediction(self, prediction_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM predictions WHERE prediction_id = ?",
                (prediction_id,),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def list_predictions(
        self,
        limit: int = 100,
        resolved_only: bool = False,
        entity_type: str | None = None,
    ) -> list[dict]:
        where = []
        params: list[object] = []
        if resolved_only:
            where.append("outcome_recorded_at IS NOT NULL")
        if entity_type:
            where.append("entity_type = ?")
            params.append(entity_type)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM predictions {clause} ORDER BY created_at DESC LIMIT ?",
                params,
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def _row_to_dict(self, row: sqlite3.Row) -> dict:
        payload = json.loads(row["payload_json"])
        inputs = json.loads(row["inputs_json"])
        outcome = json.loads(row["outcome_json"]) if row["outcome_json"] else None
        return {
            "prediction_id": row["prediction_id"],
            "created_at": row["created_at"],
            "entity_type": row["entity_type"],
            "sport_key": row["sport_key"],
            "subject_id": row["subject_id"],
            "team": row["team"],
            "recommended_action": row["recommended_action"],
            "confidence": row["confidence"],
            "model_probability": row["model_probability"],
            "implied_probability": row["implied_probability"],
            "edge": row["edge"],
            "payload": payload,
            "inputs": inputs,
            "outcome": outcome,
            "actual_outcome": row["actual_outcome"],
            "actual_points": row["actual_points"],
            "actual_minutes": row["actual_minutes"],
            "actual_available": row["actual_available"],
            "actual_odds": row["actual_odds"],
            "profit_units": row["profit_units"],
            "outcome_recorded_at": row["outcome_recorded_at"],
        }

    def _extract_inputs(self, entity_type: str, payload: dict) -> dict:
        if entity_type == "player":
            profile = payload.get("player_profile") or {}
            return dict(profile.get("computation_data") or {})
        if entity_type == "game":
            return {
                **dict(payload.get("context_signals") or {}),
                **dict(payload.get("market_signals") or {}),
                **{
                    "confidence": (payload.get("betting_edge") or {}).get("confidence"),
                    "edge": (payload.get("betting_edge") or {}).get("edge"),
                },
            }
        return {}


def _coerce_float(value) -> float | None:
    if value in {None, ""}:
        return None
    return float(value)


def _coerce_int(value) -> int | None:
    if value in {None, ""}:
        return None
    return int(value)


def _profit_units(recommended_action: str | None, actual_outcome: float, american_odds: int | None) -> float:
    if recommended_action != "bet":
        return 0.0
    if american_odds in {None, 0}:
        american_odds = -110
    if actual_outcome >= 1:
        if american_odds > 0:
            return round(american_odds / 100, 3)
        return round(100 / abs(american_odds), 3)
    return -1.0
