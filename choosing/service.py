from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import quote

from .catalog import ODDS_API_ENDPOINTS, ODDS_API_SPORTS, resolve_player_sport, resolve_sport_model
from .data_sources import (
    FantasySportsAPIClient,
    MediaBroadcastClient,
    OddsAPIClient,
    SportsDataIOClient,
    WeatherClient,
    search_players,
    search_teams,
)
from .grading import OutcomeGrader
from .learner import WeightAdaptor
from .metrics import build_backtest_summary, build_breakdown, build_timeseries
from .prediction import (
    american_to_implied_probability,
    apply_probability_calibration,
    build_game_edge,
    build_player_prediction,
    build_prop_edge,
    clamp,
)
from .storage import PredictionStore

UPSTREAM_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="choosing-upstream")
HISTORY_LIMIT = 2000
LINE_MOVE_WARNING_THRESHOLD = 0.02
PLAYER_WEATHER_SENSITIVITY = 0.06
GAME_WEATHER_SENSITIVITY = 0.08


class PredictionService:
    def __init__(
        self,
        sports_client: SportsDataIOClient | None = None,
        odds_client: OddsAPIClient | None = None,
        media_client: MediaBroadcastClient | None = None,
        fantasy_client: FantasySportsAPIClient | None = None,
        store: PredictionStore | None = None,
        learner: WeightAdaptor | None = None,
        weather_client: WeatherClient | None = None,
    ) -> None:
        self.sports_client = sports_client or SportsDataIOClient()
        self.odds_client = odds_client or OddsAPIClient()
        self.media_client = media_client or MediaBroadcastClient()
        self.fantasy_client = fantasy_client or FantasySportsAPIClient()
        self.weather_client = weather_client or WeatherClient()
        self.store = store or PredictionStore()
        self.learner = learner or WeightAdaptor()
        self.grader = OutcomeGrader(self.store, self.sports_client, self.odds_client)

    def _meta(self, entity_id: str, entity_type: str) -> dict:
        return {
            "entity_id": entity_id,
            "entity_type": entity_type,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "advisory_only": True,
            "model_version": self.current_model_version(),
        }

    def current_model_version(self) -> str:
        return self.learner.load().get("model_version")

    def get_player_prediction(self, player_id: str, overrides: dict | None = None, persist: bool = True) -> dict:
        overrides = overrides or {}
        sports_future = UPSTREAM_EXECUTOR.submit(self.sports_client.fetch_player_context, player_id, overrides)
        media_future = UPSTREAM_EXECUTOR.submit(self.media_client.fetch_player_context, player_id, overrides)
        fantasy_future = UPSTREAM_EXECUTOR.submit(self.fantasy_client.fetch_player_context, player_id, overrides)
        sports_data = sports_future.result()
        media_data = media_future.result()
        fantasy_data = fantasy_future.result()
        player_inputs = dict(sports_data)
        player_inputs.update({key: value for key, value in media_data.items() if key != "source_mode"})
        player_inputs.update({key: value for key, value in fantasy_data.items() if key != "source_mode"})
        player_inputs["sport"] = resolve_player_sport(overrides.get("sport"))
        player_inputs["sport_profile"] = resolve_sport_model(player_inputs["sport"]["odds_api_key"])
        payload = build_player_prediction(sports_data["player_id"], player_inputs)
        sport_key = player_inputs["sport"]["odds_api_key"]
        weather = self.weather_client.fetch_venue_weather(sports_data["team"], sport_key, overrides)
        payload["weather"] = _apply_weather(payload["predictions"], "expected_points", "expected_points_range", weather, PLAYER_WEATHER_SENSITIVITY)
        payload["meta"] = self._meta(sports_data["player_id"], "player")
        payload["player_name"] = sports_data["player_name"]
        payload["team"] = sports_data["team"]
        payload["sport"] = dict(player_inputs["sport"])
        payload["injury_status"] = sports_data.get("injury_status", "Unknown")
        payload["player_profile"] = _build_player_profile(payload, player_inputs)
        suggestions = _build_player_suggestions(payload, player_inputs)
        payload["predictions"]["suggestions"] = suggestions
        payload["player_profile"]["suggestions"] = suggestions
        payload["player_profile"]["computation_data"]["suggestions"] = suggestions
        prop = self._resolve_player_prop(sports_data["player_name"], sports_data["team"], sport_key, overrides)
        if prop:
            payload["prop_market"] = build_prop_edge(
                payload["predictions"]["expected_points"],
                payload["predictions"]["expected_points_range"],
                prop,
                payload["predictions"]["confidence_band"],
            )
        payload["odds_api_catalog"] = _odds_api_catalog()
        payload["predictions"]["odds_api_endpoints"] = _odds_api_catalog()["endpoints"]
        payload["source_snapshots"] = {
            "sports_data_io": {
                "mode": sports_data.get("source_mode", "fallback"),
                "recent_form": round(sports_data["recent_form"], 3),
                "workload": round(sports_data["workload"], 3),
                "injury_risk": round(sports_data["injury_risk"], 3),
                "injury_status": sports_data.get("injury_status", "Unknown"),
                "availability": round(sports_data["availability"], 3),
                "recent_form_l3": round(sports_data["recent_form_l3"], 3),
                "recent_form_l5": round(sports_data["recent_form_l5"], 3),
                "recent_form_l10": round(sports_data["recent_form_l10"], 3),
                "rest_days": round(sports_data["rest_days"], 2),
                "usage_trend": round(sports_data["usage_trend"], 3),
                "source_confidence": round(sports_data["source_confidence"], 3),
                "data_freshness": round(sports_data["data_freshness"], 3),
                "projected_role": sports_data["projected_role"],
            },
            "media_broadcast": {
                "mode": media_data.get("source_mode", "fallback"),
                "media_sentiment": round(media_data["media_sentiment"], 3),
                "broadcast_exposure": round(media_data["broadcast_exposure"], 3),
                "narrative_pressure": round(media_data["narrative_pressure"], 3),
            },
            "fantasy_sports_api": {
                "mode": fantasy_data.get("source_mode", "fallback"),
                "fantasy_projection": round(fantasy_data["fantasy_projection"], 1),
                "fantasy_value_rating": round(fantasy_data["fantasy_value_rating"], 3),
                "ownership_projection": round(fantasy_data["ownership_projection"], 3),
            },
            "odds_api": {
                "mode": self.odds_client.source_status()["mode"],
                "endpoints": _odds_api_catalog()["endpoints"],
                "sports": _odds_api_catalog()["sports"],
            },
        }
        if persist:
            prediction_id = self.store.append_prediction("player", payload)
            payload["meta"]["prediction_id"] = prediction_id
        return payload

    def get_game_edge(
        self,
        game_id: str,
        sports_overrides: dict | None = None,
        odds_overrides: dict | None = None,
        persist: bool = True,
        sport: str | None = None,
        record_snapshot: bool | None = None,
    ) -> dict:
        sport_key = resolve_player_sport(sport)["odds_api_key"] if sport else self.odds_client.sport
        sports_future = UPSTREAM_EXECUTOR.submit(self.sports_client.fetch_game_context, game_id, sports_overrides)
        odds_future = UPSTREAM_EXECUTOR.submit(self.odds_client.fetch_game_market, game_id, odds_overrides, sport_key)
        media_future = UPSTREAM_EXECUTOR.submit(self.media_client.fetch_game_context, game_id, sports_overrides)
        fantasy_future = UPSTREAM_EXECUTOR.submit(self.fantasy_client.fetch_game_context, game_id, sports_overrides)
        sports_data = sports_future.result()
        odds_data = odds_future.result()
        media_data = media_future.result()
        fantasy_data = fantasy_future.result()
        game_inputs = dict(sports_data)
        game_inputs.update({key: value for key, value in media_data.items() if key != "source_mode"})
        game_inputs.update({key: value for key, value in fantasy_data.items() if key != "source_mode"})
        game_inputs["sport_profile"] = resolve_sport_model(sport_key)
        payload = build_game_edge(sports_data["game_id"], game_inputs, odds_data)
        apply_probability_calibration(payload, self.learner.calibrator_for(sport_key))
        payload["meta"] = self._meta(sports_data["game_id"], "game")
        payload["team"] = sports_data["team"]
        payload["opponent"] = sports_data["opponent"]
        payload["team_prediction"]["expected_points"] = round(
            payload["team_prediction"]["expected_points"] + sports_data["expected_points_adjustment"],
            1,
        )
        for bound in ("low", "mid", "high"):
            payload["team_prediction"]["expected_points_range"][bound] = round(
                payload["team_prediction"]["expected_points_range"][bound] + sports_data["expected_points_adjustment"],
                1,
            )
        payload["team_prediction"]["source_mode"] = sports_data.get("source_mode", "fallback")
        payload["market_signals"]["sharp_money_index"] = round(odds_data["sharp_money_index"], 3)
        payload["market_signals"]["steam_move"] = odds_data["steam_move"]
        payload["market_signals"]["closing_line_value"] = round(odds_data["closing_line_value"], 3)
        payload["market_signals"]["source_mode"] = odds_data.get("source_mode", "fallback")
        payload["source_snapshots"] = {
            "sports_data_io": {
                "mode": sports_data.get("source_mode", "fallback"),
                "team_form": round(sports_data["team_form"], 3),
                "pace": round(sports_data["pace"], 3),
                "efficiency": round(sports_data["efficiency"], 3),
                "injury_impact": round(sports_data["injury_impact"], 3),
            },
            "media_broadcast": {
                "mode": media_data.get("source_mode", "fallback"),
                "broadcast_heat": round(media_data["broadcast_heat"], 3),
                "audience_confidence": round(media_data["audience_confidence"], 3),
                "narrative_pressure": round(media_data["narrative_pressure"], 3),
            },
            "fantasy_sports_api": {
                "mode": fantasy_data.get("source_mode", "fallback"),
                "fantasy_market_support": round(fantasy_data["fantasy_market_support"], 3),
                "fantasy_points_total": round(fantasy_data["fantasy_points_total"], 1),
                "injury_leverage": round(fantasy_data["injury_leverage"], 3),
            },
            "odds_api": {
                "mode": odds_data.get("source_mode", "fallback"),
                "opening_odds": odds_data["opening_odds"],
                "current_odds": odds_data["current_odds"],
                "market_consensus": round(odds_data["market_consensus"], 3),
                "book_disagreement": round(odds_data["book_disagreement"], 3),
                "consensus_spread": round(odds_data["consensus_spread"], 3),
                "historical_closing_line_value": round(odds_data["historical_closing_line_value"], 3),
                "market_source_confidence": round(odds_data["market_source_confidence"], 3),
            },
        }
        payload["sport"] = resolve_player_sport(sport_key)
        weather = self.weather_client.fetch_venue_weather(sports_data["team"], sport_key, sports_overrides)
        payload["weather"] = _apply_weather(
            payload["team_prediction"], "expected_points", "expected_points_range", weather, GAME_WEATHER_SENSITIVITY
        )
        should_snapshot = persist if record_snapshot is None else record_snapshot
        if should_snapshot and odds_data.get("source_mode") == "live":
            self.store.append_odds_snapshot(sport_key, sports_data["team"], "h2h", payload["market_signals"]["current_odds"])
        payload["line_history"] = self._line_history(sports_data["team"], payload)
        if persist:
            prediction_id = self.store.append_prediction("game", payload)
            payload["meta"]["prediction_id"] = prediction_id
        return payload

    def _line_history(self, team: str, payload: dict) -> dict:
        snapshots = self.store.list_odds_snapshots(team, "h2h")
        current_odds = payload["market_signals"]["current_odds"]
        opening_odds = snapshots[0]["odds"] if snapshots else payload["market_signals"]["opening_odds"]
        implied_change = american_to_implied_probability(current_odds) - american_to_implied_probability(opening_odds)
        against_pick = payload["betting_edge"]["recommended_action"] == "bet" and implied_change <= -LINE_MOVE_WARNING_THRESHOLD
        return {
            "market": "h2h",
            "snapshots": len(snapshots),
            "opening_odds": opening_odds,
            "current_odds": current_odds,
            "implied_probability_change": round(implied_change, 4),
            "movement_against_pick": against_pick,
            "warning": (
                "Market has moved against the model's pick since the first snapshot; sharp money may disagree."
                if against_pick
                else None
            ),
            "history": [{"captured_at": entry["captured_at"], "odds": entry["odds"]} for entry in snapshots[-20:]],
        }

    def _resolve_player_prop(self, player_name: str, team: str, sport_key: str, overrides: dict) -> dict | None:
        if overrides.get("prop_line") is not None:
            return {
                "market": overrides.get("prop_market") or "player_points",
                "line": overrides["prop_line"],
                "over_odds": int(overrides.get("over_odds") or -110),
                "under_odds": int(overrides.get("under_odds") or -110),
                "source_mode": "override",
            }
        if not self.odds_client.api_key:
            return None
        return self.odds_client.fetch_player_prop(player_name, team, sport_key)

    def get_slate(
        self,
        sport: str | None = None,
        min_edge: float | None = None,
        min_confidence: float | None = None,
        limit: int = 10,
        record_snapshot: bool = False,
    ) -> dict:
        selected_sport = resolve_player_sport(sport) if sport else resolve_player_sport(self.odds_client.sport)
        sport_key = selected_sport["odds_api_key"]
        events = self.odds_client.fetch_events(sport_key)
        source_mode = "live" if events else "fallback"
        if not events:
            events = [
                {"event_id": None, "home_team": entry["team"], "away_team": entry["opponent"], "commence_time": None}
                for entry in search_teams()
            ]
        entries = []
        for event in events[:25]:
            sides = [event["home_team"], event["away_team"]] if source_mode == "live" else [event["home_team"]]
            best = None
            for side in sides:
                edge_payload = self.get_game_edge(side, persist=False, sport=sport_key, record_snapshot=record_snapshot)
                if best is None or edge_payload["betting_edge"]["edge"] > best["betting_edge"]["edge"]:
                    best = edge_payload
            betting_edge = best["betting_edge"]
            entries.append(
                {
                    "event_id": event["event_id"],
                    "commence_time": event["commence_time"],
                    "matchup": f"{event['away_team']} @ {event['home_team']}" if source_mode == "live" else f"{event['home_team']} vs {event['away_team']}",
                    "pick": best["team"],
                    "opponent": best["opponent"],
                    "win_probability": betting_edge["calibrated_probability"],
                    "implied_probability": best["market_signals"]["implied_probability"],
                    "current_odds": best["market_signals"]["current_odds"],
                    "edge": betting_edge["edge"],
                    "confidence": betting_edge["confidence"],
                    "recommended_action": betting_edge["recommended_action"],
                    "kelly": betting_edge["kelly"],
                    "feature_tracking": betting_edge["feature_tracking"],
                    "line_warning": best["line_history"]["warning"],
                    "game_edge_path": f"/game/{quote(best['team'], safe='')}/edge?sport={quote(sport_key, safe='')}",
                }
            )
        filtered = [
            entry
            for entry in entries
            if (min_edge is None or entry["edge"] >= min_edge) and (min_confidence is None or entry["confidence"] >= min_confidence)
        ]
        filtered.sort(key=lambda entry: (entry["edge"], entry["confidence"]), reverse=True)
        return {
            "sport": selected_sport,
            "source_mode": source_mode,
            "filters": {"min_edge": min_edge, "min_confidence": min_confidence, "limit": limit},
            "evaluated": len(entries),
            "games": filtered[:limit],
        }

    def search_players(self, query: str = "", team: str | None = None, sport: str | None = None) -> list[dict]:
        return search_players(query, team, sport)

    def search_teams(self, query: str = "") -> list[dict]:
        return search_teams(query)

    def get_top_players_summary(self, sport: str | None = None, limit: int = 10) -> dict:
        selected_sport = resolve_player_sport(sport)
        players = self.sports_client.fetch_top_players(selected_sport["odds_api_key"], limit)
        if not players:
            players = self.search_players(sport=selected_sport["odds_api_key"])
        if len(players) < limit:
            players.extend(_synthetic_players_for_sport(selected_sport, limit - len(players)))
        summaries = []
        for entry in players[:limit]:
            prediction = self.get_player_prediction(
                entry["name"],
                {
                    "team": entry.get("team"),
                    "sport": selected_sport["odds_api_key"],
                },
                persist=False,
            )
            summaries.append(
                {
                    "player_id": prediction["player_id"],
                    "player_name": prediction["player_name"],
                    "team": prediction["team"],
                    "sport": prediction["sport"],
                    "player_prediction_path": (
                        f"/player/{prediction['player_name'].replace(' ', '%20')}/prediction"
                        f"?team={prediction['team'].replace(' ', '%20')}"
                        f"&sport={selected_sport['odds_api_key']}"
                    ),
                    "expected_points": prediction["predictions"]["expected_points"],
                    "expected_performance": prediction["predictions"]["expected_performance"],
                    "injured": prediction["predictions"]["injured"],
                    "injured_label": prediction["predictions"]["injured_label"],
                    "scoring_outlook": prediction["predictions"]["scoring_outlook"],
                    "suggestions": prediction["predictions"]["suggestions"],
                    "prediction_confidence": prediction["predictions"]["prediction_confidence"],
                    "confidence_band": prediction["predictions"]["confidence_band"],
                    "expected_points_range": prediction["predictions"]["expected_points_range"],
                    "availability_probability": prediction["predictions"]["availability_probability"],
                    "underperformance_risk": prediction["predictions"]["underperformance_risk"],
                    "player_profile": prediction["player_profile"],
                }
            )
        summaries.sort(
            key=lambda item: (item["expected_performance"], item["expected_points"], item["availability_probability"]),
            reverse=True,
        )
        return {
            "sport": selected_sport,
            "top_players": summaries[:limit],
            "summary": {
                "requested_limit": limit,
                "returned": min(limit, len(summaries)),
                "ranking_basis": "expected_performance",
            },
        }

    def source_status(self) -> dict:
        return {
            "sports_data_io": self.sports_client.source_status(),
            "media_broadcast": self.media_client.source_status(),
            "fantasy_sports_api": self.fantasy_client.source_status(),
            "odds_api": self.odds_client.source_status(),
            "open_meteo": self.weather_client.source_status(),
        }

    def record_prediction_outcome(self, prediction_id: str, outcome: dict) -> dict | None:
        record = self.store.record_outcome(prediction_id, outcome)
        if not record:
            return None
        learned_models = self._retrain()
        return {
            "prediction": record,
            "backtest_summary": self.get_backtest_summary(),
            "learned_models": _learned_model_summary(learned_models),
        }

    def _retrain(self) -> dict:
        resolved_records = self.store.list_predictions(limit=HISTORY_LIMIT, resolved_only=True)
        return self.learner.retrain(resolved_records)

    def grade_outcomes(self, date: str | None = None) -> dict:
        result = self.grader.grade(date)
        if result["graded_count"]:
            result["learned_models"] = _learned_model_summary(self._retrain())
        return result

    def get_backtest_summary(self) -> dict:
        records = self.store.list_predictions(limit=HISTORY_LIMIT)
        summary = build_backtest_summary(records)
        counts = self.store.count_predictions()
        summary["total_predictions"] = counts["total"]
        summary["pending_predictions"] = counts["pending"]
        summary["graded_predictions"] = counts["graded"]
        summary["learned_models"] = _learned_model_summary(self.learner.load())
        summary["current_model_version"] = self.current_model_version()
        summary["model_versions"] = build_breakdown(records, "model_version")["segments"]
        return summary

    def get_backtest_timeseries(self, window: str = "30d", sport: str | None = None, rolling: int = 20) -> dict:
        return build_timeseries(self.store.list_predictions(limit=HISTORY_LIMIT, resolved_only=True), window, sport, rolling)

    def get_backtest_breakdown(self, by: str = "sport") -> dict:
        return build_breakdown(self.store.list_predictions(limit=HISTORY_LIMIT, resolved_only=True), by)

    def export_predictions_csv(self) -> str:
        return self.store.export_csv(limit=HISTORY_LIMIT)


