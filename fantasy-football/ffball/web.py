"""Zero-dependency web dashboard (stdlib http.server).

A single-page dashboard to run your draft and manage your team, backed by the
same SQLite board and draft state as the CLI. No framework, no install — just
``python3 -m ffball serve`` and open the browser.

Endpoints:
  GET  /                     the dashboard page
  GET  /api/state            board + draft status + your roster + recommendations
  POST /api/pick             {"query": "...", "mine": bool}  record a pick
  POST /api/undo             undo the last pick
  POST /api/reset            clear the draft
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

from .db import Database
from .draft import DraftState, recommend
from .explain import plain_reason, pos_full
from .league import LeagueConfig
from .namematch import find
from .scoring import ScoringSystem

_PAGE = (Path(__file__).parent / "static" / "dashboard.html")


def _config(db: Database):
    scoring = ScoringSystem.from_preset(db.get_meta("scoring", "ppr"))
    league = LeagueConfig.from_preset(db.get_meta("roster", "standard_12"))
    teams_override = db.get_meta("teams", None)
    if teams_override:
        league.teams = int(teams_override)
    return scoring, league


def _state_payload(db: Database, my_slot: int) -> dict:
    board = db.load_board()
    _, league = _config(db)
    state = DraftState(league=league, my_slot=my_slot,
                       drafted_ids=db.drafted_ids(), my_player_ids=db.my_player_ids())
    drafted = set(state.drafted_ids)
    by_id = {p.player_id: p for p in board}

    recs = recommend(state, board, top_n=8) if board else []
    return {
        "league": league.summary(),
        "my_slot": my_slot,
        "on_clock": state.current_overall,
        "is_my_turn": state.is_my_turn(),
        "picks_until_next": state.picks_until_next(),
        "board": [
            {
                "id": p.player_id, "name": p.name, "pos": p.position,
                "pos_full": pos_full(p.position),
                "team": p.team, "bye": p.bye_week, "pts": p.proj_points,
                "vbd": p.vbd, "adp": p.adp, "pos_rank": p.pos_rank,
                "tier": p.tier, "rank": p.overall_rank,
                "drafted": p.player_id in drafted,
                "mine": p.player_id in set(state.my_player_ids),
            }
            for p in board
        ],
        "roster": [
            {"name": by_id[pid].name, "pos": by_id[pid].position,
             "pos_full": pos_full(by_id[pid].position),
             "pts": by_id[pid].proj_points, "bye": by_id[pid].bye_week}
            for pid in state.my_player_ids if pid in by_id
        ],
        "recommendations": [
            _rec_payload(s, state.current_overall)
            for s in recs
        ],
    }


def _rec_payload(s, current_overall: int) -> dict:
    friendly = plain_reason(s.player, s.need, s.dropoff, current_overall)
    return {
        "name": s.player.name,
        "pos": s.player.position,
        "pos_full": friendly["pos_full"],
        "vbd": s.player.vbd,
        "tag": friendly["tag"],
        "sentences": friendly["sentences"],
        "reason": s.reason,          # keep terse version for reference
        "score": s.score,
        "id": s.player.player_id,
    }


class Handler(BaseHTTPRequestHandler):
    db_path: Optional[str] = None

    def log_message(self, *args):  # quiet
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj).encode("utf-8"), "application/json")

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            html = _PAGE.read_text(encoding="utf-8")
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
            return
        if self.path.startswith("/api/state"):
            slot = 1
            if "slot=" in self.path:
                try:
                    slot = int(self.path.split("slot=")[1].split("&")[0])
                except ValueError:
                    slot = 1
            db = Database(self.db_path)
            try:
                self._json(_state_payload(db, slot))
            finally:
                db.close()
            return
        self._send(404, b"not found", "text/plain")

    def do_POST(self):
        db = Database(self.db_path)
        try:
            body = self._read_json()
            if self.path == "/api/pick":
                self._do_pick(db, body)
            elif self.path == "/api/undo":
                self._do_undo(db)
                self._json({"ok": True})
            elif self.path == "/api/reset":
                db.reset_draft()
                self._json({"ok": True})
            else:
                self._send(404, b"not found", "text/plain")
        finally:
            db.close()

    def _do_pick(self, db: Database, body: dict):
        board = db.load_board()
        _, league = _config(db)
        state = DraftState(league=league, my_slot=int(body.get("slot") or 1),
                           drafted_ids=db.drafted_ids(), my_player_ids=db.my_player_ids())
        drafted = set(state.drafted_ids)
        pid = body.get("id")
        player = None
        if pid:
            player = next((p for p in board if p.player_id == pid), None)
        if not player:
            matches = [p for p in find(body.get("query", ""), board) if p.player_id not in drafted]
            if not matches:
                self._json({"ok": False, "error": "no match"}, code=400)
                return
            player = matches[0]
        if player.player_id in drafted:
            self._json({"ok": False, "error": "already drafted"}, code=400)
            return
        overall = state.current_overall
        slot = state.overall_to_slot(overall)
        db.record_pick(overall, player.player_id, slot, bool(body.get("mine")))
        self._json({"ok": True, "player": player.name, "overall": overall})

    def _do_undo(self, db: Database):
        ids = db.drafted_ids()
        if not ids:
            return
        _, league = _config(db)
        mine = set(db.my_player_ids())
        ids.pop()
        db.reset_draft()
        st = DraftState(league=league, my_slot=1)
        for i, pid in enumerate(ids, 1):
            db.record_pick(i, pid, st.overall_to_slot(i), pid in mine)


def serve(db_path: Optional[str] = None, host: str = "127.0.0.1", port: int = 8787) -> None:
    Handler.db_path = db_path
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"ffball dashboard running at http://{host}:{port}  (Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
        httpd.server_close()
