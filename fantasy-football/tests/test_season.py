"""Tests for the in-season engine: lineup optimizer, waivers, trade analyzer."""
import unittest

from ffball.league import LeagueConfig
from ffball.models import Player
from ffball.season import optimal_lineup, waiver_targets, evaluate_trade

SF_LEAGUE = {
    "name": "SF", "total_rosters": 10,
    "roster_positions": ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "FLEX",
                          "SUPER_FLEX", "BN", "BN", "BN", "BN", "BN"],
    "scoring_settings": {"rec": 1.0, "bonus_rec_te": 0.5},
}


def mk(pid, pos, pts, bye=6):
    p = Player(pid, pid, pos)
    p.proj_points = pts
    p.bye_week = bye
    return p


def full_roster():
    return [
        mk("q1", "QB", 300), mk("q2", "QB", 280), mk("q3", "QB", 210),
        mk("r1", "RB", 250), mk("r2", "RB", 240), mk("r3", "RB", 180),
        mk("w1", "WR", 230), mk("w2", "WR", 220), mk("w3", "WR", 150),
        mk("t1", "TE", 200), mk("t2", "TE", 120),
    ]


class TestLineup(unittest.TestCase):
    def setUp(self):
        self.lg = LeagueConfig.from_sleeper_league(SF_LEAGUE)

    def test_superflex_starts_two_qbs(self):
        lu = optimal_lineup(full_roster(), self.lg)
        qbs = [p for _, p in lu.starters if p and p.position == "QB"]
        self.assertEqual(len(qbs), 2)                 # QB slot + superflex
        self.assertNotIn("q3", {p.player_id for p in qbs})  # 3rd QB sits

    def test_lineup_fills_all_slots(self):
        lu = optimal_lineup(full_roster(), self.lg)
        self.assertEqual(len([1 for _, p in lu.starters if p]), 9)  # 9 starting slots

    def test_bye_player_benched_that_week(self):
        players = full_roster()
        players[0] = mk("q1", "QB", 300, bye=5)       # top QB on bye week 5
        lu = optimal_lineup(players, self.lg, week=5)
        self.assertNotIn("q1", {p.player_id for _, p in lu.starters if p})


class TestWaivers(unittest.TestCase):
    def test_upgrade_has_positive_gain(self):
        lg = LeagueConfig.from_sleeper_league(SF_LEAGUE)
        my = full_roster()
        stud = mk("stud", "WR", 300)                  # better than my WRs
        targets = waiver_targets([stud, mk("scrub", "WR", 40)], my, lg)
        self.assertTrue(targets)
        self.assertEqual(targets[0].add.player_id, "stud")
        self.assertGreater(targets[0].gain, 0)


class TestTrade(unittest.TestCase):
    def test_winning_trade_positive_swing(self):
        lg = LeagueConfig.from_sleeper_league(SF_LEAGUE)
        my = full_roster()
        give = [p for p in my if p.player_id == "w3"]  # give a weak WR
        get = [mk("stud", "RB", 300)]                  # get a stud
        ev = evaluate_trade(my, give, get, lg)
        self.assertGreater(ev.swing, 0)
        self.assertIn("win", ev.verdict.lower())


if __name__ == "__main__":
    unittest.main()
