"""Sleeper adapter — maps Sleeper's free public API onto ``LeagueSource``.

Sleeper is the reference shape, so most of this is light normalization. An
ESPN adapter would live beside this file and translate ESPN's API into the
same shapes; nothing else in the codebase would change.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from .base import LeagueSource, apply_scoring, http_json

V1 = "https://api.sleeper.app/v1"
PROJ = "https://api.sleeper.com/projections/nfl"   # weekly projections host
OFFENSE = ("QB", "RB", "WR", "TE")


class SleeperSource(LeagueSource):
    platform = "sleeper"

    def __init__(self, league_id: str, my_owner: Optional[str] = None):
        self.league_id = str(league_id)
        self.my_owner = my_owner
        self._pdb = None       # cached player master map
        self._users = None     # cached user_id -> display name

    # ---- helpers ----------------------------------------------------------
    def _user_names(self) -> Dict[str, str]:
        if self._users is None:
            self._users = {u["user_id"]: (u.get("metadata", {}).get("team_name") or u.get("display_name"))
                           for u in http_json(f"{V1}/league/{self.league_id}/users")}
        return self._users

    # ---- interface --------------------------------------------------------
    def state(self) -> Dict:
        s = http_json(f"{V1}/state/nfl")
        return {"week": int(s.get("week") or 1) or 1, "season": s["season"]}

    def league(self) -> Dict:
        return http_json(f"{V1}/league/{self.league_id}")

    def rosters(self) -> List[Dict]:
        names = self._user_names()
        out = []
        for r in http_json(f"{V1}/league/{self.league_id}/rosters"):
            out.append({"roster_id": r["roster_id"],
                        "owner": names.get(r.get("owner_id"), f"Team {r['roster_id']}"),
                        "owner_id": r.get("owner_id"),
                        "players": [str(p) for p in (r.get("players") or [])]})
        return out

    def matchups(self, week: int) -> List[Dict]:
        out = []
        for m in http_json(f"{V1}/league/{self.league_id}/matchups/{week}"):
            out.append({"roster_id": m["roster_id"], "matchup_id": m.get("matchup_id"),
                        "points": round(m.get("points") or 0, 2),
                        "starters": [str(x) for x in (m.get("starters") or []) if x and x != "0"]})
        return out

    def player_meta(self) -> Dict[str, Dict]:
        if self._pdb is None:
            self._pdb = http_json(f"{V1}/players/nfl")
        out = {}
        for pid, p in self._pdb.items():
            st = (p.get("injury_status") or "").strip()
            inj = ""
            if st and st.lower() != "healthy":
                inj = "Q" if st.lower() == "questionable" else st.upper()
            name = p.get("full_name") or f"{p.get('first_name','')} {p.get('last_name','')}".strip() or str(pid)
            out[str(pid)] = {"name": name, "pos": p.get("position") or "NA", "injury": inj}
        return out

    def trending(self) -> Dict[str, int]:
        rows = http_json(f"{V1}/players/nfl/trending/add?limit=75")
        return {str(t["player_id"]): t["count"] for t in rows}

    def weekly_projections(self, season: str, week: int, scoring: Dict) -> Dict[str, Dict]:
        q = "&".join(f"position[]={p}" for p in OFFENSE)
        rows = http_json(f"{PROJ}/{season}/{week}?season_type=regular&{q}&order_by=pts_ppr")
        out = {}
        for pr in rows:
            out[str(pr.get("player_id"))] = {"wk": apply_scoring(pr.get("stats") or {}, scoring),
                                             "opp": pr.get("opponent") or "", "team": pr.get("team") or ""}
        return out
