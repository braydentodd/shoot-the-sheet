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
from src.core.definitions.tables import TABLES
from src.core.lib.postgres import quote_col


def _group_key(entity: str, group: Dict[str, Any]) -> str:
    """Build a stable identity key for a call-group definition."""
    cols = sorted((group.get('columns') or {}).keys())
    return f"{entity}:{group.get('dataset')}:{group.get('tier')}:{','.join(cols)}"


def compute_backfill_signature(entity: str, groups: Iterable[Dict[str, Any]]) -> str:
    """Hash group identities into a stable signature for tracker comparisons."""
    keys: List[str] = sorted(_group_key(entity, g) for g in groups)
    payload = "\n".join(keys)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def _resolve_league_id(conn: Any, league_key: str) -> int:
    """Resolve league_id for a league_key by looking it up in core.league_profiles."""
    with conn.cursor() as cur:
        cur.execute("SELECT the_glass_id FROM core.league_profiles WHERE league_key = %s", (league_key,))
        row = cur.fetchone()
        if not row:
            raise ValueError(f"League profile with league_key {league_key!r} not found in core.league_profiles")
        return int(row[0])


def is_backfill_coverage_current(
    conn: Any,
    league_key: str,
    entity: str,
    season: str,
    season_type: str,
    source_key: str,
    coverage_signature: str,
) -> bool:
    """Return True when stored coverage signature matches required signature."""
    league_id = _resolve_league_id(conn, league_key)

    meta = TABLES['backfill_tracker']
    schema = meta['schema']  # 'core'
    table = 'backfill_tracker'

    query = f"""
        SELECT coverage_signature
          FROM {schema}.{table}
         WHERE league_id = %s
           AND entity_type = %s
           AND season = %s
           AND season_type = %s
           AND source_key = %s
    """
    with conn.cursor() as cur:
        cur.execute(query, (league_id, entity, season, season_type, source_key))
        row = cur.fetchone()
    return bool(row and row[0] == coverage_signature)


def upsert_backfill_coverage(
    conn: Any,
    league_key: str,
    entity: str,
    season: str,
    season_type: str,
    source_key: str,
    coverage_signature: str,
) -> None:
    """Insert or update backfill tracker state for a completed entity/season."""
    league_id = _resolve_league_id(conn, league_key)

    meta = TABLES['backfill_tracker']
    schema = meta['schema']  # 'core'
    table = 'backfill_tracker'
    pks = meta['primary_key']

    # Build ON CONFLICT clause dynamically from configured primary keys
    conflict_cols = ", ".join(quote_col(col) for col in pks)

    query = f"""
        INSERT INTO {schema}.{table} (
            league_id,
            entity_type,
            season,
            season_type,
            source_key,
            coverage_signature,
            completed_at
        ) VALUES (%s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT ({conflict_cols})
        DO UPDATE
           SET coverage_signature = EXCLUDED.coverage_signature,
               completed_at = NOW()
    """
    with conn.cursor() as cur:
        cur.execute(
            query,
            (league_id, entity, season, season_type, source_key, coverage_signature),
        )
    conn.commit()
