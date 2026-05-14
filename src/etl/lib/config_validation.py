"""
The Glass - ETL Config Validation

ETL-specific validation: cross-reference checks, PostgreSQL type validation,
and source structure checks.  Uses the generic validation engine from
``src.core.config_validation``.

Schemas are co-located with their declarative data:

  - LEAGUES_SCHEMA, SOURCES_SCHEMA, schema constants     -> src/core/definitions/
  - DB_COLUMNS_SCHEMA                                     -> src/core/definitions/columns.py
  - OPERATIONAL_TABLES_SCHEMA                             -> src/core/definitions/tables.py
  - DATASETS_SCHEMA, SEASON_TYPES_SCHEMA, API_CONFIG_SCHEMA -> src/etl/sources/<source>/config.py

Add a new config?  Define a schema dict next to the data, then register it
in :func:`validate_config`.
"""

import logging
from typing import Any, Dict, List, Optional

from src.core.lib.config_validation import validate_dict_config

logger = logging.getLogger(__name__)


VALID_TRANSFORMS = {
    'safe_int', 'safe_str',
    'parse_height', 'parse_birthdate', 'format_season',
}


# ============================================================================
# CROSS-REFERENCE VALIDATORS
# ============================================================================

def _validate_pg_types(db_columns: Dict[str, Dict]) -> List[str]:
    """Validate that all DB_COLUMNS types are valid PostgreSQL types."""
    from src.core.definitions.tables import VALID_PG_TYPES

    errors = []
    for col_name, meta in db_columns.items():
        col_type = meta.get('type', '')
        base = col_type.split('(')[0].upper()
        if base not in VALID_PG_TYPES:
            errors.append(f"DB_COLUMNS['{col_name}']: unknown type '{col_type}'")
    return errors


def _validate_source_structure(
    db_columns: Dict[str, Dict],
    sources: Dict[str, Dict],
) -> List[str]:
    """Validate the nested sources structure in DB_COLUMNS.

    DB_COLUMNS uses a nested structure: {league: {source: {entity: {...}}}}
    where league is the league key (e.g., 'nba') and source is the actual
    source key (e.g., 'nba_api'). The validation checks that the source
    keys exist in SOURCES.
    """
    from src.core.definitions.tables import VALID_ENTITY_TYPES
    errors = []
    for col_name, meta in db_columns.items():
        col_sources = meta.get('sources')
        if col_sources is None:
            continue

        prefix = f"DB_COLUMNS['{col_name}']"
        if not isinstance(col_sources, dict):
            errors.append(f"{prefix}: 'sources' must be dict or None")
            continue

        # col_sources is {league: {source: {entity: {...}}}}
        for league, source_dict in col_sources.items():
            if not isinstance(source_dict, dict):
                errors.append(f"{prefix}: sources['{league}'] must be dict")
                continue

            for provider, entities in source_dict.items():
                if provider not in sources:
                    errors.append(f"{prefix}: sources['{league}']['{provider}'] not registered in SOURCES")
                    continue
                applies_to = sources[provider].get('applies_to', [])
                if not isinstance(entities, dict):
                    errors.append(f"{prefix}: sources['{league}']['{provider}'] must be dict")
                    continue
                for entity_name, source_def in entities.items():
                    if entity_name not in VALID_ENTITY_TYPES:
                        # Skip provider-level metadata keys (e.g. update_frequency)
                        continue
                    elif entity_name not in applies_to and entity_name != 'opponent':
                        errors.append(
                            f"{prefix}: sources['{league}']['{provider}']['{entity_name}'] - "
                            f"source '{provider}' does not declare applies_to {entity_name!r}"
                        )
                if not isinstance(source_def, dict):
                    errors.append(
                        f"{prefix}: sources.{provider}.{entity_name} must be dict"
                    )
    return errors


def _validate_dataset_refs(
    db_columns: Dict[str, Dict],
    datasets: Dict[str, Dict],
) -> List[str]:
    """Validate that source dataset references exist in DATASETS."""
    errors = []
    for col_name, meta in db_columns.items():
        sources = meta.get('sources')
        if not sources or not isinstance(sources, dict):
            continue

        prefix = f"DB_COLUMNS['{col_name}']"
        for provider, entities in sources.items():
            if not isinstance(entities, dict):
                continue
            for entity_name, source_def in entities.items():
                if not isinstance(source_def, dict):
                    continue
                ds = (
                    source_def.get('dataset')
                    or source_def.get('pipeline', {}).get('dataset')
                )
                if ds and ds not in datasets:
                    errors.append(
                        f"{prefix}: references unknown dataset '{ds}'"
                    )
    return errors


