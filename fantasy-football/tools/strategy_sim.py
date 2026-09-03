#!/usr/bin/env python3
"""Monte-Carlo strategy tournament for the draft.

Runs many simulated drafts from a given slot for several opening strategies, with
opponents drafting by ADP + noise (respecting roster construction). Each finished
team is scored by its OPTIMAL STARTING-LINEUP projected points (bench doesn't
score), and we report the average per strategy — so the data says which opening
approach tends to build the best startable team.

Run:  python3 tools/strategy_sim.py [slot] [sims_per_strategy]
Reads the current board from the SQLite DB (build it with `ffball init --league-id ...`).
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
NOISE = 7.0


def best_at(avail, pos):
    cands = [p for p in avail if p.position == pos]
    return min(cands, key=lambda p: (p.pos_rank or 999)) if cands else None


def rec_pick(state, board, exclude=None, prefer=None):
    recs = recommend(state, board, top_n=25)
    if prefer:
        for s in recs:
            if s.player.position in prefer:
                return s.player
    if exclude:
        for s in recs:
            if s.player.position not in exclude:
                return s.player
    return recs[0].player if recs else None


# --- strategies: (name, pick_fn(state, board, avail, rnd, qb_count)) ---
def s_value(state, board, avail, rnd, qbc):
    return rec_pick(state, board)

def s_qb_first(state, board, avail, rnd, qbc):
    if not state.my_player_ids:
        return best_at(avail, "QB")
    return rec_pick(state, board)

def s_two_qb_early(state, board, avail, rnd, qbc):
    if qbc < 2 and rnd <= 4:
        return best_at(avail, "QB") or rec_pick(state, board)
    return rec_pick(state, board)

def s_robust_rb(state, board, avail, rnd, qbc):
    if rnd <= 2:
        return rec_pick(state, board, prefer={"RB"}) or rec_pick(state, board)
    return rec_pick(state, board)

def s_zero_rb(state, board, avail, rnd, qbc):
    if rnd <= 3:
        return rec_pick(state, board, exclude={"RB"}) or rec_pick(state, board)
    return rec_pick(state, board)

def s_late_qb(state, board, avail, rnd, qbc):
    if rnd < 6:
        return rec_pick(state, board, exclude={"QB"}) or rec_pick(state, board)
    return rec_pick(state, board)

STRATEGIES = [
    ("Value (tool default)", s_value),
    ("Elite QB in Rd 1", s_qb_first),
    ("Two QBs early (by Rd 4)", s_two_qb_early),
    ("Robust RB (RB Rds 1-2)", s_robust_rb),
    ("Zero-RB (no RB Rds 1-3)", s_zero_rb),
    ("Wait on QB (till Rd 6)", s_late_qb),
]


def starting_points(players):
    """Optimal starting lineup: QB, 2RB, 2WR, TE, 2 FLEX, 1 SUPERFLEX."""
    pool = sorted(players, key=lambda p: -p.proj_points)
    used = set()
    total = 0.0
    def take(elig, n):
        nonlocal total
        cnt = 0
        for p in pool:
            if id(p) in used or p.position not in elig:
                continue
            used.add(id(p)); total += p.proj_points; cnt += 1
            if cnt >= n:
                break
    take({"QB"}, 1); take({"RB"}, 2); take({"WR"}, 2); take({"TE"}, 1)
    take({"RB", "WR", "TE"}, 2)          # 2 flex
    take({"QB", "RB", "WR", "TE"}, 1)    # superflex
    return total


def run_one(board, league, my_slot, strat_fn, rng):
    by_id = {p.player_id: p for p in board}
    state = DraftState(league=league, my_slot=my_slot)
    state.drafted_ids, state.my_player_ids = [], []
    drafted = set()
    opp = {t: {} for t in range(1, league.teams + 1)}
    rounds = league.total_roster_size()
    # per-sim ADP priority for opponents
    pri = sorted((p for p in board if p.position in OFFENSE),
                 key=lambda p: (p.adp or 9999) + rng.gauss(0, NOISE))
    for overall in range(1, league.teams * rounds + 1):
        slot = state.overall_to_slot(overall)
        rnd = (overall - 1) // league.teams + 1
        if slot == my_slot:
            avail = [p for p in board if p.player_id not in drafted and p.position in OFFENSE]
            qbc = sum(1 for pid in state.my_player_ids if by_id[pid].position == "QB")
            pick = strat_fn(state, board, avail, rnd, qbc)
            if pick is None:
                pick = avail[0]
            state.my_player_ids.append(pick.player_id)
            state.drafted_ids.append(pick.player_id); drafted.add(pick.player_id)
        else:
            for p in pri:
                if p.player_id in drafted:
                    continue
                if opp[slot].get(p.position, 0) >= OPP_CAP.get(p.position, 7):
                    continue
                state.drafted_ids.append(p.player_id); drafted.add(p.player_id)
                opp[slot][p.position] = opp[slot].get(p.position, 0) + 1
                break
    return starting_points([by_id[pid] for pid in state.my_player_ids])


def main():
    my_slot = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    board = Database(Path(__file__).parent.parent / "data" / "ffball.db").load_board()
    league = LeagueConfig.from_sleeper_league(Sleeper().league(LEAGUE_ID))
    print(f"Strategy tournament — slot {my_slot} of {league.teams}, {n} sims each")
    print(f"(score = optimal starting-lineup projected points; higher is better)\n")
    results = []
    for name, fn in STRATEGIES:
        rng = random.Random(12345)   # same opponent draws across strategies = fair comparison
        scores = [run_one(board, league, my_slot, fn, rng) for _ in range(n)]
        results.append((name, statistics.mean(scores), statistics.pstdev(scores)))
    results.sort(key=lambda r: -r[1])
    best = results[0][1]
    print(f"{'RANK  STRATEGY':<34}{'AVG PTS':>9}{'  vs best':>10}{'  std':>7}")
    for i, (name, mean, sd) in enumerate(results, 1):
        print(f"{i}. {name:<30}{mean:>9.0f}{mean-best:>+10.0f}{sd:>7.0f}")


if __name__ == "__main__":
    main()
