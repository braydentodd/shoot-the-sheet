"""
Shoot the Sheet - Stat Coverage Tracker

Tracks which (col_name, dataset) pairs have been fetched for each
(entity, identity, league, season, season_type) tuple.  A coverage
row simply records that the data was pulled — no params comparison
is needed because the dataset's ``source_mapping`` is the single
source of truth for API parameters.

Table: ``core.stat_coverages``
PK:    (identity, league_code, entity, season, season_type, dataset, col_name)
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

_COVERAGE_META = TABLES["stat_coverages"]
_COVERAGE_TABLE = f"{_COVERAGE_META['schema']}.stat_coverages"
_COVERAGE_PK_COLS = _COVERAGE_META["primary_key"]
_COVERAGE_CONFLICT = ", ".join(quote_col(c) for c in _COVERAGE_PK_COLS)


def _entities_for_column(col_meta: Dict[str, Any]) -> set:
    entities: set[str] = set()
    mapping = col_meta.get("dataset_mapping")
    if not mapping:
        return entities
    for league_sources in mapping.values():
        if not isinstance(league_sources, dict):
            continue
        for identity_sources in league_sources.values():
            if not isinstance(identity_sources, dict):
                continue
            entities.update(identity_sources.keys())
    return entities


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_group_coverage_current(
    conn: Any,
    league_key: str,
    entity: str,
    season: str,
    season_type: str,
    identity_key: str,
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
               AND league   = %s
               AND entity   = %s
               AND season   = %s
               AND season_type = %s
               AND dataset  = %s
               AND col_name = ANY(%s)
            """,
            (identity_key, league_key, entity, season, season_type, dataset, col_names),
        )
        covered = {row[0] for row in cur.fetchall()}

    return covered == set(col_names)


def upsert_group_coverage(
    conn: Any,
    league_key: str,
    entity: str,
    season: str,
    season_type: str,
    identity_key: str,
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
                    identity, league_code, entity, season, season_type, dataset, col_name, completed_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT ({_COVERAGE_CONFLICT})
                DO UPDATE SET completed_at = NOW()
                """,
                (
                    identity_key,
                    league_key,
                    entity,
                    season,
                    season_type,
                    dataset,
                    col_name,
                ),
            )
    conn.commit()


def prune_coverages(league_key: str) -> int:
    """Delete coverage rows for (entity, col_name) pairs no longer in config."""
    valid: set[tuple[str, str]] = set()
    for col_name, col_meta in DB_COLUMNS.items():
        for entity in _entities_for_column(col_meta):
            valid.add((entity, col_name))

    deleted = 0
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT entity, col_name FROM {_COVERAGE_TABLE} WHERE league_code = %s",
                (league_key,),
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
                  AND (entity, col_name) IN (VALUES """
                + values
                + """)
                """,
                (league_key,) + tuple(flat),
            )
            deleted = cur.rowcount
        conn.commit()

    if deleted:
        logger.info("Pruned %d stale coverage rows for %s", deleted, league_key)
    return deleted
