"""
The Glass - Publish Config Validation

Publish-specific validation: checks every declarative config in
``src.publish.definitions`` against its schema, and runs cross-reference
checks between TAB_COLUMNS and SECTIONS_CONFIG.

Add a new config?  Define a schema dict next to the data in
``src/publish/definitions/config.py``, then register it in
:func:`validate_config` here.
"""

import logging
from typing import List

from src.core.lib.config_validation import (
    validate_dict_config,
    validate_flat_config,
    validate_scalar_dict,
)

logger = logging.getLogger(__name__)


# ============================================================================
# CROSS-REFERENCE VALIDATORS
# ============================================================================

def _validate_section_subsection(sheets_columns: dict) -> List[str]:
    """Stats columns require a subsection for ordering and header display."""
    from src.publish.definitions.layout import SECTIONS_CONFIG

    stats_sections = {
        s for s, meta in SECTIONS_CONFIG.items()
        if meta.get('stats_timeframe') is not None
    }
    errors: List[str] = []

    for col_name, col_def in sheets_columns.items():
        sections = col_def.get('sections', [])
        subsection = col_def.get('subsection')
        is_stats = any(s in stats_sections for s in sections)

        if is_stats and subsection is None:
            errors.append(
                f"TAB_COLUMNS['{col_name}']: stats column missing 'subsection'"
            )

    return errors


def _validate_width_classes(sheets_columns: dict) -> List[str]:
    """String width_class values must be recognized names."""
    from src.publish.definitions.columns import _VALID_WIDTH_CLASSES

    errors: List[str] = []
    for col_name, col_def in sheets_columns.items():
        wc = col_def.get('width_class')
        if isinstance(wc, str) and wc not in _VALID_WIDTH_CLASSES:
            errors.append(
                f"TAB_COLUMNS['{col_name}']: 'width_class' value {wc!r} "
                f"not in {_VALID_WIDTH_CLASSES}"
            )
    return errors


def _validate_column_section_refs(sheets_columns: dict) -> List[str]:
    """Every section listed by a column must exist in SECTIONS_CONFIG."""
    from src.publish.definitions.layout import SECTIONS_CONFIG

    errors: List[str] = []
    known_sections = set(SECTIONS_CONFIG)
    for col_name, col_def in sheets_columns.items():
        for section in col_def.get('sections', []):
            if section not in known_sections:
                errors.append(
                    f"TAB_COLUMNS['{col_name}']: references unknown "
                    f"section '{section}'"
                )
    return errors


def _validate_subsection_section_refs() -> List[str]:
    """SUBSECTIONS may only reference sections that exist in SECTIONS_CONFIG."""
    from src.publish.definitions.layout import SECTIONS_CONFIG, SUBSECTIONS

    errors: List[str] = []
    known_sections = set(SECTIONS_CONFIG)
    for sub_name, meta in SUBSECTIONS.items():
        for section in meta.get('sections', []):
            if section not in known_sections:
                errors.append(
                    f"SUBSECTIONS['{sub_name}']: references unknown "
                    f"section '{section}'"
                )
    return errors


def _validate_stat_rates_default_unique(stat_rates: dict) -> List[str]:
    """STAT_RATES must declare exactly one default."""
    defaults = [k for k, v in stat_rates.items() if v.get('default')]
    if len(defaults) != 1:
        return [
            f"STAT_RATES: expected exactly one entry with default=True, "
            f"got {defaults!r}"
        ]
    return []


# ============================================================================
# PUBLIC API
# ============================================================================

