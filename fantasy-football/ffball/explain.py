"""Beginner-friendly, plain-English explanations of the draft math.

Turns the terse internal signals (VBD, ADP, tiers, positional need, scarcity)
into sentences a first-time player can understand, so the tool teaches the game
while you use it.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from .models import Player

POS_FULL = {
    "QB": "Quarterback",
    "RB": "Running Back",
    "WR": "Wide Receiver",
    "TE": "Tight End",
    "K": "Kicker",
    "DEF": "Defense / Special Teams",
    "FLEX": "Flex (RB, WR, or TE)",
}


def pos_full(pos: str) -> str:
    return POS_FULL.get(pos, pos)


def _value_sentence(p: Player) -> str:
    v = p.vbd
    if v >= 100:
        strength = "a massive edge"
    elif v >= 50:
        strength = "a big edge"
    elif v >= 20:
        strength = "a solid edge"
    elif v > 0:
        strength = "a slight edge"
    else:
        strength = "about the same as a bench-level player"
    role = pos_full(p.position)
    return (
        f"Projected to score about {v:+.0f} points this season versus a "
        f"freely-available backup {role} — {strength}."
    )


def _adp_sentence(p: Player, current_overall: int) -> Optional[str]:
    if p.adp is None:
        return None
    fell = current_overall - p.adp
    if fell >= 6:
        return (
            f"Normally drafted around pick {p.adp:.0f}, but he's still here at "
            f"pick {current_overall} — that's great value."
        )
    if fell <= -6:
        return (
            f"Normally drafted around pick {p.adp:.0f}. Taking him now (pick "
            f"{current_overall}) is a bit early — a 'reach'. You could likely "
            f"wait and still get him."
        )
    return f"He's going about where he's usually drafted (around pick {p.adp:.0f})."


def _need_sentence(need: str, pos: str) -> str:
    role = pos_full(pos)
    return {
        "must-fill": f"Fills one of your empty starting {role} spots.",
        "depth": f"Adds useful depth at {role} (good for your bench or flex).",
        "luxury": f"You already have your {role} starters — this would be a bonus.",
    }.get(need, "")


def _scarcity_sentence(dropoff: float, pos: str) -> Optional[str]:
    if dropoff >= 15:
        return (
            f"This position is thinning out fast — wait and the next {pos_full(pos)} "
            f"could be about {dropoff:.0f} points worse."
        )
    return None


def tag_for(p: Player, dropoff: float, current_overall: int) -> Dict[str, str]:
    """A single colored badge summarizing the pick at a glance."""
    fell = None if p.adp is None else current_overall - p.adp
    if fell is not None and fell <= -6:
        return {"key": "reach", "text": "SLIGHT REACH"}
    if fell is not None and fell >= 6:
        return {"key": "value", "text": "GREAT VALUE"}
    if dropoff >= 20:
        return {"key": "scarce", "text": "GOING FAST"}
    return {"key": "solid", "text": "SOLID PICK"}


def plain_reason(
    p: Player, need: str, dropoff: float, current_overall: int
) -> Dict[str, object]:
    """Full beginner-friendly explanation bundle for one recommended player."""
    sentences: List[str] = [_value_sentence(p)]
    adp = _adp_sentence(p, current_overall)
    if adp:
        sentences.append(adp)
    scarce = _scarcity_sentence(dropoff, p.position)
    if scarce:
        sentences.append(scarce)
    need_s = _need_sentence(need, p.position)
    if need_s:
        sentences.append(need_s)
    if p.bye_week:
        sentences.append(
            f"Bye week {p.bye_week}: the one week this player has no game, so "
            f"you'll need someone else that week."
        )
    return {
        "pos_full": pos_full(p.position),
        "tag": tag_for(p, dropoff, current_overall),
        "sentences": sentences,
    }
