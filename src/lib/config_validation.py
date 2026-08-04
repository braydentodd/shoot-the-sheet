"""
Shoot the Sheet - ETL Config Validation

ETL-specific validation: cross-reference checks, PostgreSQL type validation,
and source structure checks.  Uses the generic validation engine from
``src.core.config_validation``.

Schemas are co-located with their declarative data:

  -   schema constants     -> src/core/definitions/schema.py
  -   column definitions   -> src/core/definitions/db_columns.py
  -   source config        -> src/etl/sources/<source>/config.py

Add a new config?  Define a schema dict next to the data, then register it
in :func:`validate_config`.
"""

import logging
from typing import Any, Dict, List, Union

from src.definitions.db_columns import VALID_TRANSFORMS
from src.lib.source_resolver import get_identity_entities

logger = logging.getLogger(__name__)


# ============================================================================
# CROSS-REFERENCE VALIDATORS
# ============================================================================


def _validate_pg_types(db_columns: Dict[str, Any]) -> List[str]:
    """Validate that all DB_COLUMNS types are valid PostgreSQL types."""
    from src.definitions.schema import VALID_PG_TYPES

    errors = []
    for col_name, meta in db_columns.items():
        col_type = meta.get("type", "")
        base = col_type.split("(")[0].upper()
        if base not in VALID_PG_TYPES:
            errors.append(f"DB_COLUMNS['{col_name}']: unknown type '{col_type}'")
    return errors


def _validate_identity_structure(
    db_columns: Dict[str, Any],
) -> List[str]:
    """Validate the nested identity structure in DB_COLUMNS.

    DB_COLUMNS uses a nested structure: {league: {identity: {table: {...}}}}
    where league is the league key (e.g., 'NBA'), identity is the
    identity key (e.g., 'nba_id'), and table is a bare table name
    (e.g. 'players', 'team_seasons'). Third-level keys must be valid
    table names present in at least one schema.
    """
    from src.definitions.datasets import DATASETS
    from src.definitions.schema import iter_tables

    valid_table_names = frozenset(table_name for _, _, table_name, _ in iter_tables())

    errors = []
    for col_name, meta in db_columns.items():
        col_sources = meta.get("dataset_mapping")
        if col_sources is None:
            continue

        prefix = f"DB_COLUMNS['{col_name}']"
        if not isinstance(col_sources, dict):
            errors.append(f"{prefix}: 'dataset_mapping' must be dict or None")
            continue

        # col_sources is {league: {identity: {table: {...}}}}
        for league, identity_dict in col_sources.items():
            if not isinstance(identity_dict, dict):
                errors.append(f"{prefix}: dataset_mapping['{league}'] must be dict")
                continue

            for identity, entities in identity_dict.items():
                if identity not in DATASETS:
                    errors.append(
                        f"{prefix}: dataset_mapping['{league}']['{identity}'] not registered in DATASETS"
                    )
                    continue
                entity_types = get_identity_entities(identity)
                if not isinstance(entities, dict):
                    errors.append(
                        f"{prefix}: dataset_mapping['{league}']['{identity}'] must be dict"
                    )
                    continue
                for entity_name, source_def in entities.items():
                    if entity_name not in valid_table_names:
                        errors.append(
                            f"{prefix}: dataset_mapping['{league}']['{identity}'] contains unsupported key {entity_name!r}; "
                            "only valid table names are allowed"
                        )
                        continue
                    if not isinstance(source_def, dict):
                        errors.append(
                            f"{prefix}: dataset_mapping['{league}']['{identity}']['{entity_name}'] must be dict"
                        )
                        continue
                    if entity_name not in entity_types:
                        errors.append(
                            f"{prefix}: dataset_mapping['{league}']['{identity}']['{entity_name}'] - "
                            f"identity '{identity}' does not declare entity_types {entity_name!r}"
                        )
    return errors


