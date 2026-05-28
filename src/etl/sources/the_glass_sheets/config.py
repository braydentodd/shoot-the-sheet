"""
The Glass - Sheets Source Configuration

Pure data definitions for the ``the_glass_sheets`` source: metadata for
syncing user-edited values from Google Sheets back to profile tables.

Unlike API sources (nba_api, pbp_stats), this is a ``writer`` source that
doesn't hold source-id columns -- it edits canonical profile data via
the_glass_id anchor column.
"""

from typing import TypedDict


class SourceConfigDef(TypedDict):
    source_key: str
    glass_id_column_key: str


SOURCE_CONFIG: SourceConfigDef = {
    'source_key': 'the_glass_sheets',
    'glass_id_column_key': 'the_glass_id',
}
