import unittest

from ffball.scoring import ScoringSystem, score_stats


class TestScoring(unittest.TestCase):
    def test_ppr_vs_standard_reception_value(self):
        stats = {"rec": 100, "rec_yd": 1200, "rec_td": 10}
        ppr = ScoringSystem.from_preset("ppr").score(stats)
        std = ScoringSystem.from_preset("standard").score(stats)
        # PPR should be exactly 100 points higher (1 pt/reception * 100).
        self.assertAlmostEqual(ppr - std, 100.0, places=2)

    def test_half_ppr_between(self):
        stats = {"rec": 80}
        half = ScoringSystem.from_preset("half_ppr").score(stats)
        self.assertAlmostEqual(half, 40.0, places=2)

    def test_qb_line(self):
        stats = {"pass_yd": 4500, "pass_td": 35, "pass_int": 10, "rush_yd": 300, "rush_td": 3}
        # 4500*.04 + 35*4 + 10*-2 + 300*.1 + 3*6 = 180 +140 -20 +30 +18 = 348
        self.assertAlmostEqual(ScoringSystem.from_preset("ppr").score(stats), 348.0, places=2)

    def test_unknown_stats_and_weights_ignored(self):
        # Stat with no weight and weight with no stat both contribute nothing.
        self.assertEqual(score_stats({"mystery_stat": 999}, {"rec": 1.0}), 0.0)

    def test_from_sleeper_league(self):
        league = {"name": "Test", "scoring_settings": {"rec": 0.5, "rec_yd": 0.1, "_x": "meta"}}
        s = ScoringSystem.from_sleeper_league(league)
        self.assertEqual(s.is_ppr(), 0.5)
        self.assertAlmostEqual(s.score({"rec": 10, "rec_yd": 100}), 15.0, places=2)


if __name__ == "__main__":
    unittest.main()
