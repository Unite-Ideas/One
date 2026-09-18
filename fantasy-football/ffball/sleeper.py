"""Sleeper API client (free, no auth).

Docs: https://docs.sleeper.com/  — read-only endpoints, no API key required.

Everything returns plain Python dicts/lists straight from the API. Higher layers
(projections, valuation) normalize into our own models.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .http import get_json, get_json_cached

BASE = "https://api.sleeper.app/v1"

# Positions we care about for fantasy value.
FANTASY_POSITIONS = {"QB", "RB", "WR", "TE", "K", "DEF"}


class Sleeper:
    """Thin wrapper over the Sleeper read API."""

    def __init__(self, base: str = BASE):
        self.base = base.rstrip("/")

    # ---- global / players -------------------------------------------------
    def state(self, sport: str = "nfl") -> Dict[str, Any]:
        """Current season/week info, e.g. {'season': '2025', 'week': 1, ...}."""
        return get_json(f"{self.base}/state/{sport}")

    def players(self, sport: str = "nfl", ttl_seconds: int = 86_400) -> Dict[str, Any]:
        """The full player master map keyed by player_id (~5MB). Cached daily.

        This is the single heaviest call in the whole system; Sleeper explicitly
        asks that you fetch it at most once per day, which the cache enforces.
        """
        return get_json_cached(
            f"{self.base}/players/{sport}",
            cache_key=f"players_{sport}",
            ttl_seconds=ttl_seconds,
        )

    def trending(
        self,
        sport: str = "nfl",
        kind: str = "add",
        lookback_hours: int = 24,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Trending adds or drops: [{'player_id':..., 'count':...}, ...]."""
        url = (
            f"{self.base}/players/{sport}/trending/{kind}"
            f"?lookback_hours={lookback_hours}&limit={limit}"
        )
        return get_json(url) or []

    # ---- league -----------------------------------------------------------
    def league(self, league_id: str) -> Dict[str, Any]:
        """League settings incl. scoring_settings + roster_positions."""
        return get_json(f"{self.base}/league/{league_id}")

    def league_users(self, league_id: str) -> List[Dict[str, Any]]:
        return get_json(f"{self.base}/league/{league_id}/users") or []

    def rosters(self, league_id: str) -> List[Dict[str, Any]]:
        return get_json(f"{self.base}/league/{league_id}/rosters") or []

    def matchups(self, league_id: str, week: int) -> List[Dict[str, Any]]:
        return get_json(f"{self.base}/league/{league_id}/matchups/{week}") or []

    def transactions(self, league_id: str, week: int) -> List[Dict[str, Any]]:
        return get_json(f"{self.base}/league/{league_id}/transactions/{week}") or []

    def user(self, username_or_id: str) -> Optional[Dict[str, Any]]:
        return get_json(f"{self.base}/user/{username_or_id}")

    def user_leagues(
        self, user_id: str, season: str, sport: str = "nfl"
    ) -> List[Dict[str, Any]]:
        return get_json(f"{self.base}/user/{user_id}/leagues/{sport}/{season}") or []

    # ---- draft ------------------------------------------------------------
    def draft(self, draft_id: str) -> Dict[str, Any]:
        return get_json(f"{self.base}/draft/{draft_id}")

    def draft_picks(self, draft_id: str) -> List[Dict[str, Any]]:
        """All picks made so far — the live feed for the draft assistant."""
        return get_json(f"{self.base}/draft/{draft_id}/picks") or []

    def league_drafts(self, league_id: str) -> List[Dict[str, Any]]:
        return get_json(f"{self.base}/league/{league_id}/drafts") or []


def player_display(player: Dict[str, Any]) -> str:
    """Human-friendly name for a Sleeper player record (handles DEF)."""
    if not player:
        return "?"
    full = player.get("full_name")
    if full:
        return full
    # Team defenses come through as position DEF with player_id == team code.
    if player.get("position") == "DEF":
        return f"{player.get('player_id', '')} DEF".strip()
    first = player.get("first_name") or ""
    last = player.get("last_name") or ""
    return (first + " " + last).strip() or str(player.get("player_id", "?"))
