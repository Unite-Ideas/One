#!/usr/bin/env python3
"""Weekly in-season refresh for the Season Manager (platform-agnostic).

Pulls a league's live data through its pluggable adapter (Sleeper today, ESPN
later) and re-embeds a rich ``SEASON`` blob into that league's web app so the
Season Manager runs on current data:

  * current NFL week + season
  * every team's live roster + owner names
  * this week's head-to-head matchups + the full-season schedule/standings
  * exact weekly projections in THIS league's scoring (TE premium etc. honored)
  * rest-of-season totals (FantasyPros consensus via ffball.sources)
  * injury flags and trending-add counts
  * this week's NFL games + Vegas lines (ESPN CDN scoreboard — NFL-wide, shared)

The published web page can't call the platform itself, so this is the live
feed: run it, then republish the artifact.

Run:  python3 tools/refresh_season.py [league_key]   (default: sleeper-finaldraft)
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from ffball import sources                       # noqa: E402
from ffball.adapters import http_json            # noqa: E402
from ffball.leagues import get_league            # noqa: E402

SEASON_TAG = '<script id="season" type="application/json">'

# ESPN team abbreviations differ from the projection feed's in a couple spots.
ESPN2SLEEPER = {"WSH": "WAS", "JAC": "JAX", "LA": "LAR"}


def _abbr(a: str) -> str:
    return ESPN2SLEEPER.get(a, a)


def build_games(week: int, season: str) -> dict:
    """This week's NFL games (kickoff, venue, Vegas line/total) keyed by team.
    NFL-wide data (not platform-specific), from ESPN's CDN scoreboard mirror."""
    url = (f"https://cdn.espn.com/core/nfl/scoreboard?xhr=1&limit=50"
           f"&week={week}&year={season}&seasontype=2")
    try:
        data = http_json(url)
    except Exception:
        return {}
    sb = data.get("content", {}).get("sbData", {}) or data.get("content", {}).get("scoreboard", {})
    games: dict = {}
    for ev in sb.get("events", []):
        try:
            comp = ev["competitions"][0]
            sides = {x["homeAway"]: x for x in comp["competitors"]}
            home = _abbr(sides["home"]["team"]["abbreviation"])
            away = _abbr(sides["away"]["team"]["abbreviation"])
            ven = comp.get("venue", {}) or {}
            addr = ven.get("address", {}) or {}
            city = ", ".join(x for x in (addr.get("city"), addr.get("state") or addr.get("country")) if x)
            kick = ""
            try:
                dt = datetime.fromisoformat(ev["date"].replace("Z", "+00:00")).astimezone(timezone.utc)
                kick = (dt - timedelta(hours=4)).strftime("%a %-I:%M %p ET")
            except Exception:
                pass
            odds = (comp.get("odds") or [{}])[0]
            details = odds.get("details") or ""
            total = odds.get("overUnder")
            fav, spread = "", None
            parts = details.split()
            if len(parts) == 2:
                try:
                    fav, spread = _abbr(parts[0]), abs(float(parts[1]))
                except ValueError:
                    fav, spread = "", None
            for team, opp, is_home in ((home, away, True), (away, home, False)):
                implied = None
                if total is not None and spread is not None and fav:
                    half = float(total) / 2
                    implied = round(half + (spread / 2 if team == fav else -spread / 2), 1)
                games[team] = {"opp": opp, "home": is_home, "kick": kick,
                               "venue": ven.get("fullName", ""), "city": city,
                               "fav": fav, "spread": spread, "total": total, "implied": implied}
        except Exception:
            continue
    return games


def build_league(src, week_now: int, playoff_start: int = 15) -> tuple:
    """Full-season schedule + standings via the adapter's matchups."""
    schedule: dict = {}
    records: dict = {}
    for wk in range(1, playoff_start):
        try:
            mus = src.matchups(wk)
        except Exception:
            continue
        by_mid: dict = {}
        for m in mus:
            by_mid.setdefault(m.get("matchup_id"), []).append(m)
        final = wk < week_now
        entries = []
        for _, pair in by_mid.items():
            if len(pair) != 2:
                continue
            a, b = pair
            ap, bp = a["points"], b["points"]
            entries.append({"a": a["roster_id"], "b": b["roster_id"],
                            "a_pts": ap, "b_pts": bp, "final": final})
            for rid in (a["roster_id"], b["roster_id"]):
                records.setdefault(rid, {"w": 0, "l": 0, "t": 0, "pf": 0.0})
            if final:
                records[a["roster_id"]]["pf"] += ap
                records[b["roster_id"]]["pf"] += bp
                if ap > bp:
                    records[a["roster_id"]]["w"] += 1; records[b["roster_id"]]["l"] += 1
                elif bp > ap:
                    records[b["roster_id"]]["w"] += 1; records[a["roster_id"]]["l"] += 1
                else:
                    records[a["roster_id"]]["t"] += 1; records[b["roster_id"]]["t"] += 1
        schedule[str(wk)] = entries
    for r in records.values():
        r["pf"] = round(r["pf"], 1)
    return schedule, records


