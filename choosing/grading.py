from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .data_sources import OddsAPIClient, SportsDataIOClient, _normalize, _parse_iso_datetime, _team_matches
from .storage import PredictionStore

MAX_PENDING_SCAN = 500


def parse_grade_date(raw_value: str | None) -> str | None:
    if raw_value in {None, ""}:
        return None
    try:
        return datetime.strptime(raw_value, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("date must use YYYY-MM-DD") from exc


class OutcomeGrader:
    """Grades pending predictions from upstream final scores and box scores."""

    def __init__(self, store: PredictionStore, sports_client: SportsDataIOClient, odds_client: OddsAPIClient) -> None:
        self.store = store
        self.sports_client = sports_client
        self.odds_client = odds_client

    def grade(self, date: str | None = None) -> dict:
        date = parse_grade_date(date)
        pending = self.store.list_predictions(limit=MAX_PENDING_SCAN, pending_only=True)
        if date:
            cutoff = (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=1)).replace(tzinfo=timezone.utc)
            pending = [record for record in pending if _record_time(record) < cutoff]
        games = [record for record in pending if record["entity_type"] == "game"]
        players = [record for record in pending if record["entity_type"] == "player"]
        skipped: dict[str, int] = {}
        graded = []

        score_cache: dict[str, list[dict]] = {}
        for record in games:
            sport_key = record["sport_key"] or self.odds_client.sport
            if sport_key not in score_cache:
                score_cache[sport_key] = self._load_scores(sport_key, date)
            result = _match_game(record, score_cache[sport_key], date)
            if not result:
                _bump(skipped, "game_result_not_found")
                continue
            team = record["team"] or record["payload"].get("team") or ""
            team_score, opponent_score = result["team_score"], result["opponent_score"]
            if team_score == opponent_score:
                _bump(skipped, "game_tied")
                continue
            outcome = {
                "actual_outcome": 1 if team_score > opponent_score else 0,
                "graded_by": f"auto:{result['source']}",
                "final_score": f"{team_score:g}-{opponent_score:g}",
            }
            closing_odds = self.odds_client.fetch_closing_odds(team, result.get("commence_time"), sport_key)
            if closing_odds:
                outcome["closing_odds"] = closing_odds
            self.store.record_outcome(record["prediction_id"], outcome)
            graded.append({"prediction_id": record["prediction_id"], "entity_type": "game", **outcome})

        stat_cache: dict[tuple[str, str], list[dict]] = {}
        for record in players:
            sport_key = record["sport_key"] or "basketball_nba"
            candidate_dates = [date] if date else _candidate_dates(record)
            line = None
            for candidate_date in candidate_dates:
                cache_key = (sport_key, candidate_date)
                if cache_key not in stat_cache:
                    stat_cache[cache_key] = self.sports_client.fetch_player_game_stats_by_date(candidate_date, sport_key)
                line = _match_player(record, stat_cache[cache_key])
                if line:
                    break
            if not line:
                _bump(skipped, "player_stats_not_found")
                continue
            outcome = {
                "actual_points": line["points"],
                "actual_minutes": line["minutes"],
                "actual_available": 1 if line["played"] else 0,
                "graded_by": "auto:sportsdataio",
            }
            self.store.record_outcome(record["prediction_id"], outcome)
            graded.append({"prediction_id": record["prediction_id"], "entity_type": "player", **outcome})

        counts = self.store.count_predictions()
        return {
            "date": date,
            "checked": len(pending),
            "graded_count": len(graded),
            "graded": graded,
            "skipped": skipped,
            "pending": counts["pending"],
            "total_graded": counts["graded"],
            "sources": {
                "the_odds_api": self.odds_client.source_status()["mode"],
                "sports_data_io": self.sports_client.source_status()["mode"],
            },
        }

    def _load_scores(self, sport_key: str, date: str | None) -> list[dict]:
        scores = [entry for entry in self.odds_client.fetch_scores(sport_key, days_from=3) if entry["completed"]]
        if date:
            scores.extend(entry for entry in self.sports_client.fetch_scores_by_date(date, sport_key) if entry["completed"])
        return scores


def _record_time(record: dict) -> datetime:
    parsed = _parse_iso_datetime(record["created_at"])
    return parsed or datetime.now(timezone.utc)


def _candidate_dates(record: dict) -> list[str]:
    created = _record_time(record)
    today = datetime.now(timezone.utc).date()
    dates = []
    for offset in range(0, 2):
        candidate = created.date() + timedelta(days=offset)
        if candidate <= today:
            dates.append(candidate.strftime("%Y-%m-%d"))
    return dates


def _match_game(record: dict, scores: list[dict], date: str | None) -> dict | None:
    team = record["team"] or record["payload"].get("team") or ""
    created = _record_time(record)
    for entry in scores:
        commence = _parse_iso_datetime(entry.get("commence_time"))
        if commence and commence < created - timedelta(hours=6):
            continue
        if date and commence and commence.strftime("%Y-%m-%d") != date:
            continue
        if _team_matches(team, entry["home_team"]):
            return {**entry, "team_score": entry["home_score"], "opponent_score": entry["away_score"]}
        if _team_matches(team, entry["away_team"]):
            return {**entry, "team_score": entry["away_score"], "opponent_score": entry["home_score"]}
    return None


def _match_player(record: dict, lines: list[dict]) -> dict | None:
    subject_id = str(record["subject_id"] or "")
    name = _normalize(record["payload"].get("player_name") or "")
    for line in lines:
        if line["points"] is None:
            continue
        if name:
            if _normalize(line["name"]) == name:
                return line
        elif subject_id and line["player_id"] == subject_id:
            return line
    return None


def _bump(counter: dict[str, int], key: str) -> None:
    counter[key] = counter.get(key, 0) + 1