def _validate_dataset_refs(
    db_columns: Dict[str, Any],
    provider_filter: Union[str, None] = None,
) -> List[str]:
    """Validate that source dataset references exist in DATASETS."""
    from src.definitions.datasets import DATASETS
    from src.definitions.schema import iter_tables

    valid_table_names = frozenset(table_name for _, _, table_name, _ in iter_tables())

    errors = []
    for col_name, meta in db_columns.items():
        sources = meta.get("dataset_mapping")
        if not sources or not isinstance(sources, dict):
            continue

        prefix = f"DB_COLUMNS['{col_name}']"
        for league_code, provider_map in sources.items():
            if not isinstance(provider_map, dict):
                continue
            for provider, entities in provider_map.items():
                if provider_filter is not None and provider != provider_filter:
                    continue
                if not isinstance(entities, dict):
                    continue
                source_datasets = DATASETS.get(provider, {})
                for entity_name, source_def in entities.items():
                    if entity_name not in valid_table_names:
                        continue
                    if not isinstance(source_def, dict):
                        continue
                    ds = source_def.get("dataset") or source_def.get(
                        "pipeline", {}
                    ).get("dataset")
                    if ds and ds not in source_datasets:
                        errors.append(
                            f"{prefix}: references unknown dataset '{ds}' "
                            f"for sources['{league_code}']['{provider}']['{entity_name}']"
                        )
    return errors


def _validate_table_definitions(
    db_columns: Dict[str, Any],
) -> List[str]:
    """Robustly validate all table definitions in TABLES registry.

    Checks primary keys, indexes, foreign keys, and unique constraints.
    """
    from src.definitions.schema import (
        VALID_FK_ACTIONS,
        VALID_FK_STRATEGIES,
        iter_tables,
    )

    errors = []

    valid_tables = {qualified_name for qualified_name, _, _, _ in iter_tables()}

    for qualified_name, schema_name, table_name, meta in iter_tables():
        prefix = f"TABLES['{qualified_name}']"

        # Collect columns declared on this table (both database columns and FK columns)
        fk_columns = set()
        for fk in meta.get("foreign_keys") or []:
            fk_columns.update(fk["columns"])
        surrogate_pks = {"process_id", "id"}

        # 2. Primary Key validation
        pk_cols = meta.get("primary_key", [])
        if not isinstance(pk_cols, list):
            errors.append(f"{prefix}: primary_key must be a list")
        else:
            for col in pk_cols:
                if col == "sts_id":
                    continue
                if col in surrogate_pks:
                    continue
                if col not in db_columns and col not in fk_columns:
                    errors.append(
                        f"{prefix}: primary_key references unknown column '{col}'"
                    )

        # 3. Foreign Key validation
        fks = meta.get("foreign_keys") or []
        if not isinstance(fks, list):
            errors.append(f"{prefix}: foreign_keys must be a list")
        else:
            for idx, fk in enumerate(fks):
                fk_prefix = f"{prefix}.foreign_keys[{idx}]"
                cols = fk.get("columns", [])
                ref_schema = fk.get("ref_schema")
                ref_table = fk.get("ref_table")
                ref_cols = fk.get("ref_columns", [])

                if not cols:
                    errors.append(f"{fk_prefix}: missing 'columns'")
                if not ref_schema:
                    errors.append(f"{fk_prefix}: missing 'ref_schema'")
                if not ref_table:
                    errors.append(f"{fk_prefix}: missing 'ref_table'")
                if ref_schema and ref_table:
                    ref_qualified = f"{ref_schema}.{ref_table}"
                    if ref_qualified not in valid_tables:
                        errors.append(
                            f"{fk_prefix}: ref_table '{ref_qualified}' not in SCHEMAS"
                        )

                if not ref_cols:
                    errors.append(f"{fk_prefix}: missing 'ref_columns'")

                for action in ("on_update", "on_delete"):
                    act = fk.get(action)
                    if act and act not in VALID_FK_ACTIONS:
                        errors.append(
                            f"{fk_prefix}: {action} '{act}' not in {sorted(VALID_FK_ACTIONS)}"
                        )
                # Validate strategy vocabulary when present
                strat = fk.get("strategy")
                if strat and strat not in VALID_FK_STRATEGIES:
                    errors.append(
                        f"{fk_prefix}: strategy '{strat}' not in {sorted(VALID_FK_STRATEGIES)}"
                    )

        # 4. Unique Constraints validation
        ucs = meta.get("unique_constraints")
        if ucs is not None:
            if not isinstance(ucs, list):
                errors.append(
                    f"{prefix}: unique_constraints must be a list of lists or None"
                )
            else:
                for uc_idx, uc in enumerate(ucs):
                    if not isinstance(uc, list):
                        errors.append(
                            f"{prefix}.unique_constraints[{uc_idx}]: must be a list of column names"
                        )
                    else:
                        for col in uc:
                            if (
                                col not in db_columns
                                and col not in fk_columns
                                and col not in surrogate_pks
                            ):
                                errors.append(
                                    f"{prefix}.unique_constraints[{uc_idx}]: references unknown column '{col}'"
                                )

        # 5. Indexes validation
        idxs = meta.get("indexes") or []
        if not isinstance(idxs, list):
            errors.append(f"{prefix}: indexes must be a list")
        else:
            for idx_idx, index in enumerate(idxs):
                idx_prefix = f"{prefix}.indexes[{idx_idx}]"
                cols = index.get("columns", [])
                if not isinstance(cols, list) or not cols:
                    errors.append(f"{idx_prefix}: missing or empty 'columns'")
                else:
                    for col in cols:
                        if (
                            col not in db_columns
                            and col not in fk_columns
                            and col not in surrogate_pks
                        ):
                            errors.append(
                                f"{idx_prefix}: index column '{col}' is unknown"
                            )

    return errors