def _validate_stats_primary_keys(
    stats_tables: Dict[str, Dict],
    db_columns: Dict[str, Dict],
) -> List[str]:
    """Validate that every PK column on a stats table is either the synthetic
    ``the_glass_id`` or a column declared in DB_COLUMNS."""
    from src.core.definitions.tables import THE_GLASS_ID_COLUMN
    errors = []
    for table_name, meta in stats_tables.items():
        for col in meta.get('primary_key', []):
            if col == THE_GLASS_ID_COLUMN:
                continue
            if col not in db_columns:
                errors.append(
                    f"STATS_TABLES['{table_name}']: primary_key references "
                    f"unknown column '{col}'"
                )
    return errors


def _validate_league_primary_sources(
    leagues: Dict[str, Dict],
    sources: Dict[str, Dict],
) -> List[str]:
    """Each league.primary_source must exist in SOURCES with
    external=True and list the league in its leagues array."""
    errors = []
    for league_key, meta in leagues.items():
        rs = meta.get('primary_source')
        if not rs:
            errors.append(f"LEAGUES['{league_key}']: missing primary_source")
            continue
        if rs not in sources:
            errors.append(
                f"LEAGUES['{league_key}']: primary_source '{rs}' not in SOURCES"
            )
            continue
        src = sources[rs]
        if not src.get('external'):
            errors.append(
                f"LEAGUES['{league_key}']: primary_source '{rs}' has external=False"
            )
        if league_key not in src.get('leagues', []):
            errors.append(
                f"LEAGUES['{league_key}']: primary_source '{rs}' does not list "
                f"'{league_key}' in its leagues"
            )
    return errors


def _validate_domain_coverage(db_columns: Dict[str, Dict]) -> List[str]:
    """Every non-primary domain in STAT_DOMAINS must be referenced by at
    least one DB_COLUMNS entry (otherwise the domain is dead config)."""
    from src.core.definitions.stats import STAT_DOMAINS

    used = {meta.get('domain') for meta in db_columns.values() if meta.get('domain')}
    errors: List[str] = []
    for domain, cfg in STAT_DOMAINS.items():
        if cfg.get('primary'):
            continue
        if domain not in used:
            errors.append(
                f"STAT_DOMAINS['{domain}']: declared but no DB_COLUMNS entry "
                f"sets domain={domain!r}"
            )
    return errors


def _validate_fk_targets(
    stats_tables: Dict[str, Dict],
    junction_tables: Dict[str, Dict],
    profile_tables: Dict[str, Dict],
) -> List[str]:
    """Every FK ref_schema/ref_table must resolve to a known table, and the
    on_update / on_delete actions must be in the allowed set."""
    from src.core.definitions.tables import VALID_FK_ACTIONS

    core_tables = set(profile_tables) | set(junction_tables)
    errors: List[str] = []

    for label, table_set in (('STATS_TABLES', stats_tables),
                              ('JUNCTION_TABLES', junction_tables)):
        for tname, meta in table_set.items():
            for fk in meta.get('foreign_keys', []):
                prefix = f"{label}['{tname}'] FK on '{fk.get('column', '?')}'"
                if fk.get('ref_schema') == 'core' and fk.get('ref_table') not in core_tables:
                    errors.append(
                        f"{prefix}: references unknown table "
                        f"core.{fk.get('ref_table')}"
                    )
                for action_key in ('on_update', 'on_delete'):
                    action = fk.get(action_key)
                    if action and action not in VALID_FK_ACTIONS:
                        errors.append(
                            f"{prefix}: {action_key} {action!r} not in "
                            f"{sorted(VALID_FK_ACTIONS)}"
                        )
    return errors


# ============================================================================
# PUBLIC API
# ============================================================================

