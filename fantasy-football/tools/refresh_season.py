#!/usr/bin/env python3
"""Weekly in-season refresh for the Season Manager.

Pulls everything live from Sleeper and re-embeds a rich ``SEASON`` data blob
into webapp/draft_room.html so the Season Manager runs on current data:

  * current NFL week + season (Sleeper state)
  * every team's live roster (adds/drops included) + owner names
  * this week's head-to-head matchup pairings
  * exact weekly projections in THIS league's scoring (stat line x the league's
    148 scoring_settings, so the TE +0.5/catch premium is baked in)
  * rest-of-season totals (FantasyPros consensus via ffball.sources)
  * live injury_status flags and Sleeper trending-add counts (waiver hotness)

The published web page can't call Sleeper itself (sandbox blocks it), so this
script is the live feed: run it, then republish the artifact. Meant to run
weekly (Tue) via a scheduled routine.

Run:  python3 tools/refresh_season.py
"""
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from ffball import sources  # noqa: E402

LID = "1395483423719587840"
MY_OWNER = "GodModeEnabled"
HTML = ROOT / "webapp" / "draft_room.html"
SEASON_TAG = '<script id="season" type="application/json">'
OFFENSE = ("QB", "RB", "WR", "TE")


def _get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def weekly_points(stats: dict, scoring: dict) -> float:
    """Exact league score for a projected stat line = stats . scoring_settings."""
    return round(sum(float(v) * scoring[k] for k, v in stats.items()
                     if k in scoring and isinstance(v, (int, float))), 1)


def build_season() -> dict:
    state = _get("https://api.sleeper.app/v1/state/nfl")
    week, season = int(state["week"]) or 1, state["season"]

    league = _get(f"https://api.sleeper.app/v1/league/{LID}")
    scoring = league.get("scoring_settings", {})
    users = _get(f"https://api.sleeper.app/v1/league/{LID}/users")
    rosters = _get(f"https://api.sleeper.app/v1/league/{LID}/rosters")
    matchups = _get(f"https://api.sleeper.app/v1/league/{LID}/matchups/{week}")

    uname = {u["user_id"]: (u.get("metadata", {}).get("team_name") or u.get("display_name"))
             for u in users}
    owner_of = {r["roster_id"]: uname.get(r.get("owner_id"), f"Team {r['roster_id']}")
                for r in rosters}
    my_rid = next((r["roster_id"] for r in rosters
                   if uname.get(r.get("owner_id")) == MY_OWNER), None)

    # this-week opponent for each roster
    opp = {}
    by_mid: dict = {}
    for m in matchups:
        by_mid.setdefault(m.get("matchup_id"), []).append(m.get("roster_id"))
    for mid, rids in by_mid.items():
        if len(rids) == 2:
            opp[rids[0]], opp[rids[1]] = rids[1], rids[0]

    teams = {str(r["roster_id"]): {"owner": owner_of[r["roster_id"]],
                                   "players": [str(p) for p in (r.get("players") or [])]}
             for r in rosters}
    rostered = {pid for t in teams.values() for pid in t["players"]}

    # weekly projections in league scoring
    q = "&".join(f"position[]={p}" for p in OFFENSE)
    proj = _get(f"https://api.sleeper.com/projections/nfl/{season}/{week}"
                f"?season_type=regular&{q}&order_by=pts_ppr")
    wk = {}
    for pr in proj:
        pid = str(pr.get("player_id"))
        st = pr.get("stats") or {}
        wk[pid] = {"wk": weekly_points(st, scoring), "opp": pr.get("opponent") or "",
                   "team": pr.get("team") or ""}

    # rest-of-season totals + names/pos from the consensus board
    ros = {}
    for r in sources.fetch_board_rows(scoring="ppr", superflex=True):
        sid = str(r.get("sleeper_id") or r.get("player_id"))
        ros[sid] = {"name": r["name"], "pos": r["position"], "team": r["team"] or "",
                    "ros": r["fpts"], "bye": r["bye_week"]}

    # injuries + name fallback from the player DB; trending adds
    pdb = _get("https://api.sleeper.app/v1/players/nfl")
    trend = {str(t["player_id"]): t["count"]
             for t in _get("https://api.sleeper.app/v1/players/nfl/trending/add?limit=75")}

    # assemble the player map: everyone rostered, plus top free agents by weekly proj
    def meta(pid: str) -> dict:
        r = ros.get(pid, {})
        sp = pdb.get(pid, {})
        name = r.get("name") or sp.get("full_name") or \
            f"{sp.get('first_name','')} {sp.get('last_name','')}".strip() or pid
        pos = r.get("pos") or sp.get("position") or "NA"
        w = wk.get(pid, {})
        st = (sp.get("injury_status") or "").strip()
        d = {"name": name, "pos": pos, "team": w.get("team") or r.get("team") or "",
             "opp": w.get("opp", ""), "wk": w.get("wk", 0.0), "ros": r.get("ros", 0.0),
             "bye": r.get("bye")}
        if st and st.lower() not in ("", "healthy"):
            d["inj"] = ("Q" if st.lower() == "questionable" else st.upper())
        if pid in trend:
            d["trend"] = trend[pid]
        return d

    fa_ids = [pid for pid in wk if pid not in rostered and pid in ros]
    fa_ids.sort(key=lambda p: -wk[p]["wk"])
    fa_ids = fa_ids[:80]

    players = {pid: meta(pid) for pid in (rostered | set(fa_ids))}

    return {
        "week": week, "season": season, "updated": date.today().isoformat(),
        "myRoster": my_rid, "myOwner": MY_OWNER,
        "teams": teams, "opp": {str(k): v for k, v in opp.items()},
        "players": players, "freeAgents": fa_ids,
        "mine": teams[str(my_rid)]["players"] if my_rid else [],
        "drafted": sorted(rostered),
    }


def main() -> None:
    season = build_season()
    payload = json.dumps(season, separators=(",", ":"))
    html = HTML.read_text(encoding="utf-8")
    if SEASON_TAG not in html:
        raise SystemExit("season <script> block not found in HTML — add the placeholder first.")
    start = html.index(SEASON_TAG) + len(SEASON_TAG)
    end = html.index("</script>", start)
    HTML.write_text(html[:start] + payload + html[end:], encoding="utf-8")
    print(f"Refreshed Season Manager: Week {season['week']} {season['season']} · "
          f"{len(season['teams'])} teams · {len(season['players'])} players · "
          f"{len(season['freeAgents'])} FAs · your Wk{season['week']} opp = "
          f"{season['teams'].get(str(season['opp'].get(str(season['myRoster']))), {}).get('owner','?')}")


if __name__ == "__main__":
    main()
