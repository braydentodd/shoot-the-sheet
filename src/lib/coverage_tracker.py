"""
Shoot the Sheet - Coverage Tracker

Two coverage tables track fetch state at different granularities:

  ``core.season_coverages`` -- one row per (identity, league, target, season,
    season_type, dataset, col_name) for per-season datasets.

  ``core.game_coverages``   -- one row per (identity, league, game_id, target,
    season, season_type, dataset, col_name) for per-game datasets.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Union

from src.definitions.datasets import DATASETS
from src.definitions.db_columns import DB_COLUMNS
from src.definitions.schema import get_table
from src.lib.call_grouper import is_dataset_available
from src.lib.postgres import db_connection, quote_col

logger = logging.getLogger(__name__)


# ============================================================================
# Helpers
# ============================================================================


def _coverage_table(coverage_level: str) -> str:
    """Return the qualified table name for a coverage level."""
    if coverage_level == "season":
        return "core.season_coverages"
    elif coverage_level == "game":
        return "core.game_coverages"
    else:
        raise ValueError(f"Unknown coverage level: {coverage_level!r}")


def _coverage_pk_cols(coverage_level: str) -> list[str]:
    """Return the PK column list for a coverage level, from schema.py."""
    meta = get_table(_coverage_table(coverage_level))
    return meta.get("primary_key") or []


def _coverage_conflict_sql(coverage_level: str) -> str:
    """Return a quoted, comma-separated PK string for ON CONFLICT."""
    return ", ".join(quote_col(c) for c in _coverage_pk_cols(coverage_level))


# ============================================================================
# Check
# ============================================================================


def is_coverage_current(
    conn: Any,
    league_code: str,
    target: str,
    season: str,
    season_type: str,
    identity_code: str,
    group: Dict[str, Any],
    *,
    coverage_level: str = "season",
    game_id: Union[str, None] = None,
) -> bool:
    """Return True if every col_name in this group has ``covered=true``."""
    dataset = group.get("dataset", "")
    columns = group.get("columns") or {}
    col_names = list(columns.keys())

    if not col_names:
        return False

    table = _coverage_table(coverage_level)

    if coverage_level == "game":
        if game_id is None:
            return False
        query = f"""
            SELECT col_name
              FROM {table}
             WHERE identity = %s
               AND league_code = %s
               AND target   = %s
               AND season   = %s
               AND season_type = %s
               AND game_id  = %s
               AND dataset  = %s
               AND covered  = true
               AND col_name = ANY(%s)
            """
        params: list[Any] = [
            identity_code,
            league_code,
            target,
            season,
            season_type,
            game_id,
            dataset,
            col_names,
        ]
    else:
        query = f"""
            SELECT col_name
              FROM {table}
             WHERE identity = %s
               AND league_code = %s
               AND target   = %s
               AND season   = %s
               AND season_type = %s
               AND dataset  = %s
               AND covered  = true
               AND col_name = ANY(%s)
            """
        params = [
            identity_code,
            league_code,
            target,
            season,
            season_type,
            dataset,
            col_names,
        ]

    with conn.cursor() as cur:
        cur.execute(query, params)
        covered = {row[0] for row in cur.fetchall()}

    return covered == set(col_names)


# ============================================================================
# Upsert
# ============================================================================


def upsert_coverage(
    conn: Any,
    league_code: str,
    target: str,
    season: str,
    season_type: str,
    identity_code: str,
    group: Dict[str, Any],
    *,
    coverage_level: str = "season",
    game_id: Union[str, None] = None,
) -> None:
    """Upsert coverage rows for every col_name in this call group.

    For season-level coverage, ``game_id`` is omitted (column does not
    exist on the table).  For game-level coverage, ``game_id`` is required.
    """
    dataset = group.get("dataset", "")
    columns = group.get("columns") or {}
    col_names = list(columns.keys())

    if not col_names:
        return

    table = _coverage_table(coverage_level)
    conflict_sql = _coverage_conflict_sql(coverage_level)

    with conn.cursor() as cur:
        for col_name in col_names:
            if coverage_level == "season":
                cur.execute(
                    f"""
                    INSERT INTO {table} (
                        identity, league_code,
                        target, season, season_type,
                        dataset, col_name,
                        updated_at, covered
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,NOW(),true)
                    ON CONFLICT ({conflict_sql})
                    DO UPDATE SET updated_at = NOW(), covered = true
                    """,
                    (
                        identity_code,
                        league_code,
                        target,
                        season,
                        season_type,
                        dataset,
                        col_name,
                    ),
                )
            else:
                if game_id is None:
                    raise ValueError("game_id required for game-level coverage upsert")
                cur.execute(
                    f"""
                    INSERT INTO {table} (
                        identity, league_code,
                        target, season, season_type,
                        game_id,
                        dataset, col_name,
                        updated_at, covered
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NOW(),true)
                    ON CONFLICT ({conflict_sql})
                    DO UPDATE SET updated_at = NOW(), covered = true
                    """,
                    (
                        identity_code,
                        league_code,
                        target,
                        season,
                        season_type,
                        game_id,
                        dataset,
                        col_name,
                    ),
                )
    conn.commit()


# ============================================================================
# Seed
# ============================================================================


def seed_coverage(
    league_code: str,
    seasons: List[str],
    identity_code: str,
    *,
    coverage_level: str = "season",
) -> int:
    """Pre-create coverage rows with ``covered=false``.

    For season level, one row per season per combination.
    For game level, one row per game (discovered from ``games`` table).

    Existing ``covered=true`` rows are never overwritten (ON CONFLICT DO NOTHING).
    """
    from src.lib.leagues_resolver import get_all_canonical_season_types

    table = _coverage_table(coverage_level)
    conflict_sql = _coverage_conflict_sql(coverage_level)

    inserted = 0
    all_types = get_all_canonical_season_types(league_code)

    with db_connection() as conn:
        with conn.cursor() as cur:
            for season in seasons:
                for st_key in all_types:
                    # Discover games for game-level coverage
                    if coverage_level == "game":
                        cur.execute(
                            """SELECT game_id FROM core.games
                                    WHERE league_code = %s AND season = %s
                                      AND season_type = %s""",
                            (league_code, season, st_key),
                        )
                        game_ids: list[str] | None = [
                            str(row[0]) for row in cur.fetchall()
                        ]
                        if not game_ids:
                            continue
                    else:
                        # season_coverages has no game_id column
                        game_ids = None

                    for col_name, col_def in DB_COLUMNS.items():
                        dm = col_def.get("dataset_mapping")
                        if not dm:
                            continue
                        for league_key, identities in dm.items():
                            if league_key != league_code:
                                continue
                            for ident, targets in identities.items():
                                if ident != identity_code:
                                    continue
                                for target, datasets in targets.items():
                                    for ds_name in datasets:
                                        ds_def = DATASETS.get(identity_code, {}).get(
                                            ds_name, {}
                                        )
                                        tier = ds_def.get(
                                            "execution_tier", "per_league"
                                        )
                                        expected_level = (
                                            "game" if tier == "per_game" else "season"
                                        )
                                        if expected_level != coverage_level:
                                            continue
                                        if not is_dataset_available(
                                            ds_name, season, identity_code
                                        ):
                                            continue

                                        if game_ids is None:
                                            # season_coverages: one row, no game_id
                                            cur.execute(
                                                f"""
                                                INSERT INTO {table} (
                                                    identity, league_code,
                                                    target, season, season_type,
                                                    dataset, col_name, covered
                                                ) VALUES (%s,%s,%s,%s,%s,%s,%s,false)
                                                ON CONFLICT ({conflict_sql}) DO NOTHING
                                                """,
                                                (
                                                    identity_code,
                                                    league_code,
                                                    target,
                                                    season,
                                                    st_key,
                                                    ds_name,
                                                    col_name,
                                                ),
                                            )
                                            inserted += 1
                                        else:
                                            for game_id in game_ids:
                                                cur.execute(
                                                    f"""
                                                    INSERT INTO {table} (
                                                        identity, league_code,
                                                        target, season, season_type,
                                                        game_id,
                                                        dataset, col_name, covered
                                                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,false)
                                                    ON CONFLICT ({conflict_sql}) DO NOTHING
                                                    """,
                                                    (
                                                        identity_code,
                                                        league_code,
                                                        target,
                                                        season,
                                                        st_key,
                                                        game_id,
                                                        ds_name,
                                                        col_name,
                                                    ),
                                                )
                                                inserted += 1
            conn.commit()

    return inserted


# ============================================================================
# Prune
# ============================================================================


def _prune_coverage_table(league_code: str, table: str) -> int:
    """Delete stale coverage rows from a single coverage table.

    Removes rows where:
      - (identity, dataset, target, col_name) no longer in config
      - season is outside the retention window
    """
    from src.lib.leagues_resolver import get_current_season, get_retained_seasons

    current_season = get_current_season(league_code)
    retained = set(get_retained_seasons(league_code, current_season))

    valid_combos: set[tuple[str, str, str, str]] = set()
    for identity_code, datasets in DATASETS.items():
        for ds_name in datasets:
            for col_name, col_def in DB_COLUMNS.items():
                dm = col_def.get("dataset_mapping")
                if not dm:
                    continue
                for league_key, identities in dm.items():
                    if league_key != league_code:
                        continue
                    for ident, targets in identities.items():
                        if ident != identity_code:
                            continue
                        for target, ds_map in targets.items():
                            if ds_name in ds_map:
                                valid_combos.add(
                                    (identity_code, ds_name, target, col_name)
                                )

    deleted = 0
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT identity, dataset, target, col_name, season "
                f"FROM {table} WHERE league_code = %s",
                (league_code,),
            )
            to_delete = [
                (row[0], row[1], row[2], row[3], row[4])
                for row in cur.fetchall()
                if (row[0], row[1], row[2], row[3]) not in valid_combos
                or row[4] not in retained
            ]

            if not to_delete:
                return 0

            for identity, ds, target, col, season in to_delete:
                cur.execute(
                    f"""
                    DELETE FROM {table}
                    WHERE league_code = %s
                      AND identity = %s
                      AND dataset = %s
                      AND target = %s
                      AND col_name = %s
                      AND season = %s
                    """,
                    (league_code, identity, ds, target, col, season),
                )
                deleted += cur.rowcount
        conn.commit()

    if deleted:
        table_short = table.split(".")[-1]
        logger.info(
            "Pruned %d stale rows from %s for %s",
            deleted,
            table_short,
            league_code,
        )
    return deleted


def prune_coverage(league_code: str) -> int:
    """Delete stale coverage rows from both coverage tables."""
    total = 0
    total += _prune_coverage_table(league_code, "core.season_coverages")
    total += _prune_coverage_table(league_code, "core.game_coverages")
    return total
