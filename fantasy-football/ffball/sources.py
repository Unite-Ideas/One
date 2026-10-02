"""Live data importer for real, current draft data.

Sleeper's API (api.sleeper.app) is the intended live source, but some networks
(including the environment this was built in) block it at the egress policy
layer. The open-source **nflverse / dynastyprocess** projects publish real,
current fantasy data as CSVs on GitHub, and ``raw.githubusercontent.com`` is
almost always reachable — so this module pulls:

  * FantasyPros **redraft** Expert Consensus Rankings (ECR) — the actual
    consensus draft board, refreshed constantly, with bye weeks and ownership.
  * The nflverse/dynastyprocess **player-id crosswalk**, so every player carries
    their real ``sleeper_id`` and maps straight onto your Sleeper league.

We don't have a paid projections feed, so projected points are modeled from a
transparent **positional value curve** (documented in ``POINTS_ANCHORS``) keyed
on each player's positional ECR rank. That keeps the VBD/tiers math meaningful
and, crucially, keeps scoring a *variable*: pass the format and the curve shifts
(PPR rewards pass-catchers, standard doesn't). Swap in a real per-stat
projection CSV anytime and this becomes exact.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .http import get_json  # noqa: F401  (kept for parity; not used directly)
import urllib.request
import urllib.error

RAW = "https://raw.githubusercontent.com/dynastyprocess/data/master/files"
FPECR_URL = f"{RAW}/db_fpecr_latest.csv"
IDS_URL = f"{RAW}/db_playerids.csv"

OFFENSE = {"QB", "RB", "WR", "TE"}
OUT_DEFAULT = Path(__file__).parent.parent / "data" / "projections" / "fantasypros_live.csv"

# --- transparent positional points model (season totals) -------------------
# anchor (positional_rank, projected_points); linearly interpolated, flat past
# the last anchor. Three formats so scoring stays a variable.
POINTS_ANCHORS: Dict[str, Dict[str, List[Tuple[int, float]]]] = {
    "ppr": {
        "QB": [(1, 395), (6, 340), (12, 300), (18, 272), (24, 250), (32, 220)],
        "RB": [(1, 330), (3, 300), (6, 265), (12, 215), (18, 175), (24, 150), (36, 110), (48, 80)],
        "WR": [(1, 310), (3, 285), (6, 255), (12, 220), (18, 190), (24, 170), (36, 135), (48, 110), (60, 90)],
        "TE": [(1, 250), (3, 205), (6, 170), (12, 135), (18, 110), (24, 90)],
        "K": [(1, 155), (6, 140), (12, 125), (24, 110)],
        "DEF": [(1, 145), (6, 120), (12, 105), (24, 85)],
    },
    "half_ppr": {
        "QB": [(1, 395), (6, 340), (12, 300), (18, 272), (24, 250), (32, 220)],
        "RB": [(1, 305), (3, 278), (6, 245), (12, 198), (18, 160), (24, 137), (36, 100), (48, 72)],
        "WR": [(1, 278), (3, 255), (6, 227), (12, 194), (18, 167), (24, 148), (36, 116), (48, 94), (60, 76)],
        "TE": [(1, 218), (3, 178), (6, 147), (12, 116), (18, 94), (24, 76)],
        "K": [(1, 155), (6, 140), (12, 125), (24, 110)],
        "DEF": [(1, 145), (6, 120), (12, 105), (24, 85)],
    },
    "standard": {
        "QB": [(1, 395), (6, 340), (12, 300), (18, 272), (24, 250), (32, 220)],
        "RB": [(1, 285), (3, 258), (6, 227), (12, 182), (18, 146), (24, 125), (36, 90), (48, 64)],
        "WR": [(1, 246), (3, 224), (6, 198), (12, 168), (18, 144), (24, 127), (36, 98), (48, 78), (60, 62)],
        "TE": [(1, 188), (3, 152), (6, 124), (12, 97), (18, 78), (24, 62)],
        "K": [(1, 155), (6, 140), (12, 125), (24, 110)],
        "DEF": [(1, 145), (6, 120), (12, 105), (24, 85)],
    },
}


def _interp(anchors: List[Tuple[int, float]], rank: int) -> float:
    if rank <= anchors[0][0]:
        return anchors[0][1]
    for (r0, p0), (r1, p1) in zip(anchors, anchors[1:]):
        if r0 <= rank <= r1:
            frac = (rank - r0) / (r1 - r0)
            return p0 + (p1 - p0) * frac
    return anchors[-1][1]


# The Final Draft Lifegroup runs TE-premium scoring: TEs get +0.5 points per
# reception on top of base PPR. Estimated TE receptions by positional rank so we
# can add that premium to TE projections.
TE_REC_BONUS = 0.5
TE_REC_ANCHORS: List[Tuple[int, float]] = [
    (1, 90), (3, 76), (6, 66), (12, 52), (18, 42), (24, 32), (36, 22),
]


def points_for(pos: str, pos_rank: int, scoring: str = "ppr") -> float:
    table = POINTS_ANCHORS.get(scoring, POINTS_ANCHORS["ppr"])
    anchors = table.get(pos)
    if not anchors:
        return 0.0
    pts = _interp(anchors, pos_rank)
    if pos == "TE" and TE_REC_BONUS:
        pts += TE_REC_BONUS * _interp(TE_REC_ANCHORS, pos_rank)   # TE reception premium
    return round(pts, 1)


# --- fetching --------------------------------------------------------------
def _download_csv(url: str, timeout: int = 60) -> List[Dict[str, str]]:
    req = urllib.request.Request(url, headers={"User-Agent": "ffball/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        raise RuntimeError(
            f"Could not fetch {url}: {exc}. If raw.githubusercontent.com is also "
            "blocked here, run this on a network with open egress."
        ) from exc
    return list(csv.DictReader(io.StringIO(text)))


def _norm_name(s: str) -> str:
    return "".join(c for c in s.lower() if c.isalnum() or c == " ").strip()


def _build_sleeper_index(ids_rows: List[Dict[str, str]]):
    """Return (by_fpid, by_namepos) maps -> sleeper_id."""
    by_fpid: Dict[str, str] = {}
    by_namepos: Dict[str, str] = {}
    for r in ids_rows:
        sid = (r.get("sleeper_id") or "").strip()
        if not sid or sid.upper() == "NA":
            continue
        fpid = (r.get("fantasypros_id") or "").strip()
        if fpid and fpid.upper() != "NA":
            by_fpid[fpid] = sid
        mn = _norm_name(r.get("merge_name") or r.get("name") or "")
        pos = (r.get("position") or "").upper()
        if mn:
            by_namepos[f"{mn}|{pos}"] = sid
    return by_fpid, by_namepos


def fetch_board_rows(scoring: str = "ppr", superflex: bool = False) -> List[Dict[str, object]]:
    """Fetch + assemble real board rows (not yet written to disk).

    ``superflex`` uses FantasyPros' SUPERFLEX consensus (ecr_type 'rsf') for the
    overall draft ordering/ADP, which values QBs correctly (they go early), vs
    the 1-QB 'ro' list where QBs rank low.
    """
    fpecr = _download_csv(FPECR_URL)
    ids = _download_csv(IDS_URL)
    by_fpid, by_namepos = _build_sleeper_index(ids)

    # Offensive skill players from the consensus list — superflex or 1-QB overall.
    overall_type = "rsf" if superflex else "ro"
    offense = [
        r for r in fpecr
        if r.get("ecr_type") == overall_type and (r.get("pos") or "").upper() in OFFENSE
    ]
    # Kickers and defenses from their own redraft position lists.
    kickers = [r for r in fpecr if r.get("page_type") == "redraft-k"]
    defenses = [r for r in fpecr if r.get("page_type") == "redraft-dst"]

    def to_row(r: Dict[str, str]) -> Optional[Dict[str, object]]:
        try:
            ecr = float(r["ecr"])
        except (KeyError, ValueError):
            return None
        pos = (r.get("pos") or "").upper()
        if pos == "DST":
            pos = "DEF"
        fpid = (r.get("id") or "").strip()
        team = (r.get("tm") or r.get("team") or "").strip().upper()
        if pos == "DEF":
            # Sleeper keys team defenses by their team abbreviation.
            sid = team or None
        else:
            sid = by_fpid.get(fpid) or by_namepos.get(f"{_norm_name(r.get('player',''))}|{pos}")
        bye = r.get("bye")
        try:
            bye = int(float(bye)) if bye not in (None, "", "NA") else None
        except ValueError:
            bye = None
        return {
            "player_id": sid or f"fp{fpid}",     # real sleeper_id when known
            "sleeper_id": sid or "",
            "name": r.get("player"),
            "position": pos,
            "team": r.get("tm") or r.get("team") or "",
            "bye_week": bye,
            "ecr": ecr,
            "own": r.get("player_owned_avg") or "",
        }

    rows: List[Dict[str, object]] = []
    for group in (offense, kickers, defenses):
        parsed = [x for x in (to_row(r) for r in group) if x]
        rows.extend(parsed)

    # Positional rank by ECR within each position -> model points via the curve.
    by_pos: Dict[str, List[Dict[str, object]]] = {}
    for row in rows:
        by_pos.setdefault(row["position"], []).append(row)  # type: ignore[index]
    for pos, group in by_pos.items():
        group.sort(key=lambda x: x["ecr"])  # type: ignore[index,return-value]
        for i, row in enumerate(group, start=1):
            row["pos_rank"] = i
            row["fpts"] = points_for(pos, i, scoring)

    # Overall ADP proxy. Offense shares the true redraft-overall ECR scale, so
    # rank them by ECR. K and DEF are on their own per-position scales (each
    # starts at ECR 1), so they'd wrongly sort to the top — instead append them
    # after all offense (they're drafted last), K before DEF, by positional ECR.
    offense_rows = sorted(
        (r for r in rows if r["position"] in OFFENSE), key=lambda x: x["ecr"]  # type: ignore[index]
    )
    k_rows = sorted((r for r in rows if r["position"] == "K"), key=lambda x: x["ecr"])  # type: ignore[index]
    def_rows = sorted((r for r in rows if r["position"] == "DEF"), key=lambda x: x["ecr"])  # type: ignore[index]
    ordered = offense_rows + k_rows + def_rows
    for i, row in enumerate(ordered, start=1):
        row["adp"] = i
    return ordered


def write_projection_csv(rows: List[Dict[str, object]], out: Optional[Path] = None) -> Path:
    out = Path(out or OUT_DEFAULT)
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = ["player_id", "sleeper_id", "name", "position", "team",
              "bye_week", "adp", "fpts", "own"]
    with open(out, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return out


def fetch(scoring: str = "ppr", out: Optional[Path] = None,
          superflex: bool = False) -> Tuple[Path, int, int]:
    """Fetch real data and write a projection CSV. Returns (path, total, mapped)."""
    rows = fetch_board_rows(scoring=scoring, superflex=superflex)
    path = write_projection_csv(rows, out)
    mapped = sum(1 for r in rows if r.get("sleeper_id"))
    return path, len(rows), mapped
