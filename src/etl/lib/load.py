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
    ("league_code", "profiles"): "leagues",
    ("player", "profiles"): "players",
    ("team", "profiles"): "teams",
    ("player", "stats"): "player_seasons",
    ("player_opp", "stats"): "player_seasons",
    ("player_on", "stats"): "player_seasons",
    ("team", "stats"): "team_seasons",
    ("team_opp", "stats"): "team_seasons",
    ("player", "rosters"): "teams_players_staging",
    ("team", "rosters"): "leagues_teams_staging",
    ("country", "rosters"): "countries_players_staging",
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
    return _table_for_scope("league_code", "profiles")


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
    data_cols.discard("league_code")
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
        columns = ["league_code", "identity", "ext_id"] + sorted_data_cols
        data: List[tuple] = []
        for source_id, vals in rows.items():
            if source_id is None:
                continue
            row_values = [league_val, identity_key, str(source_id)] + [
                vals.get(c) for c in sorted_data_cols
            ]
            data.append(tuple(row_values))

        if not data:
            return 0

        bare_name = table.split(".", 1)[-1]
        conflict_columns = list(TABLES[bare_name].get("primary_key") or [])
        written = _bulk_merge_upsert(
            conn,
            table,
            columns,
            data,
            conflict_columns=conflict_columns,
            skip_unchanged=True,
        )

        # For team entities, also write the league-team relationship so
        # leagues_teams_staging stays in sync with teams_staging.
        if entity == "team":
            lt_table = _table_for_scope("team", "rosters_staging")
            lt_data = [
                (league_val, identity_key, str(source_id), str(source_id))
                for source_id in rows
                if source_id is not None
            ]
            if lt_data:
                with conn.cursor() as cur:
                    execute_values(
                        cur,
                        f"""
                        INSERT INTO {lt_table} (league_code, identity, ext_id, ext_team_id)
                        VALUES %s
                        ON CONFLICT DO NOTHING
                        """,
                        lt_data,
                    )
                conn.commit()

        # For player entities, sync country_code to countries_players_staging.
        if entity == "player":
            cp_table = _table_for_scope("country", "rosters_staging")
            cp_data = [
                (league_val, identity_key, str(source_id), country_val, str(source_id))
                for source_id, vals in rows.items()
                if source_id is not None
                and (country_val := vals.get("country_code")) is not None
            ]
            if cp_data:
                with conn.cursor() as cur:
                    execute_values(
                        cur,
                        f"""
                        INSERT INTO {cp_table} (league_code, identity, ext_id, country_code, ext_player_id)
                        VALUES %s
                        ON CONFLICT DO NOTHING
                        """,
                        cp_data,
                    )
                conn.commit()

        return written


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


def _ensure_staging_profiles(
    row_dicts,
    identity_key: str,
    league_key: str,
) -> None:
    """Insert missing player / team codes into profile staging tables.

    Scans the given row dicts for ``ext_player_id`` and ``ext_team_id`` values,
    then ensures a corresponding row exists in ``players_staging`` /
    ``teams_staging`` so that FK constraints on stats / roster staging
    tables are satisfied.
    """
    ext_player_ids: set[str] = set()
    ext_team_ids: set[str] = set()
    for row in row_dicts:
        pc = row.get("ext_player_id")
        if pc is not None:
            ext_player_ids.add(str(pc))
        tc = row.get("ext_team_id")
        if tc is not None:
            ext_team_ids.add(str(tc))

    if not ext_player_ids and not ext_team_ids:
        return

    with db_connection() as conn:
        league_val = _resolve_league_id(conn, league_key)

        for staging_table, codes in [
            ("players_staging", ext_player_ids),
            ("teams_staging", ext_team_ids),
        ]:
            if not codes:
                continue
            tbl = _table_for_scope(
                "player" if staging_table == "players_staging" else "team", "staging"
            )
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT ext_id FROM {tbl} WHERE identity = %s AND ext_id = ANY(%s)",
                    (identity_key, list(codes)),
                )
                existing = {row[0] for row in cur.fetchall()}

            missing = codes - existing
            if not missing:
                continue

            logger.debug(
                "Auto-discovering %d %s: %s",
                len(missing),
                staging_table,
                sorted(missing)[:10],
            )

            rows = [(league_val, identity_key, code) for code in missing]
            execute_values(
                cur,
                f"""
                INSERT INTO {tbl} (league_code, identity, ext_id)
                VALUES %s
                ON CONFLICT DO NOTHING
                """,
                rows,
            )
        conn.commit()


