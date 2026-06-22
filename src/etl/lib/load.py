"""
Shoot the Sheet - ETL Database Loader

Bulk-write primitives and high-level row writers used by the executor.

ID model:
    Profile tables (``core.{entity}s`` — e.g. ``core.players``)
        - PK: ``sts_id`` (auto-allocated by ``core.sts_id_seq``)
        - Per-source identity columns: ``{source}_id`` (UNIQUE)
        - Conflict key on upsert is the per-source identity column

    Stats tables (``core.{entity}_seasons`` — e.g. ``core.player_seasons``)
        - PK: composite, includes ``sts_id`` and (for player) ``team_id``
        - Source IDs are resolved to sts_id values before write
        - Rows that cannot resolve all FK references are dropped with a warning
"""

import logging
from io import StringIO
from typing import Any, Dict, List, Set, Union

from psycopg2.extras import execute_values

from src.core.definitions.schema import TABLES
from src.core.lib.postgres import db_connection, quote_col
from src.etl.definitions.execution import DEFAULT_BATCH_SIZE
from src.etl.lib.source_resolver import get_default_external_source

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema-derived table lookups (no hardcoded table/column names)
# ---------------------------------------------------------------------------

# Shared (entity, scope) -> bare-table-name mapping.
# Used by _table_for_scope here and by call_groups._columns_for_table.
ENTITY_SCOPE_TABLE: Dict[tuple, str] = {
    ("league", "profiles"): "leagues",
    ("player", "profiles"): "players",
    ("team", "profiles"): "teams",
    ("player", "stats"): "player_seasons",
    ("player_opp", "stats"): "player_seasons",
    ("player_on", "stats"): "player_seasons",
    ("team", "stats"): "team_seasons",
    ("team_opp", "stats"): "team_seasons",
    ("player", "rosters"): "teams_players",
    ("team", "rosters"): "leagues_teams",
    ("country", "rosters"): "countries_players",
    ("player", "staging"): "players_staging",
    ("team", "staging"): "teams_staging",
    ("player", "staging_stats"): "player_seasons_staging",
    ("player_opp", "staging_stats"): "player_seasons_staging",
    ("player_on", "staging_stats"): "player_seasons_staging",
    ("team", "staging_stats"): "team_seasons_staging",
    ("team_opp", "staging_stats"): "team_seasons_staging",
    ("player", "rosters_staging"): "teams_players_staging",
    ("team", "rosters_staging"): "leagues_teams_staging",
}


def _table_for_scope(entity: str, scope: str) -> str:
    """Return the schema-qualified table name for an entity/scope pair.

    Derives from ``ENTITY_SCOPE_TABLE`` + ``TABLES`` schema metadata.
    Raises ``ValueError`` if not found.
    """
    key = (entity, scope)
    if key not in ENTITY_SCOPE_TABLE:
        raise ValueError(f"No table mapping for entity={entity!r} scope={scope!r}")
    table_name = ENTITY_SCOPE_TABLE[key]
    if table_name not in TABLES:
        raise ValueError(f"Table {table_name!r} not in TABLES registry")
    meta = TABLES[table_name]
    schema = meta.get("schema")
    return f"{schema}.{table_name}" if schema else table_name


def _leagues_table() -> str:
    """Return the schema-qualified leagues profile table."""
    return _table_for_scope("league", "profiles")


def _resolve_league_id(conn, league_key: str) -> str:
    """Return the league identifier for a league key.

    Leagues are identified by their ``code`` (TEXT), so this simply validates
    the league exists and returns the key itself.
    """
    leagues_tbl = _leagues_table()
    code_col = "code"

    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {quote_col(code_col)} FROM {leagues_tbl} WHERE {quote_col(code_col)} = %s",
            (league_key,),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError(f"League {league_key!r} not found in {leagues_tbl}")
        return str(row[0])


# ---------------------------------------------------------------------------
# Bulk primitives
# ---------------------------------------------------------------------------


