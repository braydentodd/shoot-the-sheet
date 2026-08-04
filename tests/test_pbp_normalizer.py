"""nba_data normalizer tests (foul taxonomy, attributions, neutral
rebounds, substitution pairs)."""

import unittest

from src.lib.pbp_classifier import (
    FieldLookupStrategy,
    build_nba_event_key,
    build_nba_signature,
)
from src.sources.nba_data.pbp_normalizer import normalize_game


class MockResolver:
    """Resolver that treats known team ids as teams and everything else
    as a player on '11' (odd) or '22' (even)."""

    def __init__(self, teams):
        self._teams = set(teams)

    def __call__(self, entity_id):
        entity_id = str(entity_id)
        if entity_id in self._teams:
            return ("team", entity_id)
        return ("player", "11" if int(entity_id) % 2 else "22")


class _C:
    def __init__(self, handling):
        self.handling = handling
        self.is_ignore = False


class MockClassifier:
    """Classifies by a handling map keyed on the event key."""

    def __init__(self, handling_map):
        self._map = handling_map

    def classify(self, row):
        key = FieldLookupStrategy().build_event_key(
            FieldLookupStrategy().build_signature(row)
        )
        h = self._map.get(key)
        if h is None:
            raise Exception(f"unclassified {key}")
        return _C(h)


def row(msgtype, actiontype, p1="0", p2="0", p3="0", p1t="", period=1,
        pctime="12:00", desc=""):
    return {
        "EVENTNUM": "1", "GAME_ID": "G1", "PERIOD": str(period),
        "PCTIMESTRING": pctime, "EVENTMSGTYPE": str(msgtype),
        "EVENTMSGACTIONTYPE": str(actiontype), "HOMEDESCRIPTION": desc,
        "NEUTRALDESCRIPTION": "", "VISITORDESCRIPTION": "",
        "PERSON1TYPE": "1", "PLAYER1_ID": str(p1), "PLAYER1_NAME": "",
        "PLAYER1_TEAM_ID": str(p1t), "PERSON2TYPE": "1",
        "PLAYER2_ID": str(p2), "PLAYER2_NAME": "", "PLAYER2_TEAM_ID": "",
        "PERSON3TYPE": "1", "PLAYER3_ID": str(p3), "PLAYER3_NAME": "",
        "PLAYER3_TEAM_ID": "",
    }


class NormalizerTests(unittest.TestCase):
    def _run(self, rows, handling_map):
        resolver = MockResolver(["11", "22"])
        classifier = MockClassifier(handling_map)
        return normalize_game(rows, "G1", "11", "22", resolver, classifier)

    def test_foul_taxonomy_emits_foul_and_draw(self):
        handling = {
            "MSG=6_ACT=2": "standard_foul",
        }
        events = self._run(
            [row(6, 2, p1="1", p2="2", p1t="11")], handling,
        )
        names = [(e["event"], e["team_id"], e["player_id"]) for e in events]
        # The committer is on 11 (home); the fouled player on 22 (away).
        self.assertIn(("standard_foul", "11", "1"), names)
        self.assertIn(("o_foul_draw", "22", "2"), names)

    def test_elevated_foul(self):
        handling = {"MSG=6_ACT=11": "elevated_foul"}
        events = self._run([row(6, 11, p1="1", p1t="11")], handling)
        self.assertEqual(events[0]["event"], "elevated_foul")

    def test_rebound_is_neutral(self):
        handling = {"MSG=4_ACT=0": "rebound"}
        events = self._run([row(4, 0, p1="1", p1t="11")], handling)
        self.assertEqual(events[0]["event"], "rebound")

    def test_substitution_pair_same_chain(self):
        handling = {"MSG=8_ACT=0": "substitution"}
        events = self._run(
            [row(8, 0, p1="1", p2="2", p1t="11")], handling,
        )
        by_event = {e["event"]: e for e in events}
        self.assertEqual(by_event["player_out"]["player_id"], "1")
        self.assertEqual(by_event["player_in"]["player_id"], "2")
        self.assertEqual(by_event["player_out"]["chain_id"],
                         by_event["player_in"]["chain_id"])

    def test_make_emits_assist(self):
        handling = {"MSG=1_ACT=42_NO=3PT": "fg2_make"}
        events = self._run(
            [row(1, 42, p1="1", p2="2", p1t="11")], handling,
        )
        names = [e["event"] for e in events]
        self.assertIn("fg2_make", names)
        self.assertIn("fg2_assist", names)

    def test_period_events_have_no_team(self):
        handling = {"MSG=12_ACT=0": "period_start"}
        events = self._run([row(12, 0, period=1)], handling)
        self.assertEqual(events[0]["event"], "period_start")
        self.assertEqual(events[0]["team_id"], "")

    def test_sequence_assigned(self):
        handling = {
            "MSG=1_ACT=42_NO=3PT": "fg2_make",
            "MSG=12_ACT=0": "period_start",
        }
        events = self._run(
            [row(12, 0, period=1, pctime="12:00"),
             row(1, 42, p1="1", p2="2", p1t="11", pctime="11:00")],
            handling,
        )
        seqs = [e["seq"] for e in events]
        self.assertEqual(seqs, sorted(seqs))
        self.assertEqual(len(events), 3)  # period_start + make + assist

    def test_signature_builder_matches_discovery(self):
        # A made 3-pointer produces the same key as discovery would.
        sig = build_nba_signature({"EVENTMSGTYPE": "1", "EVENTMSGACTIONTYPE": "10",
                                   "HOMEDESCRIPTION": "James 3PT Jump Shot (3 PTS)",
                                   "NEUTRALDESCRIPTION": "", "VISITORDESCRIPTION": ""})
        self.assertEqual(build_nba_event_key(sig), "MSG=1_ACT=10_HAS=3PT")


if __name__ == "__main__":
    unittest.main()
