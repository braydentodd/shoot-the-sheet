# ruff: noqa: E402  -- load_dotenv() must run before src.* imports that read os.getenv at module load.
"""
The Glass - Sheets-to-DB Editable Sync

The Players and Teams Google Sheets are the authoritative source for
user-edited values (wingspan, hand, notes, ...).  This module reads those
sheets and writes the values back to the corresponding ``core.{entity}_profiles``
row, keyed by the synthetic ``the_glass_id`` column.

The Glass Sheets is registered in ``SOURCES`` as a ``writer`` source -- it
holds no source-id columns of its own; it edits canonical profile data
through the_glass_id.

Usage:
    python -m src.etl.sources.the_glass_sheets.client --league nba [--dry-run]
"""

import argparse
import logging
import re
from typing import Any, Dict, List, Tuple

from dotenv import load_dotenv
load_dotenv()

from src.core.lib.postgres import db_connection, quote_col
from src.core.lib.tables_resolver import get_table_name
from src.etl.sources.the_glass_sheets.config import SOURCE_CONFIG
from src.publish.definitions.view_columns import VIEW_COLUMNS
from src.publish.destinations.sheets.config import SHEETS_FORMATTING
from src.publish.destinations.sheets.client import get_sheets_client
from src.publish.destinations.sheets.config import GOOGLE_SHEETS_CONFIG
from src.publish.lib.column_structure import build_view_columns, get_column_index

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# VALUE PARSING
# ---------------------------------------------------------------------------

_HEIGHT_PATTERN = re.compile(r"^(\d+)'(\d+)\"?$")


def _parse_measurement(val_str: Any) -> Any:
    """Convert a sheet measurement string (e.g. ``6'8"`` or ``80``) to inches."""
    if val_str is None or val_str == '':
        return None
    text = str(val_str).strip()
    match = _HEIGHT_PATTERN.match(text)
    if match:
        return int(match.group(1)) * 12 + int(match.group(2))
    try:
        inches = int(text)
    except (TypeError, ValueError):
        return None
    return inches if 0 < inches < 120 else None


def _coerce_cell(value: Any, fmt: str) -> Any:
    """Apply per-format transforms; return ``None`` for empty cells."""
    if value == '' or value is None:
        return None
    if fmt == 'measurement':
        return _parse_measurement(value)
    return value


# ---------------------------------------------------------------------------
# SHEET INTROSPECTION
# ---------------------------------------------------------------------------

def _editable_field_specs() -> List[Dict[str, Any]]:
    """Walk VIEW_COLUMNS and yield specs for every column flagged ``editable``.

    Each spec carries the column key, target DB field, format, and the entity
    types it applies to (player / team).
    """
    specs: List[Dict[str, Any]] = []
    for col_key, col_def in VIEW_COLUMNS.items():
        if not col_def.get('editable', False):
            continue
        values = col_def.get('values', {}) or {}
        entity_types = []
        if values.get('player'):
            entity_types.append('player')
        team_value = values.get('team')
        if team_value and team_value != 'TEAM':
            entity_types.append('team')
        if not entity_types:
            continue
        # Strip Jinja-style braces: '{notes}' -> 'notes'
        db_field = (values.get('player') or values.get('team')).strip('{}')
        specs.append({
            'col_key': col_key,
            'db_field': db_field,
            'format': col_def.get('format', 'text'),
            'entity_types': entity_types,
        })
    return specs


def _resolve_column_indices(
    specs: List[Dict[str, Any]],
    columns: List[Dict[str, Any]],
    entity: str,
) -> Dict[str, Dict[str, Any]]:
    """Return ``{col_key: {col_idx, db_field, format}}`` for editable columns
    that apply to ``entity`` and have a resolvable index in ``columns``."""
    resolved: Dict[str, Dict[str, Any]] = {}
    for spec in specs:
        if entity not in spec['entity_types']:
            continue
        idx = get_column_index(spec['col_key'], columns)
        if idx is None:
            continue
        resolved[spec['col_key']] = {
            'col_idx': idx,
            'db_field': spec['db_field'],
            'format': spec['format'],
        }
    return resolved


def _read_sheet_data(worksheet, header_rows: int) -> Tuple[List[str], List[List[Any]]]:
    """Return (headers, data_rows) from a worksheet."""
    all_values = worksheet.get_all_values()
    if len(all_values) <= header_rows:
        return [], []
    return all_values[header_rows - 1], all_values[header_rows:]


def _open_first_worksheet(spreadsheet, names: List[str]):
    """Try ``names`` in order; return the first worksheet that opens, or None."""
    for name in names:
        try:
            return spreadsheet.worksheet(name)
        except Exception:  # gspread raises WorksheetNotFound; swallow generically
            continue
    return None


# ---------------------------------------------------------------------------
# DB WRITES (keyed by the_glass_id)
# ---------------------------------------------------------------------------

