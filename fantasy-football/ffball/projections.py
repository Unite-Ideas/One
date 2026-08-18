"""Load and blend projections + ADP into normalized Player objects.

Sources, in order of precedence when present:
  1. CSV files under ``data/projections/*.csv`` (one row per player-source).
  2. The bundled sample projections (``data/sample/projections.csv``) — used so
     the app runs offline in this sandbox and for demos.

A projection CSV is expected to have a header with at least:
    player_id (or name), position, team, and any Sleeper stat columns
    (pass_yd, pass_td, pass_int, rush_yd, rush_td, rec, rec_yd, rec_td,
     fum_lost, ...). Optional: bye_week, adp, source.

Multiple sources for the same player are averaged per stat (optionally
weighted), which is the "never trust one projection" rule in code.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .models import Player

_DATA_DIR = Path(__file__).parent.parent / "data"
_SAMPLE_CSV = _DATA_DIR / "sample" / "projections.csv"
_PROJ_DIR = _DATA_DIR / "projections"

# Columns that are identity/market, not scoring stats.
_NON_STAT_COLS = {
    "player_id",
    "name",
    "position",
    "pos",
    "team",
    "bye_week",
    "bye",
    "adp",
    "age",
    "source",
    "injury_status",
    "fpts",
    "proj_points",
}

_STAT_ALIASES = {
    "pos": "position",
    "bye": "bye_week",
}


def _norm_key(key: str) -> str:
    key = key.strip().lower()
    return _STAT_ALIASES.get(key, key)


def _row_to_partial(row: Dict[str, str]) -> Dict[str, object]:
    """Parse one CSV row into {identity fields + stats dict}."""
    clean = {_norm_key(k): (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
    stats: Dict[str, float] = {}
    for key, value in clean.items():
        if key in _NON_STAT_COLS or key == "position":
            continue
        if value in (None, ""):
            continue
        try:
            stats[key] = float(value)
        except ValueError:
            continue

    def num(field: str) -> Optional[float]:
        val = clean.get(field)
        if val in (None, ""):
            return None
        try:
            return float(val)
        except ValueError:
            return None

    return {
        "player_id": clean.get("player_id") or clean.get("name"),
        "name": clean.get("name") or clean.get("player_id"),
        "position": (clean.get("position") or "").upper(),
        "team": clean.get("team") or None,
        "bye_week": int(num("bye_week")) if num("bye_week") is not None else None,
        "age": num("age"),
        "adp": num("adp"),
        "injury_status": clean.get("injury_status") or None,
        "proj_points_manual": num("fpts") if num("fpts") is not None else num("proj_points"),
        "stats": stats,
    }


def _load_csv(path: Path) -> List[Dict[str, object]]:
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        return [_row_to_partial(row) for row in csv.DictReader(fh)]


def _blend(partials: Iterable[Dict[str, object]]) -> List[Player]:
    """Merge multiple partial records per player by averaging their stats."""
    by_id: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for p in partials:
        pid = str(p.get("player_id") or "").strip()
        if not pid or not p.get("position"):
            continue
        by_id[pid].append(p)

    players: List[Player] = []
    for pid, group in by_id.items():
        # Average each stat across sources that reported it.
        stat_sums: Dict[str, float] = defaultdict(float)
        stat_counts: Dict[str, int] = defaultdict(int)
        adps: List[float] = []
        for p in group:
            for key, value in p["stats"].items():  # type: ignore[index]
                stat_sums[key] += float(value)
                stat_counts[key] += 1
            if p.get("adp") is not None:
                adps.append(float(p["adp"]))  # type: ignore[arg-type]
        stats = {k: round(stat_sums[k] / stat_counts[k], 3) for k in stat_sums}

        first = group[0]
        players.append(
            Player(
                player_id=pid,
                name=str(first.get("name") or pid),
                position=str(first.get("position")),
                team=first.get("team"),  # type: ignore[arg-type]
                bye_week=first.get("bye_week"),  # type: ignore[arg-type]
                age=first.get("age"),  # type: ignore[arg-type]
                injury_status=first.get("injury_status"),  # type: ignore[arg-type]
                stats=stats,
                proj_points_manual=first.get("proj_points_manual"),  # type: ignore[arg-type]
                adp=round(sum(adps) / len(adps), 2) if adps else None,
            )
        )
    return players


def load_players(use_sample_if_empty: bool = True) -> List[Player]:
    """Load + blend all projection CSVs into Player objects.

    Reads every ``*.csv`` in ``data/projections/``. If that directory is empty
    (or missing) and ``use_sample_if_empty`` is set, falls back to the bundled
    sample so the app always has something to work with.
    """
    partials: List[Dict[str, object]] = []
    if _PROJ_DIR.exists():
        for path in sorted(_PROJ_DIR.glob("*.csv")):
            partials.extend(_load_csv(path))

    if not partials and use_sample_if_empty and _SAMPLE_CSV.exists():
        partials = _load_csv(_SAMPLE_CSV)

    return _blend(partials)