def build_season(lg) -> dict:
    src = lg.source()
    st = src.state()
    week, season = st["week"], st["season"]
    league = src.league()
    scoring = league.get("scoring_settings", {})
    settings = league.get("settings", {}) or {}

    roster_list = src.rosters()
    owner_of = {r["roster_id"]: r["owner"] for r in roster_list}
    my_rid = next((r["roster_id"] for r in roster_list if r["owner"] == lg.my_owner), None)
    teams = {str(r["roster_id"]): {"owner": r["owner"], "players": r["players"]} for r in roster_list}
    rostered = {pid for r in roster_list for pid in r["players"]}

    # this-week opponent for each roster
    opp = {}
    by_mid: dict = {}
    for m in src.matchups(week):
        by_mid.setdefault(m.get("matchup_id"), []).append(m["roster_id"])
    for _, rids in by_mid.items():
        if len(rids) == 2:
            opp[rids[0]], opp[rids[1]] = rids[1], rids[0]

    wk = src.weekly_projections(season, week, scoring)
    ros = {}
    for r in sources.fetch_board_rows(scoring="ppr", superflex=True):
        sid = str(r.get("sleeper_id") or r.get("player_id"))
        ros[sid] = {"name": r["name"], "pos": r["position"], "team": r["team"] or "",
                    "ros": r["fpts"], "bye": r["bye_week"]}
    pmeta = src.player_meta()
    trend = src.trending()

    def meta(pid: str) -> dict:
        r = ros.get(pid, {})
        pm = pmeta.get(pid, {})
        w = wk.get(pid, {})
        d = {"name": r.get("name") or pm.get("name") or pid,
             "pos": r.get("pos") or pm.get("pos") or "NA",
             "team": w.get("team") or r.get("team") or "",
             "opp": w.get("opp", ""), "wk": w.get("wk", 0.0),
             "ros": r.get("ros", 0.0), "bye": r.get("bye")}
        if pm.get("injury"):
            d["inj"] = pm["injury"]
        if pid in trend:
            d["trend"] = trend[pid]
        return d

    fa_ids = [pid for pid in wk if pid not in rostered and pid in ros]
    fa_ids.sort(key=lambda p: -wk[p]["wk"])
    fa_ids = fa_ids[:80]
    players = {pid: meta(pid) for pid in (rostered | set(fa_ids))}

    playoff_start = int(settings.get("playoff_week_start", 15))
    schedule, records = build_league(src, week, playoff_start)

    return {
        "week": week, "season": season, "updated": date.today().isoformat(),
        "myRoster": my_rid, "myOwner": lg.my_owner,
        "teams": teams, "opp": {str(k): v for k, v in opp.items()},
        "players": players, "freeAgents": fa_ids,
        "games": build_games(week, season),
        "schedule": schedule, "records": {str(k): v for k, v in records.items()},
        "playoffStart": playoff_start, "playoffTeams": int(settings.get("playoff_teams", 6)),
        "mine": teams[str(my_rid)]["players"] if my_rid is not None else [],
        "drafted": sorted(rostered),
    }


def main() -> None:
    key = sys.argv[1] if len(sys.argv) > 1 else "sleeper-finaldraft"
    lg = get_league(key)
    html_path = ROOT / lg.cfg.get("artifact_file", "webapp/draft_room.html")
    season = build_season(lg)
    payload = json.dumps(season, separators=(",", ":"))
    html = html_path.read_text(encoding="utf-8")
    if SEASON_TAG not in html:
        raise SystemExit(f"season <script> block not found in {html_path}")
    start = html.index(SEASON_TAG) + len(SEASON_TAG)
    end = html.index("</script>", start)
    html_path.write_text(html[:start] + payload + html[end:], encoding="utf-8")
    opp_owner = season["teams"].get(str(season["opp"].get(str(season["myRoster"]))), {}).get("owner", "?")
    print(f"Refreshed [{lg.key}]: Week {season['week']} {season['season']} · "
          f"{len(season['teams'])} teams · {len(season['players'])} players · "
          f"{len(season['freeAgents'])} FAs · your Wk{season['week']} opp = {opp_owner}")


if __name__ == "__main__":
    main()
