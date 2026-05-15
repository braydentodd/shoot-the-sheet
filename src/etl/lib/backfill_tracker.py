"""
The Glass - Backfill Coverage Tracker

Tracks historical stats backfill completeness by persisting a deterministic
coverage signature for each (entity_type, season, season_type, source_key).

When the required call-group surface changes (for example, a new DB column is
added), the signature changes and the next backfill run reprocesses that
entity/season automatically.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, Iterable, List


def _group_key(entity: str, group: Dict[str, Any]) -> str:
    """Build a stable identity key for a call-group definition."""
    cols = sorted((group.get('columns') or {}).keys())
    return f"{entity}:{group.get('dataset')}:{group.get('tier')}:{','.join(cols)}"


def compute_backfill_signature(entity: str, groups: Iterable[Dict[str, Any]]) -> str:
    """Hash group identities into a stable signature for tracker comparisons."""
    keys: List[str] = sorted(_group_key(entity, g) for g in groups)
    payload = "\n".join(keys)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def is_backfill_coverage_current(
    conn: Any,
    db_schema: str,
    entity: str,
    season: str,
    season_type: str,
    source_key: str,
    coverage_signature: str,
) -> bool:
    """Return True when stored coverage signature matches required signature."""
    query = f"""
        SELECT coverage_signature
          FROM {db_schema}.backfill_tracker
         WHERE entity_type = %s
           AND season = %s
           AND season_type = %s
           AND source_key = %s
    """
    with conn.cursor() as cur:
        cur.execute(query, (entity, season, season_type, source_key))
        row = cur.fetchone()
    return bool(row and row[0] == coverage_signature)


def upsert_backfill_coverage(
    conn: Any,
    db_schema: str,
    entity: str,
    season: str,
    season_type: str,
    source_key: str,
    coverage_signature: str,
) -> None:
    """Insert or update backfill tracker state for a completed entity/season."""
    query = f"""
        INSERT INTO {db_schema}.backfill_tracker (
            entity_type,
            season,
            season_type,
            source_key,
            coverage_signature,
            completed_at
        ) VALUES (%s, %s, %s, %s, %s, NOW())
        ON CONFLICT (entity_type, season, season_type, source_key)
        DO UPDATE
           SET coverage_signature = EXCLUDED.coverage_signature,
               completed_at = NOW()
    """
    with conn.cursor() as cur:
        cur.execute(
            query,
            (entity, season, season_type, source_key, coverage_signature),
        )
    conn.commit()
