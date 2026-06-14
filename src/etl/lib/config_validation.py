"""
Shoot the Sheet - ETL Config Validation

ETL-specific validation: cross-reference checks, PostgreSQL type validation,
and source structure checks.  Uses the generic validation engine from
``src.core.config_validation``.

Schemas are co-located with their declarative data:

  -   schema constants     -> src/core/definitions/
  -                                      -> src/core/definitions/columns.py
  - OPERATIONAL_TABLES_SCHEMA                             -> src/core/definitions/tables.py
  - DATASETS_SCHEMA, SEASON_TYPES_SCHEMA, API_CONFIG_SCHEMA -> src/etl/sources/<source>/config.py

Add a new config?  Define a schema dict next to the data, then register it
in :func:`validate_config`.
"""

import logging
from typing import Dict, List, Union

from src.etl.lib.source_resolver import get_identity_entities

VALID_ENTITY_TYPES = frozenset({"league", "player", "team", "country"})


logger = logging.getLogger(__name__)


VALID_TRANSFORMS = {
    "safe_int",
    "safe_str",
    "parse_height",
    "parse_birthdate",
    "format_season",
}


# ============================================================================
# CROSS-REFERENCE VALIDATORS
# ============================================================================


def _validate_pg_types(db_columns: Dict[str, Dict]) -> List[str]:
    """Validate that all DB_COLUMNS types are valid PostgreSQL types."""
    from src.core.definitions.schema import VALID_PG_TYPES

    errors = []
    for col_name, meta in db_columns.items():
        col_type = meta.get("type", "")
        base = col_type.split("(")[0].upper()
        if base not in VALID_PG_TYPES:
            errors.append(f"DB_COLUMNS['{col_name}']: unknown type '{col_type}'")
    return errors


def _validate_source_structure(
    db_columns: Dict[str, Dict],
    sources: Dict[str, Dict],
) -> List[str]:
    """Validate the nested identity structure in DB_COLUMNS.

    DB_COLUMNS uses a nested structure: {league: {identity: {entity: {...}}}}
    where league is the league key (e.g., 'NBA') and identity is the
    identity key (e.g., 'nba_id'). Provider maps may only contain entity
    keys; provider-level metadata keys are rejected.
    """
    from src.etl.definitions.datasets import DATASETS

    errors = []
    for col_name, meta in db_columns.items():
        col_sources = meta.get("dataset_mapping")
        if col_sources is None:
            continue

        prefix = f"DB_COLUMNS['{col_name}']"
        if not isinstance(col_sources, dict):
            errors.append(f"{prefix}: 'dataset_mapping' must be dict or None")
            continue

        # col_sources is {league: {identity: {entity: {...}}}}
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
                    if entity_name not in VALID_ENTITY_TYPES:
                        errors.append(
                            f"{prefix}: dataset_mapping['{league}']['{identity}'] contains unsupported key {entity_name!r}; "
                            "only entity keys are allowed"
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
    db_columns: Dict[str, Dict],
    provider_filter: Union[str, None] = None,
) -> List[str]:
    """Validate that source dataset references exist in DATASETS."""
    from src.etl.definitions.datasets import DATASETS

    errors = []
    for col_name, meta in db_columns.items():
        sources = meta.get("dataset_mapping")
        if not sources or not isinstance(sources, dict):
            continue

        prefix = f"DB_COLUMNS['{col_name}']"
        for league_key, provider_map in sources.items():
            if not isinstance(provider_map, dict):
                continue
            for provider, entities in provider_map.items():
                if provider_filter is not None and provider != provider_filter:
                    continue
                if not isinstance(entities, dict):
                    continue
                source_datasets = DATASETS.get(provider, {})
                for entity_name, source_def in entities.items():
                    if entity_name not in VALID_ENTITY_TYPES:
                        continue
                    if not isinstance(source_def, dict):
                        continue
                    ds = source_def.get("dataset") or source_def.get(
                        "pipeline", {}
                    ).get("dataset")
                    if ds and ds not in source_datasets:
                        errors.append(
                            f"{prefix}: references unknown dataset '{ds}' "
                            f"for sources['{league_key}']['{provider}']['{entity_name}']"
                        )
    return errors


def _validate_table_definitions(
    tables: Dict[str, Dict],
    db_columns: Dict[str, Dict],
) -> List[str]:
    """Robustly validate all table definitions in TABLES registry.

    Checks primary keys, indexes, foreign keys, and unique constraints.
    """
    from src.core.definitions.schema import (
        VALID_FK_ACTIONS,
        VALID_FK_STRATEGIES,
    )

    errors = []

    for table_name, meta in tables.items():
        prefix = f"TABLES['{table_name}']"

        # Collect columns declared on this table (both database columns and FK columns)
        fk_columns = {
            fk.get("column")
            for fk in (meta.get("foreign_keys") or [])
            if fk.get("column")
        }
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
                col = fk.get("column")
                ref_table = fk.get("ref_table")
                ref_col = fk.get("ref_column")

                if not col:
                    errors.append(f"{fk_prefix}: missing 'column'")
                if not ref_table:
                    errors.append(f"{fk_prefix}: missing 'ref_table'")
                elif ref_table not in tables:
                    errors.append(f"{fk_prefix}: ref_table '{ref_table}' not in TABLES")

                if not ref_col:
                    errors.append(f"{fk_prefix}: missing 'ref_column'")

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


