#!/usr/bin/env python3
"""Rebuild the standalone Draft War Room web app with fresh rankings.

Pulls current FantasyPros consensus (via ffball.sources, which reads GitHub-
hosted nflverse/dynastyprocess CSVs) for all three scoring formats, merges them
into one board (pts_ppr / pts_half_ppr / pts_standard + id/name/pos/team/bye/adp),
and re-embeds it into webapp/draft_room.html by replacing the <script id="data">
block. The page's meta defaults stay tuned to the real league (10-team, PPR).

Run:  python3 tools/build_webapp.py
This is what the scheduled pre-draft refresh routine executes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))   # so `ffball` imports whether run from repo root or tools/

from ffball import sources
HTML = ROOT / "webapp" / "draft_room.html"
DATA_TAG = '<script id="data" type="application/json">'
META = {"scoring": "ppr", "teams": 10}   # The Final Draft Lifegroup defaults


def build_board() -> list:
    merged: dict = {}
    order: list = []
    for sc in ("ppr", "half_ppr", "standard"):
        for r in sources.fetch_board_rows(scoring=sc, superflex=True):  # this league is superflex
            pid = r["player_id"]
            if pid not in merged:
                merged[pid] = {
                    "id": pid, "name": r["name"], "pos": r["position"],
                    "team": r["team"] or "", "bye": r["bye_week"], "adp": r["adp"],
                }
                order.append(pid)
            merged[pid]["pts_" + sc] = r["fpts"]
    return [merged[p] for p in order]


def main() -> None:
    board = build_board()
    payload = json.dumps({"meta": META, "board": board})
    html = HTML.read_text(encoding="utf-8")
    start = html.index(DATA_TAG) + len(DATA_TAG)
    end = html.index("</script>", start)
    html = html[:start] + payload + html[end:]
    HTML.write_text(html, encoding="utf-8")
    print(f"Rebuilt {HTML.name} with {len(board)} players (meta={META}).")


if __name__ == "__main__":
    main()
