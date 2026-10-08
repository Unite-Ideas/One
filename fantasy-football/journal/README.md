# Fantasy routine journal

Shared, append-only log of what the scheduled fantasy routines find, think, and
recommend. Every automated run writes its full output here so the **main chat**
(Sean's central Claude session) can `git pull` and reference it — no copy-paste
from phone notifications.

## How it works

- Each routine owns ONE file below and **appends** a dated entry every run.
- An entry contains the *complete* message that was sent to Sean, plus the
  reasoning/data behind it (not just the headline).
- Nothing secret ever goes in here (no ESPN cookies, no tokens) — recommendations
  and public stats only.
- Newest entries go at the **bottom**. To see the latest, read the tail.

## Files

| File | Routine | Cadence |
|------|---------|---------|
| `waiver-watch.md`    | Waiver league-winner watch (two-tier wire alerts) | daily |
| `weekly-scouting.md` | Weekly opponent scouting / battle plan            | Tue |
| `lauren-weekly.md`   | Lauren's weekly hype-email draft                  | Tue |
| `waiver-results.md`  | Post-waiver-processing results + rival scouting   | Wed |
| `sean-moves.md`      | Sean's roster moves, trade plan, reasoning (written by the main chat, not a routine) | as needed |

## For the routines (write protocol)

At the end of a run, append your entry to your file, then:

```
git add fantasy-football/journal/<yourfile>.md
git commit -m "journal: <routine> <date>"
git pull --rebase origin claude/fantasy-football-ai-n1d1kz
git push origin claude/fantasy-football-ai-n1d1kz   # if rejected: pull --rebase and retry once
```

Only ever add/commit your own journal file. Never commit secrets.