def _validate_fk_targets(tables: Dict[str, Dict]) -> List[str]:
    """Every FK ref_schema/ref_table must resolve to a known table, and the
    on_update / on_delete actions must be in the allowed set."""
    from src.core.definitions.schema import VALID_FK_ACTIONS

    errors: List[str] = []

    for tname, meta in tables.items():
        for fk in meta.get("foreign_keys") or []:
            prefix = f"TABLES['{tname}'] FK on '{fk.get('column', '?')}'"
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
    from src.etl.definitions.pipeline import (
        PIPELINE_PHASES,
        VALID_ETL_PHASES,
        VALID_ETL_STEP_HANDLERS,
    )

    errors: List[str] = []

    if not isinstance(PIPELINE_PHASES, dict):
        return [f"PIPELINE_PHASES: expected dict, got {type(PIPELINE_PHASES).__name__}"]

    unsupported_phases = sorted(
        phase for phase in PIPELINE_PHASES if phase not in VALID_ETL_PHASES
    )
    if unsupported_phases:
        errors.append(
            f"PIPELINE_PHASES: unsupported phases {unsupported_phases}; expected subset of {sorted(VALID_ETL_PHASES)}"
        )

    missing_phases = sorted(
        phase for phase in VALID_ETL_PHASES if phase not in PIPELINE_PHASES
    )
    if missing_phases:
        errors.append(f"PIPELINE_PHASES: missing required phases {missing_phases}")

    for phase, handlers in PIPELINE_PHASES.items():
        phase_prefix = f"PIPELINE_PHASES['{phase}']"
        if not isinstance(handlers, list):
            errors.append(
                f"{phase_prefix}: expected list, got {type(handlers).__name__}"
            )
            continue
        if not handlers:
            errors.append(f"{phase_prefix}: must not be empty")
            continue

        seen = set()
        for idx, handler in enumerate(handlers):
            prefix = f"{phase_prefix}[{idx}]"
            if not isinstance(handler, str) or not handler:
                errors.append(f"{prefix}: expected non-empty str")
                continue
            if handler in seen:
                errors.append(f"{phase_prefix}: duplicate handler {handler!r}")
                continue
            seen.add(handler)
            if handler not in VALID_ETL_STEP_HANDLERS:
                errors.append(
                    f"{prefix}: unknown handler {handler!r}; expected one of {sorted(VALID_ETL_STEP_HANDLERS)}"
                )

    return errors


# ============================================================================
# PUBLIC API
# ============================================================================


def validate_config() -> List[str]:
    from src.core.definitions.db_columns import DB_COLUMNS
    from src.core.definitions.leagues import LEAGUES
    from src.core.definitions.schema import TABLES
    from src.etl.definitions.sources import SOURCES

    errors: List[str] = []

    errors.extend(_validate_pg_types(DB_COLUMNS))
    errors.extend(_validate_source_structure(DB_COLUMNS, SOURCES))
    errors.extend(_validate_table_definitions(TABLES, DB_COLUMNS))
    errors.extend(_validate_fk_targets(TABLES))
    errors.extend(_validate_league_stage_definitions())

    return errors


def validate_all() -> List[str]:
    """One-call entry point that validates every ETL configuration plus all
    registered sources' own configs.

    Called from :mod:`src.etl.cli` at startup before any I/O.  Imports are
    deferred so that importing this module does not import every source.

    Raises:
        RuntimeError: if any layer reports validation errors.
    """
    from src.etl.definitions.sources import SOURCES

    # Cross-cuts ETL definitions + per-source DATASETS (no league required).
    validate_config()

    # Source-specific validation folded into the center.
    from src.core.definitions.db_columns import DB_COLUMNS

    aggregated: List[str] = []
    for source_key in sorted(SOURCES):
        # Only validate external sources (those not under sts_id identity)
        from src.etl.definitions.datasets import DATASETS

        is_internal = any(
            ds_def.get("source") == source_key
            for ds_def in DATASETS.get("sts_id", {}).values()
        )
        if is_internal:
            continue
        aggregated.extend(
            _validate_dataset_refs(
                DB_COLUMNS,
                provider_filter=source_key,
            )
        )

    if aggregated:
        for err in aggregated:
            logger.error("Source config validation: %s", err)
        raise RuntimeError(
            f"Source config validation failed with {len(aggregated)} error(s)"
        )

    return []
