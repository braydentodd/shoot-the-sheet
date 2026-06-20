"""
Shoot the Sheet - Coverage Tracker

Tracks stats coverage completeness by persisting per-field params
for each (entity, season, season_type, source, dataset, field)
in ``ops.coverages``.

When params for a field change (e.g. API parameter tweak), the mismatch
is detected and the ETL re-fetches that field automatically.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Tuple

from src.core.definitions.db_columns import DB_COLUMNS
from src.core.definitions.schema import TABLES
from src.core.lib.postgres import db_connection, quote_col

logger = logging.getLogger(__name__)


def _entities_for_column(col_meta: Dict[str, Any]) -> set:
    """Return all entity keys present anywhere in the column's dataset_mapping.

    Format: ``{league: {identity: {entity: [DatasetMapping, ...]}}}``
    """
    entities = set()
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


def _serialize_params(params: Dict[str, Any]) -> str:
    """Serialize params dict to a canonical string for comparison."""
    return json.dumps(params, sort_keys=True, separators=(",", ":"))


def is_group_coverage_current(
    conn: Any,
    league_key: str,
    entity: str,
    season: str,
    season_type: str,
    source_key: str,
    group: Dict[str, Any],
) -> bool:
    """Return True if every field in this group has current coverage."""
    dataset = group.get("dataset", "")
    params_str = _serialize_params(group.get("params", {}))
    fields = list((group.get("columns") or {}).keys())

    if not fields:
        return False

    meta = TABLES["coverages"]
    schema = meta["schema"]
    table = "coverages"

    query = f"""
        SELECT field, source_params
          FROM {schema}.{table}
         WHERE league_code = %s
           AND entity = %s
           AND season = %s
           AND season_type = %s
           AND identity = %s
           AND dataset = %s
           AND field = ANY(%s)
    """
    with conn.cursor() as cur:
        cur.execute(
            query,
            (league_key, entity, season, season_type, source_key, dataset, fields),
        )
        stored = {row[0]: row[1] for row in cur.fetchall()}

    if len(stored) != len(fields):
        return False
    return all(stored.get(f) == params_str for f in fields)


def upsert_group_coverage(
    conn: Any,
    league_key: str,
    entity: str,
    season: str,
    season_type: str,
    source_key: str,
    group: Dict[str, Any],
) -> None:
    """Upsert coverage rows for every field produced by this call group."""
    dataset = group.get("dataset", "")
    params_str = _serialize_params(group.get("params", {}))
    fields = list((group.get("columns") or {}).keys())

    if not fields:
        return

    meta = TABLES["coverages"]
    schema = meta["schema"]
    table = "coverages"
    pks = meta["primary_key"]
    conflict_cols = ", ".join(quote_col(col) for col in pks)

    query = f"""
        INSERT INTO {schema}.{table} (
            league_code, entity, season, season_type,
            identity, source_params, col_name, dataset, dataset_params, field, completed_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT ({conflict_cols})
        DO UPDATE
           SET source_params = EXCLUDED.source_params,
               completed_at = NOW()
    """
    with conn.cursor() as cur:
        for field in fields:
            cur.execute(
                query,
                (
                    league_key,
                    entity,
                    season,
                    season_type,
                    source_key,
                    params_str,
                    field,
                    dataset,
                    params_str,
                    field,
                ),
            )
    conn.commit()


def prune_coverages(league_key: str) -> int:
    """Delete coverage rows for fields/entities no longer present in config.

    Returns the number of rows deleted.
    """
    valid: set[tuple[str, str]] = set()
    for col_name, col_meta in DB_COLUMNS.items():
        for entity in _entities_for_column(col_meta):
            valid.add((entity, col_name))

    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT entity, field FROM ops.coverages WHERE league_code = %s",
                (league_key,),
            )
            to_delete: List[Tuple[str, str]] = [
                (row[0], row[1])
                for row in cur.fetchall()
                if (row[0], row[1]) not in valid
            ]

            if not to_delete:
                return 0

            values = ",".join("(%s, %s)" for _ in to_delete)
            flat = [item for pair in to_delete for item in pair]
            cur.execute(
                """
                DELETE FROM ops.coverages
                WHERE league_code = %s
                  AND (entity, field) IN (VALUES """
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
