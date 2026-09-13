#!/usr/bin/env python3
"""Generate a SYNTHETIC sample projections CSV for offline dev/demo.

These are NOT real forecasts. Names are well-known players so the demo reads
naturally, but every stat line is procedurally generated from a smooth
rank-based curve — do not use these numbers for an actual draft. Replace with
real projection CSVs in data/projections/ before draft day.

Run:  python3 tools/make_sample.py
Writes: data/sample/projections.csv
"""
from __future__ import annotations

import csv
from pathlib import Path

OUT = Path(__file__).parent.parent / "data" / "sample" / "projections.csv"

# A pool deep enough that 12-team replacement baselines are meaningful.
QBS = [
    "Josh Allen", "Jalen Hurts", "Lamar Jackson", "Jayden Daniels",
    "Patrick Mahomes", "Joe Burrow", "C.J. Stroud", "Justin Herbert",
    "Dak Prescott", "Jordan Love", "Kyler Murray", "Brock Purdy",
    "Caleb Williams", "Bo Nix", "Trevor Lawrence", "Anthony Richardson",
]
RBS = [
    "Bijan Robinson", "Saquon Barkley", "Jahmyr Gibbs", "Christian McCaffrey",
    "Ashton Jeanty", "De'Von Achane", "Derrick Henry", "Josh Jacobs",
    "Jonathan Taylor", "Bucky Irving", "Kyren Williams", "Chase Brown",
    "James Cook", "Breece Hall", "Kenneth Walker", "Alvin Kamara",
    "Joe Mixon", "Chuba Hubbard", "James Conner", "David Montgomery",
    "Aaron Jones", "D'Andre Swift", "Tony Pollard", "Isiah Pacheco",
    "Rhamondre Stevenson", "Zamir White", "Brian Robinson", "Najee Harris",
    "Rachaad White", "Jaylen Warren", "Tyjae Spears", "Javonte Williams",
]
WRS = [
    "Ja'Marr Chase", "Justin Jefferson", "CeeDee Lamb", "Amon-Ra St. Brown",
    "Puka Nacua", "Malik Nabers", "Nico Collins", "Brian Thomas Jr.",
    "A.J. Brown", "Drake London", "Ladd McConkey", "Jaylen Waddle",
    "Tee Higgins", "Davante Adams", "Mike Evans", "Terry McLaurin",
    "DK Metcalf", "Garrett Wilson", "Marvin Harrison Jr.", "DJ Moore",
    "Zay Flowers", "Xavier Worthy", "DeVonta Smith", "Jaxon Smith-Njigba",
    "Chris Olave", "Rome Odunze", "Jordan Addison", "Calvin Ridley",
    "Cooper Kupp", "Jerry Jeudy", "Courtland Sutton", "Jameson Williams",
]
TES = [
    "Brock Bowers", "Trey McBride", "George Kittle", "Sam LaPorta",
    "T.J. Hockenson", "Travis Kelce", "Mark Andrews", "David Njoku",
    "Dallas Goedert", "Evan Engram", "Jonnu Smith", "Kyle Pitts",
    "Dalton Kincaid", "Tucker Kraft", "Jake Ferguson",
]
KS = ["Brandon Aubrey", "Harrison Butker", "Jake Bates", "Chris Boswell",
      "Ka'imi Fairbairn", "Jason Sanders", "Cameron Dicker", "Younghoe Koo"]
DEFS = ["Ravens", "Broncos", "Eagles", "Bills", "Steelers", "Texans",
        "Chiefs", "Vikings", "Lions", "Packers"]

# Rotate byes deterministically so bye-balancing has something to chew on.
BYES = [5, 6, 7, 8, 9, 10, 11, 12, 14]


def bye_for(i: int) -> int:
    return BYES[i % len(BYES)]


def lerp(top: float, bottom: float, i: int, n: int) -> float:
    if n <= 1:
        return top
    return top + (bottom - top) * (i / (n - 1))


def slug(name: str) -> str:
    return name.lower().replace("'", "").replace(".", "").replace(" ", "-")


def qb_row(name, i, n):
    return dict(
        pass_yd=round(lerp(4750, 3300, i, n)),
        pass_td=round(lerp(41, 17, i, n)),
        pass_int=round(lerp(7, 13, i, n)),
        rush_yd=round(lerp(520, 60, i, n)),
        rush_td=round(lerp(5, 1, i, n), 1),
        fum_lost=round(lerp(2, 4, i, n)),
    )


