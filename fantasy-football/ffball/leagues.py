"""League registry — one JSON file per league under ``config/leagues/``.

Each config names its ``platform`` (which adapter to use), the league id, the
owner to treat as "me", and the artifact URL that league's web app publishes
to. Tools take a league key (default below) so a second league — even on a
different platform — is a new config file plus, if it's a new platform, a new
adapter. The existing league is never touched.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from .adapters import LeagueSource, SleeperSource

_DIR = Path(__file__).parent / "config" / "leagues"
DEFAULT_KEY = "sleeper-finaldraft"

# platform name -> adapter class. Add "espn": EspnSource here when built.
_ADAPTERS = {"sleeper": SleeperSource}


class LeagueRef:
    """A resolved league: its config plus a factory for its data source."""

    def __init__(self, cfg: Dict):
        self.cfg = cfg
        self.key = cfg["key"]
        self.platform = cfg["platform"]
        self.league_id = str(cfg["league_id"])
        self.name = cfg.get("league_name") or self.key
        self.my_owner = cfg.get("my_owner")
        self.artifact_url = cfg.get("artifact_url")

    def source(self) -> LeagueSource:
        if self.platform not in _ADAPTERS:
            raise KeyError(f"No adapter for platform {self.platform!r}. "
                           f"Have: {sorted(_ADAPTERS)}")
        return _ADAPTERS[self.platform](self.league_id, self.my_owner)


def get_league(key: str = DEFAULT_KEY) -> LeagueRef:
    path = _DIR / f"{key}.json"
    if not path.exists():
        raise FileNotFoundError(f"No league config {key!r} in {_DIR}. Have: {available()}")
    cfg = json.loads(path.read_text(encoding="utf-8"))
    cfg.setdefault("key", key)
    return LeagueRef(cfg)


def available() -> List[str]:
    return sorted(p.stem for p in _DIR.glob("*.json")) if _DIR.exists() else []
