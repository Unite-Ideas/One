"""Fuzzy player-name matching for fast draft-day entry.

Typing full names on the clock is too slow, so we match loose input ("cmc",
"jefferson", "bijan") to a unique player on the board. Returns a single match,
a short disambiguation list, or nothing.
"""
from __future__ import annotations

from typing import List, Sequence

from .models import Player


def _norm(s: str) -> str:
    return "".join(c for c in s.lower() if c.isalnum() or c == " ").strip()


# A few common shorthands people actually type at the draft table.
_ALIASES = {
    "cmc": "christian mccaffrey",
    "jsn": "jaxon smith-njigba",
    "arsb": "amon-ra st brown",
    "mhj": "marvin harrison",
    "btj": "brian thomas",
    "dj moore": "dj moore",
}


def find(query: str, players: Sequence[Player]) -> List[Player]:
    """Return candidate players matching ``query``, best first.

    Match priority: exact id/name > alias > startswith > substring > last-name.
    """
    q = _norm(query)
    if not q:
        return []
    q = _norm(_ALIASES.get(q, q))  # normalize alias target too (drops hyphens)

    exact, prefix, sub, lastname = [], [], [], []
    for p in players:
        pid = _norm(p.player_id)
        name = _norm(p.name)
        if q == pid or q == name:
            exact.append(p)
            continue
        if name.startswith(q) or pid.startswith(q):
            prefix.append(p)
            continue
        if q in name or q in pid:
            sub.append(p)
            continue
        last = name.split(" ")[-1] if " " in name else name
        if last.startswith(q):
            lastname.append(p)

    # De-dup while preserving order/priority.
    seen = set()
    ordered: List[Player] = []
    for bucket in (exact, prefix, sub, lastname):
        bucket.sort(key=lambda p: (p.overall_rank or 9999))
        for p in bucket:
            if p.player_id not in seen:
                seen.add(p.player_id)
                ordered.append(p)
    return ordered