def validate_config(
    datasets: Optional[Dict[str, Any]] = None,
    datasets_schema: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Validate every ETL configuration dict at startup.

    Args:
        datasets:        Optional DATASETS dict from the active source config.
                          If supplied, source dataset references are cross-checked.
        datasets_schema: Optional schema dict for validating ``datasets``.

    Raises:
        RuntimeError: if any validation errors are found.
    """
    from src.core.lib.config_validation import validate_core_constants
    from src.core.definitions.tables import (
        DB_COLUMNS_SCHEMA,
        JUNCTION_TABLES,
        JUNCTION_TABLES_SCHEMA,
        OPERATIONAL_TABLES,
        OPERATIONAL_TABLES_SCHEMA,
        PROFILE_TABLES,
        PROFILE_TABLES_SCHEMA,
        STATS_TABLES,
        STATS_TABLES_SCHEMA,
    )
    from src.core.definitions.leagues import LEAGUES, LEAGUES_SCHEMA
    from src.etl.definitions.sources import SOURCES, SOURCES_SCHEMA
    from src.core.definitions.columns import DB_COLUMNS

    errors: List[str] = []

    errors.extend(validate_core_constants())

    # Schema-level validations
    errors.extend(validate_dict_config(DB_COLUMNS, DB_COLUMNS_SCHEMA, 'DB_COLUMNS'))
    errors.extend(validate_dict_config(LEAGUES, LEAGUES_SCHEMA, 'LEAGUES'))
    errors.extend(validate_dict_config(SOURCES, SOURCES_SCHEMA, 'SOURCES'))
    errors.extend(validate_dict_config(PROFILE_TABLES, PROFILE_TABLES_SCHEMA, 'PROFILE_TABLES'))
    errors.extend(validate_dict_config(STATS_TABLES, STATS_TABLES_SCHEMA, 'STATS_TABLES'))
    errors.extend(validate_dict_config(JUNCTION_TABLES, JUNCTION_TABLES_SCHEMA, 'JUNCTION_TABLES'))
    errors.extend(validate_dict_config(OPERATIONAL_TABLES, OPERATIONAL_TABLES_SCHEMA, 'OPERATIONAL_TABLES'))

    if datasets and datasets_schema:
        errors.extend(validate_dict_config(datasets, datasets_schema, 'DATASETS'))

    # Type and structural validations
    errors.extend(_validate_pg_types(DB_COLUMNS))
    errors.extend(_validate_source_structure(DB_COLUMNS, SOURCES))
    errors.extend(_validate_stats_primary_keys(STATS_TABLES, DB_COLUMNS))
    errors.extend(_validate_league_primary_sources(LEAGUES, SOURCES))
    errors.extend(_validate_domain_coverage(DB_COLUMNS))
    errors.extend(_validate_fk_targets(STATS_TABLES, JUNCTION_TABLES, PROFILE_TABLES))

    if datasets:
        errors.extend(_validate_dataset_refs(DB_COLUMNS, datasets))

    if errors:
        for err in errors:
            logger.error('Config validation: %s', err)
        raise RuntimeError(
            f"Config validation failed with {len(errors)} error(s)"
        )

    logger.info(
        'Config validation passed (%d columns, %d profiles, %d stats, %d junctions)',
        len(DB_COLUMNS), len(PROFILE_TABLES), len(STATS_TABLES), len(JUNCTION_TABLES),
    )
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

    # Source-specific validation folded into the center.  Each source is
    # validated explicitly so that adding a new source requires editing this
    # module (intentional: it keeps the validation surface visible).
    aggregated: List[str] = []
    for source_key in sorted(SOURCES):
        source_meta = SOURCES[source_key]
        if not source_meta.get('external'):
            continue

        try:
            cfg_mod = __import__(f'src.etl.sources.{source_key}.config', fromlist=['config'])
        except ModuleNotFoundError:
            logger.warning(
                'External source %r is missing config module; '
                'skipping source-specific validation.', source_key,
            )
            continue

        if source_key == 'nba_api':
            aggregated.extend(_validate_nba_api(cfg_mod))

        datasets = getattr(cfg_mod, 'DATASETS', None)
        if datasets is not None:
            from src.core.definitions.columns import DB_COLUMNS
            aggregated.extend(_validate_dataset_refs(DB_COLUMNS, datasets))

    if aggregated:
        for err in aggregated:
            logger.error('Source config validation: %s', err)
        raise RuntimeError(
            f"Source config validation failed with {len(aggregated)} error(s)"
        )

    return []


def _validate_nba_api(cfg_mod) -> List[str]:
    """Validate the ``nba_api`` source config against its local schemas."""
    from src.core.lib.config_validation import validate_dict_config, validate_flat_config

    errors: List[str] = []
    errors.extend(validate_flat_config(
        getattr(cfg_mod, 'API_CONFIG', {}),
        getattr(cfg_mod, 'API_CONFIG_SCHEMA', {}),
        'nba_api.API_CONFIG',
    ))
    errors.extend(validate_dict_config(
        getattr(cfg_mod, 'SEASON_TYPES', {}),
        getattr(cfg_mod, 'SEASON_TYPES_SCHEMA', {}),
        'nba_api.SEASON_TYPES',
    ))
    errors.extend(validate_dict_config(
        getattr(cfg_mod, 'DATASETS', {}),
        getattr(cfg_mod, 'DATASETS_SCHEMA', {}),
        'nba_api.DATASETS',
    ))
    return errors