def _validate_fk_targets() -> List[str]:
    """Every FK ref_schema/ref_table must resolve to a known table, and the
    on_update / on_delete actions must be in the allowed set."""
    from src.definitions.schema import VALID_FK_ACTIONS, iter_tables

    errors: List[str] = []

    for qualified_name, schema_name, table_name, meta in iter_tables():
        for fk in meta.get("foreign_keys") or []:
            prefix = f"TABLES['{qualified_name}'] FK on '{fk.get('columns', ['?'])[0]}'"
            for action_key in ("on_update", "on_delete"):
                action = fk.get(action_key)
                if action and action not in VALID_FK_ACTIONS:
                    errors.append(
                        f"{prefix}: {action_key} {action!r} not in "
                        f"{sorted(VALID_FK_ACTIONS)}"
                    )
    return errors


def _validate_league_stage_definitions() -> List[str]:
    """Validate global ETL phase ordering declarations."""
    from src.definitions.pipeline import (
        PIPELINE,
        VALID_CLUSTERS,
        VALID_PHASES,
    )

    errors: List[str] = []

    if not isinstance(PIPELINE, dict):
        return [f"PIPELINE: expected dict, got {type(PIPELINE).__name__}"]

    unsupported = sorted(
        cluster for cluster in PIPELINE if cluster not in VALID_CLUSTERS
    )
    if unsupported:
        errors.append(
            f"PIPELINE: unsupported clusters {unsupported}; expected subset of {sorted(VALID_CLUSTERS)}"
        )

    missing = sorted(cluster for cluster in VALID_CLUSTERS if cluster not in PIPELINE)
    if missing:
        errors.append(f"PIPELINE: missing required clusters {missing}")

    for cluster, phases in PIPELINE.items():
        prefix = f"PIPELINE['{cluster}']"
        if not isinstance(phases, list):
            errors.append(f"{prefix}: expected list, got {type(phases).__name__}")
            continue
        if not phases:
            errors.append(f"{prefix}: must not be empty")
            continue

        seen = set()
        for idx, phase in enumerate(phases):
            pfx = f"{prefix}[{idx}]"
            if not isinstance(phase, str) or not phase:
                errors.append(f"{pfx}: expected non-empty str")
                continue
            if phase in seen:
                errors.append(f"{prefix}: duplicate phase {phase!r}")
                continue
            seen.add(phase)
            if phase not in VALID_PHASES:
                errors.append(
                    f"{pfx}: unknown phase {phase!r}; expected one of {sorted(VALID_PHASES)}"
                )

    return errors


def _validate_dataset_mapping_references() -> List[str]:
    """Validate that all dataset_mapping references point to valid datasets."""
    from src.definitions.datasets import DATASETS
    from src.definitions.db_columns import DB_COLUMNS

    errors: List[str] = []

    for col_name, col_def in DB_COLUMNS.items():
        mapping = col_def.get("dataset_mapping")
        if not mapping:
            continue

        for league_code, league_map in mapping.items():
            for identity_code, identity_map in league_map.items():
                # Check that identity exists in DATASETS
                if identity_code not in DATASETS:
                    errors.append(
                        f"DB_COLUMNS['{col_name}'] dataset_mapping: "
                        f"identity '{identity_code}' not found in DATASETS"
                    )
                    continue

                for entity, entity_map in identity_map.items():
                    for dataset_name in entity_map.keys():
                        # Check that dataset exists under this identity
                        if dataset_name not in DATASETS.get(identity_code, {}):
                            errors.append(
                                f'DB_COLUMNS[\'{col_name}\'] dataset_mapping["{league_code}"]["{identity_code}"]["{entity}"]: '
                                f"dataset '{dataset_name}' not found in DATASETS[\"{identity_code}\"]"
                            )

    return errors