def _learned_model_summary(learned_models: dict) -> dict:
    return {
        "updated_at": learned_models.get("updated_at"),
        "model_version": learned_models.get("model_version"),
        "sports": sorted(learned_models.get("profiles", {}).keys()),
        "calibration": {
            key: {"a": value.get("a"), "b": value.get("b"), "samples": value.get("samples")}
            for key, value in (learned_models.get("calibration") or {}).items()
        },
        "fit_methods": {
            key: value.get("fit_methods", {}) for key, value in (learned_models.get("profiles") or {}).items()
        },
    }


def _apply_weather(section: dict, value_key: str, range_key: str, weather: dict | None, sensitivity: float) -> dict | None:
    if not weather:
        return None
    impact = weather.get("weather_impact", 0.0) or 0.0
    factor = 1 - impact * sensitivity
    if impact:
        section[value_key] = round(section[value_key] * factor, 1)
        for bound in ("low", "mid", "high"):
            section[range_key][bound] = round(section[range_key][bound] * factor, 1)
    return {**weather, "scoring_factor": round(factor, 4)}


def _build_player_profile(prediction: dict, sports_data: dict) -> dict:
    expected_points = prediction["predictions"]["expected_points"]
    expected_minutes = prediction["predictions"]["expected_minutes"]
    availability_probability = prediction["predictions"]["availability_probability"]
    underperformance_risk = prediction["predictions"]["underperformance_risk"]
    prediction_confidence = prediction["predictions"]["prediction_confidence"]
    readiness_score = clamp(
        availability_probability * 0.4
        + prediction["player_signals"]["recent_form"] * 0.25
        + prediction["player_signals"]["team_context"] * 0.2
        + prediction["player_signals"]["consistency"] * 0.15,
        0,
        1,
    )
    scoring_index = clamp(expected_points / 35, 0, 1)
    if expected_points >= 26:
        scoring_band = "High-volume scorer"
    elif expected_points >= 18:
        scoring_band = "Reliable scorer"
    else:
        scoring_band = "Low-volume scorer"

    if underperformance_risk >= 0.55:
        risk_level = "High"
    elif underperformance_risk >= 0.35:
        risk_level = "Moderate"
    else:
        risk_level = "Low"

    return {
        "readiness_score": round(readiness_score, 3),
        "scoring_index": round(scoring_index, 3),
        "scoring_band": scoring_band,
        "risk_level": risk_level,
        "projected_role": sports_data.get("projected_role")
        or ("Featured scorer" if expected_minutes >= 32 or expected_points >= 24 else "Rotation scorer"),
        "sport": dict(sports_data.get("sport", resolve_player_sport())),
        "injury_status": sports_data.get("injury_status", "Unknown"),
        "injured": prediction["predictions"]["injured"],
        "injured_label": prediction["predictions"]["injured_label"],
        "prediction_confidence": round(prediction_confidence, 3),
        "confidence_band": prediction["predictions"]["confidence_band"],
        "availability_tier": prediction["predictions"]["availability_tier"],
        "feature_tracking": prediction["predictions"]["feature_tracking"],
        "odds_api_coverage": _odds_api_catalog(),
        "computation_data": {
            "recent_form": prediction["player_signals"]["recent_form"],
            "recent_form_l3": prediction["player_signals"]["recent_form_l3"],
            "recent_form_l5": prediction["player_signals"]["recent_form_l5"],
            "recent_form_l10": prediction["player_signals"]["recent_form_l10"],
            "effective_form": prediction["player_signals"]["effective_form"],
            "consistency": prediction["player_signals"]["consistency"],
            "team_context": prediction["player_signals"]["team_context"],
            "workload_fatigue": prediction["player_signals"]["workload_fatigue"],
            "matchup_difficulty": prediction["player_signals"]["matchup_difficulty"],
            "rest_days": prediction["player_signals"]["rest_days"],
            "usage_trend": prediction["player_signals"]["usage_trend"],
            "home_split": prediction["player_signals"]["home_split"],
            "away_split": prediction["player_signals"]["away_split"],
            "opponent_split": prediction["player_signals"]["opponent_split"],
            "source_confidence": prediction["player_signals"]["source_confidence"],
            "data_freshness": prediction["player_signals"]["data_freshness"],
            "teammate_absences": prediction["player_signals"]["teammate_absences"],
            "lineup_support": prediction["player_signals"]["lineup_support"],
            "injury_risk": prediction["player_signals"]["injury_risk"],
            "broadcast_exposure": prediction["media_broadcast_signals"]["broadcast_exposure"],
            "narrative_pressure": prediction["media_broadcast_signals"]["narrative_pressure"],
            "fantasy_projection": prediction["fantasy_sports_signals"]["fantasy_projection"],
            "fantasy_value_rating": prediction["fantasy_sports_signals"]["fantasy_value_rating"],
            "injury_status": sports_data.get("injury_status", "Unknown"),
            "injured": prediction["predictions"]["injured"],
            "injured_label": prediction["predictions"]["injured_label"],
            "injury_days_out": sports_data.get("injury_days_out", 0.0),
            "availability_probability": availability_probability,
            "availability_tier": prediction["predictions"]["availability_tier"],
            "expected_minutes": expected_minutes,
            "expected_minutes_range": prediction["predictions"]["expected_minutes_range"],
            "expected_points": expected_points,
            "expected_points_range": prediction["predictions"]["expected_points_range"],
            "expected_performance_range": prediction["predictions"]["expected_performance_range"],
            "prediction_confidence": prediction_confidence,
            "confidence_band": prediction["predictions"]["confidence_band"],
            "feature_tracking": prediction["predictions"]["feature_tracking"],
            "calibration": prediction["predictions"]["calibration"],
            "source_mode": sports_data.get("source_mode", "fallback"),
            "odds_api_endpoints": _odds_api_catalog()["endpoints"],
            "odds_api_sports": _odds_api_catalog()["sports"],
        },
    }


