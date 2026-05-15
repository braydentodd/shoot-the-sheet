"""

The Glass - Google Sheets Destination Configuration

Sheets-API-only configuration: per-league spreadsheet identifiers, OAuth
scopes, credentials file path, and Sheets-specific presentation settings.
Cross-destination presentation knobs (PRESENTATION_DEFAULTS, HEADER_ROWS)
live in :mod:`src.publish.definitions.presentation` and
:mod:`src.publish.lib.tabular_layout` because they're tabular-renderer
abstractions, not Sheets-specific.
"""

from typing import Dict, List, TypedDict, Union, Any


import os

class SheetsConfigDef(TypedDict):
    credentials_file: str
    spreadsheet_id: Union[str, None]
    scopes: List[str]

GOOGLE_SHEETS_CONFIG: Dict[str, SheetsConfigDef] = {

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