def _validate_transform_references() -> List[str]:
    """Validate that all transform references are in VALID_TRANSFORMS."""
    from src.definitions.db_columns import DB_COLUMNS

    errors: List[str] = []

    for col_name, col_def in DB_COLUMNS.items():
        mapping = col_def.get("dataset_mapping")
        if not mapping:
            continue

        for league_code, league_map in mapping.items():
            for identity_code, identity_map in league_map.items():
                for entity, entity_map in identity_map.items():
                    for dataset_name, ds_mapping in entity_map.items():
                        transform = ds_mapping.get("transform")
                        if transform and transform not in VALID_TRANSFORMS:
                            errors.append(
                                f'DB_COLUMNS[\'{col_name}\'] dataset_mapping["{league_code}"]["{identity_code}"]["{entity}"]["{dataset_name}"]: '
                                f"unknown transform '{transform}'; expected one of {sorted(VALID_TRANSFORMS)}"
                            )

    return errors


def _validate_target_tables() -> List[str]:
    """Validate that every target_tables entry exists in SCHEMAS registry."""
    from src.definitions.datasets import DATASETS
    from src.definitions.schema import iter_tables

    valid_qualified = {qual for qual, _, _, _ in iter_tables()}
    errors: List[str] = []

    for identity_code, datasets in DATASETS.items():
        for dataset_name, ds_def in datasets.items():
            target_tables = ds_def.get("target_tables")
            if not target_tables:
                continue

            for table_name in target_tables:
                if table_name not in valid_qualified:
                    errors.append(
                        f'DATASETS["{identity_code}"]["{dataset_name}"] target_tables: '
                        f"table '{table_name}' not found in SCHEMAS registry"
                    )

    return errors


def _validate_target_tables_cover_dataset_mapping() -> List[str]:
    """Validate that every table a dataset populates via DB_COLUMNS is
    declared in that dataset's ``target_tables``.

    DB_COLUMNS['col']['dataset_mapping'][league][identity][table][dataset]
    is the reverse-index source of truth for *data-bearing* writes. Every
    (identity, dataset, table) triple discovered there must appear in
    DATASETS[identity][dataset]['target_tables'], otherwise the dataset's
    declared write surface has silently drifted out of sync with the
    columns that actually target it (this is the class of bug that left
    ``staging.games`` out of ``_maintain_games``'s hardcoded target list
    despite ``DB_COLUMNS['date']`` mapping into it).

    Note: this check is one-directional. ``target_tables`` may legally
    contain tables with NO db_columns.py mapping at all (pure
    existence/junction tables like ``staging.leagues_teams``, or tables
    whose identity/FK columns are resolved outside the generic column
    system, like ``staging.games``). Those are not flagged here.
    """
    from src.definitions.datasets import DATASETS
    from src.definitions.db_columns import DB_COLUMNS

    errors: List[str] = []

    for col_name, col_def in DB_COLUMNS.items():
        mapping = col_def.get("dataset_mapping")
        if not mapping:
            continue

        for league_code, league_map in mapping.items():
            for identity_code, identity_map in league_map.items():
                ds_registry = DATASETS.get(identity_code, {})
                for table_name, table_map in identity_map.items():
                    for dataset_name in table_map.keys():
                        ds_def = ds_registry.get(dataset_name)
                        if ds_def is None:
                            # Reported separately by
                            # _validate_dataset_mapping_references.
                            continue
                        target_tables = ds_def.get("target_tables") or []
                        qualified = f"staging.{table_name}"
                        if qualified not in target_tables:
                            errors.append(
                                f'DATASETS["{identity_code}"]["{dataset_name}"] '
                                f"target_tables is missing '{qualified}', which is "
                                f"populated by DB_COLUMNS['{col_name}'] "
                                f'dataset_mapping["{league_code}"]["{identity_code}"]'
                                f'["{table_name}"]["{dataset_name}"]'
                            )

    return errors


