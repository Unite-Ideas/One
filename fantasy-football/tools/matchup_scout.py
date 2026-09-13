#!/usr/bin/env python3
"""Adversarial matchup scout: your team vs this week's opponent (any platform).

Reads the league's live SEASON blob plus each team's actual set starters (via
the pluggable adapter) and surfaces your optimal lineup vs the opponent's,
positional head-to-head, the opponent's mistakes (points left on their bench,
injured/bye players still starting), and the NFL games both sides are in so a
web layer can add Vegas odds / weather / news.

Run:  python3 tools/matchup_scout.py [week] [league_key]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from ffball.league import LeagueConfig            # noqa: E402
from ffball.leagues import get_league             # noqa: E402
from ffball.models import Player                  # noqa: E402
from ffball.season import optimal_lineup          # noqa: E402


def load_season(html_path: Path) -> dict:
    m = re.search(r'<script id="season" type="application/json">(.*?)</script>',
                  html_path.read_text(encoding="utf-8"), re.S)
    return json.loads(m.group(1))


def mk(ids, players, key="wk"):
    out = []
    for i in ids:
        d = players.get(str(i))
        if not d:
            continue
        p = Player(str(i), d["name"], d["pos"])
        p.proj_points = d.get(key, 0) or 0
        p.bye_week = 0
        out.append(p)
    return out


def describe(ids, players):
    rows = []
    for i in ids:
        d = players.get(str(i), {})
        rows.append({"id": str(i), "name": d.get("name", str(i)), "pos": d.get("pos", "?"),
                     "team": d.get("team", ""), "opp": d.get("opp", ""),
                     "wk": d.get("wk", 0), "inj": d.get("inj", "")})
    return rows


def scout(week: int | None = None, key: str = "sleeper-finaldraft") -> dict:
    lg = get_league(key)
    src = lg.source()
    html_path = ROOT / lg.cfg.get("artifact_file", "webapp/draft_room.html")
    S = load_season(html_path)
    week = week or S["week"]
    players = S["players"]
    league = LeagueConfig.from_sleeper_league(src.league())
    my_rid = S["myRoster"]
    opp_rid = S["opp"].get(str(my_rid))
    if opp_rid is None:
        return {"error": "No opponent found for this week."}

    set_starters = {m["roster_id"]: m["starters"] for m in src.matchups(week)}
    me = S["teams"][str(my_rid)]
    opp = S["teams"][str(opp_rid)]
    my_opt = optimal_lineup(mk(me["players"], players), league)
    opp_opt = optimal_lineup(mk(opp["players"], players), league)

    opp_set = set_starters.get(opp_rid, [])
    opp_mistakes = {}
    if opp_set:
        set_total = round(sum((players.get(i, {}).get("wk", 0) or 0) for i in opp_set), 1)
        opt_ids = [p.player_id for _, p in opp_opt.starters if p]
        benched_better = [i for i in opt_ids if i not in opp_set]
        started_weak = [i for i in opp_set if i not in opt_ids]
        dead = [i for i in opp_set if (players.get(i, {}).get("inj", "") not in ("", "Q"))]
        opp_mistakes = {
            "set_projected": set_total, "optimal_projected": opp_opt.total,
            "points_left_on_bench": round(opp_opt.total - set_total, 1),
            "should_start_but_benched": describe(benched_better, players),
            "starting_but_suboptimal": describe(started_weak, players),
            "injured_still_starting": describe(dead, players),
        }

    def pos_strength(team_players):
        agg = {}
        for i in team_players:
            d = players.get(i, {})
            agg.setdefault(d.get("pos", "?"), []).append(d.get("wk", 0) or 0)
        return {k: round(sum(sorted(v, reverse=True)[:2]), 1) for k, v in agg.items()}

    def games(team_players):
        g = set()
        for i in team_players:
            d = players.get(i, {})
            if d.get("team") and d.get("opp"):
                g.add(f"{d['team']} vs {d['opp']}")
        return sorted(g)

    return {
        "week": week, "league": lg.name,
        "me": {"owner": me["owner"], "optimal_total": my_opt.total,
               "starters": describe([p.player_id for _, p in my_opt.starters if p], players),
               "pos_strength": pos_strength(me["players"]), "games": games(me["players"])},
        "opponent": {"owner": opp["owner"], "optimal_total": opp_opt.total,
                     "starters": describe([p.player_id for _, p in opp_opt.starters if p], players),
                     "pos_strength": pos_strength(opp["players"]), "games": games(opp["players"]),
                     "mistakes": opp_mistakes},
        "projected_margin": round(my_opt.total - opp_opt.total, 1),
    }


def main() -> None:
    wk = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else None
    key = next((a for a in sys.argv[1:] if not a.isdigit()), "sleeper-finaldraft")
    print(json.dumps(scout(wk, key), indent=2))


if __name__ == "__main__":
    main()
