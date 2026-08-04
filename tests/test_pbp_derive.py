"""Derivation engine tests: scoring sequences, possession, lineups,
rebounds, fouls/FTs, jump-ball turnovers, and invariants.

Run with ``python -m unittest discover tests``.
"""

import unittest

from src.lib.pbp_derive import derive_game_context_events
from tests.pbp_helpers import ev, events_of, untimed


H = "H"
A = "A"


def full_lineup(period: int = 1, secs: int = 0):
    """Return a full 5-per-team period skeleton (starters via on-court events).

    ``o_foul_draw`` marks on-court without a possession transition.
    """
    rows = [ev("ps", "period_start", "", period=period, secs=secs)]
    for i, pid in enumerate(["h1", "h2", "h3", "h4", "h5"], start=1):
        rows.append(ev(f"hi{i}", "o_foul_draw", H, pid, secs=secs + 1, period=period))
    for i, pid in enumerate(["a1", "a2", "a3", "a4", "a5"], start=1):
        rows.append(ev(f"ai{i}", "o_foul_draw", A, pid, secs=secs + 1, period=period))
    return rows


class ScoringSequenceTests(unittest.TestCase):
    """pot_poss_ending_scoring_opp placement (Section 7.3)."""

    def test_and_one_single_attempt_before_make(self):
        events = full_lineup()
        events += [
            ev("m1", "fg2_make", H, "h1", secs=10),
            ev("f1", "standard_foul", A, "a1", secs=11, chain_id="f1"),
            ev("fd1", "o_foul_draw", H, "h1", secs=11, chain_id="f1"),
            ev("t1", "ft1_make", H, "h1", secs=12),
            ev("pe", "period_end", "", period=1, secs=720),
        ]
        res = derive_game_context_events(events, H, A, lineup_size=5)
        self.assertEqual(len(res.errors), 0, res.errors)
        ppos = events_of(res, "pot_poss_ending_scoring_opp")
        self.assertEqual(len(ppos), 1)
        # The single attempt is placed BEFORE the make, not on the FT.
        make_seq = next(e["seq"] for e in res.events
                        if e["event"] == "fg2_make")
        self.assertEqual(ppos[0]["seq"], make_seq - 1)
        self.assertEqual(ppos[0]["team_id"], H)

    def test_miss_loose_ball_foul_two_attempts(self):
        events = full_lineup()
        events += [
            ev("m1", "fg2_miss", H, "h1", secs=10),
            ev("f1", "standard_foul", A, "a1", secs=11, chain_id="f1"),
            ev("fd1", "o_foul_draw", H, "h4", secs=11, chain_id="f1"),
            ev("t1", "ft1_make", H, "h4", secs=12),
            ev("t2", "ft1_make", H, "h4", secs=13),
            ev("pe", "period_end", "", period=1, secs=720),
        ]
        res = derive_game_context_events(events, H, A, lineup_size=5)
        self.assertEqual(len(res.errors), 0, res.errors)
        ppos = events_of(res, "pot_poss_ending_scoring_opp")
        self.assertEqual(len(ppos), 2)
        self.assertEqual(ppos[0]["team_id"], H)
        self.assertEqual(ppos[1]["team_id"], H)

    def test_miss_o_reb_make_two_attempts(self):
        events = full_lineup()
        events += [
            ev("m1", "fg2_miss", H, "h1", secs=10),
            ev("r1", "o_reb", H, "h2", secs=11),
            ev("m2", "fg2_make", H, "h1", secs=12),
            ev("pe", "period_end", "", period=1, secs=720),
        ]
        res = derive_game_context_events(events, H, A, lineup_size=5)
        self.assertEqual(len(res.errors), 0, res.errors)
        self.assertEqual(len(events_of(res, "pot_poss_ending_scoring_opp")), 2)

    def test_elevated_foul_trip_transparent(self):
        # H possesses: miss -> [elevated pause: A shoots tech FTs] -> make.
        # The trip neither starts nor continues a sequence: one attempt
        # (the miss's); the make continues it.
        events = full_lineup()
        events += [
            ev("m1", "fg2_miss", H, "h1", secs=10),
            ev("f1", "elevated_foul", H, "", secs=11, chain_id="f1"),
            ev("t1", "ft1_make", A, "a4", secs=12),
            ev("m2", "fg2_make", H, "h2", secs=20),
            ev("pe", "period_end", "", period=1, secs=720),
        ]
        res = derive_game_context_events(events, H, A, lineup_size=5)
        self.assertEqual(len(res.errors), 0, res.errors)
        ppos = events_of(res, "pot_poss_ending_scoring_opp")
        self.assertEqual(len(ppos), 1)
        self.assertEqual(ppos[0]["team_id"], H)
        # The possession window spans the pause untouched.
        starts = events_of(res, "poss_start")
        self.assertEqual([e["team_id"] for e in starts], [H])

    def test_standard_trip_fresh_sequence(self):
        # H make, then a fresh standard trip by A (foul on A's a4).
        events = full_lineup()
        events += [
            ev("m1", "fg2_make", H, "h1", secs=10),
            ev("f1", "standard_foul", H, "h3", secs=11, chain_id="f1"),
            ev("fd1", "o_foul_draw", A, "a4", secs=11, chain_id="f1"),
            ev("t1", "ft1_make", A, "a4", secs=12),
            ev("t2", "ft1_make", A, "a4", secs=13),
            ev("pe", "period_end", "", period=1, secs=720),
        ]
        res = derive_game_context_events(events, H, A, lineup_size=5)
        self.assertEqual(len(res.errors), 0, res.errors)
        # The make is its own attempt; the standard trip is its own.
        self.assertEqual(len(events_of(res, "pot_poss_ending_scoring_opp")), 2)


