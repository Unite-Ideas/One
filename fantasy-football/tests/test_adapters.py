"""Tests for the pluggable league-source layer (offline, no network)."""
import unittest

from ffball import leagues
from ffball.adapters import SleeperSource, apply_scoring
from ffball.adapters import sleeper as sleeper_mod


class TestApplyScoring(unittest.TestCase):
    def test_dot_product_with_te_premium(self):
        scoring = {"rec": 1.0, "rec_td": 6.0, "rec_yd": 0.1, "bonus_rec_te": 0.5, "pass_int": -1.0}
        stats = {"rec": 5, "rec_td": 1, "rec_yd": 80, "bonus_rec_te": 4}
        # 5 + 6 + 8 + 2 = 21
        self.assertEqual(apply_scoring(stats, scoring), 21.0)

    def test_ignores_keys_absent_from_scoring(self):
        self.assertEqual(apply_scoring({"gp": 1, "adp_dd_ppr": 50, "rec": 3}, {"rec": 1.0}), 3.0)


FAKE = {
    "state": {"week": 3, "season": "2026"},
    "league": {"name": "T", "total_rosters": 10, "roster_positions": ["QB", "RB", "BN"],
               "scoring_settings": {"rec": 1.0, "rec_td": 6.0},
               "settings": {"playoff_week_start": 15, "playoff_teams": 6}},
    "users": [{"user_id": "u1", "display_name": "Alice"},
              {"user_id": "u2", "metadata": {"team_name": "Bravo"}}],
    "rosters": [{"roster_id": 1, "owner_id": "u1", "players": [10, 11]},
                {"roster_id": 2, "owner_id": "u2", "players": [20]}],
    "matchups": [{"roster_id": 1, "matchup_id": 1, "points": 100.5, "starters": [10, "0", 11]},
                 {"roster_id": 2, "matchup_id": 1, "points": 90, "starters": [20]}],
    "players": {"10": {"full_name": "Joe QB", "position": "QB", "injury_status": "Questionable"},
                "20": {"first_name": "Bo", "last_name": "RB", "position": "RB", "injury_status": ""}},
    "trending": [{"player_id": "20", "count": 999}],
    "proj": [{"player_id": "10", "stats": {"rec": 0, "rec_td": 2}, "opponent": "KC", "team": "SF"}],
}


def fake_http(url, timeout=60):
    if "/state/" in url:
        return FAKE["state"]
    if url.endswith("/users"):
        return FAKE["users"]
    if url.endswith("/rosters"):
        return FAKE["rosters"]
    if "/matchups/" in url:
        return FAKE["matchups"]
    if url.endswith("/players/nfl"):
        return FAKE["players"]
    if "trending/add" in url:
        return FAKE["trending"]
    if "/projections/" in url:
        return FAKE["proj"]
    if "/league/" in url:
        return FAKE["league"]
    raise AssertionError("unexpected url " + url)


class TestSleeperSource(unittest.TestCase):
    def setUp(self):
        self._orig = sleeper_mod.http_json
        sleeper_mod.http_json = fake_http
        self.src = SleeperSource("123", "Alice")

    def tearDown(self):
        sleeper_mod.http_json = self._orig

    def test_state(self):
        self.assertEqual(self.src.state(), {"week": 3, "season": "2026"})

    def test_rosters_normalized_with_owner_names(self):
        rs = self.src.rosters()
        self.assertEqual(rs[0], {"roster_id": 1, "owner": "Alice", "owner_id": "u1", "players": ["10", "11"]})
        self.assertEqual(rs[1]["owner"], "Bravo")             # team_name preferred over display_name

    def test_matchups_drop_empty_slots(self):
        m = self.src.matchups(3)[0]
        self.assertEqual(m["starters"], ["10", "11"])         # "0" placeholder removed
        self.assertEqual(m["points"], 100.5)

    def test_player_meta_injury_normalized(self):
        pm = self.src.player_meta()
        self.assertEqual(pm["10"]["injury"], "Q")             # Questionable -> Q
        self.assertEqual(pm["20"]["injury"], "")              # healthy/blank -> none
        self.assertEqual(pm["20"]["name"], "Bo RB")           # first+last fallback

    def test_trending(self):
        self.assertEqual(self.src.trending(), {"20": 999})

    def test_weekly_projection_applies_league_scoring(self):
        wk = self.src.weekly_projections("2026", 3, {"rec": 1.0, "rec_td": 6.0})
        self.assertEqual(wk["10"]["wk"], 12.0)                # 2 TD * 6
        self.assertEqual(wk["10"]["opp"], "KC")


class TestRegistry(unittest.TestCase):
    def test_default_league_resolves_to_sleeper(self):
        lg = leagues.get_league()
        self.assertEqual(lg.platform, "sleeper")
        self.assertEqual(lg.league_id, "1395483423719587840")
        self.assertEqual(lg.my_owner, "GodModeEnabled")
        self.assertIsInstance(lg.source(), SleeperSource)

    def test_available_lists_the_default(self):
        self.assertIn("sleeper-finaldraft", leagues.available())


if __name__ == "__main__":
    unittest.main()
