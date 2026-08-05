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
                {"indicate_poss", "indicate_on_court", "shot", "points",
                 "shot_family", "shot_result", "foul_family",
                 "poss_transition"},
                name,
            )

    def test_chain_rules_uniform(self):
        from src.definitions.pbp import CHAIN_RULES

        self.assertGreaterEqual(len(CHAIN_RULES), 15)
        required = {"anchor", "scope", "skip", "max_gap",
                    "cross_period", "reanchor", "required", "synthesize",
                    "suppress", "superseded_by"}
        for name, rule in CHAIN_RULES.items():
            self.assertEqual(set(rule.keys()), required, name)
            self.assertIsInstance(rule["anchor"], tuple)

    def test_invariants_uniform(self):
        from src.definitions.pbp import INVARIANTS

        self.assertGreaterEqual(len(INVARIANTS), 12)
        required = {"except_events", "severity"}
        for name, inv in INVARIANTS.items():
            self.assertEqual(set(inv.keys()), required, name)

    def test_ft_misses_consolidated(self):
        # FT misses are one canonical event (ft_miss, 0 points); the
        # per-index miss events no longer exist anywhere in the config.
        from src.definitions.pbp import CHAIN_RULES, PBP_EVENTS

        self.assertIn("ft_miss", PBP_EVENTS)
        self.assertEqual(PBP_EVENTS["ft_miss"]["points"], 0)
        self.assertEqual(PBP_EVENTS["ft_miss"]["shot_family"], "ft")
        self.assertEqual(PBP_EVENTS["ft_miss"]["shot_result"], "miss")
        for name in ("ft1_miss", "ft2_miss", "ft3_miss"):
            self.assertNotIn(name, PBP_EVENTS)
            self.assertNotIn(name, CHAIN_RULES)
        self.assertIn("ft_miss", CHAIN_RULES)
        # The FT chain skip lists reference the consolidated miss (and no
        # stale per-index miss names).
        for name in ("ft1_make", "ft2_make", "ft3_make", "ft_miss"):
            self.assertIn("ft_miss", CHAIN_RULES[name]["skip"])

    def test_column_checks_complete(self):
        # Directive-6 picklists: laterality is inline, target derives
        # from the schema registry, col_name is unconstrained (None).
        from src.definitions.db_columns import (
            DB_COLUMNS,
            TABLE_NAME_VALUES,
        )

        self.assertEqual(DB_COLUMNS["laterality"]["check"], ["L", "R"])
        self.assertEqual(DB_COLUMNS["target"]["check"],
                         sorted(TABLE_NAME_VALUES))
        self.assertIsNone(DB_COLUMNS["col_name"]["check"])
        self.assertNotIn("hand", DB_COLUMNS)

    def test_db_mapping_guard_passes(self):
        # Every count result field maps to a pbp_stats DB column.
        self.assertEqual(_validate_pbp_db_mappings(), [])

    def test_db_mapping_guard_catches_drift(self):
        # Simulate the historical drift: a result field with no DB column
        # for one of its scopes.  steals has no opp_steals column, so
        # adding the opp_team scope must trip the guard.
        from src.definitions.pbp import RESULT_SET_FIELDS

        original = RESULT_SET_FIELDS["steals"]
        RESULT_SET_FIELDS["steals"] = dict(original)
        RESULT_SET_FIELDS["steals"]["result_sets"] = (
            "team", "player", "opp_team",
        )
        try:
            errors = _validate_pbp_db_mappings()
            self.assertTrue(
                any("steals" in e and "opp_team" in e for e in errors),
                errors,
            )
        finally:
            RESULT_SET_FIELDS["steals"] = original

    def test_db_mapping_guard_catches_reverse_drift(self):
        # A DB column whose pbp_stats field has no RESULT_SET_FIELDS
        # entry would silently never populate -- the guard must flag it.
        from src.definitions.db_columns import DB_COLUMNS

        original = dict(DB_COLUMNS["fg2m"])
        fake = {
            "type": "SMALLINT",
            "tables": ["team_games"],
            "nullable": True,
            "default": None,
            "dataset_mapping": {
                "NBA": {
                    "nba_id": {
                        "team_games": {
                            "pbp_stats": {
                                "field": "no_such_field",
                                "min_season": None,
                                "result_set": "team",
                            },
                        },
                    },
                }
            },
        }
        DB_COLUMNS["fg2m"] = fake
        try:
            errors = _validate_pbp_db_mappings()
            self.assertTrue(
                any("no_such_field" in e and "fg2m" in e for e in errors),
                errors,
            )
        finally:
            DB_COLUMNS["fg2m"] = original


if __name__ == "__main__":
    unittest.main()
