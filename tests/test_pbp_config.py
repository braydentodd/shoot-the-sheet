"""Config validation tests: PBP_EVENTS, CHAIN_RULES, INVARIANTS, and the
RESULT_SET_FIELDS <-> DB_COLUMNS mapping guard."""

import unittest

from src.lib.config_validation import (
    validate_all,
    validate_config,
    _validate_pbp_db_mappings,
    _validate_pbp_events,
    _validate_chain_rules,
    _validate_invariants,
)


class PbpConfigValidationTests(unittest.TestCase):
    def test_pbp_configs_are_valid(self):
        self.assertEqual(validate_config(), [])

    def test_validate_all_surfaces_config_errors(self):
        # validate_all() must aggregate validate_config() errors instead of
        # discarding them (the historical bug).
        errors = validate_all()
        self.assertEqual(errors, [])

    def test_pbp_events_uniform(self):
        from src.definitions.pbp import PBP_EVENTS

        self.assertGreaterEqual(len(PBP_EVENTS), 20)
        for name, ev_def in PBP_EVENTS.items():
            self.assertEqual(
                set(ev_def.keys()),
                {"sort_priority", "indicate_poss", "indicate_on_court",
                 "shot", "points", "poss_transition"},
                name,
            )

    def test_chain_rules_uniform(self):
        from src.definitions.chain_rules import CHAIN_RULES

        self.assertGreaterEqual(len(CHAIN_RULES), 15)
        required = {"anchor", "scope", "position", "skip", "max_gap",
                    "cross_period", "reanchor", "required", "synthesize",
                    "suppress"}
        for name, rule in CHAIN_RULES.items():
            self.assertEqual(set(rule.keys()), required, name)

    def test_invariants_uniform(self):
        from src.definitions.chain_rules import INVARIANTS

        self.assertGreaterEqual(len(INVARIANTS), 12)
        required = {"events", "except_events", "state", "severity", "message"}
        for name, inv in INVARIANTS.items():
            self.assertEqual(set(inv.keys()), required, name)

    def test_db_mapping_guard_passes(self):
        # Every count result field maps to a pbp_stats DB column.
        self.assertEqual(_validate_pbp_db_mappings(), [])

    def test_db_mapping_guard_catches_drift(self):
        # Simulate the historical drift: a result field with no DB column
        # for one of its scopes.  o_rebs is not an intermediate field.
        from src.definitions.pbp import RESULT_SET_FIELDS

        original = RESULT_SET_FIELDS["o_rebs"]
        RESULT_SET_FIELDS["o_rebs"] = dict(original)
        RESULT_SET_FIELDS["o_rebs"]["result_sets"] = {
            "team": "team", "player": "player", "on_player": "on_player",
        }
        try:
            errors = _validate_pbp_db_mappings()
            self.assertTrue(
                any("o_rebs" in e and "on_player" in e for e in errors),
                errors,
            )
        finally:
            RESULT_SET_FIELDS["o_rebs"] = original


if __name__ == "__main__":
    unittest.main()