def _validate_result_sets() -> List[str]:
    """Validate that all result_set entries are consistent within a dataset."""
    from src.definitions.db_columns import DB_COLUMNS

    errors: List[str] = []

    # Build a map of identity -> dataset -> list of result_sets used
    dataset_result_sets: Dict[str, Dict[str, set]] = {}

    for col_name, col_def in DB_COLUMNS.items():
        mapping = col_def.get("dataset_mapping")
        if not mapping:
            continue

        for league_code, league_map in mapping.items():
            for identity_code, identity_map in league_map.items():
                if identity_code not in dataset_result_sets:
                    dataset_result_sets[identity_code] = {}

                for entity, entity_map in identity_map.items():
                    for dataset_name, ds_mapping in entity_map.items():
                        result_set = ds_mapping.get("result_set")
                        if result_set:
                            if dataset_name not in dataset_result_sets[identity_code]:
                                dataset_result_sets[identity_code][dataset_name] = set()
                            dataset_result_sets[identity_code][dataset_name].add(
                                result_set
                            )

    # Check for datasets with multiple result_sets (which may be intentional but should be flagged)
    # PBP accumulation (phase="maintain_pbp") is inherently multi-result-set:
    # the same dataset populates team/player/opp_team/opp_player/on_player scopes.
    from src.definitions.datasets import DATASETS

    for identity_code, datasets in dataset_result_sets.items():
        for dataset_name, result_sets in datasets.items():
            if len(result_sets) <= 2:
                continue
            ds_cfg = DATASETS.get(identity_code, {}).get(dataset_name, {})
            if ds_cfg.get("phase") == "maintain_pbp":
                continue
            errors.append(
                f'DATASETS["{identity_code}"]["{dataset_name}"]: '
                f"multiple result_sets detected: {sorted(result_sets)}. "
                f"This may be intentional for multi-result datasets."
            )

    return errors


# ============================================================================
# PUBLIC API
# ============================================================================


def _validate_rate_limit_sources() -> List[str]:
    """Every key in SOURCE_RATE_LIMITS must be a registered source."""
    from src.definitions.rate_limits import SOURCE_RATE_LIMITS
    from src.definitions.sources import VALID_SOURCES

    errors: List[str] = []
    for source_code in SOURCE_RATE_LIMITS:
        if source_code not in VALID_SOURCES:
            errors.append(
                f"SOURCE_RATE_LIMITS: unknown source {source_code!r}; "
                f"expected one of {sorted(VALID_SOURCES)}"
            )
    return errors


# ============================================================================
# PBP CONFIG VALIDATION
# ============================================================================


def _validate_pbp_events() -> List[str]:
    """Validate every ``PBP_EVENTS`` entry against its uniform schema."""
    from src.definitions.pbp import PBP_EVENTS

    errors: List[str] = []
    required = {
        "sort_priority", "indicate_poss", "indicate_on_court",
        "shot", "points", "poss_transition",
    }
    valid_conditions = {"always", "live_shot", "jump_ball_changes_possession", None}
    valid_end = {"self", "opponent", "last_possessing", None}
    valid_start = {"self", "opponent", "next_poss_event", None}

    for name, ev_def in PBP_EVENTS.items():
        prefix = f"PBP_EVENTS['{name}']"
        if not isinstance(ev_def, dict):
            errors.append(f"{prefix}: expected dict")
            continue
        missing = required - set(ev_def.keys())
        if missing:
            errors.append(f"{prefix}: missing required key(s) {sorted(missing)}")
        extra = set(ev_def.keys()) - required
        if extra:
            errors.append(f"{prefix}: unknown key(s) {sorted(extra)}")
        if not isinstance(ev_def.get("sort_priority"), int):
            errors.append(f"{prefix}: sort_priority must be int")
        for bool_key in ("indicate_poss", "indicate_on_court", "shot"):
            if not isinstance(ev_def.get(bool_key), bool):
                errors.append(f"{prefix}: {bool_key} must be bool")
        if not isinstance(ev_def.get("points"), int):
            errors.append(f"{prefix}: points must be int")
        trans = ev_def.get("poss_transition")
        if trans is not None:
            if not isinstance(trans, dict):
                errors.append(f"{prefix}: poss_transition must be dict or None")
                continue
            if trans.get("end_team") not in valid_end:
                errors.append(f"{prefix}: poss_transition.end_team invalid: {trans.get('end_team')!r}")
            if trans.get("start_team") not in valid_start:
                errors.append(f"{prefix}: poss_transition.start_team invalid: {trans.get('start_team')!r}")
            if trans.get("condition") not in valid_conditions:
                errors.append(f"{prefix}: poss_transition.condition invalid: {trans.get('condition')!r}")
    return errors


