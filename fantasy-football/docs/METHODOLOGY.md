# How to Beat Your Buddies: The Methodology

Your friends know you're using AI. Good. The edge isn't a secret model — it's
**discipline, information, and never missing a decision.** Humans lose fantasy
leagues by reaching on draft day, falling in love with players, forgetting
byes, ignoring the waiver wire on a Tuesday, and setting lineups on vibes. The
AI's job is to remove every one of those leaks and make the mathematically
sound choice, every time, all season.

There is no legal way to see the future. What we *can* do is make **better
risk-adjusted decisions than 11 humans**, consistently, over ~17 weeks. Do that
and you win far more often than not.

---

## The 8 pillars

### 1. Value-Based Drafting (VBD) is the spine
Do **not** draft by projected points. Draft by **points above a replacement-level
player at the same position** (a.k.a. Value Over Replacement / VBD).

A RB projected for 250 points sounds great — but if the 30th-best RB (the guy
you could get off waivers) is projected for 200, that stud is only worth **+50**.
Meanwhile a TE projected for 150 when the 12th TE is projected for 90 is worth
**+60** and more valuable to draft, even though he "scores less." VBD converts
every position onto one common currency so you can compare a QB to a WR to a TE
honestly.

The replacement baseline is set by your **league size and starting lineup**
(e.g., 12 teams × 2 RB starters + flex share → the ~30th RB is "replacement").
This is why we make league settings a config variable — the baseline *is* the
league.

### 2. Tiers over rankings
A ranking says "Player #14 > Player #15." A **tier** says "these 5 guys are
basically the same — after them there's a cliff." That's the decision-relevant
truth. On the clock you don't ask "who's ranked highest?" — you ask **"which
position's tier is about to break?"** If 5 RBs and 1 elite TE remain in their
tiers and the TE tier drops off a cliff after him, you take the TE even if an RB
ranks a hair higher. Tiers turn scarcity into action.

### 3. Positional scarcity & VONA (Value Over Next Available)
In a **snake draft you know exactly when you pick again.** Between now and your
next pick, some players at each position will be gone. The right question is:
*"If I wait, how much value do I lose at each position?"* Draft the position
with the **biggest expected drop-off before your next turn**, not just the
highest raw value. This is how you avoid taking a WR now when the WR pool is
deep but the elite TEs / QBs are about to vanish.

### 4. Aggregate projections — never trust one source
Any single projection is noisy. We blend **multiple sources** (consensus
projections, ADP-implied value, our own model off historical data) into one
number. Consensus beats any individual forecaster over a season because it
cancels idiosyncratic error. Then we **shade by your exact scoring** (PPR vs
standard completely reorders WRs and pass-catching RBs).

### 5. ADP arbitrage — let value fall to you
Average Draft Position (ADP) tells you when the *market* takes each player. Our
value board tells us what they're *worth*. When a player's worth outpaces where
the room is drafting him, we pounce; when the room is reaching, we wait. **Never
reach more than ~half a round past ADP.** Discipline here alone beats most
drafters.

### 6. Roster construction: byes, handcuffs, correlation
- **Bye-week balance:** don't stack your starters on the same bye or you punt a
  week.
- **Handcuffs:** own the backup to your stud RB — one injury swings a season.
- **Stacking (tournament edge):** in a winner-take-all season-long format, a
  QB + his WR/TE correlates outcomes — when your QB has a huge day, so does your
  receiver. Correlated upside is worth more than the sum of parts when you need
  ceiling to win it all.

### 7. In-season: the waiver wire wins leagues
Most managers draft hard and then coast. **The waiver wire is where leagues are
actually won.** Every week we:
- Compute **points-above-replacement for every free agent** and target
  breakouts *before* the room reacts (Sleeper's trending-adds tells us when the
  herd is about to move — we want to be one step ahead).
- Spend **FAAB/waiver priority** rationally (a season-long budget problem, not
  an impulse buy).
- **Stream** low-commitment positions (DST, and QB/TE in shallow formats) based
  on weekly matchups — start defenses facing turnover-prone offenses, etc.

### 8. Weekly lineup optimization + matchup exploitation
Set the **projection-maximizing legal lineup** every week — but adjust for
**matchup** (opponent defense's points-allowed-vs-position) and **game
environment** (Vegas totals, weather). Never leave points on the bench because a
name "feels" boring. When you're the underdog in a matchup, tilt toward
**ceiling**; when you're favored, tilt toward **floor/safety**. Simple, ruthless,
repeated 17 times.

---

## The AI advantage, concretely
The model doesn't need to be smarter than your friends about football. It needs
to:
1. **Never miss a decision** — every waiver run, every bye, every favorable
   trade, every optimal lineup, automatically.
2. **Have no ego** — cuts the shiny name for the better play; doesn't "believe
   in" a slumping star past the data.
3. **Quantify uncertainty** — makes floor plays when ahead, ceiling plays when
   behind (we can Monte-Carlo the rest-of-season to guide these).
4. **React first** — polls trending data and news continuously, so we claim the
   breakout Tuesday morning while they're still asleep.

That's the whole game: **out-decide them 500 times over a season.**

---

## Draft-day playbook (snake), in one paragraph
Build the value board (VBD + tiers + ADP). On each pick, the assistant looks at
who's gone, your current roster needs, and the drop-off before your next pick,
and recommends the pick that maximizes value *and* respects scarcity. Take the
best value that also addresses a tier about to break. Don't reach. Balance byes.
Grab a handcuff for your RB1 late. Leave the draft with the highest total board
value in the league — then let the in-season engine keep the lead.
