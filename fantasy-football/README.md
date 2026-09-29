# ffball — a Sleeper-powered fantasy football draft & season assistant

Built to win a snake-draft league by out-*deciding* everyone: value-based draft
board, tiers, live draft recommendations that account for positional scarcity,
and a zero-dependency web "war room" dashboard — all driven by your league's
**exact** scoring settings pulled from Sleeper.

> **Why it wins:** humans lose fantasy leagues by reaching on draft day,
> ignoring the waiver wire, and setting lineups on vibes. This removes those
> leaks and makes the mathematically sound call every time. Full write-up in
> [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md).

## Highlights
- **Configurable scoring** — the scoring system is a plug-in variable. Use a
  preset (`ppr` / `half_ppr` / `standard`) now, or drop in your league's real
  `scoring_settings` straight from Sleeper later. Same engine scores projections
  and actual results.
- **Value-Based Drafting (VBD)** — ranks every player by points **above
  replacement** at their position, so a QB, WR and TE compare on one currency.
- **Gap-based tiers** — shows you when a position is about to fall off a cliff.
- **Live snake-draft assistant** — knows the snake order, tracks who's gone,
  your roster needs, and the value drop-off before your next pick (VONA), then
  recommends the best pick with a plain-English reason.
- **Web dashboard** — a draft "war room" you can click through on draft night.
- **Zero dependencies** — pure Python 3.9+ standard library. Nothing to install.

## Quick start
```bash
cd fantasy-football

# 0. (recommended) Pull REAL current FantasyPros ranks + byes + Sleeper ids
python3 -m ffball fetch --scoring ppr

# 1. Build the value board (uses the fetched data, or the bundled sample)
python3 -m ffball init --scoring ppr --roster standard_12

# 2. Look at the board and tiers
python3 -m ffball board --pos RB --limit 20
python3 -m ffball tiers --pos WR

# 3a. Draft night — terminal assistant (you are draft slot 4)
python3 -m ffball draft --slot 4
#     then type:  bijan          (someone else drafted Bijan)
#                 me chase        (you drafted Chase)
#                 rec             (show recommendations)

# 3b. ...or the web war room
python3 -m ffball serve
#     open http://127.0.0.1:8787
```

## Connect your real league (when network is available)
Sleeper's API is free and needs no key. Point the tool at your league to pull
your **exact** scoring + roster settings, and sync a live draft:
```bash
# Build the board from your league's real settings:
python3 -m ffball init --league-id <YOUR_SLEEPER_LEAGUE_ID>

# During the draft, mirror Sleeper's live picks into the board:
python3 -m ffball sync --draft-id <YOUR_SLEEPER_DRAFT_ID> --slot 4
```
Find your `league_id` in the Sleeper league URL; `draft_id` via
`/v1/league/{league_id}/drafts`.

## Bring your own projections
The bundled `data/sample/projections.csv` is **synthetic** (procedurally
generated — not real forecasts) so everything runs offline. Before your draft,
drop real projection CSVs into `data/projections/` — they're auto-blended. See
[`data/projections/README.md`](data/projections/README.md) and
[`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md).

## Commands
| Command | What it does |
|---|---|
| `fetch` | Pull real current FantasyPros ECR + byes + Sleeper ids from GitHub |
| `init` | Build the value board (scoring + roster preset, or `--league-id`) |
| `board [--pos] [--limit]` | Print the ranked value board |
| `tiers [--pos]` | Print tiered rankings by position |
| `draft --slot N` | Interactive draft-day assistant |
| `roster` | Show your drafted team |
| `sync --league-id/--draft-id` | Pull league settings / live draft from Sleeper |
| `serve` | Run the web dashboard |

## Layout
```
ffball/
  scoring.py      configurable scoring engine + presets
  league.py       teams + roster settings (defines replacement value)
  projections.py  load & blend projection/ADP CSVs -> Player objects
  valuation.py    score -> VBD -> tiers -> ranked board
  draft.py        snake math + live recommender (value + scarcity + need)
  sleeper.py      Sleeper API client (no auth)
  db.py           SQLite persistence
  web.py          stdlib web dashboard
  cli.py          command-line entry point
docs/             METHODOLOGY.md, DATA_SOURCES.md
tests/            unit tests (python3 -m unittest discover -s tests)
tools/            make_sample.py, refresh_season.py, matchup_scout.py,
                  build_espn_season.py (in-season data + scouting scripts)
journal/          shared append-only log the scheduled routines write to
webapp/           published web dashboards (draft_room*.html)
```

## Tests
```bash
python3 -m unittest discover -s tests -v
```

## In-season automation & shared journal
Scheduled routines (Claude Code Remote triggers) run the season on autopilot and
ping Sean on his phone. So their output isn't trapped in notifications, **every
fantasy routine appends its full recommendation to a shared log under
[`journal/`](journal/) and pushes it to the working branch**
(`claude/fantasy-football-ai-n1d1kz`). The main chat session then just
`git pull`s and reads the journal to discuss anything a routine sent — no
copy-paste from the phone.

| Routine | Cadence | Journal file |
|---|---|---|
| Waiver league-winner watch (two-tier: 🚨 spend #2 / 🟢 free grabs) | daily | `journal/waiver-watch.md` |
| Weekly opponent scouting / battle plan | Tue | `journal/weekly-scouting.md` |
| Lauren's ESPN hype-email draft | Tue | `journal/lauren-weekly.md` |
| Post-waiver results + rival scouting | Wed | `journal/waiver-results.md` |

Rules the routines follow (see [`journal/README.md`](journal/README.md)): append
only (newest at the bottom), one commit touching only that routine's own journal
file, `pull --rebase` + retry once on a push race, and **never write a secret**
(ESPN cookies `ESPN_S2`/`ESPN_SWID` live only as environment variables, never in
the repo). If a run can't push, it still delivers the alert and flags the failed
journal write.

## Roadmap (season management — phase 2)
- Weekly **lineup optimizer** (projection-max legal lineup, matchup-adjusted).
- **Waiver-wire** points-above-replacement + Sleeper trending-adds alerts.
- **Trade analyzer** (rest-of-season value swing).
- **Start/sit** with opponent defense-vs-position and Vegas totals.
- Own-projection model from `nflverse` historical data.

See `docs/METHODOLOGY.md` for how each of these presses the edge.
