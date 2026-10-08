"""ffball — a Sleeper-powered fantasy football draft & season assistant.

Layers (bottom to top):
  http/sleeper      : dependency-free API access + caching
  projections       : load & blend projection/ADP CSVs (or Sleeper) -> Players
  scoring           : configurable scoring engine (your league's exact settings)
  league            : teams + roster settings that define replacement value
  valuation         : Players -> VBD -> tiers -> ranked board
  draft             : live snake-draft recommender (value + scarcity + need)
  db                : SQLite persistence
  cli               : command-line entry point
"""

__version__ = "0.1.0"
