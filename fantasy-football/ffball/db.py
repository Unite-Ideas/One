"""SQLite persistence (stdlib ``sqlite3``, zero external deps).

Stores the value board, league config, and live draft state so the CLI and
dashboard share one source of truth across runs. SQLite keeps setup at zero
while remaining a real relational store you can later point at Postgres.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional

from .models import Player

DEFAULT_DB_PATH = Path(__file__).parent.parent / "data" / "ffball.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS board (
    player_id     TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    position      TEXT NOT NULL,
    team          TEXT,
    bye_week      INTEGER,
    proj_points   REAL,
    vbd           REAL,
    adp           REAL,
    pos_rank      INTEGER,
    overall_rank  INTEGER,
    tier          INTEGER,
    injury_status TEXT,
    stats_json    TEXT
);
CREATE INDEX IF NOT EXISTS idx_board_vbd ON board(vbd DESC);
CREATE TABLE IF NOT EXISTS draft_picks (
    overall_pick INTEGER PRIMARY KEY,
    player_id    TEXT NOT NULL,
    slot         INTEGER,
    is_mine      INTEGER DEFAULT 0
);
"""


class Database:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path or DEFAULT_DB_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    # ---- meta -------------------------------------------------------------
    def set_meta(self, key: str, value: object) -> None:
        self.conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value)),
        )
        self.conn.commit()

    def get_meta(self, key: str, default=None):
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    # ---- board ------------------------------------------------------------
    def save_board(self, players: List[Player]) -> None:
        self.conn.execute("DELETE FROM board")
        self.conn.executemany(
            "INSERT INTO board(player_id,name,position,team,bye_week,proj_points,"
            "vbd,adp,pos_rank,overall_rank,tier,injury_status,stats_json) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    p.player_id, p.name, p.position, p.team, p.bye_week,
                    p.proj_points, p.vbd, p.adp, p.pos_rank, p.overall_rank,
                    p.tier, p.injury_status, json.dumps(p.stats),
                )
                for p in players
            ],
        )
        self.conn.commit()

    def load_board(self) -> List[Player]:
        rows = self.conn.execute("SELECT * FROM board ORDER BY vbd DESC").fetchall()
        out: List[Player] = []
        for r in rows:
            out.append(
                Player(
                    player_id=r["player_id"], name=r["name"], position=r["position"],
                    team=r["team"], bye_week=r["bye_week"],
                    injury_status=r["injury_status"],
                    stats=json.loads(r["stats_json"] or "{}"),
                    proj_points=r["proj_points"] or 0.0, adp=r["adp"],
                    vbd=r["vbd"] or 0.0, pos_rank=r["pos_rank"],
                    overall_rank=r["overall_rank"], tier=r["tier"],
                )
            )
        return out

    # ---- draft ------------------------------------------------------------
    def record_pick(self, overall: int, player_id: str, slot: int, is_mine: bool) -> None:
        self.conn.execute(
            "INSERT INTO draft_picks(overall_pick,player_id,slot,is_mine) "
            "VALUES(?,?,?,?) ON CONFLICT(overall_pick) DO UPDATE SET "
            "player_id=excluded.player_id, slot=excluded.slot, is_mine=excluded.is_mine",
            (overall, player_id, slot, 1 if is_mine else 0),
        )
        self.conn.commit()

    def drafted_ids(self) -> List[str]:
        rows = self.conn.execute(
            "SELECT player_id FROM draft_picks ORDER BY overall_pick"
        ).fetchall()
        return [r["player_id"] for r in rows]

    def my_player_ids(self) -> List[str]:
        rows = self.conn.execute(
            "SELECT player_id FROM draft_picks WHERE is_mine=1 ORDER BY overall_pick"
        ).fetchall()
        return [r["player_id"] for r in rows]

    def reset_draft(self) -> None:
        self.conn.execute("DELETE FROM draft_picks")
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