def _validate_chain_rules() -> List[str]:
    """Validate every ``CHAIN_RULES`` entry against its uniform schema."""
    from src.definitions.chain_rules import CHAIN_RULES
    from src.definitions.pbp import PBP_EVENTS

    errors: List[str] = []
    required = {
        "anchor", "scope", "position", "skip", "max_gap",
        "cross_period", "reanchor", "required", "synthesize", "suppress",
    }
    valid_scopes = {"previous", "next", "sequence"}
    valid_positions = {"before", "after"}
    valid_synthesize = {
        "none", "team_rebound", "team_turnover", "scoring_opp",
        "poss_marker", "lineup_sweep", "starters",
    }
    valid_suppress = {"none", "open_scoring_sequence"}
    special_anchors = {"shot", "miss", "first_shot_of_scoring_sequence",
                       "possession_end_event"}

    for name, rule in CHAIN_RULES.items():
        prefix = f"CHAIN_RULES['{name}']"
        if not isinstance(rule, dict):
            errors.append(f"{prefix}: expected dict")
            continue
        missing = required - set(rule.keys())
        if missing:
            errors.append(f"{prefix}: missing required key(s) {sorted(missing)}")
        extra = set(rule.keys()) - required
        if extra:
            errors.append(f"{prefix}: unknown key(s) {sorted(extra)}")
        if rule.get("scope") not in valid_scopes:
            errors.append(f"{prefix}: scope invalid: {rule.get('scope')!r}")
        if rule.get("position") not in valid_positions:
            errors.append(f"{prefix}: position invalid: {rule.get('position')!r}")
        if rule.get("synthesize") not in valid_synthesize:
            errors.append(f"{prefix}: synthesize invalid: {rule.get('synthesize')!r}")
        if rule.get("suppress") not in valid_suppress:
            errors.append(f"{prefix}: suppress invalid: {rule.get('suppress')!r}")
        if not isinstance(rule.get("max_gap"), int):
            errors.append(f"{prefix}: max_gap must be int")
        for bool_key in ("cross_period", "reanchor", "required"):
            if not isinstance(rule.get(bool_key), bool):
                errors.append(f"{prefix}: {bool_key} must be bool")
        if not isinstance(rule.get("skip"), tuple):
            errors.append(f"{prefix}: skip must be a tuple of event names")
        else:
            for skip_name in rule["skip"]:
                if skip_name not in PBP_EVENTS:
                    errors.append(f"{prefix}: skip references unknown event {skip_name!r}")
        for anchor_name in str(rule.get("anchor", "")).split("|"):
            if anchor_name not in PBP_EVENTS and anchor_name not in special_anchors:
                errors.append(f"{prefix}: anchor references unknown token {anchor_name!r}")
    return errors


def _validate_invariants() -> List[str]:
    """Validate every ``INVARIANTS`` entry against its uniform schema."""
    from src.definitions.chain_rules import INVARIANTS
    from src.definitions.pbp import PBP_EVENTS

    errors: List[str] = []
    required = {"events", "except_events", "state", "severity", "message"}

    for name, inv in INVARIANTS.items():
        prefix = f"INVARIANTS['{name}']"
        if not isinstance(inv, dict):
            errors.append(f"{prefix}: expected dict")
            continue
        missing = required - set(inv.keys())
        if missing:
            errors.append(f"{prefix}: missing required key(s) {sorted(missing)}")
        extra = set(inv.keys()) - required
        if extra:
            errors.append(f"{prefix}: unknown key(s) {sorted(extra)}")
        if inv.get("severity") not in ("error", "warn"):
            errors.append(f"{prefix}: severity invalid: {inv.get('severity')!r}")
        if not isinstance(inv.get("message"), str):
            errors.append(f"{prefix}: message must be str")
        for key in ("events", "except_events"):
            if not isinstance(inv.get(key), tuple):
                errors.append(f"{prefix}: {key} must be a tuple of event names")
            else:
                for evt in inv[key]:
                    if evt not in PBP_EVENTS:
                        errors.append(f"{prefix}: {key} references unknown event {evt!r}")
    return errors


