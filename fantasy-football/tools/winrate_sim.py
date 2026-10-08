#!/usr/bin/env python3
"""Full-draft win-rate simulator: YOUR team (using the tool) vs 9 ADP drafters.

Simulates complete 10-team drafts where your seat drafts with the tool's
recommender and every opponent drafts by ADP (with noise) — i.e. exactly the
"me with AI vs buddies drafting off rankings" matchup. Each finished team is
scored by its optimal starting-lineup points; we record where your team
finishes and report win / top-3 rates.

Modes:
  python3 tools/winrate_sim.py winrate [slot=2] [sims=60] [room=normal]
  python3 tools/winrate_sim.py allseats [sims=40] [room=normal]
  python3 tools/winrate_sim.py stress   [slot=2] [sims=60]

Rooms: normal | qb-crazy (opponents hammer QBs) | chaotic (big reaches/falls).
Needs the board built: `ffball init --league-id ...`.
"""
from __future__ import annotations

import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from ffball.db import Database
from ffball.draft import DraftState, recommend
from ffball.league import LeagueConfig
from ffball.sleeper import Sleeper

LEAGUE_ID = "1395483423719587840"
OFFENSE = ("QB", "RB", "WR", "TE")
OPP_CAP = {"QB": 3, "RB": 6, "WR": 7, "TE": 2}


def starting_points(players):
    """Optimal starting lineup: QB, 2RB, 2WR, TE, 2 FLEX, 1 SUPERFLEX."""
    pool = sorted(players, key=lambda p: -p.proj_points)
    used, total = set(), 0.0
    def take(elig, n):
        nonlocal total
        c = 0
        for p in pool:
            if id(p) in used or p.position not in elig:
                continue
            used.add(id(p)); total += p.proj_points; c += 1
            if c >= n:
                break
    take({"QB"}, 1); take({"RB"}, 2); take({"WR"}, 2); take({"TE"}, 1)
    take({"RB", "WR", "TE"}, 2)
    take({"QB", "RB", "WR", "TE"}, 1)
    return total


def build_priority(board, room, rng):
    """Opponent draft order for one sim, per room type."""
    def key(p):
        adp = p.adp or 9999
        if room == "qb-crazy":
            adp = adp * (0.6 if p.position == "QB" else 1.0) + rng.gauss(0, 5)
        elif room == "chaotic":
            adp = adp + rng.gauss(0, 14)
        else:  # normal
            adp = adp + rng.gauss(0, 7)
        return adp
    return sorted((p for p in board if p.position in OFFENSE), key=key)


def simulate(board, league, my_slot, room, rng):
    by_id = {p.player_id: p for p in board}
    teams, rounds = league.teams, league.total_roster_size()
    rosters = {t: [] for t in range(1, teams + 1)}
    drafted, order = set(), []
    opp_counts = {t: {} for t in range(1, teams + 1)}
    pri = build_priority(board, room, rng)
    state = DraftState(league=league, my_slot=my_slot)

    for overall in range(1, teams * rounds + 1):
        slot = state.overall_to_slot(overall)
        if slot == my_slot:
            state.drafted_ids = order
            state.my_player_ids = rosters[my_slot]
            recs = recommend(state, board, top_n=1)
            avail = [p for p in board if p.player_id not in drafted and p.position in OFFENSE]
            pick = recs[0].player if recs else (avail[0] if avail else None)
        else:
            oc = opp_counts[slot]
            pick = None
            for p in pri:
                if p.player_id in drafted:
                    continue
                if oc.get(p.position, 0) >= OPP_CAP.get(p.position, 7):
                    continue
                pick = p
                break
            if pick:
                oc[pick.position] = oc.get(pick.position, 0) + 1
        if pick is None:
            continue
        rosters[slot].append(pick.player_id)
        drafted.add(pick.player_id); order.append(pick.player_id)

    scores = {t: starting_points([by_id[pid] for pid in r]) for t, r in rosters.items()}
    my_pts = scores[my_slot]
    my_rank = 1 + sum(1 for v in scores.values() if v > my_pts)
    field_avg = statistics.mean(v for t, v in scores.items() if t != my_slot)
    return my_rank, my_pts, field_avg, rosters


# --- season simulation with weekly variance (the honest win-rate) ---
WEEKS = range(1, 15)          # 14-week regular season
WEEKLY_CV = 0.42             # week-to-week volatility (fantasy is swingy)

def _week_points(players, week, rng):
    """A team's points this week: optimal lineup from noisy weekly scores."""
    scored = []
    for p in players:
        if p.bye_week == week:
            wk = 0.0
        else:
            mean = max(0.0, p.proj_points) / 14.0
            wk = max(0.0, rng.gauss(mean, mean * WEEKLY_CV))
        scored.append((p, wk))
    scored.sort(key=lambda x: -x[1])
    used, total = set(), 0.0
    def take(elig, n):
        nonlocal total
        c = 0
        for p, wk in scored:
            if id(p) in used or p.position not in elig:
                continue
            used.add(id(p)); total += wk; c += 1
            if c >= n:
                break
    take({"QB"}, 1); take({"RB"}, 2); take({"WR"}, 2); take({"TE"}, 1)
    take({"RB", "WR", "TE"}, 2); take({"QB", "RB", "WR", "TE"}, 1)
    return total