def validate_config() -> List[str]:
    """Validate every declarative publish configuration against its schema.

    Returns the list of errors (empty = clean) and raises ``RuntimeError``
    if anything failed, so callers can both inspect the errors AND fail fast.
    """
    from src.core.lib.config_validation import validate_core_constants
    from src.publish.definitions.columns import TAB_COLUMNS, TAB_COLUMNS_SCHEMA
    from src.publish.definitions.layout import (
        SECTIONS_CONFIG,
        SECTIONS_SCHEMA,
        SUBSECTIONS,
        SUBSECTIONS_SCHEMA,
        TABS_CONFIG,
        TABS_CONFIG_SCHEMA,
        VALUES_KEY_ENTITY,
    )
    from src.publish.definitions.stats import (
        HISTORICAL_TIMEFRAMES,
        STAT_RATES,
        STAT_RATES_SCHEMA,
    )
    from src.publish.definitions.presentation import (
        PRESENTATION_DEFAULTS,
        PRESENTATION_DEFAULTS_SCHEMA,
    )
    from src.publish.destinations.sheets.config import (
        GOOGLE_SHEETS_CONFIG,
        GOOGLE_SHEETS_CONFIG_SCHEMA,
        SHEETS_FORMATTING,
        SHEETS_FORMATTING_SCHEMA,
    )
    from src.publish.definitions.presentation import (
        COLOR_THRESHOLDS,
        COLOR_THRESHOLDS_SCHEMA,
        COLORS,
        COLORS_SCHEMA,
        WIDTH_CLASSES,
    )
    from src.publish.definitions.destinations import (
        DESTINATIONS,
        DESTINATIONS_SCHEMA,
        APPS_SCRIPT_SCHEMA,
    )

    errors: List[str] = []

    errors.extend(validate_core_constants())

    # Per-entry dict-of-dict schemas
    errors.extend(validate_dict_config(TAB_COLUMNS, TAB_COLUMNS_SCHEMA, 'TAB_COLUMNS'))
    errors.extend(validate_dict_config(GOOGLE_SHEETS_CONFIG, GOOGLE_SHEETS_CONFIG_SCHEMA, 'GOOGLE_SHEETS_CONFIG'))
    errors.extend(validate_dict_config(SECTIONS_CONFIG, SECTIONS_SCHEMA, 'SECTIONS_CONFIG'))
    errors.extend(validate_dict_config(COLORS, COLORS_SCHEMA, 'COLORS'))
    errors.extend(validate_dict_config(STAT_RATES, STAT_RATES_SCHEMA, 'STAT_RATES'))
    errors.extend(validate_dict_config(TABS_CONFIG, TABS_CONFIG_SCHEMA, 'TABS_CONFIG'))
    errors.extend(validate_dict_config(SUBSECTIONS, SUBSECTIONS_SCHEMA, 'SUBSECTIONS'))
    errors.extend(validate_dict_config(DESTINATIONS, DESTINATIONS_SCHEMA, 'DESTINATIONS'))

    # Nested apps_script blocks within DESTINATIONS
    for dest_key, dest_entry in DESTINATIONS.items():
        apps_script = dest_entry.get('apps_script')
        if apps_script is not None:
            errors.extend(validate_flat_config(
                apps_script,
                APPS_SCRIPT_SCHEMA,
                f"DESTINATIONS['{dest_key}'].apps_script",
            ))

    # Flat dict schemas
    errors.extend(validate_flat_config(SHEETS_FORMATTING, SHEETS_FORMATTING_SCHEMA, 'SHEETS_FORMATTING'))
    errors.extend(validate_flat_config(PRESENTATION_DEFAULTS, PRESENTATION_DEFAULTS_SCHEMA, 'PRESENTATION_DEFAULTS'))
    errors.extend(validate_flat_config(COLOR_THRESHOLDS, COLOR_THRESHOLDS_SCHEMA, 'COLOR_THRESHOLDS'))

    # Scalar-valued mappings
    errors.extend(validate_scalar_dict(
        HISTORICAL_TIMEFRAMES, 'HISTORICAL_TIMEFRAMES',
        key_types=(int,), value_types=(str,),
    ))
    errors.extend(validate_scalar_dict(
        VALUES_KEY_ENTITY, 'VALUES_KEY_ENTITY',
        key_types=(str,), value_types=(str,),
    ))
    errors.extend(validate_scalar_dict(
        WIDTH_CLASSES, 'WIDTH_CLASSES',
        key_types=(str,), value_types=(int, type(None)),
    ))

    # Cross-reference validations
    errors.extend(_validate_section_subsection(TAB_COLUMNS))
    errors.extend(_validate_width_classes(TAB_COLUMNS))
    errors.extend(_validate_column_section_refs(TAB_COLUMNS))
    errors.extend(_validate_subsection_section_refs())
    errors.extend(_validate_stat_rates_default_unique(STAT_RATES))

    if errors:
        for err in errors:
            logger.error('Publish config validation: %s', err)
        raise RuntimeError(
            f"Publish config validation failed with {len(errors)} error(s)"
        )

    logger.info(
        'Publish config validation passed (%d columns, %d sections, %d leagues)',
        len(TAB_COLUMNS), len(SECTIONS_CONFIG), len(GOOGLE_SHEETS_CONFIG),
    )
    return errors


def validate_all() -> List[str]:
    """One-call entry point for the publish CLI.

    Currently equivalent to :func:`validate_config`, but kept separate so the
    CLI signature stays symmetrical with :func:`src.etl.config_validation.validate_all`.
    """
    return validate_config()
