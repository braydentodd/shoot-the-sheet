"""
Shoot the Sheet - Stat Coverage Tracker

Tracks which (col_name, dataset) pairs have been fetched for each
(target, identity, league, season, season_type) tuple.  A coverage
row simply records that the data was pulled — no params comparison
is needed because the dataset's ``source_mapping`` is the single
source of truth for API parameters.

Table: ``core.season_coverages``
PK:    (identity, league_code, target, season, season_type, dataset, col_name)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from src.core.definitions.db_columns import DB_COLUMNS
from src.core.definitions.schema import TABLES
from src.core.lib.postgres import db_connection, quote_col

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_COVERAGE_META = TABLES["season_coverages"]
_COVERAGE_TABLE = f"{_COVERAGE_META['schema']}.season_coverages"
_COVERAGE_PK_COLS = _COVERAGE_META["primary_key"] or []
_COVERAGE_CONFLICT = ", ".join(quote_col(c) for c in _COVERAGE_PK_COLS)


def _targets_for_column(col_meta: Any) -> set:
    targets: set[str] = set()
    mapping = col_meta.get("dataset_mapping")
    if not mapping:
        return targets
    for league_sources in mapping.values():
        if not isinstance(league_sources, dict):
            continue
        for identity_sources in league_sources.values():
            if not isinstance(identity_sources, dict):
                continue
            targets.update(identity_sources.keys())
    return targets


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_group_coverage_current(
    conn: Any,
    league_code: str,
    target: str,
    season: str,
    season_type: str,
    identity_code: str,
    group: Dict[str, Any],
) -> bool:
    """Return True if every col_name in this group already has a coverage row."""
    dataset = group.get("dataset", "")
    columns = group.get("columns") or {}
    col_names = list(columns.keys())

    if not col_names:
        return False

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT col_name
              FROM {_COVERAGE_TABLE}
             WHERE identity = %s
               AND league_code = %s
               AND target   = %s
               AND season   = %s
               AND season_type = %s
               AND dataset  = %s
               AND col_name = ANY(%s)
            """,
            (
                identity_code,
                league_code,
                target,
                season,
                season_type,
                dataset,
                col_names,
            ),
        )
        covered = {row[0] for row in cur.fetchall()}

    return covered == set(col_names)


