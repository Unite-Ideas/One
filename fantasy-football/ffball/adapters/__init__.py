"""Pluggable league data sources.

Each fantasy platform (Sleeper, ESPN, …) implements the ``LeagueSource``
interface in ``base.py``, mapping its own API onto one normalized set of
shapes. The engine, tools, and web-app builder depend only on that interface,
so adding a platform is a new adapter file — never a change to the engine.
"""
from .base import LeagueSource, apply_scoring, http_json  # noqa: F401
from .sleeper import SleeperSource  # noqa: F401

__all__ = ["LeagueSource", "SleeperSource", "apply_scoring", "http_json"]
