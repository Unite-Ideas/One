"""League/roster configuration used by the value model.

A LeagueConfig captures the two things that define replacement value:
  * how many teams (more teams -> shallower talent -> deeper baseline), and
  * the starting lineup (how many of each position start, plus flex slots).

It can be built from a bundled preset or straight from a Sleeper league payload
(``roster_positions`` + ``total_rosters``), so it matches your league exactly.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Mapping

_CONFIG_DIR = Path(__file__).parent / "config"

# Default share of FLEX slots taken by each eligible position (empirically RB/WR
# heavy). Used to push the replacement baseline deeper for flex-eligible spots.
DEFAULT_FLEX_WEIGHTS = {"RB": 0.45, "WR": 0.45, "TE": 0.10}
DEFAULT_SUPERFLEX_WEIGHTS = {"QB": 0.80, "RB": 0.08, "WR": 0.10, "TE": 0.02}

# Sleeper roster_positions strings that aren't a single startable position.
_SLEEPER_FLEX = {"FLEX", "WRRB_FLEX", "REC_FLEX"}
_SLEEPER_SUPERFLEX = {"SUPER_FLEX"}
_SLEEPER_IGNORE = {"BN", "TAXI", "IR"}
# Normalize Sleeper's IDP/oddball slots we don't model to nothing.


@dataclass
class LeagueConfig:
    teams: int
    starters: Dict[str, int]          # e.g. {"QB":1,"RB":2,"WR":2,"TE":1,"K":1,"DEF":1}
    flex: int = 0                     # generic RB/WR/TE flex slots per team
    super_flex: int = 0               # QB-eligible flex slots per team
    bench: int = 6
    flex_weights: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_FLEX_WEIGHTS))
    super_flex_weights: Dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_SUPERFLEX_WEIGHTS)
    )
    name: str = "custom"

    # ---- constructors -----------------------------------------------------
    @classmethod
    def from_preset(cls, name: str) -> "LeagueConfig":
        with open(_CONFIG_DIR / "roster_presets.json", "r", encoding="utf-8") as fh:
            presets = json.load(fh)
        if name not in presets:
            raise KeyError(f"Unknown roster preset {name!r}. Available: {sorted(presets)}")
        p = presets[name]
        starters = dict(p["starters"])
        flex = starters.pop("FLEX", 0)
        super_flex = starters.pop("SUPER_FLEX", 0)
        return cls(
            teams=p["teams"],
            starters=starters,
            flex=flex,
            super_flex=super_flex,
            bench=p.get("bench", 6),
            name=name,
        )

    @classmethod
    def from_sleeper_league(cls, league: Mapping[str, object]) -> "LeagueConfig":
        positions: List[str] = list(league.get("roster_positions") or [])  # type: ignore[arg-type]
        teams = int(league.get("total_rosters") or 12)
        starters: Dict[str, int] = {}
        flex = super_flex = bench = 0
        for slot in positions:
            if slot in _SLEEPER_IGNORE:
                if slot == "BN":
                    bench += 1
                continue
            if slot in _SLEEPER_FLEX:
                flex += 1
            elif slot in _SLEEPER_SUPERFLEX:
                super_flex += 1
            else:
                starters[slot] = starters.get(slot, 0) + 1
        return cls(
            teams=teams,
            starters=starters,
            flex=flex,
            super_flex=super_flex,
            bench=bench or 6,
            name=str(league.get("name") or "sleeper_league"),
        )

    # ---- derived ----------------------------------------------------------
    def startable_slots(self) -> Dict[str, float]:
        """League-wide number of *startable* players at each position.

        = teams * (dedicated starters + that position's share of flex/superflex).
        This is the replacement baseline rank: the (startable+1)-th best player
        at a position is roughly "freely available," so value is measured above
        the startable cutoff.
        """
        slots: Dict[str, float] = {}
        for pos, n in self.starters.items():
            slots[pos] = float(n)
        for pos, w in self.flex_weights.items():
            slots[pos] = slots.get(pos, 0.0) + self.flex * w
        for pos, w in self.super_flex_weights.items():
            slots[pos] = slots.get(pos, 0.0) + self.super_flex * w
        # Scale to the whole league.
        return {pos: v * self.teams for pos, v in slots.items()}

    def total_roster_size(self) -> int:
        dedicated = sum(self.starters.values())
        return dedicated + self.flex + self.super_flex + self.bench

    def summary(self) -> str:
        parts = [f"{n}{pos}" for pos, n in self.starters.items()]
        if self.flex:
            parts.append(f"{self.flex}FLEX")
        if self.super_flex:
            parts.append(f"{self.super_flex}SFLEX")
        return f"{self.teams}-team | " + "/".join(parts) + f" | {self.bench} bench"
