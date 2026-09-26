from __future__ import annotations

TENNIS_SURFACES = ("hard", "clay", "grass")
DEFAULT_SURFACE = "hard"
ELO_BASE_RATING = 1500.0
ELO_K_FACTOR = 32.0
SURFACE_WEIGHT = 0.5
ELO_BLEND_MAX = 0.5
ELO_BLEND_FULL_MATCHES = 20


def is_tennis(sport_key: str | None) -> bool:
    return (sport_key or "").lower().startswith("tennis")


def normalize_surface(raw_value: str | None) -> str | None:
    value = (raw_value or "").strip().lower()
    if not value:
        return None
    if value not in TENNIS_SURFACES:
        raise ValueError(f"surface must be one of {', '.join(TENNIS_SURFACES)}")
    return value


def infer_surface(sport_key: str | None) -> str:
    key = (sport_key or "").lower()
    if "french_open" in key or "clay" in key:
        return "clay"
    if "wimbledon" in key or "grass" in key:
        return "grass"
    return DEFAULT_SURFACE


def elo_expected(rating: float, opponent_rating: float) -> float:
    return 1 / (1 + 10 ** ((opponent_rating - rating) / 400))


def _key(name: str) -> str:
    return " ".join((name or "").lower().split())


class SurfaceElo:
    """Overall + surface-specific Elo ratings rebuilt from graded tennis results."""

    def __init__(self, k_factor: float = ELO_K_FACTOR) -> None:
        self.k_factor = k_factor
        self.overall: dict[str, float] = {}
        self.surface: dict[tuple[str, str], float] = {}
        self.matches: dict[str, int] = {}
        self.surface_matches: dict[tuple[str, str], int] = {}

    def rating(self, player: str, surface: str) -> float:
        key = _key(player)
        overall = self.overall.get(key, ELO_BASE_RATING)
        surface_rating = self.surface.get((key, surface), overall)
        return (1 - SURFACE_WEIGHT) * overall + SURFACE_WEIGHT * surface_rating

    def update(self, player: str, opponent: str, surface: str, player_won: bool) -> None:
        player_key, opponent_key = _key(player), _key(opponent)
        if not player_key or not opponent_key or player_key == opponent_key:
            return
        score = 1.0 if player_won else 0.0
        overall_expected = elo_expected(
            self.overall.get(player_key, ELO_BASE_RATING), self.overall.get(opponent_key, ELO_BASE_RATING)
        )
        surface_expected = elo_expected(
            self.surface.get((player_key, surface), self.overall.get(player_key, ELO_BASE_RATING)),
            self.surface.get((opponent_key, surface), self.overall.get(opponent_key, ELO_BASE_RATING)),
        )
        for key, sign in ((player_key, 1), (opponent_key, -1)):
            base = self.overall.get(key, ELO_BASE_RATING)
            surface_base = self.surface.get((key, surface), base)
            self.overall[key] = base + sign * self.k_factor * (score - overall_expected)
            self.surface[(key, surface)] = surface_base + sign * self.k_factor * (score - surface_expected)
            self.matches[key] = self.matches.get(key, 0) + 1
            self.surface_matches[(key, surface)] = self.surface_matches.get((key, surface), 0) + 1

    def predict(self, player: str, opponent: str, surface: str) -> dict:
        player_rating = self.rating(player, surface)
        opponent_rating = self.rating(opponent, surface)
        player_matches = self.matches.get(_key(player), 0)
        opponent_matches = self.matches.get(_key(opponent), 0)
        sample = min(player_matches, opponent_matches)
        blend = ELO_BLEND_MAX * min(sample / ELO_BLEND_FULL_MATCHES, 1.0)
        return {
            "surface": surface,
            "player_rating": round(player_rating, 1),
            "opponent_rating": round(opponent_rating, 1),
            "player_matches": player_matches,
            "opponent_matches": opponent_matches,
            "player_surface_matches": self.surface_matches.get((_key(player), surface), 0),
            "opponent_surface_matches": self.surface_matches.get((_key(opponent), surface), 0),
            "elo_probability": round(elo_expected(player_rating, opponent_rating), 4),
            "blend_weight": round(blend, 3),
        }


def build_surface_elo(records: list[dict]) -> SurfaceElo:
    """Replay graded tennis predictions oldest-first; each record is (team vs opponent) with a 0/1 outcome.

    Predictions for the same pairing, surface and day count as one match so both sides are not double counted.
    """
    elo = SurfaceElo()
    seen: set[tuple[str, str, str, str]] = set()
    for record in sorted(records, key=lambda item: item.get("created_at") or ""):
        if not is_tennis(record.get("sport_key")) or record.get("entity_type") != "game":
            continue
        outcome = record.get("actual_outcome")
        if outcome not in (0, 1, 0.0, 1.0):
            continue
        payload = record.get("payload") or {}
        player = record.get("team") or payload.get("team") or ""
        opponent = payload.get("opponent") or ""
        surface = (payload.get("tennis_elo") or {}).get("surface") or infer_surface(record.get("sport_key"))
        match_key = tuple(sorted((_key(player), _key(opponent)))) + (surface, (record.get("created_at") or "")[:10])
        if match_key in seen:
            continue
        seen.add(match_key)
        elo.update(player, opponent, surface, bool(outcome))
    return elo
