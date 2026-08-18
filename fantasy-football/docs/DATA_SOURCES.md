# Where the data comes from

The whole system is only as good as its inputs. Here's the sourcing strategy,
ordered by how much we lean on each.

## Primary: Sleeper API (free, no key, no OAuth)
Base URL: `https://api.sleeper.app`

Because your league is on **Sleeper**, we get almost everything for free with no
authentication:

| Data | Endpoint | Used for |
|------|----------|----------|
| NFL state (season, week) | `/v1/state/nfl` | Knowing "what week is it" |
| All players (metadata, position, team, injury, bye) | `/v1/players/nfl` | The player master table (~5MB, cache daily) |
| Trending adds/drops | `/v1/players/nfl/trending/add` | Waiver-wire early-warning |
| Your league | `/v1/league/{league_id}` | **Scoring settings + roster settings** (this is the scoring "variable") |
| Rosters | `/v1/league/{league_id}/rosters` | Who owns whom |
| Users | `/v1/league/{league_id}/users` | Team names |
| Matchups | `/v1/league/{league_id}/matchups/{week}` | Weekly scores, start/sit |
| Transactions | `/v1/league/{league_id}/transactions/{week}` | Waivers/trades log |
| Draft | `/v1/draft/{draft_id}` + `/picks` | **Live draft board sync** |

> The killer detail: Sleeper's `league.scoring_settings` uses the **same stat
> keys** our scoring engine uses (`pass_yd`, `rush_td`, `rec`, ...). So once you
> paste your `league_id`, your league's *exact* scoring drops straight into the
> value model — no manual entry, no guessing PPR vs half.

## Projections (blended)
Sleeper exposes stat/projection endpoints, but coverage varies year to year, so
we treat projections as a **pluggable, multi-source layer**:
- **Sleeper projections** (when available) — auto-pulled.
- **CSV import** — drop any projection export (FantasyPros, a subscription, your
  own) into `data/projections/*.csv` and we normalize + blend it.
- **Our own model (roadmap)** — built from `nflverse` historical play-by-play
  and weekly stats (free, open data) via regression/aging curves.

Multiple sources are averaged (optionally weighted) so no single bad forecast
sinks a pick.

## ADP (Average Draft Position)
- **CSV import** (`data/adp/*.csv`) from Fantasy Football Calculator / FantasyPros.
- **Derived** from public Sleeper mock drafts.
ADP drives the VONA "who'll be gone before my next pick" math and the
don't-reach guardrail.

## News / injuries
- Sleeper `players` payload carries `injury_status`, `injury_body_part`,
  practice status, and bye weeks — enough to auto-flag risky starts.
- Trending-adds is our fastest breakout signal.

## Optional enrichments (roadmap)
- **Vegas game totals / spreads** — game environment for ceiling/floor tilt.
- **Weather** — wind/precip flags for outdoor games.
- **Defense vs position** — computed from nflverse weekly data.

## Caching & rate limits
Sleeper asks for < ~1000 calls/min and no auth. We cache the big/slow payloads
(the full players list especially) to local JSON with a TTL, so normal use is a
handful of requests. See `ffball/http.py`.

## Note on this build environment
The remote sandbox this was authored in blocks outbound calls to
`api.sleeper.app` at the network-policy layer, so live sync can't run *here*.
Everything is written to run against the real API the moment you run it on your
own machine (or any environment with open network). A bundled **sample dataset**
(`data/sample/`) lets every command work offline for development and demos.
