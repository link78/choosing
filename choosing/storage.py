from __future__ import annotations

import csv
import io
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


EXTRA_PREDICTION_COLUMNS = {
    "model_version": "TEXT",
    "market": "TEXT",
    "bet_odds": "INTEGER",
    "closing_odds": "INTEGER",
    "clv": "REAL",
    "graded_by": "TEXT",
}

CSV_COLUMNS = [
    "prediction_id",
    "created_at",
    "entity_type",
    "sport_key",
    "subject",
    "team",
    "market",
    "model_version",
    "recommended_action",
    "confidence",
    "model_probability",
    "implied_probability",
    "edge",
    "bet_odds",
    "closing_odds",
    "clv",
    "actual_outcome",
    "actual_points",
    "actual_minutes",
    "profit_units",
    "graded_by",
    "outcome_recorded_at",
]


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
                CREATE TABLE IF NOT EXISTS odds_snapshots (
                    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    captured_at TEXT NOT NULL,
                    sport_key TEXT,
                    subject TEXT NOT NULL,
                    market TEXT NOT NULL,
                    odds INTEGER NOT NULL,
                    implied_probability REAL,
                    line REAL
                );
                CREATE INDEX IF NOT EXISTS idx_odds_snapshots_subject ON odds_snapshots(subject, market, captured_at);
                """
            )
            existing_columns = {row["name"] for row in connection.execute("PRAGMA table_info(predictions)").fetchall()}
            for column, column_type in EXTRA_PREDICTION_COLUMNS.items():
                if column not in existing_columns:
                    connection.execute(f"ALTER TABLE predictions ADD COLUMN {column} {column_type}")
            snapshot_columns = {row["name"] for row in connection.execute("PRAGMA table_info(odds_snapshots)").fetchall()}
            if "line" not in snapshot_columns:
                connection.execute("ALTER TABLE odds_snapshots ADD COLUMN line REAL")

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
        market = None
        bet_odds = None
        model_version = (payload.get("meta") or {}).get("model_version")

        if entity_type == "player":
            subject_id = payload.get("player_id")
            sport_key = (payload.get("sport") or {}).get("odds_api_key")
            confidence = (payload.get("predictions") or {}).get("prediction_confidence")
            prop = payload.get("prop_market") or {}
            if prop.get("line") is not None:
                market = prop.get("market") or "player_points"
                recommended_action = prop.get("recommended_action")
                model_probability = prop.get("model_probability")
                implied_probability = prop.get("implied_probability")
                edge = prop.get("edge")
                bet_odds = prop.get("bet_odds")
            else:
                market = "player_projection"
        elif entity_type == "game":
            subject_id = payload.get("game_id")
            sport_key = (payload.get("sport") or {}).get("odds_api_key")
            recommended_action = (payload.get("betting_edge") or {}).get("recommended_action")
            confidence = (payload.get("betting_edge") or {}).get("confidence")
            model_probability = (payload.get("team_prediction") or {}).get("win_probability")
            implied_probability = (payload.get("market_signals") or {}).get("implied_probability")
            edge = (payload.get("betting_edge") or {}).get("edge")
            market = "h2h"
            bet_odds = (payload.get("market_signals") or {}).get("current_odds")
        inputs = self._extract_inputs(entity_type, payload)

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO predictions (
                    prediction_id, created_at, entity_type, sport_key, subject_id, team,
                    recommended_action, confidence, model_probability, implied_probability, edge,
                    payload_json, inputs_json, model_version, market, bet_odds
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    model_version,
                    market,
                    bet_odds,
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
        closing_odds = _coerce_int(outcome.get("closing_odds"))
        if closing_odds == 0:
            raise ValueError("closing_odds cannot be zero")
        if closing_odds is None:
            closing_odds = record.get("closing_odds")
        graded_by = str(outcome.get("graded_by") or "manual")
        profit_units = None

        if entity_type == "game":
            if actual_outcome is None:
                raise ValueError("actual_outcome is required for game predictions")
            if actual_odds is None:
                actual_odds = (payload.get("market_signals") or {}).get("current_odds")
            recommended_action = (payload.get("betting_edge") or {}).get("recommended_action")
            profit_units = _profit_units(recommended_action, actual_outcome, actual_odds)
        elif entity_type == "player":
            prop = payload.get("prop_market") or {}
            if actual_points is not None and prop.get("line") is not None:
                side = prop.get("recommended_action")
                if side in {"over", "under"}:
                    won = actual_points > prop["line"] if side == "over" else actual_points < prop["line"]
                    push = actual_points == prop["line"]
                    actual_outcome = None if push else (1.0 if won else 0.0)
                    if actual_odds is None:
                        actual_odds = prop.get("bet_odds")
                    profit_units = 0.0 if push else _profit_units("bet", actual_outcome, actual_odds)
        clv = compute_clv(record.get("bet_odds"), closing_odds)

        with self._connect() as connection:
            connection.execute(
                """
                UPDATE predictions
                SET outcome_json = ?, actual_outcome = ?, actual_points = ?, actual_minutes = ?,
                    actual_available = ?, actual_odds = ?, profit_units = ?, outcome_recorded_at = ?,
                    closing_odds = ?, clv = ?, graded_by = ?
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
                    closing_odds,
                    clv,
                    graded_by,
                    prediction_id,
                ),
            )
        return self.get_prediction(prediction_id)

    def set_closing_odds(self, prediction_id: str, closing_odds: int) -> dict | None:
        record = self.get_prediction(prediction_id)
        if not record or not closing_odds:
            return record
        clv = compute_clv(record.get("bet_odds"), closing_odds)
        with self._connect() as connection:
            connection.execute(
                "UPDATE predictions SET closing_odds = ?, clv = ? WHERE prediction_id = ?",
                (int(closing_odds), clv, prediction_id),
            )
        return self.get_prediction(prediction_id)

    def count_predictions(self) -> dict:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN outcome_recorded_at IS NULL THEN 1 ELSE 0 END) AS pending,
                       SUM(CASE WHEN outcome_recorded_at IS NOT NULL THEN 1 ELSE 0 END) AS graded
                FROM predictions
                """
            ).fetchone()
        return {"total": row["total"] or 0, "pending": row["pending"] or 0, "graded": row["graded"] or 0}

    def append_odds_snapshot(
        self, sport_key: str | None, subject: str, market: str, odds: int, line: float | None = None
    ) -> None:
        if not odds:
            return
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO odds_snapshots (captured_at, sport_key, subject, market, odds, implied_probability, line)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    sport_key,
                    subject,
                    market,
                    int(odds),
                    round(american_to_probability(int(odds)), 4),
                    None if line is None else float(line),
                ),
            )

    def list_odds_snapshots(self, subject: str, market: str, limit: int = 50) -> list[dict]:
        """Opening snapshot followed by the most recent `limit` snapshots, oldest first."""
        columns = "snapshot_id, captured_at, sport_key, subject, market, odds, implied_probability, line"
        with self._connect() as connection:
            recent = connection.execute(
                f"""
                SELECT {columns} FROM odds_snapshots
                WHERE subject = ? AND market = ? ORDER BY captured_at DESC, snapshot_id DESC LIMIT ?
                """,
                (subject, market, limit),
            ).fetchall()
            opening = connection.execute(
                f"""
                SELECT {columns} FROM odds_snapshots
                WHERE subject = ? AND market = ? ORDER BY captured_at ASC, snapshot_id ASC LIMIT 1
                """,
                (subject, market),
            ).fetchone()
        rows = [dict(row) for row in reversed(recent)]
        if opening and (not rows or rows[0]["snapshot_id"] != opening["snapshot_id"]):
            rows.insert(0, dict(opening))
        for row in rows:
            row.pop("snapshot_id", None)
        return rows

    def export_csv(self, limit: int = 1000) -> str:
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for record in self.list_predictions(limit=limit):
            row = {key: record.get(key) for key in CSV_COLUMNS}
            row["subject"] = record["payload"].get("player_name") or record["payload"].get("game_id")
            writer.writerow({key: _csv_safe(value) for key, value in row.items()})
        return buffer.getvalue()

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
        pending_only: bool = False,
        created_before: str | None = None,
    ) -> list[dict]:
        where = []
        params: list[object] = []
        if resolved_only:
            where.append("outcome_recorded_at IS NOT NULL")
        if pending_only:
            where.append("outcome_recorded_at IS NULL")
        if created_before:
            where.append("created_at < ?")
            params.append(created_before)
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
            "model_version": row["model_version"],
            "market": row["market"],
            "bet_odds": row["bet_odds"],
            "closing_odds": row["closing_odds"],
            "clv": row["clv"],
            "graded_by": row["graded_by"],
        }

    def _extract_inputs(self, entity_type: str, payload: dict) -> dict:
        if entity_type == "player":
            profile = payload.get("player_profile") or {}
            return dict(profile.get("computation_data") or {})
        if entity_type == "game":
            return {
                **dict(payload.get("context_signals") or {}),
                **dict(payload.get("market_signals") or {}),
                "pace": (payload.get("team_prediction") or {}).get("pace"),
                "efficiency": (payload.get("team_prediction") or {}).get("efficiency"),
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


def american_to_probability(american_odds: int) -> float:
    if american_odds > 0:
        return 100 / (american_odds + 100)
    return abs(american_odds) / (abs(american_odds) + 100)


def compute_clv(bet_odds: int | None, closing_odds: int | None) -> float | None:
    """Closing line value in implied-probability points; positive means the bet beat the close."""
    if not bet_odds or not closing_odds:
        return None
    return round(american_to_probability(int(closing_odds)) - american_to_probability(int(bet_odds)), 4)


def _csv_safe(value):
    if isinstance(value, str) and value[:1] in {"=", "+", "-", "@"} and not _looks_numeric(value):
        return f"'{value}"
    return value


def _looks_numeric(value: str) -> bool:
    try:
        float(value)
        return True
    except ValueError:
        return False