class PossessionTests(unittest.TestCase):
    """Possession markers, transitions, and synthesis (Section 7.2/7.6)."""

    def test_poss_start_placed_at_period_start(self):
        events = full_lineup()
        events += [
            ev("m1", "fg2_make", H, "h1", secs=10),
            ev("pe", "period_end", "", period=1, secs=720),
        ]
        res = derive_game_context_events(events, H, A, lineup_size=5)
        self.assertEqual(len(res.errors), 0, res.errors)
        ps = next(e for e in res.events if e["event"] == "poss_start")
        period_start = next(e for e in res.events if e["event"] == "period_start")
        self.assertEqual(ps["seq"], period_start["seq"] + 1)

    def test_make_transition_closes_and_opens(self):
        events = full_lineup()
        events += [
            ev("m1", "fg2_make", H, "h1", secs=10),
            ev("m2", "fg2_make", A, "a1", secs=20),
            ev("pe", "period_end", "", period=1, secs=720),
        ]
        res = derive_game_context_events(events, H, A, lineup_size=5)
        self.assertEqual(len(res.errors), 0, res.errors)
        starts = events_of(res, "poss_start")
        ends = events_of(res, "poss_end")
        # H opens; H's make closes H and opens A; A's make closes A and
        # opens H; the final H window is empty (no indicate_poss) and is
        # removed by the empty-window cleanup.
        self.assertEqual([e["team_id"] for e in starts], [H, A])
        self.assertEqual([e["team_id"] for e in ends], [H, A])

    def test_empty_final_window_removed(self):
        events = full_lineup()
        events += [
            ev("m1", "fg2_make", H, "h1", secs=10),
            ev("pe", "period_end", "", period=1, secs=720),
        ]
        res = derive_game_context_events(events, H, A, lineup_size=5)
        self.assertEqual(len(res.errors), 0, res.errors)
        starts = events_of(res, "poss_start")
        ends = events_of(res, "poss_end")
        self.assertEqual(len(starts), 1)
        self.assertEqual(len(ends), 1)

    def test_jump_ball_turnover_synthesis(self):
        events = full_lineup()
        events += [
            ev("m1", "fg2_make", H, "h1", secs=10),
            # H made -> A possesses; H wins the held ball -> synthesized
            # team turnover for A.
            ev("jb", "jump_ball_win", H, secs=11),
            ev("m2", "fg2_make", H, "h1", secs=20),
            ev("pe", "period_end", "", period=1, secs=720),
        ]
        res = derive_game_context_events(events, H, A, lineup_size=5)
        self.assertEqual(len(res.errors), 0, res.errors)
        tovs = [e for e in res.events if e["event"] == "turnover"]
        # A synthesized team turnover for A (the possessor).
        self.assertEqual(len(tovs), 1)
        self.assertEqual(tovs[0]["team_id"], A)
        self.assertEqual(tovs[0]["player_id"], "")
        self.assertTrue(tovs[0]["source"].startswith("derived:"))

    def test_jump_ball_opening_tip_no_synthesis(self):
        events = full_lineup()
        events += [
            ev("jb", "jump_ball_win", H, secs=1),
            ev("m1", "fg2_make", H, "h1", secs=10),
            ev("pe", "period_end", "", period=1, secs=720),
        ]
        res = derive_game_context_events(events, H, A, lineup_size=5)
        self.assertEqual(len(res.errors), 0, res.errors)
        self.assertEqual(len(events_of(res, "turnover")), 0)

    def test_poss_mismatch_is_error(self):
        events = full_lineup()
        events += [
            ev("jb", "jump_ball_win", H, secs=1),
            # A makes while H possesses (the opening tip went to H).
            ev("m1", "fg2_make", A, "a1", secs=10),
            ev("pe", "period_end", "", period=1, secs=720),
        ]
        res = derive_game_context_events(events, H, A, lineup_size=5)
        rules = {er.rule for er in res.errors}
        self.assertIn("poss_mismatch", rules)

    def test_poss_markers_pair(self):
        events = full_lineup()
        events += [
            ev("m1", "fg2_make", H, "h1", secs=10),
            ev("pe", "period_end", "", period=1, secs=720),
        ]
        res = derive_game_context_events(events, H, A, lineup_size=5)
        self.assertEqual(len(events_of(res, "poss_start")),
                         len(events_of(res, "poss_end")))