def rb_row(name, i, n):
    return dict(
        rush_yd=round(lerp(1425, 480, i, n)),
        rush_td=round(lerp(12, 3, i, n), 1),
        rec=round(lerp(62, 18, i, n)),
        rec_yd=round(lerp(520, 110, i, n)),
        rec_td=round(lerp(3, 0, i, n), 1),
        fum_lost=round(lerp(1, 2, i, n)),
    )


def wr_row(name, i, n):
    return dict(
        rec=round(lerp(104, 44, i, n)),
        rec_yd=round(lerp(1480, 610, i, n)),
        rec_td=round(lerp(11, 3, i, n), 1),
        rush_yd=round(lerp(60, 0, i, n)),
    )


def te_row(name, i, n):
    return dict(
        rec=round(lerp(88, 30, i, n)),
        rec_yd=round(lerp(1020, 320, i, n)),
        rec_td=round(lerp(8, 2, i, n), 1),
    )


def main() -> None:
    rows = []
    adp_counter = 1  # rough overall ADP by interleaving positions

    def add(name, pos, stats=None, fpts=None, i=0, n=1):
        nonlocal adp_counter
        row = {
            "player_id": slug(name) if pos != "DEF" else name,
            "name": name if pos != "DEF" else f"{name} DEF",
            "position": pos,
            "team": "",
            "bye_week": bye_for(i),
        }
        if stats:
            row.update(stats)
        if fpts is not None:
            row["fpts"] = fpts
        rows.append(row)

    n = len(QBS)
    for i, nm in enumerate(QBS):
        add(nm, "QB", stats=qb_row(nm, i, n), i=i)
    n = len(RBS)
    for i, nm in enumerate(RBS):
        add(nm, "RB", stats=rb_row(nm, i, n), i=i)
    n = len(WRS)
    for i, nm in enumerate(WRS):
        add(nm, "WR", stats=wr_row(nm, i, n), i=i)
    n = len(TES)
    for i, nm in enumerate(TES):
        add(nm, "TE", stats=te_row(nm, i, n), i=i)
    n = len(KS)
    for i, nm in enumerate(KS):
        add(nm, "K", fpts=round(lerp(165, 120, i, n)), i=i)
    n = len(DEFS)
    for i, nm in enumerate(DEFS):
        add(nm, "DEF", fpts=round(lerp(150, 95, i, n)), i=i)

    # Assign a rough ADP by descending projected-ish order within the CSV:
    # skill players first (already roughly ranked), then K/DEF late.
    # Real ADP should come from data/adp/*.csv; this is only a sensible default.
    for idx, row in enumerate(_adp_order(rows), start=1):
        row["adp"] = idx

    fieldnames = [
        "player_id", "name", "position", "team", "bye_week", "adp",
        "pass_yd", "pass_td", "pass_int", "rush_yd", "rush_td",
        "rec", "rec_yd", "rec_td", "fum_lost", "fpts",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    print(f"Wrote {len(rows)} synthetic players -> {OUT}")


def _adp_order(rows):
    """Interleave positions into a plausible overall draft order.

    Roughly: rounds pull top RBs/WRs first, QBs/TEs sprinkled, K/DEF last.
    """
    by_pos = {p: [r for r in rows if r["position"] == p] for p in
              ["RB", "WR", "QB", "TE", "K", "DEF"]}
    order = []
    # Weighted round-robin: lots of RB/WR early, QB/TE trickle, K/DEF at the end.
    pattern = ["RB", "WR", "WR", "RB", "TE", "WR", "RB", "QB", "WR", "RB"]
    idx = {p: 0 for p in by_pos}
    while any(idx[p] < len(by_pos[p]) for p in ["RB", "WR", "QB", "TE"]):
        for p in pattern:
            if idx[p] < len(by_pos[p]):
                order.append(by_pos[p][idx[p]])
                idx[p] += 1
    # Remaining QB/TE, then K, then DEF.
    for p in ["QB", "TE", "RB", "WR", "K", "DEF"]:
        while idx[p] < len(by_pos[p]):
            order.append(by_pos[p][idx[p]])
            idx[p] += 1
    return order


if __name__ == "__main__":
    main()
