"""Turn projections into a draftable value board: points -> VBD -> tiers.

Pipeline:
  1. apply_scoring   : projected stats + scoring -> proj_points
  2. compute_vbd     : proj_points - positional replacement baseline -> vbd
  3. assign_tiers    : gap-based tiers within each position
  4. rank            : overall + positional ranks by vbd

The board is the single source of truth the draft assistant reads from.
"""
from __future__ import annotations

import statistics
from typing import Dict, List, Sequence

from .league import LeagueConfig
from .models import Player
from .scoring import ScoringSystem


def apply_scoring(players: Sequence[Player], scoring: ScoringSystem) -> None:
    """Set ``proj_points`` on each player from stats (or manual fallback)."""
    for p in players:
        pts = scoring.score(p.stats) if p.stats else 0.0
        if pts == 0.0 and p.proj_points_manual is not None:
            pts = float(p.proj_points_manual)
        p.proj_points = round(pts, 2)


def _replacement_points(pos_players: List[Player], baseline_rank: float) -> float:
    """Projected points of the replacement-level player at a position.

    ``baseline_rank`` may be fractional (flex share). We linearly interpolate
    between the two surrounding ranked players for a smooth baseline.
    """
    if not pos_players:
        return 0.0
    ranked = sorted(pos_players, key=lambda p: p.proj_points, reverse=True)
    # baseline_rank is a 1-indexed count of startable players; the replacement
    # player is the next one down (index == baseline_rank in 0-indexed terms).
    idx = max(0.0, baseline_rank)
    lo = int(idx)
    if lo >= len(ranked):
        return ranked[-1].proj_points
    if lo == 0:
        hi_pts = ranked[0].proj_points
        return hi_pts
    frac = idx - lo
    lo_pts = ranked[lo - 1].proj_points
    hi_pts = ranked[lo].proj_points if lo < len(ranked) else lo_pts
    return lo_pts + (hi_pts - lo_pts) * frac


def compute_vbd(players: Sequence[Player], league: LeagueConfig) -> Dict[str, float]:
    """Compute VBD for every player. Returns the baseline points per position."""
    slots = league.startable_slots()
    by_pos: Dict[str, List[Player]] = {}
    for p in players:
        by_pos.setdefault(p.position, []).append(p)

    baselines: Dict[str, float] = {}
    for pos, pos_players in by_pos.items():
        baseline_rank = slots.get(pos, len(pos_players))
        baselines[pos] = round(_replacement_points(pos_players, baseline_rank), 2)
        for p in pos_players:
            p.vbd = round(p.proj_points - baselines[pos], 2)
    return baselines


def assign_tiers(
    players: Sequence[Player],
    gap_factor: float = 1.0,
    min_gap: float = 8.0,
    max_tiers: int = 12,
) -> None:
    """Gap-based tiers within each position.

    Walking down a position by value, a new tier starts whenever the drop to the
    next player exceeds a dynamic threshold (a multiple of the typical gap, with
    a floor of ``min_gap`` points). Big cliffs -> new tier; smooth slopes stay
    together. This is what tells you "this position is about to fall off."
    """
    by_pos: Dict[str, List[Player]] = {}
    for p in players:
        by_pos.setdefault(p.position, []).append(p)

    for pos_players in by_pos.values():
        ranked = sorted(pos_players, key=lambda p: p.vbd, reverse=True)
        if not ranked:
            continue
        gaps = [ranked[i].vbd - ranked[i + 1].vbd for i in range(len(ranked) - 1)]
        if gaps:
            typical = statistics.median(g for g in gaps) if gaps else 0.0
            stdev = statistics.pstdev(gaps) if len(gaps) > 1 else 0.0
            threshold = max(min_gap, typical + gap_factor * stdev)
        else:
            threshold = min_gap
        tier = 1
        ranked[0].tier = tier
        for i in range(1, len(ranked)):
            gap = ranked[i - 1].vbd - ranked[i].vbd
            if gap >= threshold and tier < max_tiers:
                tier += 1
            ranked[i].tier = tier


def rank_board(players: List[Player]) -> List[Player]:
    """Assign overall + positional ranks by VBD; return sorted-by-VBD board."""
    board = sorted(players, key=lambda p: p.vbd, reverse=True)
    for i, p in enumerate(board, start=1):
        p.overall_rank = i
    pos_counter: Dict[str, int] = {}
    for p in board:
        pos_counter[p.position] = pos_counter.get(p.position, 0) + 1
        p.pos_rank = pos_counter[p.position]
    return board


def build_board(
    players: List[Player],
    scoring: ScoringSystem,
    league: LeagueConfig,
) -> List[Player]:
    """Full pipeline: score -> VBD -> tiers -> rank. Returns the ranked board."""
    apply_scoring(players, scoring)
    compute_vbd(players, league)
    assign_tiers(players)
    return rank_board(players)