class ReboundTests(unittest.TestCase):
    """Rebound chaining, suppression, and synthesis (Section 7.4)."""

    def test_rebound_off_def_from_chain(self):
        events = full_lineup()
        events += [
            ev("m1", "fg2_miss", H, "h1", secs=10),
            ev("r1", "rebound", A, "a2", secs=11),
            ev("pe", "period_end", "", period=1, secs=720),
        ]
        res = derive_game_context_events(events, H, A, lineup_size=5)
        self.assertEqual(len(res.errors), 0, res.errors)
        rebs = [e for e in res.events if e["event"] in ("o_reb", "d_reb")]
        self.assertEqual(len(rebs), 1)
        self.assertEqual(rebs[0]["event"], "d_reb")

    def test_intra_trip_rebound_suppressed(self):
        events = full_lineup()
        events += [
            ev("f1", "standard_foul", A, "a1", secs=10, chain_id="f1"),
            ev("fd1", "o_foul_draw", H, "h4", secs=10, chain_id="f1"),
            ev("t1", "ft1_miss", H, "h4", secs=11),
            ev("r1", "o_reb", H, "", secs=12),
            ev("t2", "ft1_make", H, "h4", secs=13),
            ev("pe", "period_end", "", period=1, secs=720),
        ]
        res = derive_game_context_events(events, H, A, lineup_size=5)
        self.assertEqual(len(res.errors), 0, res.errors)
        self.assertEqual(len(events_of(res, "o_reb")), 0)

    def test_sequence_final_miss_synthesizes_team_rebound(self):
        events = full_lineup()
        events += [
            ev("m1", "fg2_miss", H, "h1", secs=10),
            ev("f1", "standard_foul", A, "a1", secs=11, chain_id="f1"),
            ev("fd1", "o_foul_draw", H, "h4", secs=11, chain_id="f1"),
            ev("t1", "ft1_make", H, "h4", secs=12),
            ev("pe", "period_end", "", period=1, secs=720),
        ]
        res = derive_game_context_events(events, H, A, lineup_size=5)
        self.assertEqual(len(res.errors), 0, res.errors)
        # The miss is sequence-final with no rebound: the next
        # indicate_poss is the trip's ppo (same team) -> team o_reb.
        syn = [e for e in res.events if e["source"] == "derived:team_rebound"]
        self.assertEqual(len(syn), 1)
        self.assertEqual(syn[0]["event"], "o_reb")
        self.assertEqual(syn[0]["player_id"], "")
        # The synthesized rebound carries the anchor's timestamp.
        self.assertEqual(syn[0]["secs"], 10)

    def test_period_end_rebound_goes_to_defender(self):
        events = full_lineup()
        events += [
            ev("m1", "fg2_miss", H, "h1", secs=700),
            ev("pe", "period_end", "", period=1, secs=720),
        ]
        res = derive_game_context_events(events, H, A, lineup_size=5)
        self.assertEqual(len(res.errors), 0, res.errors)
        syn = [e for e in res.events if e["source"] == "derived:team_rebound"]
        self.assertEqual(len(syn), 1)
        self.assertEqual(syn[0]["event"], "d_reb")
        self.assertEqual(syn[0]["team_id"], A)


