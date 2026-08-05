"""Accumulator tests: result-set counts, points from config, seq-based
on-court scoping, clock gating."""

import unittest

from src.definitions.pbp import PBP_EVENTS
from src.lib.pbp_accumulator import (
    accumulate_result_set,
    player_on_court_intervals,
)
from tests.pbp_helpers import ev, untimed


H = "H"
A = "A"


class AccumulatorTests(unittest.TestCase):
    def test_points_from_config(self):
        events = [
            ev("1", "fg2_make", H, "h1"),
            ev("2", "fg3_make", H, "h2"),
            ev("3", "ft1_make", H, "h3"),
            ev("4", "fg2_make", A, "a1"),
        ]
        result = accumulate_result_set(events, "team", H, opp_entity_id=A)
        self.assertEqual(result["points"], 6)  # 2 + 3 + 1
        self.assertEqual(result["win"], True)

    def test_points_honor_multi_point_ft_events(self):
        # Points sum the PBP_EVENTS point values, so a league with
        # 2-point free throws scores them correctly (not ftm*1).
        events = [
            ev("1", "ft2_make", H, "h1"),
            ev("2", "ft3_make", H, "h2"),
        ]
        result = accumulate_result_set(events, "team", H, opp_entity_id=A)
        self.assertEqual(result["ftm"], 2)
        self.assertEqual(result["points"], 5)  # 2 + 3

    def test_assists_counts_both_fg_assist_types(self):
        events = [
            ev("1", "fg2_make", H, "h1"),
            ev("2", "fg2_assist", H, "h2"),
            ev("3", "fg3_make", H, "h1"),
            ev("4", "fg3_assist", H, "h2"),
        ]
        result = accumulate_result_set(events, "team", H, opp_entity_id=A)
        self.assertEqual(result["assists"], 2)
        self.assertEqual(result["fg2_assists"], 1)
        self.assertEqual(result["fg3_assists"], 1)
        self.assertEqual(result["assist_points"], 5)  # 2 + 3

    def test_opp_scope_counts(self):
        events = [
            ev("1", "d_reb", A, "a1"),
            ev("2", "turnover", A, "a1"),
            ev("3", "fg2_make", A, "a1"),
        ]
        # The opponent values live in the opp_team scope row of the same
        # field (no opp_-prefixed field names).
        result = accumulate_result_set(events, "opp_team", H, opp_entity_id=A)
        self.assertEqual(result["d_rebs"], 1)
        self.assertEqual(result["turnovers"], 1)
        self.assertEqual(result["fg2m"], 1)
        self.assertEqual(result["points"], 2)

    def test_ft_points_are_indexed(self):
        self.assertEqual(PBP_EVENTS["ft1_make"]["points"], 1)
        self.assertEqual(PBP_EVENTS["ft2_make"]["points"], 2)
        self.assertEqual(PBP_EVENTS["ft3_make"]["points"], 3)

    def test_fta_counts_consolidated_miss(self):
        # FT misses are one canonical event (ft_miss); FTA counts makes
        # and the miss together.
        events = [
            ev("1", "ft1_make", H, "h1"),
            ev("2", "ft_miss", H, "h1"),
            ev("3", "ft2_make", H, "h1"),
        ]
        result = accumulate_result_set(events, "team", H, opp_entity_id=A)
        self.assertEqual(result["ftm"], 2)
        self.assertEqual(result["fta"], 3)

    def test_on_court_scoping_is_seq_based(self):
        events = [
            ev("1", "player_in", H, "h1"),
            ev("2", "fg2_make", H, "h2"),
            ev("3", "fg2_make", A, "a1"),
            ev("4", "player_out", H, "h1"),
            ev("5", "fg2_make", H, "h2"),
        ]
        for i, e in enumerate(events):
            e["seq"] = i
        intervals = player_on_court_intervals(events, "h1")
        self.assertEqual(intervals, [(0, 3)])
        result = accumulate_result_set(
            events, "on_player", "h1", opp_entity_id=A,
            player_team_id=H, on_court_intervals=intervals,
        )
        # on_* values count teammate/team events while h1 was on court
        # (seq 0..3) -- the same field in the on_player scope.
        self.assertEqual(result["fg2m"], 1)
        self.assertEqual(result["fg2a"], 1)
        self.assertEqual(result["points"], 2)

    def test_clock_gated_fields_none_when_untimed(self):
        events = [
            untimed("1", "player_in", H, "h1"),
            untimed("2", "fg2_make", H, "h1"),
            untimed("3", "player_out", H, "h1"),
        ]
        # Clock-derived fields are scope-specific: secs lives in the player
        # scope; on-court possession seconds in the on_player scope.
        player_result = accumulate_result_set(
            events, "player", "h1", player_team_id=H,
        )
        self.assertIsNone(player_result["secs"])
        self.assertEqual(player_result["fg2m"], 1)
        on_result = accumulate_result_set(
            events, "on_player", "h1", player_team_id=H,
        )
        self.assertIsNone(on_result["o_poss_secs"])

    def test_team_secs_requires_timed_period_ends(self):
        # Team secs reads only period_end events: an untimed period_end
        # yields None even when other events are timed.
        events = [
            ev("1", "period_end", "", period=1, secs=None),
            ev("2", "fg2_make", H, "h1", secs=100),
        ]
        result = accumulate_result_set(events, "team", H, opp_entity_id=A)
        self.assertIsNone(result["secs"])

    def test_possession_secs_sums_timed_windows_only(self):
        # Partially timed game: untimed windows are skipped; timed
        # windows still produce a value, and possession counts stay
        # seq-based.
        events = [
            ev("1", "poss_start", H, secs=10),
            ev("2", "poss_end", H, secs=30),
            ev("3", "poss_start", H, secs=None),
            ev("4", "poss_end", H, secs=None),
        ]
        result = accumulate_result_set(events, "team", H, opp_entity_id=A)
        self.assertEqual(result["o_poss_secs"], 20)
        self.assertEqual(result["poss"], 2)

    def test_possession_secs_none_when_no_timed_window(self):
        events = [
            ev("1", "poss_start", H, secs=None),
            ev("2", "poss_end", H, secs=None),
        ]
        result = accumulate_result_set(events, "team", H, opp_entity_id=A)
        self.assertIsNone(result["o_poss_secs"])
        self.assertEqual(result["poss"], 1)

    def test_player_secs_scoped_to_own_interval(self):
        # Another player's untimed in/out markers must not blank h1's
        # minutes (per-event clock gating).
        events = [
            ev("1", "player_in", H, "h1", secs=0),
            ev("2", "player_out", H, "h1", secs=100),
            ev("3", "player_in", A, "a1", secs=None),
            ev("4", "player_out", A, "a1", secs=None),
        ]
        for i, e in enumerate(events):
            e["seq"] = i
        result = accumulate_result_set(events, "player", "h1", player_team_id=H)
        self.assertEqual(result["secs"], 100)

    def test_poss_count(self):
        events = [
            ev("1", "poss_start", H),
            ev("2", "fg2_make", H, "h1"),
            ev("3", "poss_end", H),
        ]
        result = accumulate_result_set(events, "team", H, opp_entity_id=A)
        self.assertEqual(result["poss"], 1)
        # The opponent scope of poss counts the opponent's windows.
        opp_result = accumulate_result_set(events, "opp_team", H, opp_entity_id=A)
        self.assertEqual(opp_result["poss"], 0)

    def test_on_player_possession_secs_use_team_windows(self):
        # on_player possession seconds measure the PLAYER'S TEAM's windows
        # (o_poss_secs); the opponent's offensive possession seconds are
        # the same field in the opp_player scope (the d_poss_secs column
        # maps that scope).
        events = [
            ev("1", "player_in", H, "h1", secs=0),
            ev("2", "poss_start", H, secs=10),
            ev("3", "turnover", H, "h2", secs=20),
            ev("4", "poss_end", H, secs=30),
            ev("5", "poss_start", A, secs=31),
            ev("6", "turnover", A, "a1", secs=40),
            ev("7", "poss_end", A, secs=50),
            ev("8", "player_out", H, "h1", secs=60),
        ]
        for i, e in enumerate(events):
            e["seq"] = i
        intervals = player_on_court_intervals(events, "h1")
        result = accumulate_result_set(
            events, "on_player", "h1", opp_entity_id=A,
            player_team_id=H, on_court_intervals=intervals,
        )
        # H's window (20s) while h1 was on court.
        self.assertEqual(result["o_poss_secs"], 20)
        # A's window (19s) is the same field in the opp_player scope.
        opp_result = accumulate_result_set(
            events, "opp_player", "h1", opp_entity_id=A,
            player_team_id=H, on_court_intervals=intervals,
        )
        self.assertEqual(opp_result["o_poss_secs"], 19)


if __name__ == "__main__":
    unittest.main()
