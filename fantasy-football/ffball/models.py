"""Core data models shared across the system."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

# Positions eligible for our value model, in a stable display order.
POSITIONS = ["QB", "RB", "WR", "TE", "K", "DEF"]


@dataclass
class Player:
    """A normalized player with projected stats and market data.

    ``stats`` holds *season-total* projected stats keyed by Sleeper stat keys
    (e.g. ``rec``, ``rush_yd``). ``proj_points`` is filled once a ScoringSystem
    is applied. ``adp`` is average draft position (lower = drafted earlier).
    """

    player_id: str
    name: str
    position: str
    team: Optional[str] = None
    bye_week: Optional[int] = None
    age: Optional[float] = None
    injury_status: Optional[str] = None
    stats: Dict[str, float] = field(default_factory=dict)
    # Pre-scored fantasy points, used as a fallback when raw stats aren't worth
    # modeling (kickers, team defenses). Ignored when scorable stats exist.
    proj_points_manual: Optional[float] = None

    # Derived / market fields (populated by later stages)
    proj_points: float = 0.0
    adp: Optional[float] = None
    vbd: float = 0.0            # points above positional replacement baseline
    pos_rank: Optional[int] = None
    overall_rank: Optional[int] = None
    tier: Optional[int] = None

    @property
    def is_startable_pos(self) -> bool:
        return self.position in POSITIONS

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return (
            f"Player({self.name!r}, {self.position}, "
            f"pts={self.proj_points}, vbd={round(self.vbd,1)}, adp={self.adp})"
        )