def bulk_upsert(
    conn: Any,
    table: str,
    columns: List[str],
    data: List[tuple],
    conflict_columns: List[str],
    update_columns: Union[List[str], None] = None,
    skip_unchanged: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> int:
    """``INSERT ... ON CONFLICT DO UPDATE SET`` for a batch of rows.

    Args:
        conn:             psycopg2 connection.
        table:            Schema-qualified table name.
        columns:          Ordered column names matching ``data`` tuples.
        data:             List of value tuples (one per row).
        conflict_columns: Unique-constraint columns for conflict detection.
        update_columns:   Columns to overwrite on conflict.  ``None`` -> all
                          non-conflict columns.
        batch_size:       Rows per ``execute_values`` call.

    Returns:
        Number of rows written.
    """
    if not data:
        return 0

    if update_columns is None:
        conflict_set = set(conflict_columns)
        update_columns = [c for c in columns if c not in conflict_set]

    cols_sql = ", ".join(quote_col(c) for c in columns)
    conflict_sql = ", ".join(quote_col(c) for c in conflict_columns)

    if update_columns:
        update_sql = ", ".join(
            f"{quote_col(c)} = EXCLUDED.{quote_col(c)}" for c in update_columns
        )
        if skip_unchanged:
            conflict_clause = (
                f"ON CONFLICT ({conflict_sql}) DO UPDATE SET "
                f"{update_sql}, updated_at = NOW() "
                f"WHERE (target.*) IS DISTINCT FROM (EXCLUDED.*)"
            )
            table_sql = f"{table} AS target"
        else:
            conflict_clause = (
                f"ON CONFLICT ({conflict_sql}) DO UPDATE SET "
                f"{update_sql}, updated_at = NOW()"
            )
            table_sql = table
    else:
        conflict_clause = f"ON CONFLICT ({conflict_sql}) DO NOTHING"
        table_sql = table

    query = f"INSERT INTO {table_sql} ({cols_sql}) VALUES %s {conflict_clause}"

    cursor = conn.cursor()
    written = 0

    for offset in range(0, len(data), batch_size):
        batch = data[offset : offset + batch_size]
        try:
            execute_values(cursor, query, batch, page_size=batch_size)
            written += len(batch)
        except Exception:
            logger.error("Batch failed at offset %d in %s", offset, table)
            conn.rollback()
            raise

    conn.commit()
    return written


def bulk_copy(
    conn: Any,
    table: str,
    columns: List[str],
    data: List[tuple],
) -> int:
    """Ultra-fast initial load via PostgreSQL ``COPY FROM``.

    Does **not** handle conflicts -- intended for empty-table initial loads.
    Uses ``copy_expert`` to support schema-qualified table names.
    """
    if not data:
        return 0

    buf = StringIO()
    for row in data:
        line = "\t".join(str(v) if v is not None else "\\N" for v in row)
        buf.write(line + "\n")
    buf.seek(0)

    cols_sql = ", ".join(quote_col(c) for c in columns)
    copy_sql = f"COPY {table} ({cols_sql}) FROM STDIN WITH (FORMAT text)"

    cursor = conn.cursor()
    try:
        cursor.copy_expert(copy_sql, buf)
        conn.commit()
        return len(data)
    except Exception:
        logger.error("COPY into %s failed", table)
        conn.rollback()
        raise


def write_entity_rows(
    entity: str,
    scope: str,
    rows: Dict[Any, Dict[str, Any]],
    season: str,
    season_type: str,
    league_key: str,
    source_key: Union[str, None] = None,
) -> int:
    """Write extracted rows to the database.

    Args:
        entity:       ``'league'``, ``'team'`` or ``'player'``.
        scope:        ``'profiles'`` or ``'stats'``.
        rows:         ``{source_entity_id: {col_name: value, ...}, ...}``.
        season:       Season label (``'2024-25'``).
        season_type:  Season type code (``'rs'``, ``'po'``, ``'pi'``, ...).
        league_key:   League key (e.g. ``'nba'``).  Used for stats scope.
        source_key:   Source registry key.  Defaults to the league's reader.

    Returns:
        Number of rows written.
    """
    if not rows:
        return 0

    if source_key is None:
        source_key = get_default_external_source(league_key)

    if scope == "profiles":
        return write_staged_entity_rows(entity, rows, league_key, source_key)

    if scope == "rosters":
        return write_staged_roster_rows(entity, rows, league_key, source_key)

    if scope == "stats":
        return write_staged_stats_rows(
            entity, rows, season, season_type, league_key, source_key
        )

    raise ValueError(f"Unsupported scope: {scope!r}")


def write_staged_entity_rows(
    entity: str,
    rows: Dict[Any, Dict[str, Any]],
    league_key: str,
    identity_key: str,
) -> int:
    """Merge entity data into the staging table for ``league_key``/``identity_key``.

    Uses INSERT ON CONFLICT with COALESCE so that later datasets fill in
    NULL columns without overwriting data from earlier datasets.
    """
    table = _table_for_scope(entity, "staging")

    data_cols: Set[str] = set()
    for vals in rows.values():
        data_cols.update(vals.keys())
    data_cols.discard("league")
    data_cols.discard("identity")
    sorted_data_cols = sorted(data_cols)

    with db_connection() as conn:
        league_val = _resolve_league_id(conn, league_key)

        # Always inject gender from league config when the staging table
        # declares a gender column (even though no dataset extracts it).
        from src.core.definitions.db_columns import DB_COLUMNS
        from src.core.definitions.leagues import LEAGUES

        bare_name = table.split(".", 1)[-1]
        has_gender = any(
            bare_name in (col_meta.get("tables") or [])
            for col_name, col_meta in DB_COLUMNS.items()
            if col_name == "gender"
        )
        league_gender = LEAGUES.get(league_key, {}).get("gender")
        if has_gender and league_gender:
            for vals in rows.values():
                vals["gender"] = league_gender
            data_cols.add("gender")

        sorted_data_cols = sorted(data_cols)
        # Drop columns not declared on this staging table (e.g. team_id
        # injected by the executor for per-team calls on profile scope).
        valid_cols = {
            c for c, m in DB_COLUMNS.items() if bare_name in (m.get("tables") or [])
        }
        sorted_data_cols = [c for c in sorted_data_cols if c in valid_cols]
        columns = ["league", "identity"] + sorted_data_cols
        data: List[tuple] = []
        for source_id, vals in rows.items():
            if source_id is None:
                continue
            row_values = [league_val, str(source_id)] + [
                vals.get(c) for c in sorted_data_cols
            ]
            data.append(tuple(row_values))

        if not data:
            return 0

        bare_name = table.split(".", 1)[-1]
        conflict_columns = list(TABLES[bare_name].get("primary_key") or [])
        return _bulk_merge_upsert(
            conn,
            table,
            columns,
            data,
            conflict_columns=conflict_columns,
            skip_unchanged=True,
        )


def _bulk_merge_upsert(
    conn: Any,
    table: str,
    columns: List[str],
    data: List[tuple],
    conflict_columns: List[str],
    update_columns: Union[List[str], None] = None,
    skip_unchanged: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> int:
    """``INSERT ... ON CONFLICT DO UPDATE`` merge that preserves non-null values."""
    if not data:
        return 0

    if update_columns is None:
        conflict_set = set(conflict_columns)
        update_columns = [c for c in columns if c not in conflict_set]

    bare_table = table.split(".", 1)[-1] if "." in table else table
    cols_sql = ", ".join(quote_col(c) for c in columns)
    conflict_sql = ", ".join(quote_col(c) for c in conflict_columns)
    if update_columns:
        update_sql = ", ".join(
            f"{quote_col(c)} = COALESCE(EXCLUDED.{quote_col(c)}, {bare_table}.{quote_col(c)})"
            for c in update_columns
        )
        conflict_clause = f"ON CONFLICT ({conflict_sql}) DO UPDATE SET {update_sql}"
    else:
        conflict_clause = f"ON CONFLICT ({conflict_sql}) DO NOTHING"

    query = f"INSERT INTO {table} ({cols_sql}) VALUES %s {conflict_clause}"
    cursor = conn.cursor()
    written = 0

    for offset in range(0, len(data), batch_size):
        batch = data[offset : offset + batch_size]
        try:
            execute_values(cursor, query, batch, page_size=batch_size)
            written += len(batch)
        except Exception:
            logger.error("Batch failed at offset %d in %s", offset, table)
            conn.rollback()
            raise

    conn.commit()
    return written


def write_staged_roster_rows(
    entity: str,
    rows: Dict[Any, Dict[str, Any]],
    league_key: str,
    identity_key: str,
) -> int:
    """Write roster relationships to the roster staging table.

    Each row must have ``team_id`` (source team identity code) set by the
    per-team extraction context.  Table resolved from ``ENTITY_SCOPE_TABLE``
    so the correct staging table is always used regardless of entity.
    """
    table = _table_for_scope(entity, "rosters_staging")

    data_cols: Set[str] = set()
    for vals in rows.values():
        data_cols.update(vals.keys())
    data_cols.discard("league")
    data_cols.discard("identity")
    data_cols.discard("team_identity")
    data_cols.discard("player_identity")
    sorted_data_cols = sorted(data_cols)

    with db_connection() as conn:
        league_val = _resolve_league_id(conn, league_key)

        columns = [
            "league",
            "identity",
            "team_identity",
            "player_identity",
        ] + sorted_data_cols
        data: List[tuple] = []
        for player_source_id, vals in rows.items():
            team_source_id = vals.get("team_identity")
            if player_source_id is None or team_source_id is None:
                continue
            row_values = [
                league_val,
                identity_key,
                str(team_source_id),
                str(player_source_id),
            ] + [vals.get(c) for c in sorted_data_cols]
            data.append(tuple(row_values))

        if not data:
            return 0

        bare_name = table.split(".", 1)[-1]
        conflict_columns = list(TABLES[bare_name].get("primary_key") or [])
        return _bulk_merge_upsert(
            conn,
            table,
            columns,
            data,
            conflict_columns=conflict_columns,
        )


def write_staged_stats_rows(
    entity: str,
    rows: Dict[Any, Dict[str, Any]],
    season: str,
    season_type: str,
    league_key: str,
    identity_key: str,
) -> int:
    """Write stats rows to the staging table, preserving source IDs for later FK resolution.

    Base columns and conflict key are derived from the table's primary key
    in ``TABLES`` so that a schema change propagates automatically.
    """
    table = _table_for_scope(entity, "staging_stats")
    bare_name = table.split(".", 1)[-1]
    meta = TABLES[bare_name]
    pk_cols = list(meta.get("primary_key") or [])

    # Data columns: everything in the row values minus the reserved set.
    data_cols: Set[str] = set()
    for vals in rows.values():
        data_cols.update(vals.keys())
    reserved = {"league", "season", "season_type", "team_identity", "player_identity"}
    data_cols -= reserved
    sorted_data_cols = sorted(data_cols)

    # How to resolve each PK column for a given (source_id, row_values) pair.
    _PK_SOURCES = {
        "identity": lambda sid, vals: str(sid),
        "season": lambda sid, vals: season,
        "season_type": lambda sid, vals: season_type,
    }

    with db_connection() as conn:
        league_val = _resolve_league_id(conn, league_key)

        columns = ["league"] + pk_cols + sorted_data_cols
        data: List[tuple] = []
        for source_id, vals in rows.items():
            if source_id is None:
                continue
            pk_values = [_PK_SOURCES[col](source_id, vals) for col in pk_cols]
            row_values = (
                [league_val] + pk_values + [vals.get(c) for c in sorted_data_cols]
            )
            data.append(tuple(row_values))

        if not data:
            return 0

        return _bulk_merge_upsert(
            conn,
            table,
            columns,
            data,
            conflict_columns=pk_cols,
            skip_unchanged=True,
        )


def _write_stats_rows(
    entity: str,
    rows: Dict[Any, Dict[str, Any]],
    season: str,
    season_type: str,
    league_key: str,
    source_key: str,
) -> int:
    """Removed — stats now flow through staging tables exclusively.

    Kept as a stub to guide any future direct-to-core path.
    """
    raise NotImplementedError(
        "Direct-to-core stats writes are no longer supported. "
        "Use write_staged_stats_rows and promote via upsert_entities."
    )