def _validate_pbp_result_set_fields() -> List[str]:
    """Validate every ``RESULT_SET_FIELDS`` entry has the uniform shape."""
    from src.definitions.pbp import PBP_EVENTS, RESULT_SET_FIELDS

    errors: List[str] = []
    required = {"op", "type", "events", "formula", "fields",
                "result_sets", "requires_clock"}
    valid_scopes = {"team", "player", "opp_team", "opp_player", "on_player"}

    for field, f_def in RESULT_SET_FIELDS.items():
        prefix = f"RESULT_SET_FIELDS['{field}']"
        missing = required - set(f_def.keys())
        if missing:
            errors.append(f"{prefix}: missing required key(s) {sorted(missing)}")
        op = f_def.get("op")
        if op not in ("count", "derived", "special"):
            errors.append(f"{prefix}: op invalid: {op!r}")
        if not isinstance(f_def.get("requires_clock"), bool):
            errors.append(f"{prefix}: requires_clock must be bool")
        for evt in f_def.get("events") or []:
            if evt not in PBP_EVENTS:
                errors.append(f"{prefix}: events references unknown event {evt!r}")
        for rs, scope in (f_def.get("result_sets") or {}).items():
            if op == "count" and scope not in valid_scopes:
                errors.append(f"{prefix}: result_sets[{rs!r}] scope invalid: {scope!r}")
    return errors


def _validate_pbp_db_mappings() -> List[str]:
    """Every count result field must have a ``pbp_stats`` DB column mapping.

    This is the guard against the silent naming-drift bug where a
    ``RESULT_SET_FIELDS`` key had no matching ``DB_COLUMNS`` entry and the
    player/team column never populated.  Intermediate fields (those
    referenced only by derived formulas, e.g. the fg2/fg3 assist split
    behind ``assist_points``) are exempt.
    """
    from src.definitions.db_columns import DB_COLUMNS
    from src.definitions.pbp import RESULT_SET_FIELDS

    errors: List[str] = []
    valid_scopes = {"team", "player", "opp_team", "opp_player", "on_player"}

    intermediate: set[str] = set()
    for f_def in RESULT_SET_FIELDS.values():
        if f_def.get("op") == "derived":
            intermediate.update(f_def.get("fields") or [])

    for field, f_def in RESULT_SET_FIELDS.items():
        if f_def.get("op") != "count":
            continue
        if field in intermediate:
            continue
        for rs, scope in (f_def.get("result_sets") or {}).items():
            if scope not in valid_scopes:
                continue
            found = False
            for col_def in DB_COLUMNS.values():
                mapping = col_def.get("dataset_mapping") or {}
                for league_map in mapping.values():
                    for identity_map in league_map.values():
                        for target_map in identity_map.values():
                            if not isinstance(target_map, dict):
                                continue
                            pbp = target_map.get("pbp_stats")
                            if (
                                isinstance(pbp, dict)
                                and pbp.get("field") == field
                                and pbp.get("result_set") == scope
                            ):
                                found = True
                                break
                        if found:
                            break
                    if found:
                        break
                if found:
                    break
            if not found:
                errors.append(
                    f"RESULT_SET_FIELDS['{field}'] result_sets[{rs!r}]: "
                    f"no DB_COLUMNS entry maps pbp_stats field {field!r} "
                    f"with result_set {scope!r}"
                )
    return errors