def _apply_updates(
    profile_table: str,
    updates: List[Tuple[int, Dict[str, Any]]],
    dry_run: bool,
) -> int:
    """UPDATE each ``the_glass_id`` row with the supplied field map."""
    if not updates:
        return 0
    count = 0
    with db_connection() as conn:
        with conn.cursor() as cur:
            for glass_id, fields in updates:
                if not fields:
                    continue
                set_clause = ', '.join(f'{quote_col(f)} = %s' for f in fields)
                values = list(fields.values()) + [glass_id]
                sql = (
                    f'UPDATE {profile_table} '
                    f'SET {set_clause}, updated_at = NOW() '
                    f'WHERE {quote_col("the_glass_id")} = %s'
                )
                if dry_run:
                    logger.info('[DRY RUN] %s | params=%s', sql, values)
                else:
                    cur.execute(sql, values)
                count += 1
    action = 'Would update' if dry_run else 'Updated'
    logger.info('%s %d rows in %s', action, count, profile_table)
    return count


# ---------------------------------------------------------------------------
# ROW EXTRACTION
# ---------------------------------------------------------------------------

def _extract_rows(
    data_rows: List[List[Any]],
    glass_id_idx: int,
    field_map: Dict[str, Dict[str, Any]],
) -> List[Tuple[int, Dict[str, Any]]]:
    """Pull (the_glass_id, {db_field: value}) tuples from a data-row block."""
    out: List[Tuple[int, Dict[str, Any]]] = []
    for row in data_rows:
        if len(row) <= glass_id_idx:
            continue
        raw = row[glass_id_idx]
        if not raw:
            continue
        try:
            glass_id = int(raw)
        except (TypeError, ValueError):
            continue
        fields: Dict[str, Any] = {}
        for mapping in field_map.values():
            idx = mapping['col_idx']
            if idx >= len(row):
                continue
            fields[mapping['db_field']] = _coerce_cell(row[idx], mapping['format'])
        if fields:
            out.append((glass_id, fields))
    return out


# ---------------------------------------------------------------------------
# PUBLIC ENTRYPOINT
# ---------------------------------------------------------------------------

def sync_edits(league_key: str, dry_run: bool = False) -> Dict[str, int]:
    """Read editable fields from the league's sheets and write to core profiles.

    Sheets layout assumption (handled by the publish layer):
        - Player view has a ``the_glass_id`` column.
        - Team view has a ``the_glass_id`` column.

    Returns ``{'players_updated': N, 'teams_updated': N}``.
    """
    google_config = GOOGLE_SHEETS_CONFIG.get(league_key)
    if not google_config:
        raise ValueError(f"No Google Sheets config for league: {league_key!r}")

    specs = _editable_field_specs()
    if not specs:
        logger.info('No editable fields defined; nothing to sync')
        return {'players_updated': 0, 'teams_updated': 0}

    players_columns = build_view_columns(
        entity='player', stats_mode='both', view_type='players', league=league_key,
    )
    teams_columns = build_view_columns(
        entity='team', stats_mode='both', view_type='teams', league=league_key,
    )

    player_field_map = _resolve_column_indices(specs, players_columns, 'player')
    team_field_map = _resolve_column_indices(specs, teams_columns, 'team')

    glass_id_key = SOURCE_CONFIG['glass_id_column_key']
    pid_idx = get_column_index(glass_id_key, players_columns)
    tid_idx = get_column_index(glass_id_key, teams_columns)
    if pid_idx is None and player_field_map:
        raise RuntimeError(
            f"Player sheet has no '{glass_id_key}' column -- update the publish "
            f"layout to emit it before syncing edits."
        )
    if tid_idx is None and team_field_map:
        raise RuntimeError(
            f"Team sheet has no '{glass_id_key}' column -- update the publish "
            f"layout to emit it before syncing edits."
        )

    header_rows = SHEETS_FORMATTING.get('header_rows', 4)

    sheets_client = get_sheets_client(google_config)
    spreadsheet = sheets_client.open_by_key(google_config['spreadsheet_id'])

    results = {'players_updated': 0, 'teams_updated': 0}

    if player_field_map:
        candidates = [league_key.upper(), 'ALL_PLAYERS', 'PLAYERS']
        ws = _open_first_worksheet(spreadsheet, candidates)
        if ws is None:
            logger.warning('No player worksheet (%s); skipping', candidates)
        else:
            _, data_rows = _read_sheet_data(ws, header_rows)
            logger.info('Read %d rows from %s', len(data_rows), ws.title)
            updates = _extract_rows(data_rows, pid_idx, player_field_map)
            results['players_updated'] = _apply_updates(
                get_table_name('player', 'profiles'), updates, dry_run,
            )

    if team_field_map:
        ws = _open_first_worksheet(spreadsheet, ['ALL_TEAMS', 'TEAMS'])
        if ws is None:
            logger.warning('No team worksheet (ALL_TEAMS / TEAMS); skipping')
        else:
            _, data_rows = _read_sheet_data(ws, header_rows)
            logger.info('Read %d rows from %s', len(data_rows), ws.title)
            updates = _extract_rows(data_rows, tid_idx, team_field_map)
            results['teams_updated'] = _apply_updates(
                get_table_name('team', 'profiles'), updates, dry_run,
            )

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    parser = argparse.ArgumentParser(description='Sync editable fields from Sheets to DB')
    parser.add_argument('--league', required=True, help='League key, e.g. "NBA"')
    parser.add_argument('--dry-run', action='store_true', help='Log SQL without executing')
    args = parser.parse_args()

    results = sync_edits(args.league, dry_run=args.dry_run)
    print(f"Players updated: {results['players_updated']}")
    print(f"Teams updated: {results['teams_updated']}")


if __name__ == '__main__':
    main()