def upsert_group_coverage(
    conn: Any,
    league_code: str,
    target: str,
    season: str,
    season_type: str,
    identity_code: str,
    group: Dict[str, Any],
) -> None:
    """Upsert coverage rows for every col_name produced by this call group."""
    dataset = group.get("dataset", "")
    columns = group.get("columns") or {}
    col_names = list(columns.keys())

    if not col_names:
        return

    with conn.cursor() as cur:
        for col_name in col_names:
            cur.execute(
                f"""
                INSERT INTO {_COVERAGE_TABLE} (
                    identity, league_code, target, season, season_type, dataset, col_name, completed_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT ({_COVERAGE_CONFLICT})
                DO UPDATE SET completed_at = NOW()
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
    conn.commit()


def prune_season_coverages(league_code: str) -> int:
    """Delete coverage rows for (target, col_name) pairs no longer in config."""
    valid: set[tuple[str, str]] = set()
    for col_name, col_meta in DB_COLUMNS.items():
        for target in _targets_for_column(col_meta):
            valid.add((target, col_name))

    deleted = 0
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT target, col_name FROM {_COVERAGE_TABLE} WHERE league_code = %s",
                (league_code,),
            )
            to_delete: List[tuple[str, str]] = [
                (row[0], row[1])
                for row in cur.fetchall()
                if (row[0], row[1]) not in valid
            ]

            if not to_delete:
                return 0

            values = ",".join("(%s, %s)" for _ in to_delete)
            flat = [item for pair in to_delete for item in pair]
            cur.execute(
                f"""
                DELETE FROM {_COVERAGE_TABLE}
                WHERE league_code = %s
                  AND (target, col_name) IN (VALUES """
                + values
                + """)
                """,
                (league_code,) + tuple(flat),
            )
            deleted = cur.rowcount
        conn.commit()

    if deleted:
        logger.info("Pruned %d stale coverage rows for %s", deleted, league_code)
    return deleted


# ---------------------------------------------------------------------------
# Game coverage (mirrors season_coverages at game granularity)
# ---------------------------------------------------------------------------

_GAME_COVERAGE_META = TABLES["game_coverages"]
_GAME_COVERAGE_TABLE = f"{_GAME_COVERAGE_META['schema']}.game_coverages"
_GAME_COVERAGE_PK_COLS = _GAME_COVERAGE_META["primary_key"] or []
_GAME_COVERAGE_CONFLICT = ", ".join(quote_col(c) for c in _GAME_COVERAGE_PK_COLS)


def is_game_coverage_current(
    conn: Any,
    league_code: str,
    target: str,
    season: str,
    season_type: str,
    identity_code: str,
    group: Dict[str, Any],
) -> bool:
    """Return True if every col_name in this group has game coverage for the season.

    For league-wide game datasets (like ``leaguegamelog``), coverage is tracked
    at the season level since a single call fetches all games.
    """
    dataset = group.get("dataset", "")
    columns = group.get("columns") or {}
    col_names = list(columns.keys())

    if not col_names:
        return False

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT col_name
              FROM {_GAME_COVERAGE_TABLE}
             WHERE identity = %s
               AND league_code = %s
               AND target   = %s
               AND season   = %s
               AND season_type = %s
               AND dataset  = %s
               AND col_name = ANY(%s)
            """,
            (
                identity_code,
                league_code,
                target,
                season,
                season_type,
                dataset,
                col_names,
            ),
        )
        covered = {row[0] for row in cur.fetchall()}

    return covered == set(col_names)


def upsert_game_coverage(
    conn: Any,
    league_code: str,
    target: str,
    season: str,
    season_type: str,
    identity_code: str,
    ext_game_id: str,
    group: Dict[str, Any],
) -> None:
    """Upsert game-level coverage rows for every col_name in this call group."""
    dataset = group.get("dataset", "")
    columns = group.get("columns") or {}
    col_names = list(columns.keys())

    if not col_names:
        return

    with conn.cursor() as cur:
        for col_name in col_names:
            cur.execute(
                f"""
                INSERT INTO {_GAME_COVERAGE_TABLE} (
                    identity, league_code, ext_game_id, target, season, season_type,
                    dataset, col_name, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT ({_GAME_COVERAGE_CONFLICT})
                DO UPDATE SET updated_at = NOW()
                """,
                (
                    identity_code,
                    league_code,
                    ext_game_id,
                    target,
                    season,
                    season_type,
                    dataset,
                    col_name,
                ),
            )
    conn.commit()


def prune_game_coverages(league_code: str) -> int:
    """Delete game coverage rows for (target, col_name) pairs no longer in config."""
    valid: set[tuple[str, str]] = set()
    for col_name, col_meta in DB_COLUMNS.items():
        for target in _targets_for_column(col_meta):
            valid.add((target, col_name))

    deleted = 0
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT target, col_name FROM {_GAME_COVERAGE_TABLE} WHERE league_code = %s",
                (league_code,),
            )
            to_delete: List[tuple[str, str]] = [
                (row[0], row[1])
                for row in cur.fetchall()
                if (row[0], row[1]) not in valid
            ]

            if not to_delete:
                return 0

            values = ",".join("(%s, %s)" for _ in to_delete)
            flat = [item for pair in to_delete for item in pair]
            cur.execute(
                f"""
                DELETE FROM {_GAME_COVERAGE_TABLE}
                WHERE league_code = %s
                  AND (target, col_name) IN (VALUES """
                + values
                + """)
                """,
                (league_code,) + tuple(flat),
            )
            deleted = cur.rowcount
        conn.commit()

    if deleted:
        logger.info("Pruned %d stale game coverage rows for %s", deleted, league_code)
    return deleted
