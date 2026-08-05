"""Clock-completion pass tests: scoped per-period forward fill of missing secs.

Only ``PBP_CLOCK_EVENTS`` event types (period boundaries, player in/out
markers, possession markers) are filled; every other event keeps its own
parsed ``secs`` (or None).  A filled event inherits the nearest previous
timed event in the same period; a period with no clock data stays None.
"""

import unittest

from src.lib.pbp_clock import fill_missing_secs
from tests.pbp_helpers import ev, untimed


class FillMissingSecsTests(unittest.TestCase):
    def test_fills_clock_required_events_from_nearest_previous_timed(self):
        events = [
            ev("1", "period_start", "", period=1, secs=0),
            ev("2", "player_in", "H", "h1", period=1, secs=None),
            ev("3", "fg2_make", "H", "h1", period=1, secs=100),
            ev("4", "turnover", "A", "a1", period=1, secs=None),
            ev("5", "player_out", "H", "h1", period=1, secs=None),
        ]
        fill_missing_secs(events)
        self.assertEqual(
            [e["secs"] for e in events], [0, 0, 100, None, 100],
        )

    def test_non_clock_required_events_keep_their_own_missing_secs(self):
        # A timed non-eligible event is a valid clock source for later
        # eligible events, but an untimed non-eligible event is never
        # filled itself.
        events = [
            ev("1", "period_start", "", period=1, secs=0),
            ev("2", "fg2_make", "H", "h1", period=1, secs=None),
            ev("3", "poss_start", "H", period=1, secs=None),
            ev("4", "turnover", "A", "a1", period=1, secs=None),
        ]
        fill_missing_secs(events)
        self.assertEqual(
            [e["secs"] for e in events], [0, None, 0, None],
        )

    def test_never_fabricates_an_unknown_clock_period(self):
        events = [
            ev("1", "period_start", "", period=1, secs=0),
            ev("2", "fg2_make", "H", "h1", period=1, secs=None),
            ev("3", "period_start", "", period=2, secs=None),
            ev("4", "poss_end", "H", period=2, secs=None),
        ]
        fill_missing_secs(events)
        self.assertEqual(events[0]["secs"], 0)
        self.assertIsNone(events[1]["secs"])
        self.assertIsNone(events[2]["secs"])
        self.assertIsNone(events[3]["secs"])

    def test_never_crosses_period_boundaries(self):
        events = [
            ev("1", "period_start", "", period=1, secs=0),
            ev("2", "player_in", "H", "h1", period=1, secs=None),
            ev("3", "period_start", "", period=2, secs=720),
            ev("4", "player_out", "H", "h1", period=2, secs=None),
        ]
        fill_missing_secs(events)
        self.assertEqual(
            [e["secs"] for e in events], [0, 0, 720, 720],
        )

    def test_fully_timed_and_fully_untimed_are_no_ops(self):
        timed = [
            ev("1", "period_start", "", period=1, secs=0),
            ev("2", "player_in", "H", "h1", period=1, secs=10),
            ev("3", "period_end", "", period=1, secs=720),
        ]
        fill_missing_secs(timed)
        self.assertEqual([e["secs"] for e in timed], [0, 10, 720])

        blank = [
            untimed("1", "period_start", "", period=1),
            untimed("2", "player_in", "H", "h1", period=1),
            untimed("3", "period_end", "", period=1),
        ]
        fill_missing_secs(blank)
        self.assertTrue(all(e["secs"] is None for e in blank))


if __name__ == "__main__":
    unittest.main()
