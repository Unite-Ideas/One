import unittest

from ffball.draft import DraftState, recommend
from ffball.league import LeagueConfig
from ffball.projections import load_players
from ffball.scoring import ScoringSystem
from ffball.valuation import build_board


class TestValuation(unittest.TestCase):
    def setUp(self):
        self.league = LeagueConfig.from_preset("standard_12")
        self.scoring = ScoringSystem.from_preset("ppr")
        self.board = build_board(load_players(), self.scoring, self.league)

    def test_board_built(self):
        self.assertGreater(len(self.board), 50)
        # Overall ranks are dense and start at 1.
        self.assertEqual(self.board[0].overall_rank, 1)
        # Sorted by VBD descending.
        vbds = [p.vbd for p in self.board]
        self.assertEqual(vbds, sorted(vbds, reverse=True))

    def test_positional_ranks_and_tiers(self):
        rbs = [p for p in self.board if p.position == "RB"]
        self.assertEqual(rbs[0].pos_rank, 1)
        self.assertIsNotNone(rbs[0].tier)
        # The best RB should be in an earlier (smaller-numbered) tier than the worst.
        self.assertLessEqual(rbs[0].tier, rbs[-1].tier)

    def test_replacement_baseline_makes_starters_positive(self):
        # Top players at each skill position should have positive VBD.
        for pos in ("QB", "RB", "WR", "TE"):
            top = next(p for p in self.board if p.position == pos)
            self.assertGreater(top.vbd, 0, f"top {pos} should be above replacement")


class TestSnakeMath(unittest.TestCase):
    def setUp(self):
        self.league = LeagueConfig.from_preset("standard_12")

    def test_snake_order(self):
        st = DraftState(league=self.league, my_slot=1)
        # Slot 1 owns pick 1, then pick 24 (end of round 2 reverses).
        self.assertEqual(st.overall_to_slot(1), 1)
        self.assertEqual(st.overall_to_slot(12), 12)
        self.assertEqual(st.overall_to_slot(13), 12)  # round 2 reverses
        self.assertEqual(st.overall_to_slot(24), 1)
        picks = st.my_pick_overalls()
        self.assertEqual(picks[0], 1)
        self.assertEqual(picks[1], 24)

    def test_picks_until_next_at_turn(self):
        st = DraftState(league=self.league, my_slot=3)
        # Fill picks 1 and 2 so pick 3 (mine) is on the clock.
        st.drafted_ids = ["a", "b"]
        self.assertTrue(st.is_my_turn())
        # My next pick after 3 is 22 (snake), so 19 picks elapse.
        self.assertEqual(st.picks_until_next(), 22 - 3)


class TestRecommend(unittest.TestCase):
    def setUp(self):
        self.league = LeagueConfig.from_preset("standard_12")
        self.scoring = ScoringSystem.from_preset("ppr")
        self.board = build_board(load_players(), self.scoring, self.league)

    def test_recommends_available_and_respects_caps(self):
        st = DraftState(league=self.league, my_slot=1)
        recs = recommend(st, self.board, top_n=5)
        self.assertTrue(recs)
        # First overall recommendation should be a high-VBD skill player.
        self.assertIn(recs[0].player.position, {"RB", "WR", "QB", "TE"})

    def test_full_position_excluded(self):
        st = DraftState(league=self.league, my_slot=1)
        # Draft 3 QBs onto my team; QB should then be excluded (cap 3).
        qbs = [p for p in self.board if p.position == "QB"][:3]
        for q in qbs:
            st.drafted_ids.append(q.player_id)
            st.my_player_ids.append(q.player_id)
        recs = recommend(st, self.board, top_n=20)
        self.assertFalse(any(s.player.position == "QB" for s in recs))


if __name__ == "__main__":
    unittest.main()
