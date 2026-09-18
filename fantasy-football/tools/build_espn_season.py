#!/usr/bin/env python3
"""Build a live SEASON blob for an ESPN private league and embed it in its web app.

ESPN exposes projected points already in the league's own scoring (weekly and
rest-of-season), so no external projections are needed. Requires the account's
read cookies via env: ESPN_S2 and ESPN_SWID. Cookies are never written to disk
or committed — pass them at runtime.

Run:  ESPN_S2=... ESPN_SWID='{...}' python3 tools/build_espn_season.py lauren
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from tools.refresh_season import build_games, _abbr   # NFL-wide odds/schedule (public)  # noqa: E402

SEASON_TAG = '<script id="season" type="application/json">'
POS = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DEF"}
PROTEAM = {1: "ATL", 2: "BUF", 3: "CHI", 4: "CIN", 5: "CLE", 6: "DAL", 7: "DEN", 8: "DET",
           9: "GB", 10: "TEN", 11: "IND", 12: "KC", 13: "LV", 14: "LAR", 15: "MIA", 16: "MIN",
           17: "NE", 18: "NO", 19: "NYG", 20: "NYJ", 21: "PHI", 22: "ARI", 23: "PIT", 24: "LAC",
           25: "SF", 26: "SEA", 27: "TB", 28: "WAS", 29: "CAR", 30: "JAX", 33: "BAL", 34: "HOU"}

# One entry per ESPN league we run.
CONFIGS = {
    "lauren": {"league_id": "632127067", "season": "2026", "my_team_id": 19,
               "my_owner": "Lauren's Loud Team", "artifact_file": "webapp/draft_room_lauren.html"},
}


def _cookies():
    s2, swid = os.environ.get("ESPN_S2"), os.environ.get("ESPN_SWID")
    if not (s2 and swid):
        raise SystemExit("Set ESPN_S2 and ESPN_SWID in the environment (never commit them).")
    return f"SWID={swid}; espn_s2={s2}"


def _get(url: str, cookie: str, filt: dict | None = None):
    h = {"User-Agent": "Mozilla/5.0", "Cookie": cookie}
    if filt is not None:
        h["x-fantasy-filter"] = json.dumps(filt)
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=60))


def _proj(stats, week, season):
    """(weekly, rest-of-season) projected points in league scoring from a stats list."""
    wk = ros = 0.0
    for s in stats or []:
        if s.get("statSourceId") != 1 or str(s.get("seasonId")) != str(season):
            continue
        if s.get("statSplitTypeId") == 1 and s.get("scoringPeriodId") == week:
            wk = round(s.get("appliedTotal", 0.0), 1)
        elif s.get("statSplitTypeId") == 0 and s.get("scoringPeriodId") == 0:
            ros = round(s.get("appliedTotal", 0.0), 1)
    return wk, ros


def build(cfg) -> dict:
    ck = _cookies()
    LID, season, my_tid = cfg["league_id"], cfg["season"], cfg["my_team_id"]
    base = f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/segments/0/leagues/{LID}"
    d = _get(base + "?view=mSettings&view=mTeam&view=mRoster&view=mMatchup", ck)
    week = int(d.get("status", {}).get("currentMatchupPeriod") or 1)
    settings = d.get("settings", {})
    games = build_games(week, season)

    teams, players = {}, {}
    for t in d.get("teams", []):
        tid = t["id"]
        owner = (t.get("name") or f"Team {tid}").strip()
        ids = []
        for e in t.get("roster", {}).get("entries", []):
            pp = e["playerPoolEntry"]["player"]
            pid = str(pp["id"])
            ids.append(pid)
            team = PROTEAM.get(pp.get("proTeamId"), "")
            g = games.get(_abbr(team)) if team else None
            wk, ros = _proj(pp.get("stats"), week, season)
            inj = (pp.get("injuryStatus") or "").upper()
            inj = "" if inj in ("", "ACTIVE", "NORMAL") else ("Q" if inj == "QUESTIONABLE" else inj)
            players[pid] = {"name": pp.get("fullName", pid), "pos": POS.get(pp.get("defaultPositionId"), "NA"),
                            "team": team, "opp": (g or {}).get("opp", ""), "wk": wk, "ros": ros,
                            "bye": None, **({"inj": inj} if inj else {})}
        teams[str(tid)] = {"owner": owner, "players": ids}

    # this-week opponents + full schedule/records from ESPN's schedule
    opp, schedule, records = {}, {}, {}
    for m in d.get("schedule", []):
        wkn = m.get("matchupPeriodId")
        a, b = m.get("home", {}), m.get("away", {})
        if not a or not b or "teamId" not in a or "teamId" not in b:
            continue
        ap, bp = round(a.get("totalPoints") or 0, 2), round(b.get("totalPoints") or 0, 2)
        final = wkn < week
        schedule.setdefault(str(wkn), []).append({"a": a["teamId"], "b": b["teamId"],
                                                  "a_pts": ap, "b_pts": bp, "final": final})
        for tid in (a["teamId"], b["teamId"]):
            records.setdefault(tid, {"w": 0, "l": 0, "t": 0, "pf": 0.0})
        if wkn == week:
            opp[a["teamId"]], opp[b["teamId"]] = b["teamId"], a["teamId"]
        if final:
            records[a["teamId"]]["pf"] += ap; records[b["teamId"]]["pf"] += bp
            if ap > bp: records[a["teamId"]]["w"] += 1; records[b["teamId"]]["l"] += 1
            elif bp > ap: records[b["teamId"]]["w"] += 1; records[a["teamId"]]["l"] += 1
            else: records[a["teamId"]]["t"] += 1; records[b["teamId"]]["t"] += 1
    for r in records.values():
        r["pf"] = round(r["pf"], 1)

    # free agents: top available by rest-of-season projection
    rostered = {pid for t in teams.values() for pid in t["players"]}
    filt = {"players": {"filterStatus": {"value": ["FREEAGENT", "WAIVERS"]},
                        "limit": 120, "offset": 0,
                        "sortDraftRanks": {"sortPriority": 1, "sortAsc": True, "value": "PPR"}}}
    fa = _get(base + "?view=kona_player_info", ck, filt)
    fa_ids = []
    for pe in (fa.get("players") or []):
        pp = pe.get("player", {})
        pid = str(pp.get("id"))
        if pid in rostered or POS.get(pp.get("defaultPositionId")) is None:
            continue
        team = PROTEAM.get(pp.get("proTeamId"), "")
        g = games.get(_abbr(team)) if team else None
        wk, ros = _proj(pp.get("stats"), week, season)
        players[pid] = {"name": pp.get("fullName", pid), "pos": POS.get(pp.get("defaultPositionId"), "NA"),
                        "team": team, "opp": (g or {}).get("opp", ""), "wk": wk, "ros": ros, "bye": None,
                        **({"trend": int(round(pp.get("ownership", {}).get("percentOwned", 0)))} if pp.get("ownership") else {})}
        fa_ids.append((ros, pid))
    fa_ids = [pid for _, pid in sorted(fa_ids, reverse=True)[:80]]

    return {
        "week": week, "season": season, "updated": date.today().isoformat(),
        "myRoster": my_tid, "myOwner": cfg["my_owner"],
        "teams": teams, "opp": {str(k): v for k, v in opp.items()},
        "players": players, "freeAgents": fa_ids, "games": games,
        "schedule": schedule, "records": {str(k): v for k, v in records.items()},
        "playoffStart": int(settings.get("scheduleSettings", {}).get("matchupPeriodCount", 14)) + 1,
        "playoffTeams": int(settings.get("scheduleSettings", {}).get("playoffTeamCount", 4)),
        "mine": teams[str(my_tid)]["players"], "drafted": sorted(rostered),
    }


def main():
    key = sys.argv[1] if len(sys.argv) > 1 else "lauren"
    cfg = CONFIGS[key]
    blob = build(cfg)
    payload = json.dumps(blob, separators=(",", ":"))
    html_path = ROOT / cfg["artifact_file"]
    html = html_path.read_text(encoding="utf-8")
    start = html.index(SEASON_TAG) + len(SEASON_TAG)
    end = html.index("</script>", start)
    html_path.write_text(html[:start] + payload + html[end:], encoding="utf-8")
    opp_owner = blob["teams"].get(str(blob["opp"].get(str(blob["myRoster"]))), {}).get("owner", "?")
    print(f"Built ESPN season [{key}]: Week {blob['week']} · {len(blob['teams'])} teams · "
          f"{len(blob['players'])} players · {len(blob['freeAgents'])} FAs · "
          f"Wk{blob['week']} opp = {opp_owner}")


if __name__ == "__main__":
    main()
