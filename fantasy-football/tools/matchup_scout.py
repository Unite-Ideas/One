#!/usr/bin/env python3
"""Adversarial matchup scout: your team vs this week's opponent.

Builds the structured half of a "how to smash them" report. It reads the live
SEASON blob (already refreshed from Sleeper) plus each team's ACTUAL set
starters, and surfaces:

  * your optimal lineup vs your opponent's optimal lineup (projected score),
  * your opponent's MISTAKES — points they're leaving on their bench, and any
    injured / bye player still sitting in their starting slots (free points),
  * both sides' key players and the exact NFL games they're in, so a web layer
    can pull Vegas totals / weather / breaking news for each game.

The numbers come from here; the web intel (odds, news, weather) is added by the
Claude session that runs this in the weekly routine. Prints a JSON brief.

Run:  python3 tools/matchup_scout.py [week]
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from ffball.league import LeagueConfig            # noqa: E402
from ffball.models import Player                  # noqa: E402
from ffball.season import lineup_slots, optimal_lineup  # noqa: E402

LID = "1395483423719587840"
HTML = ROOT / "webapp" / "draft_room.html"


def _get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def load_season() -> dict:
    m = re.search(r'<script id="season" type="application/json">(.*?)</script>',
                  HTML.read_text(encoding="utf-8"), re.S)
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
    """Human-readable player rows with matchup + status."""
    rows = []
    for i in ids:
        d = players.get(str(i), {})
        rows.append({"id": str(i), "name": d.get("name", str(i)), "pos": d.get("pos", "?"),
                     "team": d.get("team", ""), "opp": d.get("opp", ""),
                     "wk": d.get("wk", 0), "inj": d.get("inj", "")})
    return rows


def scout(week: int | None = None) -> dict:
    S = load_season()
    week = week or S["week"]
    players = S["players"]
    league = LeagueConfig.from_sleeper_league(_get(f"https://api.sleeper.app/v1/league/{LID}"))
    my_rid = S["myRoster"]
    opp_rid = S["opp"].get(str(my_rid))
    if opp_rid is None:
        return {"error": "No opponent found for this week."}

    matchups = _get(f"https://api.sleeper.app/v1/league/{LID}/matchups/{week}")
    set_starters = {m["roster_id"]: [str(x) for x in (m.get("starters") or []) if x and x != "0"]
                    for m in matchups}

    me = S["teams"][str(my_rid)]
    opp = S["teams"][str(opp_rid)]

    my_opt = optimal_lineup(mk(me["players"], players), league)
    opp_opt = optimal_lineup(mk(opp["players"], players), league)

    # opponent mistakes: set lineup vs optimal
    opp_set = set_starters.get(opp_rid, [])
    opp_mistakes = []
    if opp_set:
        set_total = round(sum((players.get(i, {}).get("wk", 0) or 0) for i in opp_set), 1)
        opt_ids = [p.player_id for _, p in opp_opt.starters if p]
        # players they're starting who are injured/on a bad slot, or benched studs
        benched_better = [i for i in opt_ids if i not in opp_set]
        started_weak = [i for i in opp_set if i not in opt_ids]
        dead = [i for i in opp_set if (players.get(i, {}).get("inj", "") not in ("", "Q"))]
        opp_mistakes = {
            "set_projected": set_total,
            "optimal_projected": opp_opt.total,
            "points_left_on_bench": round(opp_opt.total - set_total, 1),
            "should_start_but_benched": describe(benched_better, players),
            "starting_but_suboptimal": describe(started_weak, players),
            "injured_still_starting": describe(dead, players),
        }

    # positional head-to-head (best 2 per spot, weekly)
    def pos_strength(team_players):
        agg = {}
        for i in team_players:
            d = players.get(i, {})
            agg.setdefault(d.get("pos", "?"), []).append(d.get("wk", 0) or 0)
        return {k: round(sum(sorted(v, reverse=True)[:2]), 1) for k, v in agg.items()}

    # all NFL games involved (for the web layer to fetch odds/weather)
    def games(team_players):
        g = set()
        for i in team_players:
            d = players.get(i, {})
            if d.get("team") and d.get("opp"):
                g.add(f"{d['team']} vs {d['opp']}")
        return sorted(g)

    return {
        "week": week,
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
    wk = int(sys.argv[1]) if len(sys.argv) > 1 else None
    print(json.dumps(scout(wk), indent=2))


if __name__ == "__main__":
    main()
