"""
The Glass - Google Sheets Destination Configuration

Sheets-API-only configuration: per-league spreadsheet identifiers, OAuth
scopes, credentials file path, and Sheets-specific presentation settings.
Cross-destination presentation knobs (PRESENTATION_DEFAULTS, HEADER_ROWS)
live in :mod:`src.publish.definitions.presentation` and
:mod:`src.publish.lib.tabular_layout` because they're tabular-renderer
abstractions, not Sheets-specific.
"""

import os
from typing import Any, Dict


# ============================================================================
# GOOGLE SHEETS CREDENTIALS
# ============================================================================

GOOGLE_SHEETS_CONFIG_SCHEMA: Dict[str, Dict[str, Any]] = {
    'credentials_file': {'required': True, 'types': (str, type(None))},
    'spreadsheet_id':   {'required': True, 'types': (str, type(None))},
    'scopes':           {'required': True, 'types': (list,)},
}

GOOGLE_SHEETS_CONFIG: Dict[str, Dict[str, Any]] = {
    'nba': {
        'credentials_file': 'google-credentials.json',
        'spreadsheet_id':   os.getenv('NBA_SPREADSHEET_ID'),
        'scopes': [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive',
        ],
    },
    'ncaa': {
        'credentials_file': 'google-credentials.json',
        'spreadsheet_id':   os.getenv('NCAA_SPREADSHEET_ID'),
        'scopes': [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive',
        ],
    },
}


# ============================================================================
# SHEETS-SPECIFIC PRESENTATION SETTINGS
# ============================================================================

SHEETS_FORMATTING: Dict[str, Any] = {
    'frozen_columns':              1,
    'frozen_rows':                 6,
    'header_rows':                 6,
    'sync_delay_seconds':          0,
    'data_only_sync_delay_seconds': 0,
}

SHEETS_FORMATTING_SCHEMA: Dict[str, Dict[str, Any]] = {
    'frozen_columns':               {'required': True, 'types': (int,)},
    'frozen_rows':                  {'required': True, 'types': (int,)},
    'header_rows':                  {'required': True, 'types': (int,)},
    'sync_delay_seconds':           {'required': True, 'types': (int,)},
    'data_only_sync_delay_seconds': {'required': True, 'types': (int,)},
}
