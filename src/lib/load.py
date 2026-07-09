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

from src.definitions.execution import DEFAULT_BATCH_SIZE
from src.definitions.schema import get_table
from src.lib.postgres import db_connection, quote_col
from src.lib.source_resolver import get_default_external_source

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Table resolution helpers
# ---------------------------------------------------------------------------


def _leagues_table() -> str:
    """Return the schema-qualified leagues profile table."""
    return "core.leagues"


def _resolve_league_id(conn, league_code: str) -> str:
    """Return the league identifier for a league key."""
    leagues_tbl = _leagues_table()
    code_col = "code"

    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {quote_col(code_col)} FROM {leagues_tbl} WHERE {quote_col(code_col)} = %s",
            (league_code,),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError(f"League {league_code!r} not found in {leagues_tbl}")
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
    coalesce: bool = False,
) -> int:
    """``INSERT ... ON CONFLICT DO UPDATE SET`` for a batch of rows.

    Args:
        coalesce: If True, use ``COALESCE(target.col, EXCLUDED.col)`` instead of
            ``EXCLUDED.col`` for updates (first-write-wins semantics).
    """
    if not data:
        return 0

    if update_columns is None:
        conflict_set = set(conflict_columns)
        update_columns = [c for c in columns if c not in conflict_set]

    cols_sql = ", ".join(quote_col(c) for c in columns)
    conflict_sql = ", ".join(quote_col(c) for c in conflict_columns)

    if update_columns:
        if coalesce:
            update_sql = ", ".join(
                f"{quote_col(c)} = COALESCE({table}.{quote_col(c)}, EXCLUDED.{quote_col(c)})"
                for c in update_columns
            )
        else:
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
    """Ultra-fast initial load via PostgreSQL ``COPY FROM``."""
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


# ---------------------------------------------------------------------------
# Row routing
# ---------------------------------------------------------------------------


def write_entity_rows(
    target: str,
    table_name: str,
    rows: Dict[Any, Dict[str, Any]],
    season: str,
    season_type: str,
    league_code: str,
    identity_code: Union[str, None] = None,
) -> int:
    """Write extracted rows to the database.

    Args:
        target:        ``'player'``, ``'team'``, ``'player_opp'``, etc.
        table_name:    Bare target table (``'players'``, ``'player_seasons'``,
                       ``'teams_players'``).  Determines which staging table
                       and write strategy to use.
        rows:          ``{source_entity_id: {col_name: value, ...}, ...}``.
        season:        Season label (``'2024-25'``).
        season_type:   Season type code (``'rs'``, ``'po'``, ``'pi'``, ...).
        league_code:   League key (e.g. ``'nba'``).
        identity_code: Identity registry key.  Defaults to the league's reader.

    Returns:
        Number of rows written.
    """
    if not rows:
        return 0

    if identity_code is None:
        identity_code = get_default_external_source(league_code)

    _profile_tables = {"players", "teams"}
    _roster_tables = {"teams_players", "leagues_teams", "countries_players"}
    _stats_tables = {"player_seasons", "team_seasons", "games"}
    _game_tables = {"team_games", "player_games"}

    if table_name in _profile_tables:
        return write_staged_entity_rows(target, rows, league_code, identity_code)

    if table_name in _roster_tables:
        return write_staged_roster_rows(target, rows, league_code, identity_code)

    if table_name in _game_tables:
        return write_staged_stats_rows(
            target, rows, season, season_type, league_code, identity_code
        )

    if table_name in _stats_tables:
        return write_staged_stats_rows(
            target, rows, season, season_type, league_code, identity_code
        )

    raise ValueError(f"Unknown target table: {table_name!r}")


# ---------------------------------------------------------------------------
# Staged entity rows (profile tables)
# ---------------------------------------------------------------------------


