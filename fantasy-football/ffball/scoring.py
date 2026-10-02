"""Configurable fantasy scoring engine.

The engine is intentionally dumb and generic: give it a bag of projected stats
(keyed by Sleeper's stat keys) and a scoring-settings dict (keyed the same way),
and it returns the fantasy points. This is what makes scoring a *variable*:

  * Use a bundled preset ("ppr", "half_ppr", "standard"), OR
  * Drop in your league's real ``scoring_settings`` straight from the Sleeper
    ``/v1/league/{id}`` payload (same keys), so the value model matches your
    league exactly.

Because Sleeper's league scoring settings and Sleeper's stat projections share
the same key vocabulary, the same function scores both projections and actual
results with no translation layer.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Mapping

_CONFIG_DIR = Path(__file__).parent / "config"

# Keys in a scoring preset that are metadata, not stat weights.
_META_PREFIX = "_"


def load_presets() -> Dict[str, Dict[str, float]]:
    """Return all bundled scoring presets keyed by name."""
    with open(_CONFIG_DIR / "scoring_presets.json", "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_preset(name: str) -> Dict[str, float]:
    """Return a single scoring preset by name (e.g. ``"ppr"``)."""
    presets = load_presets()
    if name not in presets:
        raise KeyError(
            f"Unknown scoring preset {name!r}. Available: {sorted(presets)}"
        )
    return presets[name]


def clean_settings(settings: Mapping[str, object]) -> Dict[str, float]:
    """Strip metadata keys (``_label`` etc.) and coerce weights to floats.

    Sleeper's ``scoring_settings`` may contain many keys we don't project
    (kicker distances, IDP stats, ...). Those are harmless: a stat we don't
    project simply contributes nothing. We keep every numeric weight.
    """
    out: Dict[str, float] = {}
    for key, value in settings.items():
        if key.startswith(_META_PREFIX):
            continue
        try:
            out[key] = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            # Non-numeric setting (rare); skip it.
            continue
    return out


def score_stats(stats: Mapping[str, float], settings: Mapping[str, float]) -> float:
    """Compute fantasy points for a bag of stats under given scoring settings.

    ``stats``    : {sleeper_stat_key: value}   (e.g. {"rec": 80, "rec_yd": 1100})
    ``settings`` : {sleeper_stat_key: weight}  (e.g. {"rec": 1.0, "rec_yd": 0.1})

    Any stat without a matching weight, or weight without a matching stat,
    contributes zero. Returns points rounded to 2 dp.
    """
    weights = clean_settings(settings)
    total = 0.0
    for key, value in stats.items():
        weight = weights.get(key)
        if weight is None:
            continue
        try:
            total += float(value) * weight
        except (TypeError, ValueError):
            continue
    return round(total, 2)


class ScoringSystem:
    """A named scoring configuration you can reuse to score many players."""

    def __init__(self, settings: Mapping[str, object], name: str = "custom"):
        self.name = name
        self.settings = clean_settings(settings)

    @classmethod
    def from_preset(cls, name: str) -> "ScoringSystem":
        return cls(load_preset(name), name=name)

    @classmethod
    def from_sleeper_league(cls, league: Mapping[str, object]) -> "ScoringSystem":
        """Build directly from a Sleeper ``/v1/league/{id}`` payload."""
        settings = league.get("scoring_settings") or {}
        name = str(league.get("name") or "sleeper_league")
        return cls(settings, name=name)

    def score(self, stats: Mapping[str, float]) -> float:
        return score_stats(stats, self.settings)

    def is_ppr(self) -> float:
        """Points per reception in this system (0 / 0.5 / 1.0 typically)."""
        return self.settings.get("rec", 0.0)

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"ScoringSystem(name={self.name!r}, ppr={self.is_ppr()})"
