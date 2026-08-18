"""Live snake-draft assistant.

Given the board, who has already been drafted, your roster, and your draft slot,
recommend the best pick — balancing raw value (VBD), positional scarcity (VONA:
how much value falls off before your next pick), and roster need.

Everything here is pure functions over a DraftState so it's easy to test and to
drive from either the CLI or the dashboard.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .league import LeagueConfig
from .models import Player

# Hard caps: don't recommend more of a position than you could ever use.
DEFAULT_POSITION_CAPS = {"QB": 3, "RB": 8, "WR": 8, "TE": 3, "K": 1, "DEF": 2}
# Desired depth beyond starters (starters + this) before need drops to zero.
DEFAULT_DEPTH_TARGETS = {"QB": 1, "RB": 3, "WR": 3, "TE": 1, "K": 0, "DEF": 0}


@dataclass
class DraftState:
    """Snapshot of a snake draft in progress."""

    league: LeagueConfig
    my_slot: int                      # your draft position, 1..teams
    drafted_ids: List[str] = field(default_factory=list)   # in pick order
    my_player_ids: List[str] = field(default_factory=list)  # your picks

    @property
    def teams(self) -> int:
        return self.league.teams

    @property
    def rounds(self) -> int:
        return self.league.total_roster_size()

    @property
    def picks_made(self) -> int:
        return len(self.drafted_ids)

    @property
    def current_overall(self) -> int:
        """The overall pick number currently on the clock (1-indexed)."""
        return self.picks_made + 1

    def overall_to_slot(self, overall: int) -> int:
        """Which draft slot owns a given overall pick, under snake order."""
        rnd = (overall - 1) // self.teams          # 0-indexed round
        pos_in_round = (overall - 1) % self.teams   # 0-indexed
        if rnd % 2 == 0:                            # left-to-right
            return pos_in_round + 1
        return self.teams - pos_in_round            # right-to-left

    def my_pick_overalls(self) -> List[int]:
        total_picks = self.teams * self.rounds
        return [o for o in range(1, total_picks + 1) if self.overall_to_slot(o) == self.my_slot]

    def is_my_turn(self) -> bool:
        return self.overall_to_slot(self.current_overall) == self.my_slot

    def my_next_overall(self, after: Optional[int] = None) -> Optional[int]:
        after = after if after is not None else self.current_overall - 1
        for o in self.my_pick_overalls():
            if o > after:
                return o
        return None

    def picks_until_next(self) -> Optional[int]:
        """How many total picks elapse from now until my *following* pick.

        If it's my turn at pick N, this is (my next pick after N) - N, i.e. how
        many players come off the board before I'm up again. Drives VONA.
        """
        cur = self.current_overall
        nxt = self.my_next_overall(after=cur)
        if nxt is None:
            return None
        return nxt - cur


@dataclass
class Suggestion:
    player: Player
    score: float
    dropoff: float           # VONA: value lost at this position if you wait
    need: str                # "must-fill" | "depth" | "luxury" | "full"
    reason: str


def roster_counts(state: DraftState, board_by_id: Dict[str, Player]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for pid in state.my_player_ids:
        p = board_by_id.get(pid)
        if p:
            counts[p.position] = counts.get(p.position, 0) + 1
    return counts


def _need_state(
    pos: str, counts: Dict[str, int], league: LeagueConfig,
    depth_targets: Dict[str, int], caps: Dict[str, int],
) -> str:
    have = counts.get(pos, 0)
    starters = league.starters.get(pos, 0)
    # Flex-eligible positions effectively need one more than dedicated starters.
    if pos in league.flex_weights and league.flex:
        starters += 1
    cap = caps.get(pos, 99)
    target = starters + depth_targets.get(pos, 0)
    if have >= cap:
        return "full"
    if have < starters:
        return "must-fill"
    if have < target:
        return "depth"
    return "luxury"


_NEED_MULT = {"must-fill": 1.0, "depth": 0.6, "luxury": 0.15, "full": -1.0}


def _future_dropoff(
    available: List[Player], picks_ahead: int,
) -> Dict[str, float]:
    """VONA per position: best-available-now VBD minus best-available-next.

    We assume the ``picks_ahead`` players with the lowest ADP (most likely to be
    taken) are gone by your next pick, then measure how much the best remaining
    player at each position drops. Positions with steep drops are scarce — take
    them now.
    """
    # Rank likely-gone players by ADP (fallback to overall_rank when ADP absent).
    def take_key(p: Player):
        return p.adp if p.adp is not None else (p.overall_rank or 9999)

    likely_gone = set(
        id(p) for p in sorted(available, key=take_key)[:max(0, picks_ahead)]
    )
    now_best: Dict[str, float] = {}
    next_best: Dict[str, float] = {}
    for p in available:
        now_best[p.position] = max(now_best.get(p.position, float("-inf")), p.vbd)
        if id(p) not in likely_gone:
            next_best[p.position] = max(next_best.get(p.position, float("-inf")), p.vbd)
    dropoff: Dict[str, float] = {}
    for pos, now in now_best.items():
        fut = next_best.get(pos, now)  # if all gone, treat drop as small
        dropoff[pos] = round(max(0.0, now - fut), 2)
    return dropoff


def recommend(
    state: DraftState,
    board: Sequence[Player],
    top_n: int = 7,
    scarcity_weight: float = 0.5,
    depth_targets: Optional[Dict[str, int]] = None,
    caps: Optional[Dict[str, int]] = None,
) -> List[Suggestion]:
    """Rank the best available picks for the team on the clock (you)."""
    depth_targets = depth_targets or DEFAULT_DEPTH_TARGETS
    caps = caps or DEFAULT_POSITION_CAPS

    board_by_id = {p.player_id: p for p in board}
    drafted = set(state.drafted_ids)
    available = [p for p in board if p.player_id not in drafted]
    if not available:
        return []

    counts = roster_counts(state, board_by_id)
    picks_ahead = state.picks_until_next() or 0
    dropoff = _future_dropoff(available, picks_ahead)

    suggestions: List[Suggestion] = []
    for p in available:
        need = _need_state(p.position, counts, state.league, depth_targets, caps)
        need_mult = _NEED_MULT[need]
        if need == "full":
            continue  # never suggest a position you can't use
        pos_drop = dropoff.get(p.position, 0.0)
        # Composite: raw value, scaled by need, plus a scarcity nudge toward
        # positions about to fall off before your next pick.
        score = p.vbd * (0.5 + 0.5 * max(need_mult, 0.0)) + scarcity_weight * pos_drop
        # Small tilt for must-fill starters so you don't punt a starting slot.
        if need == "must-fill":
            score += 5.0
        reason = _explain(p, need, pos_drop, state)
        suggestions.append(
            Suggestion(player=p, score=round(score, 2), dropoff=pos_drop,
                       need=need, reason=reason)
        )

    suggestions.sort(key=lambda s: s.score, reverse=True)
    return suggestions[:top_n]


def _explain(p: Player, need: str, dropoff: float, state: DraftState) -> str:
    bits = [f"{p.position}{p.pos_rank or '?'}", f"VBD {p.vbd:+.0f}"]
    if p.tier is not None:
        bits.append(f"tier {p.tier}")
    if p.adp is not None:
        edge = p.adp - state.current_overall
        if edge >= 6:
            bits.append(f"value (ADP {p.adp:.0f}, ~{edge:.0f} past)")
        elif edge <= -6:
            bits.append(f"reach (ADP {p.adp:.0f})")
        else:
            bits.append(f"ADP {p.adp:.0f}")
    if dropoff >= 15:
        bits.append(f"scarce: -{dropoff:.0f} VBD if you wait")
    need_label = {
        "must-fill": "fills a starting slot",
        "depth": "adds needed depth",
        "luxury": "best-player-available",
    }.get(need, need)
    bits.append(need_label)
    if p.bye_week:
        bits.append(f"bye {p.bye_week}")
    return " · ".join(bits)