def write_staged_entity_rows(
    target: str,
    rows: Dict[Any, Dict[str, Any]],
    league_code: str,
    identity_code: str,
) -> int:
    """Merge entity data into the staging table for ``league_code``/``identity_code``."""
    table = f"staging.{target}"

    data_cols: Set[str] = set()
    for vals in rows.values():
        data_cols.update(vals.keys())
    data_cols.discard("league_code")
    data_cols.discard("identity")
    sorted_data_cols = sorted(data_cols)

    with db_connection() as conn:
        league_val = _resolve_league_id(conn, league_code)

        from src.definitions.db_columns import DB_COLUMNS
        from src.definitions.leagues import LEAGUES

        bare_name = table.split(".", 1)[-1]
        has_gender = any(
            bare_name in (col_meta.get("tables") or [])
            for col_name, col_meta in DB_COLUMNS.items()
            if col_name == "gender"
        )
        league_gender = LEAGUES.get(league_code, {}).get("gender")
        if has_gender and league_gender:
            for vals in rows.values():
                vals["gender"] = league_gender
            data_cols.add("gender")

        sorted_data_cols = sorted(data_cols)
        valid_cols = {
            c for c, m in DB_COLUMNS.items() if bare_name in (m.get("tables") or [])
        }
        sorted_data_cols = [c for c in sorted_data_cols if c in valid_cols]
        columns = ["league_code", "identity", "ext_id"] + sorted_data_cols
        data: List[tuple] = []
        for source_id, vals in rows.items():
            if source_id is None:
                continue
            row_values = [league_val, identity_code, str(source_id)] + [
                vals.get(c) for c in sorted_data_cols
            ]
            data.append(tuple(row_values))

        if not data:
            return 0

        conflict_columns = list(
            get_table(f"staging.{bare_name}").get("primary_key") or []
        )
        written = _bulk_merge_upsert(
            conn,
            table,
            columns,
            data,
            conflict_columns=conflict_columns,
            skip_unchanged=True,
        )

        # Sync columns declared on both teams and leagues_teams
        # (e.g. conf) so roster tables stay populated.
        if target == "team":
            lt_cols = [
                c
                for c, m in DB_COLUMNS.items()
                if "leagues_teams" in (m.get("tables") or [])
                and c not in ("league_code", "identity", "ext_team_id")
            ]
            extra_cols = [c for c in lt_cols if c in sorted_data_cols]
            lt_table = "staging.leagues_teams"
            lt_columns = [
                "league_code",
                "identity",
                "ext_team_id",
            ] + extra_cols
            lt_data = []
            for source_id in rows:
                if source_id is None:
                    continue
                vals = rows[source_id]
                row_values = [league_val, identity_code, str(source_id)]
                row_values += [vals.get(c) for c in extra_cols]
                lt_data.append(tuple(row_values))
            if lt_data:
                with conn.cursor() as cur:
                    execute_values(
                        cur,
                        f"""
                        INSERT INTO {lt_table} ({", ".join(quote_col(c) for c in lt_columns)})
                        VALUES %s
                        ON CONFLICT DO NOTHING
                        """,
                        lt_data,
                    )
                conn.commit()

        # Sync country_code from players to countries_players
        if target == "player":
            cp_table = "staging.countries_players"
            cp_data = [
                (league_val, identity_code, country_val, str(source_id))
                for source_id, vals in rows.items()
                if source_id is not None
                and (country_val := vals.get("country_code")) is not None
            ]
            if cp_data:
                with conn.cursor() as cur:
                    execute_values(
                        cur,
                        f"""
                        INSERT INTO {cp_table} (league_code, identity, country_code, ext_player_id)
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
    """``INSERT ... ON CONFLICT DO UPDATE`` merge that preserves existing non-null values."""
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
            f"{quote_col(c)} = COALESCE({bare_table}.{quote_col(c)}, EXCLUDED.{quote_col(c)})"
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
    identity_code: str,
    league_code: str,
) -> None:
    """Insert missing player / team codes into profile staging tables."""
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
        league_val = _resolve_league_id(conn, league_code)

        for staging_table, codes in [
            ("players", ext_player_ids),
            ("teams", ext_team_ids),
        ]:
            if not codes:
                continue
            tbl = f"staging.{staging_table}"
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT ext_id FROM {tbl} WHERE identity = %s AND ext_id = ANY(%s)",
                    (identity_code, list(codes)),
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

            rows = [(league_val, identity_code, code) for code in missing]
            with conn.cursor() as cur:
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


# ---------------------------------------------------------------------------
# Staged roster rows
# ---------------------------------------------------------------------------


def write_staged_roster_rows(
    target: str,
    rows: Dict[Any, Dict[str, Any]],
    league_code: str,
    identity_code: str,
) -> int:
    """Write roster relationships to the roster staging table."""
    _ROSTER_TABLES = {
        "teams_players": "staging.teams_players",
        "leagues_teams": "staging.leagues_teams",
        "countries_players": "staging.countries_players",
    }
    table = _ROSTER_TABLES.get(target)
    if table is None:
        raise ValueError(f"Unsupported target for roster write: {target!r}")

    data_cols: Set[str] = set()
    for vals in rows.values():
        data_cols.update(vals.keys())
    data_cols.discard("league_code")
    data_cols.discard("identity")
    data_cols.discard("ext_team_id")
    data_cols.discard("ext_player_id")
    data_cols.discard("country_code")
    sorted_data_cols = sorted(data_cols)

    with db_connection() as conn:
        league_val = _resolve_league_id(conn, league_code)

        data: List[tuple] = []

        if target == "teams_players":
            columns = [
                "league_code",
                "identity",
                "ext_team_id",
                "ext_player_id",
            ] + sorted_data_cols
            for source_id, vals in rows.items():
                team_source_id = vals.get("ext_team_id")
                if source_id is None or team_source_id is None:
                    continue
                row_values = [
                    league_val,
                    identity_code,
                    str(team_source_id),
                    str(source_id),
                ] + [vals.get(c) for c in sorted_data_cols]
                data.append(tuple(row_values))

        elif target == "leagues_teams":
            columns = [
                "league_code",
                "identity",
                "ext_team_id",
            ] + sorted_data_cols
            for source_id, vals in rows.items():
                if source_id is None:
                    continue
                row_values = [
                    league_val,
                    identity_code,
                    str(source_id),
                ] + [vals.get(c) for c in sorted_data_cols]
                data.append(tuple(row_values))

        elif target == "countries_players":
            columns = [
                "league_code",
                "identity",
                "country_code",
                "ext_player_id",
            ] + sorted_data_cols
            for source_id, vals in rows.items():
                country = vals.get("country_code")
                if source_id is None or country is None:
                    continue
                row_values = [
                    league_val,
                    identity_code,
                    country,
                    str(source_id),
                ] + [vals.get(c) for c in sorted_data_cols]
                data.append(tuple(row_values))

        else:
            raise ValueError(f"Unsupported target for roster write: {target!r}")

        if not data:
            return 0

        bare_name = table.split(".", 1)[-1]
        conflict_columns = list(
            get_table(f"staging.{bare_name}").get("primary_key") or []
        )
        return _bulk_merge_upsert(
            conn, table, columns, data, conflict_columns=conflict_columns
        )


# ---------------------------------------------------------------------------
# Staged stats rows
# ---------------------------------------------------------------------------


def write_staged_stats_rows(
    target: str,
    rows: Dict[Any, Dict[str, Any]],
    season: str,
    season_type: str,
    league_code: str,
    identity_code: str,
) -> int:
    """Write stats rows to the staging table, preserving source IDs for later FK resolution."""
    table = f"staging.{target}"
    bare_name = table.split(".", 1)[-1]
    meta = get_table(f"staging.{bare_name}")
    pk_cols = list(meta.get("primary_key") or [])

    # Inject external entity IDs from source IDs so _ensure_staging_profiles
    # can auto-discover missing entities.  Determines which column to populate
    # by checking which ext_*_id columns exist in the staging table schema.
    ext_id_cols = [c for c in pk_cols if c.startswith("ext_") and c.endswith("_id")]
    for ext_col in ext_id_cols:
        for source_id, vals in rows.items():
            if ext_col not in vals:
                vals[ext_col] = str(source_id)

    _ensure_staging_profiles(rows.values(), identity_code, league_code)

    data_cols: Set[str] = set()
    for vals in rows.values():
        data_cols.update(vals.keys())
    sorted_data_cols = sorted(data_cols)

    # PK columns are resolved by trying row data first, then falling back
    # to context defaults.  ext_player_id / ext_team_id are injected above;
    # identity / season / season_type come from ETL parameters.
    _CTX_DEFAULTS = {
        "identity": identity_code,
        "season": season,
        "season_type": season_type,
    }

    with db_connection() as conn:
        league_val = _resolve_league_id(conn, league_code)

        # PK columns may also appear in row data (e.g. ext_team_id injected
        # during per_team extraction).  Keep them out of the data-column list
        # so they aren't included twice in the INSERT.
        pk_set = set(pk_cols)
        sorted_data_cols = [c for c in sorted_data_cols if c not in pk_set]

        columns = ["league_code"] + pk_cols + sorted_data_cols
        data: List[tuple] = []
        for source_id, vals in rows.items():
            if source_id is None:
                continue
            pk_values = []
            for col in pk_cols:
                val = vals.get(col)
                if val is None and col in _CTX_DEFAULTS:
                    val = _CTX_DEFAULTS[col]
                pk_values.append(val)
            row_values = (
                [league_val] + pk_values + [vals.get(c) for c in sorted_data_cols]
            )
            data.append(tuple(row_values))

        if not data:
            return 0

        return _bulk_merge_upsert(
            conn, table, columns, data, conflict_columns=pk_cols, skip_unchanged=True
        )