def write_staged_roster_rows(
    entity: str,
    rows: Dict[Any, Dict[str, Any]],
    league_key: str,
    identity_key: str,
) -> int:
    """Write roster relationships to the roster staging table.

    Each row must have ``ext_team_id`` (source team identity code) set by the
    per-team extraction context.  Table resolved from ``ENTITY_SCOPE_TABLE``
    so the correct staging table is always used regardless of entity.
    """
    table = _table_for_scope(entity, "rosters_staging")

    data_cols: Set[str] = set()
    for vals in rows.values():
        data_cols.update(vals.keys())
    data_cols.discard("league_code")
    data_cols.discard("identity")
    data_cols.discard("ext_team_id")
    data_cols.discard("ext_player_id")
    sorted_data_cols = sorted(data_cols)

    with db_connection() as conn:
        league_val = _resolve_league_id(conn, league_key)

        data: List[tuple] = []

        if entity == "player":
            columns = [
                "league_code",
                "identity",
                "code",
                "ext_team_id",
                "ext_player_id",
            ] + sorted_data_cols
            for source_id, vals in rows.items():
                team_source_id = vals.get("ext_team_id")
                if source_id is None or team_source_id is None:
                    continue
                row_values = [
                    league_val,
                    identity_key,
                    str(source_id),
                    str(team_source_id),
                    str(source_id),
                ] + [vals.get(c) for c in sorted_data_cols]
                data.append(tuple(row_values))

        elif entity == "team":
            columns = [
                "league_code",
                "identity",
                "ext_id",
                "ext_team_id",
            ] + sorted_data_cols
            for source_id, vals in rows.items():
                if source_id is None:
                    continue
                row_values = [
                    league_val,
                    identity_key,
                    str(source_id),
                    str(source_id),
                ] + [vals.get(c) for c in sorted_data_cols]
                data.append(tuple(row_values))

        elif entity == "country":
            columns = [
                "league_code",
                "identity",
                "code",
                "country",
                "ext_player_id",
            ] + sorted_data_cols
            for source_id, vals in rows.items():
                country = vals.get("country")
                if source_id is None or country is None:
                    continue
                row_values = [
                    league_val,
                    identity_key,
                    str(source_id),
                    country,
                    str(source_id),
                ] + [vals.get(c) for c in sorted_data_cols]
                data.append(tuple(row_values))

        else:
            raise ValueError(f"Unsupported entity for roster write: {entity!r}")

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

    Before writing, any ``ext_team_id`` / ``ext_player_id`` values present in the
    rows that do not yet exist in ``teams_staging`` / ``players_staging`` are
    inserted so the FK constraints on stats staging tables are satisfied.
    """
    table = _table_for_scope(entity, "staging_stats")
    bare_name = table.split(".", 1)[-1]
    meta = TABLES[bare_name]
    pk_cols = list(meta.get("primary_key") or [])

    # Ensure referenced profiles exist in staging before the FK-constrained INSERT.
    _ensure_staging_profiles(rows.values(), identity_key, league_key)

    # Data columns: everything in the row values.
    data_cols: Set[str] = set()
    for vals in rows.values():
        data_cols.update(vals.keys())
    sorted_data_cols = sorted(data_cols)

    # Resolve PK values for each row from the column registry.
    # Columns declared in the staging table's PK but not present in row values
    # are resolved from the call context (identity, season, season_type).

    # Inject ext_player_id from the source_id for player entities so the FK
    # column is populated and auto-discovery can find new players.
    if entity in ("player", "player_opp", "player_on"):
        for source_id, vals in rows.items():
            if "ext_player_id" not in vals:
                vals["ext_player_id"] = str(source_id)
    _PK_SOURCES = {
        "identity": lambda sid, vals: identity_key,
        "ext_id": lambda sid, vals: str(sid),
        "season": lambda sid, vals: season,
        "season_type": lambda sid, vals: season_type,
    }

    with db_connection() as conn:
        league_val = _resolve_league_id(conn, league_key)

        # Build column list from TABLES PK + data cols (no hardcoded reserved set).
        all_pk_cols = pk_cols.copy()
        # ext_team_id and ext_player_id are declared on the table but not in every row.
        # If a row carries them, they're treated as data cols; they are NOT in the PK
        # for stats staging so they sit in sorted_data_cols.
        columns = ["league_code"] + all_pk_cols + sorted_data_cols
        data: List[tuple] = []
        for source_id, vals in rows.items():
            if source_id is None:
                continue
            pk_values = [_PK_SOURCES[col](source_id, vals) for col in all_pk_cols]
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
