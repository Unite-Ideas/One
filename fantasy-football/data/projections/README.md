# Drop your projection CSVs here

Any `*.csv` file in this folder is loaded and **blended** (averaged per player
across files) when you run `ffball init`. If this folder is empty, the app falls
back to the bundled synthetic sample so it still runs.

## Expected columns
A header row with at least `name` (or `player_id`) and `position`, plus any
Sleeper stat columns you have. Everything else is optional.

```
name,position,team,bye_week,adp,pass_yd,pass_td,pass_int,rush_yd,rush_td,rec,rec_yd,rec_td,fum_lost,fpts
Ja'Marr Chase,WR,CIN,10,2,,,,40,0,105,1450,12,1,
```

- **Stat columns** use Sleeper's keys: `pass_yd pass_td pass_int rush_yd rush_td
  rec rec_yd rec_td fum_lost` (add more; unknown keys are ignored by scoring).
- **`fpts`** — optional pre-scored fantasy points, used only when a player has no
  raw stats (handy for K/DEF where modeling raw stats isn't worth it).
- **`adp`** — average draft position (lower = earlier). Drives the VONA
  "who'll be gone before my next pick" math. You can also put ADP in
  `../adp/*.csv`.

## Where to get projections
- FantasyPros export (rankings/projections) → save as CSV here.
- Any subscription's season projections export.
- Your own model output.

Blend 2–3 sources for the sturdiest board. See `../../docs/DATA_SOURCES.md`.
