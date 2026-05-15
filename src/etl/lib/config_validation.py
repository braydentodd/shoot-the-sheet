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
    source key (e.g., 'nba_api'). Provider maps may only contain entity
    keys; provider-level metadata keys are rejected.
    """
    from src.core.definitions.tables import VALID_ENTITY_TYPES
    errors = []
    for col_name, meta in db_columns.items():
        col_sources = meta.get('dataset_mapping')
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
                        errors.append(
                            f"{prefix}: sources['{league}']['{provider}'] contains unsupported key {entity_name!r}; "
                            "only entity keys are allowed"
                        )
                        continue
                    if not isinstance(source_def, dict):
                        errors.append(
                            f"{prefix}: sources['{league}']['{provider}']['{entity_name}'] must be dict"
                        )
                        continue
                    if entity_name not in applies_to and entity_name != 'opponent':
                        errors.append(
                            f"{prefix}: sources['{league}']['{provider}']['{entity_name}'] - "
                            f"source '{provider}' does not declare applies_to {entity_name!r}"
                        )
    return errors


def _validate_dataset_refs(
    db_columns: Dict[str, Dict],
    datasets: Dict[str, Dict],
    provider_filter: Optional[str] = None,
) -> List[str]:
    """Validate that source dataset references exist in DATASETS."""
    from src.core.definitions.tables import VALID_ENTITY_TYPES

    errors = []
    for col_name, meta in db_columns.items():
        sources = meta.get('dataset_mapping')
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
                for entity_name, source_def in entities.items():
                    if entity_name not in VALID_ENTITY_TYPES:
                        continue
                    if not isinstance(source_def, dict):
                        continue
                    ds = (
                        source_def.get('dataset')
                        or source_def.get('pipeline', {}).get('dataset')
                    )
                    if ds and ds not in datasets:
                        errors.append(
                            f"{prefix}: references unknown dataset '{ds}' "
                            f"for sources['{league_key}']['{provider}']['{entity_name}']"
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


def _validate_league_source_roles(
    leagues: Dict[str, Dict],
    sources: Dict[str, Dict],
) -> List[str]:
    """Validate league source role mappings against SOURCES registry."""
    from src.core.definitions.leagues import VALID_SOURCE_ROLE_KEYS

    errors = []
    for league_key, meta in leagues.items():
        role_map = meta.get('source_roles')
        prefix = f"LEAGUES['{league_key}'].source_roles"
        if not isinstance(role_map, dict):
            errors.append(f"{prefix}: expected dict")
            continue

        missing_roles = sorted(role for role in VALID_SOURCE_ROLE_KEYS if role not in role_map)
        if missing_roles:
            errors.append(f"{prefix}: missing required roles {missing_roles}")

        extra_roles = sorted(role for role in role_map if role not in VALID_SOURCE_ROLE_KEYS)
        if extra_roles:
            errors.append(f"{prefix}: unsupported roles {extra_roles}")

        for role, role_cfg in role_map.items():
            role_prefix = f"{prefix}['{role}']"
            if not isinstance(role_cfg, dict):
                errors.append(f"{role_prefix}: expected dict")
                continue

            if len(role_cfg) != 1:
                errors.append(f"{role_prefix}: must contain exactly one source_key mapping")
                continue
            
            source_key = list(role_cfg.keys())[0]

            if not isinstance(source_key, str) or not source_key:
                errors.append(f"{role_prefix}: missing required source_key")
                continue

            if source_key not in sources:
                errors.append(f"{role_prefix}: source '{source_key}' not in SOURCES")
                continue
            src = sources[source_key]
            if not src.get('external'):
                errors.append(f"{role_prefix}: source '{source_key}' has external=False")
            if league_key not in src.get('leagues', []):
                errors.append(
                    f"{role_prefix}: source '{source_key}' does not list "
                    f"'{league_key}' in its leagues"
                )

            applies_to = set(src.get('applies_to', []))
            if role == 'roster_maintainer' and not {'team', 'player'}.issubset(applies_to):
                errors.append(
                    f"{role_prefix}: source '{source_key}' must apply to both team and player"
                )

            snapshot_cfg = role_cfg[source_key]
            # Both roles can hold explicit dataset payload properties if populated
            if snapshot_cfg and isinstance(snapshot_cfg, dict):
                required_keys = {
                    'dataset',
                    'team_id_field',
                    'player_id_field',
                    'jersey_field',
                    'params',
                }
                extra_snapshot_keys = sorted(k for k in snapshot_cfg if k not in required_keys)
                if extra_snapshot_keys:
                    errors.append(
                        f"{role_prefix}.{source_key}: unsupported keys {extra_snapshot_keys}; "
                        f"allowed keys are {sorted(required_keys)}"
                    )
                missing = sorted(k for k in required_keys if k not in snapshot_cfg)
                if missing:
                    errors.append(
                        f"{role_prefix}.{source_key}: missing required keys {missing}"
                    )
                else:
                    if not isinstance(snapshot_cfg['dataset'], str):
                        errors.append(f"{role_prefix}.{source_key}.dataset: expected str")
                    if not isinstance(snapshot_cfg['team_id_field'], str):
                        errors.append(f"{role_prefix}.{source_key}.team_id_field: expected str")
                    if not isinstance(snapshot_cfg['player_id_field'], str):
                        errors.append(f"{role_prefix}.{source_key}.player_id_field: expected str")
                    if not isinstance(snapshot_cfg['jersey_field'], str):
                        errors.append(f"{role_prefix}.{source_key}.jersey_field: expected str")
                    if not isinstance(snapshot_cfg['params'], dict):
                        errors.append(f"{role_prefix}.{source_key}.params: expected dict")
            elif role == 'roster_maintainer':
                errors.append(f"{role_prefix}.{source_key}: expected dict with snapshot config")

    return errors


def _validate_legacy_source_fields(leagues: Dict[str, Dict]) -> List[str]:
    """Disallow legacy league source fields after source-role migration."""
    errors: List[str] = []
    for league_key, meta in leagues.items():
        if 'primary_source' in meta:
            errors.append(
                f"LEAGUES['{league_key}']: legacy field 'primary_source' is not allowed; stats/profile source selection is driven by DB_COLUMNS sources"
            )
        if 'roster_maintainer' in meta:
            errors.append(
                f"LEAGUES['{league_key}']: legacy field 'roster_maintainer' is not allowed; use source_roles['roster_maintainer']"
            )
    return errors


def _validate_legacy_pipeline_fields(leagues: Dict[str, Dict]) -> List[str]:
    """Disallow pipeline-policy fields in league config.

    Pipeline behavior is defined globally in ``src.etl.definitions.pipeline``.
    """
    errors: List[str] = []
    for league_key, meta in leagues.items():
        if 'pipeline' in meta:
            errors.append(
                f"LEAGUES['{league_key}']: field 'pipeline' is not allowed; use src.etl.definitions.pipeline"
            )
        if 'pipeline_profile' in meta:
            errors.append(
                f"LEAGUES['{league_key}']: legacy field 'pipeline_profile' is not allowed; use src.etl.definitions.pipeline"
            )
        if 'entity_identity_columns' in meta:
            errors.append(
                f"LEAGUES['{league_key}']: legacy field 'entity_identity_columns' is not allowed"
            )
        if 'entity_matcher' in meta:
            errors.append(
                f"LEAGUES['{league_key}']: legacy field 'entity_matcher' is not allowed; use ENTITY_MATCHER_POLICY"
            )
        if 'etl_stages' in meta:
            errors.append(
                f"LEAGUES['{league_key}']: legacy field 'etl_stages' is not allowed; use PIPELINE_STEPS/PIPELINE_PHASES"
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
    roster_tables: Dict[str, Dict],
    profile_tables: Dict[str, Dict],
) -> List[str]:
    """Every FK ref_schema/ref_table must resolve to a known table, and the
    on_update / on_delete actions must be in the allowed set."""
    from src.core.definitions.tables import VALID_FK_ACTIONS

    core_tables = set(profile_tables) | set(roster_tables)
    errors: List[str] = []

    for label, table_set in (('STATS_TABLES', stats_tables),
                              ('ROSTER_TABLES', roster_tables)):
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


def _validate_league_stage_definitions() -> List[str]:
    """Validate global ETL steps and phase ordering declarations."""
    from src.etl.definitions.pipeline import PIPELINE_PHASES, PIPELINE_STEPS, PIPELINE_STEP_SCHEMA, VALID_ETL_PHASES
    from src.core.lib.config_validation import validate_entry

    errors: List[str] = []
    expected_keys = set(PIPELINE_STEP_SCHEMA.keys())
    referenced_steps = set()

    if not isinstance(PIPELINE_STEPS, dict):
        return [
            f"PIPELINE_STEPS: expected dict, got {type(PIPELINE_STEPS).__name__}"
        ]

    for step_name, step in PIPELINE_STEPS.items():
        prefix = f"PIPELINE_STEPS['{step_name}']"
        if not isinstance(step_name, str) or not step_name:
            errors.append('PIPELINE_STEPS: step key must be non-empty str')
            continue
        if not isinstance(step, dict):
            errors.append(f"{prefix}: expected dict, got {type(step).__name__}")
            continue

        step_keys = set(step.keys())
        if step_keys != expected_keys:
            errors.append(
                f"{prefix}: keys must exactly match {sorted(expected_keys)}; "
                f"got {sorted(step_keys)}"
            )

        errors.extend(validate_entry(step, PIPELINE_STEP_SCHEMA, prefix))

    if not isinstance(PIPELINE_PHASES, dict):
        errors.append(
            f"PIPELINE_PHASES: expected dict, got {type(PIPELINE_PHASES).__name__}"
        )
        return errors

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
        errors.append(
            f"PIPELINE_PHASES: missing required phases {missing_phases}"
        )

    for phase, step_names in PIPELINE_PHASES.items():
        phase_prefix = f"PIPELINE_PHASES['{phase}']"
        if not isinstance(step_names, list):
            errors.append(f"{phase_prefix}: expected list, got {type(step_names).__name__}")
            continue
        if not step_names:
            errors.append(f"{phase_prefix}: must not be empty")
            continue

        seen = set()
        for idx, step_name in enumerate(step_names):
            prefix = f"{phase_prefix}[{idx}]"
            if not isinstance(step_name, str) or not step_name:
                errors.append(f"{prefix}: expected non-empty str")
                continue
            if step_name in seen:
                errors.append(f"{phase_prefix}: duplicate step {step_name!r}")
                continue
            seen.add(step_name)
            if step_name not in PIPELINE_STEPS:
                errors.append(f"{prefix}: unknown step key {step_name!r}")
                continue
            referenced_steps.add(step_name)

    unused_steps = sorted(step for step in PIPELINE_STEPS if step not in referenced_steps)
    if unused_steps:
        errors.append(
            f"PIPELINE_STEPS: unreferenced step keys {unused_steps}"
        )

    return errors


def _validate_entity_matcher_definitions() -> List[str]:
    """Validate global entity matcher policy."""
    from src.etl.definitions.pipeline import (
        ENTITY_MATCHER_POLICY,
        VALID_ENTITY_MATCHER_MODES,
    )

    errors: List[str] = []
    valid_entities = {'team', 'player'}

    prefix = 'ENTITY_MATCHER_POLICY'
    matcher_cfg = ENTITY_MATCHER_POLICY
    if not isinstance(matcher_cfg, dict):
        errors.append(f"{prefix}: expected dict")
        return errors

    default_mode = matcher_cfg.get('default_mode')
    if default_mode not in VALID_ENTITY_MATCHER_MODES:
        errors.append(
            f"{prefix}.default_mode: expected one of {sorted(VALID_ENTITY_MATCHER_MODES)}, got {default_mode!r}"
        )

    entity_rules = matcher_cfg.get('entity_rules')
    if not isinstance(entity_rules, dict):
        errors.append(f"{prefix}.entity_rules: expected dict")
        return errors

    for entity, rule in entity_rules.items():
        rule_prefix = f"{prefix}.entity_rules['{entity}']"
        if entity not in valid_entities:
            errors.append(
                f"{prefix}.entity_rules: unsupported entity {entity!r}; expected one of {sorted(valid_entities)}"
            )
            continue

        if not isinstance(rule, dict):
            errors.append(f"{rule_prefix}: expected dict")
            continue

        mode = rule.get('mode')
        if mode not in VALID_ENTITY_MATCHER_MODES:
            errors.append(
                f"{rule_prefix}.mode: expected one of {sorted(VALID_ENTITY_MATCHER_MODES)}, got {mode!r}"
            )

        blocked_ids = rule.get('blocked_source_ids', [])
        if not isinstance(blocked_ids, list):
            errors.append(f"{rule_prefix}.blocked_source_ids: expected list")

    return errors

def _validate_pipeline_structure() -> List[str]:
    """Validate global pipeline policy top-level shape."""
    from src.etl.definitions.pipeline import (
        ENTITY_MATCHER_POLICY,
        PIPELINE_PHASES,
        PIPELINE_STEPS,
    )

    errors: List[str] = []
    if not isinstance(ENTITY_MATCHER_POLICY, dict):
        errors.append(
            f"ENTITY_MATCHER_POLICY: expected dict, got {type(ENTITY_MATCHER_POLICY).__name__}"
        )
    if not isinstance(PIPELINE_STEPS, dict):
        errors.append(
            f"PIPELINE_STEPS: expected dict, got {type(PIPELINE_STEPS).__name__}"
        )
    if not isinstance(PIPELINE_PHASES, dict):
        errors.append(
            f"PIPELINE_PHASES: expected dict, got {type(PIPELINE_PHASES).__name__}"
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
        ROSTER_TABLES,
        ROSTER_TABLES_SCHEMA,
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
    errors.extend(validate_dict_config(ROSTER_TABLES, ROSTER_TABLES_SCHEMA, 'ROSTER_TABLES'))
    errors.extend(validate_dict_config(OPERATIONAL_TABLES, OPERATIONAL_TABLES_SCHEMA, 'OPERATIONAL_TABLES'))

    if datasets and datasets_schema:
        errors.extend(validate_dict_config(datasets, datasets_schema, 'DATASETS'))

    # Type and structural validations
    errors.extend(_validate_pg_types(DB_COLUMNS))
    errors.extend(_validate_source_structure(DB_COLUMNS, SOURCES))
    errors.extend(_validate_stats_primary_keys(STATS_TABLES, DB_COLUMNS))
    errors.extend(_validate_league_source_roles(LEAGUES, SOURCES))
    errors.extend(_validate_legacy_source_fields(LEAGUES))
    errors.extend(_validate_legacy_pipeline_fields(LEAGUES))
    errors.extend(_validate_pipeline_structure())
    errors.extend(_validate_league_stage_definitions())
    errors.extend(_validate_entity_matcher_definitions())
    errors.extend(_validate_domain_coverage(DB_COLUMNS))
    errors.extend(_validate_fk_targets(STATS_TABLES, ROSTER_TABLES, PROFILE_TABLES))

    if datasets:
        errors.extend(_validate_dataset_refs(DB_COLUMNS, datasets))

    if errors:
        for err in errors:
            logger.error('Config validation: %s', err)
        raise RuntimeError(
            f"Config validation failed with {len(errors)} error(s)"
        )

    logger.info(
        'Config validation passed (%d columns, %d profiles, %d stats, %d rosters)',
        len(DB_COLUMNS), len(PROFILE_TABLES), len(STATS_TABLES), len(ROSTER_TABLES),
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
            aggregated.extend(_validate_dataset_refs(
                DB_COLUMNS,
                datasets,
                provider_filter=source_key,
            ))

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