class FoulFtTests(unittest.TestCase):
    """Foul taxonomy and FT chaining (Section 7.5)."""

    def test_ft_without_foul_errors(self):
        events = full_lineup()
        events += [
            ev("t1", "ft1_make", H, "h1", secs=10),
            ev("pe", "period_end", "", period=1, secs=720),
        ]
        res = derive_game_context_events(events, H, A, lineup_size=5)
        rules = {er.rule for er in res.errors}
        self.assertIn("ft_without_foul", rules)

    def test_elevated_ft_trip_does_not_transition(self):
        events = full_lineup()
        events += [
            ev("m1", "fg2_make", H, "h1", secs=10),
            ev("f1", "elevated_foul", A, "", secs=11, chain_id="f1"),
            ev("t1", "ft1_make", A, "a4", secs=12),
            ev("m2", "fg2_make", A, "a1", secs=20),
            ev("pe", "period_end", "", period=1, secs=720),
        ]
        res = derive_game_context_events(events, H, A, lineup_size=5)
        self.assertEqual(len(res.errors), 0, res.errors)
        # A's window spans the elevated pause without markers.
        starts = events_of(res, "poss_start")
        self.assertEqual([e["team_id"] for e in starts], [H, A])

    def test_fouled_shot_miss_removed(self):
        events = full_lineup()
        events += [
            ev("m1", "fg2_miss", H, "h1", secs=10),
            ev("f1", "standard_foul", A, "a1", secs=11, chain_id="f1"),
            ev("fd1", "o_foul_draw", H, "h1", secs=11, chain_id="f1"),
            ev("t1", "ft1_make", H, "h1", secs=12),
            ev("pe", "period_end", "", period=1, secs=720),
        ]
        res = derive_game_context_events(events, H, A, lineup_size=5)
        rules = {er.rule for er in res.errors}
        self.assertIn("fouled_shot_miss", rules)
        self.assertEqual(len(events_of(res, "fg2_miss")), 0)