def _odds_api_catalog() -> dict:
    return {
        "provider": "The Odds API",
        "endpoints": [dict(entry) for entry in ODDS_API_ENDPOINTS],
        "sports": [dict(entry) for entry in ODDS_API_SPORTS],
    }


def _build_player_suggestions(prediction: dict, sports_data: dict) -> list[str]:
    sport_key = sports_data.get("sport", {}).get("odds_api_key", "basketball_nba")
    availability = prediction["predictions"]["availability_probability"]
    underperformance_risk = prediction["predictions"]["underperformance_risk"]
    recent_form = prediction["player_signals"]["recent_form"]
    consistency = prediction["player_signals"]["consistency"]
    workload = prediction["player_signals"]["workload_fatigue"]
    injured = prediction["predictions"]["injured"]

    suggestions = []
    if injured:
        suggestions.append("Lower stake size or avoid aggressive overs until the injury flag turns back to No.")
    else:
        suggestions.append("Prioritize this player when injury is No and availability stays above the market average.")

    if sport_key == "basketball_nba":
        suggestions.append("NBA: favor points or combo props when recent form is strong and workload fatigue stays under control.")
    elif sport_key == "baseball_mlb":
        suggestions.append("MLB: look for hitter props when consistency is stable and avoid chasing lines during cold streaks.")
    elif sport_key == "americanfootball_nfl":
        suggestions.append("NFL: match the player role to the prop type, backing volume-based markets only when availability is strong.")
    elif sport_key == "icehockey_nhl":
        suggestions.append("NHL: lean toward shots or points markets when recent form is rising and underperformance risk is low.")
    else:
        suggestions.append("Use the selected sport context to compare recent form, role, and line movement before placing a bet.")

    if recent_form >= 0.75 and consistency >= 0.65:
        suggestions.append("Strong recent form plus solid consistency supports backing performance-related overs.")
    elif underperformance_risk >= 0.5 or workload >= 0.75:
        suggestions.append("High risk or fatigue suggests waiting for a better number or shifting to safer alternate lines.")
    else:
        suggestions.append("Balanced form and risk profile favor selective betting only when the implied odds still leave clear edge.")
    return suggestions


def _synthetic_players_for_sport(sport: dict, count: int) -> list[dict]:
    synthetic = []
    for index in range(count):
        synthetic.append(
            {
                "id": f"{sport['odds_api_key']}-{index + 1}",
                "name": f"{sport['league']} Featured Player {index + 1}",
                "team": f"{sport['league']} Select",
                "sport_key": sport["odds_api_key"],
            }
        )
    return synthetic
