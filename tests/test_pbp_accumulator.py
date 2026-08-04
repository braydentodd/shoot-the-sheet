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

    def test_ft_points_are_indexed(self):
        self.assertEqual(PBP_EVENTS["ft1_make"]["points"], 1)
        self.assertEqual(PBP_EVENTS["ft2_make"]["points"], 2)
        self.assertEqual(PBP_EVENTS["ft3_make"]["points"], 3)

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
            events, "player", "h1", opp_entity_id=A,
            player_team_id=H, on_court_intervals=intervals,
        )
        # on_* counts only events while h1 was on court (seq 0..3).
        self.assertEqual(result["on_fg2m"], 1)
        self.assertEqual(result["on_fg2a"], 1)

    def test_clock_gated_fields_none_when_untimed(self):
        events = [
            untimed("1", "player_in", H, "h1"),
            untimed("2", "fg2_make", H, "h1"),
            untimed("3", "player_out", H, "h1"),
        ]
        result = accumulate_result_set(events, "player", "h1", player_team_id=H)
        self.assertIsNone(result["secs"])
        self.assertIsNone(result["o_poss_secs"])
        # Non-clock fields still compute.
        self.assertEqual(result["fg2m"], 1)

    def test_poss_count(self):
        events = [
            ev("1", "poss_start", H),
            ev("2", "fg2_make", H, "h1"),
            ev("3", "poss_end", H),
        ]
        result = accumulate_result_set(events, "team", H, opp_entity_id=A)
        self.assertEqual(result["poss"], 1)


if __name__ == "__main__":
    unittest.main()
