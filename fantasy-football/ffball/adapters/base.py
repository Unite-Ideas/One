"""The platform-neutral league interface every adapter implements.

An adapter's whole job is to translate one fantasy platform's API into these
normalized shapes. Downstream code (LeagueConfig, the season engine, the
refresh + scout tools, the web-app builder) is written against this interface
only, so a second platform is purely additive: a new subclass, no engine edits.

Normalized shapes
-----------------
state()               -> {"week": int, "season": str}
league()              -> Sleeper-shaped league dict: at least
                         name, total_rosters, roster_positions[list],
                         scoring_settings{dict}, settings{playoff_week_start,...}
rosters()             -> [{"roster_id": int, "owner": str, "players": [str id]}]
matchups(week)        -> [{"roster_id": int, "matchup_id": int|None,
                          "points": float, "starters": [str id]}]
player_meta()         -> {id: {"name": str, "pos": str, "injury": str}}
trending()            -> {id: int}          (herd add-count; may be empty)
weekly_projections()  -> {id: {"wk": float, "opp": str, "team": str}}
                         where wk is projected points IN THIS LEAGUE'S SCORING

Anything NFL-wide (Vegas odds/schedule from ESPN, FantasyPros rest-of-season
consensus) is not platform-specific and stays in shared helpers, not here.
"""
from __future__ import annotations

import abc
import json
import urllib.request
from typing import Dict, List


def http_json(url: str, timeout: int = 60):
    """Fetch JSON with a browser-ish UA (shared by adapters)."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def apply_scoring(stats: dict, scoring: dict) -> float:
    """Exact fantasy points for a stat line = stats · scoring settings.

    Platform-neutral: works for any {stat_key: value} projection line and any
    {stat_key: point_value} scoring map (so a league's TE premium, first-down
    bonuses, etc. are all honored). Keys absent from the scoring map score 0.
    """
    return round(sum(float(v) * scoring[k] for k, v in stats.items()
                     if k in scoring and isinstance(v, (int, float))), 1)


class LeagueSource(abc.ABC):
    """Read-only, platform-neutral view of one fantasy league."""

    platform: str = "base"

    @abc.abstractmethod
    def state(self) -> Dict: ...

    @abc.abstractmethod
    def league(self) -> Dict: ...

    @abc.abstractmethod
    def rosters(self) -> List[Dict]: ...

    @abc.abstractmethod
    def matchups(self, week: int) -> List[Dict]: ...

    @abc.abstractmethod
    def player_meta(self) -> Dict[str, Dict]: ...

    @abc.abstractmethod
    def weekly_projections(self, season: str, week: int, scoring: Dict) -> Dict[str, Dict]: ...

    def trending(self) -> Dict[str, int]:
        """Herd add-count per player id. Optional; default none."""
        return {}
