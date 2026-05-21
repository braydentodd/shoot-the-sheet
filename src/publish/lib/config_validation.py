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


def _validate_field_prefixes(sheets_columns: dict) -> List[str]:
    """All fields in values[key]['fields'] must have explicit SQL alias prefixes.
    
    Valid prefixes: 'p.' (player_profiles), 't.' (team_profiles),
    's.' (stats), 'tr.' (team_rosters).
    """
    import re
    
    errors: List[str] = []
    valid_prefixes = {'p.', 't.', 's.', 'tr.'}
    prefix_pattern = re.compile(r'^(p|t|s|tr)\.')
    
    for col_name, col_def in sheets_columns.items():
        values = col_def.get('values', {})
        if not isinstance(values, dict):
            continue
            
        for values_key, spec in values.items():
            if not isinstance(spec, dict):
                continue
                
            fields = spec.get('fields', ())
            for field in fields:
                if not isinstance(field, str):
                    continue
                    
                if not prefix_pattern.match(field):
                    errors.append(
                        f"TAB_COLUMNS['{col_name}']['values']['{values_key}']: "
                        f"field '{field}' missing required prefix (must start with "
                        f"one of {sorted(valid_prefixes)})"
                    )
    
    return errors


# ============================================================================
# PUBLIC API
# ============================================================================


def validate_config(league_key: str = None) -> List[str]:
    from src.publish.definitions.columns import TAB_COLUMNS
    from src.publish.definitions.stats import STAT_RATES
    errors: List[str] = []
    errors.extend(_validate_section_subsection(TAB_COLUMNS))
    errors.extend(_validate_width_classes(TAB_COLUMNS))
    errors.extend(_validate_column_section_refs(TAB_COLUMNS))
    errors.extend(_validate_subsection_section_refs())
    errors.extend(_validate_stat_rates_default_unique(STAT_RATES))
    errors.extend(_validate_field_prefixes(TAB_COLUMNS))
    return errors



def validate_all() -> List[str]:
    """One-call entry point for the publish CLI.

    Currently equivalent to :func:`validate_config`, but kept separate so the
    CLI signature stays symmetrical with :func:`src.etl.config_validation.validate_all`.
    """
    return validate_config()
