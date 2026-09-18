"""In-season management engine: lineup optimizer, waivers, and trade analyzer.

Everything reduces to one operation: the best legal STARTING LINEUP a set of
players can field (``optimal_lineup``). From that:
  * a waiver add is worth how much it *raises* your optimal lineup,
  * a trade is worth the *swing* in your optimal lineup,
so all three tools share the same core and stay consistent.

Player value here is ``proj_points`` (rest-of-season projection). Swap in weekly
projections for weekly start/sit; the logic is identical.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Set, Tuple

from .league import LeagueConfig
from .models import Player


def lineup_slots(league: LeagueConfig) -> List[Tuple[str, Set[str]]]:
    """Ordered starting slots as (label, eligible-positions). Most-constrained first."""
    slots: List[Tuple[str, Set[str]]] = []
    for pos, n in league.starters.items():
        slots += [(pos, {pos})] * n
    if league.flex:
        slots += [("FLEX", set(league.flex_weights))] * league.flex
    if getattr(league, "super_flex", 0):
        slots += [("SUPERFLEX", set(getattr(league, "super_flex_weights", {})))] * league.super_flex
    return slots


@dataclass
class Lineup:
    starters: List[Tuple[str, Optional[Player]]]   # (slot label, player or None)
    bench: List[Player]
    total: float


def optimal_lineup(players: Sequence[Player], league: LeagueConfig,
                   week: Optional[int] = None) -> Lineup:
    """Best legal starting lineup. If ``week`` given, players on bye that week sit."""
    eligible = [p for p in players if not (week is not None and p.bye_week == week)]
    ranked = sorted(eligible, key=lambda p: -p.proj_points)
    used: Set[str] = set()
    starters: List[Tuple[str, Optional[Player]]] = []
    for label, elig in lineup_slots(league):
        pick = None
        for p in ranked:
            if p.player_id in used or p.position not in elig:
                continue
            pick = p
            break
        if pick:
            used.add(pick.player_id)
        starters.append((label, pick))
    bench = [p for p in players if p.player_id not in used]
    total = round(sum(p.proj_points for _, p in starters if p), 1)
    return Lineup(starters=starters, bench=bench, total=total)


# ---------------------------------------------------------------------------
# Waivers
# ---------------------------------------------------------------------------
@dataclass
class WaiverTarget:
    add: Player
    drop: Optional[Player]
    gain: float            # projected starting-lineup points gained
    trending: int          # Sleeper trending-add count (herd signal)


def waiver_targets(free_agents: Sequence[Player], my_players: Sequence[Player],
                   league: LeagueConfig, trending: Optional[Dict[str, int]] = None,
                   top: int = 12) -> List[WaiverTarget]:
    """Rank free agents by how much they'd improve YOUR optimal starting lineup.

    ``gain`` is the rise in optimal-lineup points from adding the player and
    dropping your least-useful bench player. Positive gain = a real upgrade.
    """
    trending = trending or {}
    base = optimal_lineup(my_players, league).total
    my = list(my_players)
    # The natural drop is the bench player who contributes least to future lineups.
    droppable = sorted(my, key=lambda p: p.proj_points)
    results: List[WaiverTarget] = []
    for fa in free_agents:
        drop = droppable[0] if droppable else None
        new_roster = [p for p in my if not (drop and p.player_id == drop.player_id)] + [fa]
        gain = optimal_lineup(new_roster, league).total - base
        if gain > 0 or fa.player_id in trending:
            results.append(WaiverTarget(add=fa, drop=drop, gain=round(gain, 1),
                                        trending=trending.get(fa.player_id, 0)))
    # Rank by lineup gain, then by herd signal as a tiebreaker/early-warning.
    results.sort(key=lambda w: (w.gain, w.trending), reverse=True)
    return results[:top]


# ---------------------------------------------------------------------------
# Trades
# ---------------------------------------------------------------------------
@dataclass
class TradeEval:
    swing: float           # change in your optimal starting-lineup points
    raw_value: float       # rest-of-season points you get minus give
    verdict: str


def evaluate_trade(my_players: Sequence[Player], give: Sequence[Player],
                   get: Sequence[Player], league: LeagueConfig) -> TradeEval:
    """Grade a trade by the swing in your optimal starting lineup (and raw value)."""
    give_ids = {p.player_id for p in give}
    before = optimal_lineup(my_players, league).total
    after = optimal_lineup([p for p in my_players if p.player_id not in give_ids] + list(get),
                           league).total
    swing = round(after - before, 1)
    raw = round(sum(p.proj_points for p in get) - sum(p.proj_points for p in give), 1)
    if swing >= 8:
        verdict = "Clear win — accept"
    elif swing >= 2:
        verdict = "Slight win — worth it"
    elif swing > -2:
        verdict = "Roughly even"
    elif swing > -8:
        verdict = "Slight loss — lean pass"
    else:
        verdict = "Clear loss — reject"
    return TradeEval(swing=swing, raw_value=raw, verdict=verdict)


# ---------------------------------------------------------------------------
# Live Sleeper sync helpers
# ---------------------------------------------------------------------------
def rostered_player_ids(sleeper, league_id: str) -> Set[str]:
    """Every player currently on any team in the league."""
    ids: Set[str] = set()
    for r in sleeper.rosters(league_id):
        for pid in (r.get("players") or []):
            ids.add(str(pid))
    return ids


def my_roster_ids(sleeper, league_id: str, owner_id: Optional[str] = None,
                  roster_id: Optional[int] = None) -> List[str]:
    """Your player ids, found by owner (user) id or roster id."""
    for r in sleeper.rosters(league_id):
        if (owner_id and str(r.get("owner_id")) == str(owner_id)) or \
           (roster_id and r.get("roster_id") == roster_id):
            return [str(p) for p in (r.get("players") or [])]
    return []


def free_agents(board: Sequence[Player], rostered: Set[str]) -> List[Player]:
    """Board players not on any roster, best first."""
    fas = [p for p in board if p.player_id not in rostered]
    fas.sort(key=lambda p: -p.proj_points)
    return fas
