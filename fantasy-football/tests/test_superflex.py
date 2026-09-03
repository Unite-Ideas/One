"""Regression tests for the league's live rules: superflex, TE premium, no K/DEF."""
import unittest

from ffball.draft import DraftState, recommend, _startable_capacity
from ffball.league import LeagueConfig
from ffball.models import Player
from ffball.sources import points_for

# A fake Sleeper league payload matching The Final Draft Lifegroup.
SF_LEAGUE = {
    "name": "SF Test",
    "total_rosters": 10,
    "roster_positions": ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "FLEX",
                          "SUPER_FLEX", "BN", "BN", "BN", "BN", "BN"],
    "scoring_settings": {"rec": 1.0, "bonus_rec_te": 0.5},
}


def mk(pid, pos, vbd, adp, pos_rank=1):
    p = Player(pid, pid, pos)
    p.vbd = vbd
    p.adp = adp
    p.pos_rank = pos_rank
    p.overall_rank = int(adp)
    p.tier = 1
    p.bye_week = 6
    p.proj_points = 100 + vbd
    return p


class TestSuperflexLeague(unittest.TestCase):
    def setUp(self):
        self.sf = LeagueConfig.from_sleeper_league(SF_LEAGUE)

    def test_parsed_as_superflex_without_k_def(self):
        self.assertEqual(self.sf.teams, 10)
        self.assertEqual(self.sf.super_flex, 1)
        self.assertEqual(self.sf.flex, 2)
        self.assertNotIn("K", self.sf.starters)
        self.assertNotIn("DEF", self.sf.starters)

    def test_qb_capacity_reflects_superflex(self):
        # Superflex makes QB worth ~2 startable slots; a 1-QB league is 1.
        self.assertGreater(_startable_capacity("QB", self.sf), 1.5)
        reg = LeagueConfig.from_preset("standard_12")
        self.assertAlmostEqual(_startable_capacity("QB", reg), 1.0, places=2)

    def test_no_kicker_or_defense_recommended(self):
        board = [mk("Kicker", "K", 50, 5), mk("QBguy", "QB", 80, 3), mk("RBguy", "RB", 120, 2)]
        recs = recommend(DraftState(league=self.sf, my_slot=1), board, top_n=5)
        self.assertFalse(any(s.player.position in ("K", "DEF") for s in recs))

    def test_superflex_prioritizes_qb_over_similar_wr(self):
        # With the superflex QB premium, a QB should beat a WR of comparable value.
        board = [mk("QBguy", "QB", 90, 3), mk("WRguy", "WR", 95, 2), mk("WR2", "WR", 30, 10, 2)]
        recs = recommend(DraftState(league=self.sf, my_slot=1), board, top_n=3)
        self.assertEqual(recs[0].player.position, "QB")


class TestTEPremium(unittest.TestCase):
    def test_te_points_include_reception_premium(self):
        # TE1 base anchor (PPR) is 250; the +0.5/catch premium pushes it higher.
        self.assertGreater(points_for("TE", 1, "ppr"), 250)

    def test_premium_scales_down_the_ranks(self):
        top = points_for("TE", 1, "ppr")
        mid = points_for("TE", 12, "ppr")
        self.assertGreater(top, mid)


if __name__ == "__main__":
    unittest.main()
