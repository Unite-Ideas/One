#!/usr/bin/env python3
"""Monte Carlo sims for Lauren's league (12-team, 1-QB PPR, K+DEF, top-4).

Same idea as tools/winrate_sim.py but built for HER format instead of the
superflex Sleeper league: her board is valued for a 1-QB league that starts a
kicker and a defense, and teams are scored by her actual starting lineup
(QB / 2RB / 2WR / TE / FLEX / K / D-ST). You draft with the tool from pick 7;
11 opponents draft by ADP with noise. Reports draft win-rate + an honest
season sim with weekly variance and top-4 playoff odds.

Run:  python3 tools/sim_lauren.py [sims=60]
"""
from __future__ import annotations

import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from ffball import sources                                  # noqa: E402
from ffball.draft import DraftState, recommend              # noqa: E402
from ffball.league import LeagueConfig                      # noqa: E402
from ffball.models import Player                            # noqa: E402
from ffball.valuation import compute_vbd, assign_tiers, rank_board  # noqa: E402

MY_SLOT = 7
POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF")
OPP_CAP = {"QB": 2, "RB": 6, "WR": 7, "TE": 2, "K": 2, "DEF": 2}
WEEKS = range(1, 15)
WEEKLY_CV = 0.42


def lauren_league() -> LeagueConfig:
    return LeagueConfig(teams=12, starters={"QB": 1, "RB": 2, "WR": 2, "TE": 1, "K": 1, "DEF": 1},
                        flex=1, super_flex=0, bench=7, name="Lauren")


def build_board():
    players = []
    for r in sources.fetch_board_rows(scoring="ppr", superflex=False):   # 1-QB rankings, keeps K/DEF
        p = Player(str(r["player_id"]), r["name"], r["position"])
        p.proj_points = float(r["fpts"])
        p.adp = r["adp"]
        p.bye_week = r["bye_week"]
        players.append(p)
    lg = lauren_league()
    compute_vbd(players, lg)
    assign_tiers(players)
    return rank_board(players), lg


def start_pts(players):
    """Her optimal lineup: QB, 2RB, 2WR, TE, 1 FLEX (RB/WR/TE), K, D/ST."""
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
    take({"RB", "WR", "TE"}, 1); take({"K"}, 1); take({"DEF"}, 1)
    return total


def opp_priority(board, rng):
    def key(p):
        return (p.adp or 9999) + rng.gauss(0, 7)
    return sorted(board, key=key)


def simulate(board, lg, rng):
    by_id = {p.player_id: p for p in board}
    teams, rounds = lg.teams, lg.total_roster_size()
    rosters = {t: [] for t in range(1, teams + 1)}
    drafted, order = set(), []
    caps = {t: {} for t in range(1, teams + 1)}
    pri = opp_priority(board, rng)
    state = DraftState(league=lg, my_slot=MY_SLOT)
    for overall in range(1, teams * rounds + 1):
        slot = state.overall_to_slot(overall)
        if slot == MY_SLOT:
            state.drafted_ids = order
            state.my_player_ids = rosters[MY_SLOT]
            recs = recommend(state, board, top_n=1)
            pick = recs[0].player if recs else next((p for p in board if p.player_id not in drafted), None)
        else:
            oc = caps[slot]; pick = None
            rnd = (overall - 1) // teams + 1
            # Real managers (and ESPN autodraft) fill a K and D/ST in the last
            # couple rounds — model that so the field isn't handicapped.
            need_pos = None
            if rnd >= rounds - 1:
                if oc.get("K", 0) < 1:
                    need_pos = "K"
                elif oc.get("DEF", 0) < 1:
                    need_pos = "DEF"
            for p in pri:
                if p.player_id in drafted:
                    continue
                if need_pos:
                    if p.position != need_pos:
                        continue
                elif oc.get(p.position, 0) >= OPP_CAP.get(p.position, 7):
                    continue
                pick = p; break
            if pick:
                oc[pick.position] = oc.get(pick.position, 0) + 1
        if pick is None:
            continue
        rosters[slot].append(pick.player_id); drafted.add(pick.player_id); order.append(pick.player_id)
    scores = {t: start_pts([by_id[i] for i in r]) for t, r in rosters.items()}
    mine = scores[MY_SLOT]
    rank = 1 + sum(1 for v in scores.values() if v > mine)
    field = statistics.mean(v for t, v in scores.items() if t != MY_SLOT)
    return rank, mine, field, rosters, by_id


def week_pts(players, wk, rng):
    scored = []
    for p in players:
        mean = 0.0 if p.bye_week == wk else max(0.0, p.proj_points) / 14.0
        scored.append((p, max(0.0, rng.gauss(mean, mean * WEEKLY_CV)) if mean else 0.0))
    scored.sort(key=lambda x: -x[1])
    used, total = set(), 0.0
    def take(elig, n):
        nonlocal total
        c = 0
        for p, wpt in scored:
            if id(p) in used or p.position not in elig:
                continue
            used.add(id(p)); total += wpt; c += 1
            if c >= n:
                break
    take({"QB"}, 1); take({"RB"}, 2); take({"WR"}, 2); take({"TE"}, 1)
    take({"RB", "WR", "TE"}, 1); take({"K"}, 1); take({"DEF"}, 1)
    return total


def simulate_season(rosters, by_id, rng):
    teams = list(rosters)
    wins = {t: 0 for t in teams}
    for wk in WEEKS:
        wp = {t: week_pts([by_id[i] for i in r], wk, rng) for t, r in rosters.items()}
        for t in teams:
            wins[t] += sum(1 for u in teams if u != t and wp[t] > wp[u])
    games = len(WEEKS) * (len(teams) - 1)
    pct = {t: wins[t] / games for t in teams}
    rank = 1 + sum(1 for t in teams if pct[t] > pct[MY_SLOT])
    return pct[MY_SLOT], rank == 1, rank <= 4   # top-4 make playoffs


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    rng = random.Random(2026)
    board, lg = build_board()
    ranks, mypts, field = [], [], []
    wps, titles, playoffs = [], 0, 0
    for _ in range(n):
        r, mp, fa, rosters, by_id = simulate(board, lg, rng)
        ranks.append(r); mypts.append(mp); field.append(fa)
        wp, best, po = simulate_season(rosters, by_id, rng)
        wps.append(wp); titles += best; playoffs += po
    win = sum(1 for r in ranks if r == 1) / n
    top3 = sum(1 for r in ranks if r <= 3) / n
    print(f"Lauren's league — {n} sims, pick {MY_SLOT} of 12, 1-QB PPR w/ K+DEF")
    print(f"(she drafts with the tool; 11 opponents draft off rankings)\n")
    print("  DRAFT (by best starting lineup):")
    print(f"    Win the draft (most talent):   {win*100:.0f}%")
    print(f"    Top-3 roster:                  {top3*100:.0f}%")
    print(f"    Avg finish:                    {statistics.mean(ranks):.1f} of 12")
    print(f"    Her starting pts:  {statistics.mean(mypts):.0f}  vs field {statistics.mean(field):.0f} "
          f"(+{statistics.mean(mypts)-statistics.mean(field):.0f})\n")
    print("  SEASON (weekly variance, 14 weeks):")
    print(f"    Weekly win rate:               {statistics.mean(wps)*100:.0f}%  (50% = average)")
    print(f"    Best regular-season record:    {titles/n*100:.0f}% of seasons")
    print(f"    Made playoffs (TOP 4 of 12):   {playoffs/n*100:.0f}% of seasons")


if __name__ == "__main__":
    main()