# ============================================================================
# PUBLIC API
# ============================================================================
def _validate_cross_row_config() -> List[str]:
    """Validate every ``cross_row`` config in DB_COLUMNS.

    Checks that each ``cross_row`` dict has the required fields:
    ``group_by``, ``match_field``, ``match_contains``.
    Also warns if ``cross_row`` is used without a ``result_set``
    (cross-row derivation is inherently result-set-scoped).
    """
    from src.definitions.db_columns import DB_COLUMNS

    errors: List[str] = []
    allowed_keys = frozenset({"group_by", "match_field", "match_contains"})

    for col_name, col_def in DB_COLUMNS.items():
        mapping = col_def.get("dataset_mapping")
        if not mapping:
            continue

        # Walk the nested structure: league -> identity -> table -> dataset -> source
        for league_code, league_map in mapping.items():
            if not isinstance(league_map, dict):
                continue
            for identity_code, identity_map in league_map.items():
                if not isinstance(identity_map, dict):
                    continue
                for table_name, table_map in identity_map.items():
                    if not isinstance(table_map, dict):
                        continue
                    for dataset_name, ds_mapping in table_map.items():
                        if not isinstance(ds_mapping, dict):
                            continue
                        cr = ds_mapping.get("cross_row")
                        if cr is None:
                            continue
                        if not isinstance(cr, dict):
                            errors.append(
                                f'DB_COLUMNS["{col_name}"] '
                                f'dataset_mapping["{league_code}"]'
                                f'["{identity_code}"]["{table_name}"]'
                                f'["{dataset_name}"]["cross_row"] '
                                f"is {type(cr).__name__}, expected dict"
                            )
                            continue

                        for key in allowed_keys:
                            if key not in cr:
                                errors.append(
                                    f'DB_COLUMNS["{col_name}"] '
                                    f'dataset_mapping["{league_code}"]'
                                    f'["{identity_code}"]["{table_name}"]'
                                    f'["{dataset_name}"]["cross_row"] '
                                    f"missing required key {key!r}"
                                )

                        unknown = set(cr.keys()) - allowed_keys
                        if unknown:
                            errors.append(
                                f'DB_COLUMNS["{col_name}"] '
                                f'dataset_mapping["{league_code}"]'
                                f'["{identity_code}"]["{table_name}"]'
                                f'["{dataset_name}"]["cross_row"] '
                                f"unknown key(s): {sorted(unknown)}"
                            )

                        # cross_row inherently requires a result_set to scope
                        # which API result to group across
                        if not ds_mapping.get("result_set"):
                            errors.append(
                                f'DB_COLUMNS["{col_name}"] '
                                f'dataset_mapping["{league_code}"]'
                                f'["{identity_code}"]["{table_name}"]'
                                f'["{dataset_name}"] '
                                f"has cross_row but no result_set -- "
                                f"cross-row derivation is result-set-scoped"
                            )

    return errors


def validate_config() -> List[str]:
    from src.definitions.db_columns import DB_COLUMNS

    errors: List[str] = []

    errors.extend(_validate_pg_types(DB_COLUMNS))
    errors.extend(_validate_identity_structure(DB_COLUMNS))
    errors.extend(_validate_table_definitions(DB_COLUMNS))
    errors.extend(_validate_fk_targets())
    errors.extend(_validate_league_stage_definitions())
    errors.extend(_validate_dataset_mapping_references())
    errors.extend(_validate_transform_references())
    errors.extend(_validate_target_tables())
    errors.extend(_validate_target_tables_cover_dataset_mapping())
    errors.extend(_validate_result_sets())
    errors.extend(_validate_cross_row_config())
    errors.extend(_validate_rate_limit_sources())
    errors.extend(_validate_pbp_events())
    errors.extend(_validate_chain_rules())
    errors.extend(_validate_invariants())
    errors.extend(_validate_pbp_result_set_fields())
    errors.extend(_validate_pbp_db_mappings())

    return errors


def validate_all() -> List[str]:
    """One-call entry point that validates every ETL configuration plus all
    registered sources' own configs.

    Called from :mod:`src.cli` at startup before any I/O.  Imports are
    deferred so that importing this module does not import every source.

    Raises:
        RuntimeError: if any layer reports validation errors.
    """
    from src.definitions.sources import SOURCES

    aggregated: List[str] = []
    # Cross-cuts ETL definitions + per-source DATASETS (no league required).
    aggregated.extend(validate_config())

    # Source-specific validation folded into the center.
    from src.definitions.db_columns import DB_COLUMNS

    for source_code in sorted(SOURCES):
        # Only validate external sources (those not under sts_id identity)
        from src.definitions.datasets import DATASETS

        is_internal = any(
            ds_def.get("source") == source_code
            for ds_def in DATASETS.get("sts_id", {}).values()
        )
        if is_internal:
            continue
        aggregated.extend(
            _validate_dataset_refs(
                DB_COLUMNS,
                provider_filter=source_code,
            )
        )

    if aggregated:
        for err in aggregated:
            logger.error("Source config validation: %s", err)
        raise RuntimeError(
            f"Source config validation failed with {len(aggregated)} error(s)"
        )

    return []