def simulate_season(rosters, by_id, my_slot, rng):
    """All-play-each-week: returns my weekly-matchup win rate + whether I had the best record."""
    teams = list(rosters)
    wins = {t: 0 for t in teams}
    for wk in WEEKS:
        wpts = {t: _week_points([by_id[pid] for pid in r], wk, rng) for t, r in rosters.items()}
        for t in teams:
            wins[t] += sum(1 for u in teams if u != t and wpts[t] > wpts[u])
    games = len(WEEKS) * (len(teams) - 1)
    winpct = {t: wins[t] / games for t in teams}
    best = 1 + sum(1 for t in teams if winpct[t] > winpct[my_slot])   # rank by record
    made_playoffs = best <= 6
    return winpct[my_slot], best == 1, made_playoffs


def run(board, league, my_slot, room, n, rng):
    ranks, mypts, field = [], [], []
    for _ in range(n):
        r, mp, fa, _ = simulate(board, league, my_slot, room, rng)
        ranks.append(r); mypts.append(mp); field.append(fa)
    wins = sum(1 for r in ranks if r == 1) / n
    top3 = sum(1 for r in ranks if r <= 3) / n
    return {
        "win": wins, "top3": top3, "avg_rank": statistics.mean(ranks),
        "my_pts": statistics.mean(mypts), "field_pts": statistics.mean(field),
    }


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "winrate"
    board = Database(Path(__file__).parent.parent / "data" / "ffball.db").load_board()
    league = LeagueConfig.from_sleeper_league(Sleeper().league(LEAGUE_ID))
    rng = random.Random(2024)

    if mode == "winrate":
        slot = int(sys.argv[2]) if len(sys.argv) > 2 else 2
        n = int(sys.argv[3]) if len(sys.argv) > 3 else 60
        room = sys.argv[4] if len(sys.argv) > 4 else "normal"
        r = run(board, league, slot, room, n, rng)
        print(f"Win-rate — slot {slot} of {league.teams}, {n} drafts, {room} room "
              f"(you use the tool, 9 opponents draft off rankings)\n")
        print(f"  Finish 1st (win the draft):  {r['win']*100:.0f}%")
        print(f"  Finish top-3:                {r['top3']*100:.0f}%")
        print(f"  Average finish:              {r['avg_rank']:.1f} of {league.teams}")
        print(f"  Your starting pts (avg):     {r['my_pts']:.0f}   vs field {r['field_pts']:.0f} "
              f"(+{r['my_pts']-r['field_pts']:.0f})")

    elif mode == "allseats":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 40
        room = sys.argv[3] if len(sys.argv) > 3 else "normal"
        print(f"All-seats analysis — {n} drafts per slot, {room} room\n")
        print(f"{'SLOT':<6}{'WIN%':>6}{'TOP3%':>7}{'AVG FIN':>9}{'YOUR PTS':>10}{'vs FIELD':>10}")
        for slot in range(1, league.teams + 1):
            rng = random.Random(2024)
            r = run(board, league, slot, room, n, rng)
            print(f"{slot:<6}{r['win']*100:>5.0f}%{r['top3']*100:>6.0f}%{r['avg_rank']:>9.1f}"
                  f"{r['my_pts']:>10.0f}{r['my_pts']-r['field_pts']:>+10.0f}")

    elif mode == "stress":
        slot = int(sys.argv[2]) if len(sys.argv) > 2 else 2
        n = int(sys.argv[3]) if len(sys.argv) > 3 else 60
        print(f"Opponent stress test — slot {slot}, {n} drafts per room\n")
        print(f"{'ROOM':<12}{'WIN%':>6}{'TOP3%':>7}{'AVG FIN':>9}{'vs FIELD':>10}")
        for room in ("normal", "qb-crazy", "chaotic"):
            rng = random.Random(2024)
            r = run(board, league, slot, room, n, rng)
            print(f"{room:<12}{r['win']*100:>5.0f}%{r['top3']*100:>6.0f}%{r['avg_rank']:>9.1f}"
                  f"{r['my_pts']-r['field_pts']:>+10.0f}")
    elif mode == "season":
        slot = int(sys.argv[2]) if len(sys.argv) > 2 else 2
        n = int(sys.argv[3]) if len(sys.argv) > 3 else 60
        room = sys.argv[4] if len(sys.argv) > 4 else "normal"
        by_id = {p.player_id: p for p in board}
        wps, titles, playoffs = [], 0, 0
        for _ in range(n):
            _, _, _, rosters = simulate(board, league, slot, room, rng)
            wp, title, po = simulate_season(rosters, by_id, slot, rng)
            wps.append(wp); titles += title; playoffs += po
        print(f"Season simulation — slot {slot}, {n} seasons, {room} room, with weekly variance\n")
        print(f"(you draft with the tool; 9 opponents draft off rankings; 14-week season)\n")
        print(f"  Your weekly win rate:        {statistics.mean(wps)*100:.0f}%  (a 50% team is average)")
        print(f"  Best regular-season record:  {titles/n*100:.0f}% of seasons")
        print(f"  Made playoffs (top 6):       {playoffs/n*100:.0f}% of seasons")

    else:
        print(__doc__)


if __name__ == "__main__":
    main()
