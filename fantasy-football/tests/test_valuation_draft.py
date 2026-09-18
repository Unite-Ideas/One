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

    def test_kickers_and_defenses_suppressed_early(self):
        # No sane draft takes a K or DEF in the first round; they're streamable.
        st = DraftState(league=self.league, my_slot=1)
        recs = recommend(st, self.board, top_n=25)
        self.assertFalse(any(s.player.position in ("K", "DEF") for s in recs))

    def test_starter_need_beats_hoarding(self):
        # With 2 RBs already and no WR, the top rec should NOT be a third RB
        # when a fillable WR starter exists — filling starters takes priority.
        st = DraftState(league=self.league, my_slot=1)
        rbs = [p for p in self.board if p.position == "RB"][:2]
        for r in rbs:
            st.drafted_ids.append(r.player_id)
            st.my_player_ids.append(r.player_id)
        recs = recommend(st, self.board, top_n=5)
        top_positions = {s.player.position for s in recs[:3]}
        # A must-fill starting slot (WR/QB/TE) should appear near the top.
        self.assertTrue(top_positions & {"WR", "QB", "TE"})


class TestExplainLabels(unittest.TestCase):
    def test_adp_value_vs_reach_direction(self):
        from ffball.draft import _explain
        from ffball.models import Player
        league = LeagueConfig.from_preset("standard_12")
        st = DraftState(league=league, my_slot=1)
        st.drafted_ids = ["x"] * 39  # pick 40 on the clock
        self.assertEqual(st.current_overall, 40)
        # Player whose ADP is 20 but still here at 40 = fell 20 past = value.
        fell = Player("a", "Faller", "WR", adp=20.0, pos_rank=5, tier=2)
        # Player usually drafted at 60 but taken now at 40 = 20 early = reach.
        early = Player("b", "Reacher", "WR", adp=60.0, pos_rank=6, tier=2)
        self.assertIn("value", _explain(fell, "depth", 0.0, st))
        self.assertIn("reach", _explain(early, "depth", 0.0, st))


if __name__ == "__main__":
    unittest.main()
