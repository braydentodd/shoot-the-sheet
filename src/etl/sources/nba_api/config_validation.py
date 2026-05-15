"""
The Glass - NBA API Provider Validation

Schema validation for the ``nba_api`` source.  Kept separate from
``config.py`` so the config module remains pure declarative data per the
project-wide "no functions in config files" rule.

Invoked by :func:`src.etl.config_validation.validate_all` once per
registered reader source.
"""

from typing import List

from src.core.lib.config_validation import validate_dict_config, validate_flat_config
from src.etl.sources.nba_api.config import (
    API_CONFIG,
    API_CONFIG_SCHEMA,
    DATASETS,
    DATASETS_SCHEMA,
    RETRY_CONFIG,
    RETRY_CONFIG_SCHEMA,
    SEASON_TYPES,
    SEASON_TYPES_SCHEMA,
)


def validate_provider_config() -> List[str]:
    """Validate every nba_api config dict against its co-located schema.

    Returns a list of error strings (empty = clean).  Caller (typically
    :func:`src.etl.config_validation.validate_all`) handles surfacing.
    """
    errors: List[str] = []
    errors.extend(validate_flat_config(API_CONFIG, API_CONFIG_SCHEMA, 'API_CONFIG'))
    errors.extend(validate_flat_config(RETRY_CONFIG, RETRY_CONFIG_SCHEMA, 'RETRY_CONFIG'))
    errors.extend(validate_dict_config(SEASON_TYPES, SEASON_TYPES_SCHEMA, 'SEASON_TYPES'))
    errors.extend(validate_dict_config(DATASETS, DATASETS_SCHEMA, 'DATASETS'))
    return errors