class LineupTests(unittest.TestCase):
    """Lineup derivation: starters, sweeps, boundary subs (Section 7.1)."""

    def test_sweep_at_period_end_and_starters(self):
        events = full_lineup(period=1, secs=0)
        events += [ev("pe", "period_end", "", period=1, secs=720)]
        res = derive_game_context_events(events, H, A, lineup_size=5)
        self.assertEqual(len(res.errors), 0, res.errors)
        # 5 starters per team in period 1; 5 sweeps per team at the end.
        ins = events_of(res, "player_in")
        outs = events_of(res, "player_out")
        self.assertEqual(len(ins), 10)
        self.assertEqual(len(outs), 10)
        for e in ins:
            self.assertEqual(e["source"], "derived:starter")

    def test_lineup_never_carries_over(self):
        # Period 1: h1..h5.  Period 2: only a1..a5 appear.
        events = full_lineup(period=1, secs=0)
        events += [ev("pe", "period_end", "", period=1, secs=720)]
        events += [ev("ps2", "period_start", "", period=2, secs=720)]
        for i, pid in enumerate(["a1", "a2", "a3", "a4", "a5"]):
            events.append(ev(f"p2a{i}", "o_foul_draw", A, pid, secs=730, period=2))
        events += [ev("pe2", "period_end", "", period=2, secs=1440)]
        res = derive_game_context_events(events, H, A, lineup_size=5)
        # H has no period-2 activity: lineup_too_small fires for H.
        rules = {er.rule for er in res.errors}
        self.assertIn("lineup_too_small", rules)
        # A's period-2 starters are derived fresh (no carryover of H).
        p2_ins = [e for e in events_of(res, "player_in")
                  if e.get("period") == 2]
        self.assertEqual({e["player_id"] for e in p2_ins},
                         {"a1", "a2", "a3", "a4", "a5"})

    def test_boundary_sub_period2(self):
        # Period 2 opens with a boundary sub pair (h6 in, h1 out) before
        # any on-court event: h6 is a starter, h1 is not.
        events = full_lineup(period=1, secs=0)
        events += [ev("pe", "period_end", "", period=1, secs=720)]
        events += [ev("ps2", "period_start", "", period=2, secs=720)]
        events += [
            ev("sub", "player_out", H, "h1", secs=721, period=2, chain_id="sub"),
            ev("sub", "player_in", H, "h6", secs=721, period=2, chain_id="sub"),
        ]
        for i, pid in enumerate(["h6", "h2", "h3", "h4", "h5"]):
            events.append(ev(f"b{i}", "o_foul_draw", H, pid, secs=730, period=2))
        for i, pid in enumerate(["a1", "a2", "a3", "a4", "a5"]):
            events.append(ev(f"c{i}", "o_foul_draw", A, pid, secs=730, period=2))
        events += [ev("pe2", "period_end", "", period=2, secs=1440)]
        res = derive_game_context_events(events, H, A, lineup_size=5)
        self.assertEqual(len(res.errors), 0, res.errors)
        p2_h_ins = [e["player_id"] for e in events_of(res, "player_in")
                    if e.get("period") == 2 and e["team_id"] == H]
        self.assertIn("h6", p2_h_ins)
        self.assertNotIn("h1", p2_h_ins)

    def test_over_lineup_errors(self):
        events = full_lineup(period=1, secs=0)
        events += [
            ev("x", "fg2_make", H, "h6", secs=5),
            ev("pe", "period_end", "", period=1, secs=720),
        ]
        res = derive_game_context_events(events, H, A, lineup_size=5)
        rules = {er.rule for er in res.errors}
        self.assertIn("lineup_too_large", rules)


class UntimedTests(unittest.TestCase):
    """No-timestamp games derive identically (Section 8)."""

    def test_untimed_game_derives(self):
        events = [
            untimed("1", "period_start", "", period=1),
            untimed("2", "jump_ball_win", H, period=1),
            untimed("3", "fg2_make", H, "h1", period=1),
            untimed("4", "fg2_make", A, "a1", period=1),
            untimed("5", "period_end", "", period=1),
        ]
        res = derive_game_context_events(events, H, A, lineup_size=1)
        # lineup_size=1 so the single-event starters are valid.
        self.assertEqual(len(res.errors), 0, res.errors)
        self.assertEqual(len(events_of(res, "poss_start")),
                         len(events_of(res, "poss_end")))


class InvariantTests(unittest.TestCase):
    """Pairing and end-of-game invariants."""

    def test_activity_after_final_period_end_errors(self):
        events = full_lineup(period=1, secs=0)
        events += [
            ev("pe", "period_end", "", period=1, secs=720),
            ev("late", "fg2_make", H, "h1", secs=800),
        ]
        res = derive_game_context_events(events, H, A, lineup_size=5)
        rules = {er.rule for er in res.errors}
        self.assertIn("activity_after_end", rules)

    def test_event_off_court_errors(self):
        events = full_lineup(period=1, secs=0)
        events += [
            # h1 leaves the court, then acts -> off-court activity.
            ev("out1", "player_out", H, "h1", secs=5),
            ev("x", "fg2_make", H, "h1", secs=6),
            ev("pe", "period_end", "", period=1, secs=720),
        ]
        res = derive_game_context_events(events, H, A, lineup_size=5)
        rules = {er.rule for er in res.errors}
        self.assertIn("event_off_court", rules)


if __name__ == "__main__":
    unittest.main()
