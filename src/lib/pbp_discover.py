"""
Shoot the Sheet - PBP Discovery

Discovers every unique event shape from a PBP source and populates
``core.pbp_events`` with ``handling='unreviewed'`` entries for human review.

Run via::

    python -m src.cli discover-pbp nba_id.pbp_stats
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def discover(
    conn,
    identity_code: str,
    dataset_name: str,
    *,
    season: str | None = None,
    game_id: str | None = None,
) -> dict[str, Any]:
    """Discover event shapes and populate ``core.pbp_events``."""
    client_module = _resolve_source(identity_code, dataset_name)

    from src.lib.pbp_classifier import (
        build_nba_event_key,
        build_nba_signature,
        _to_int as _ctoi,
    )

    def _desc(row: dict) -> str:
        parts = [
            str(row.get("HOMEDESCRIPTION", "")),
            str(row.get("NEUTRALDESCRIPTION", "")),
            str(row.get("VISITORDESCRIPTION", "")),
        ]
        return " ".join(p for p in parts if p)

    build_signature = build_nba_signature
    build_event_key = build_nba_event_key

    games = _load_games(conn, identity_code, dataset_name, season, game_id)
    if not games:
        logger.info("No games found: identity=%s dataset=%s", identity_code, dataset_name)
        return {"games_processed": 0, "total_events": 0,
                "new_entries": 0, "updated_entries": 0, "classified_pct": 0}

    new_entries = 0
    updated_entries = 0
    total_events = 0

    for ext_game_id, game_season in games:
        raw_rows = client_module.fetch_raw_rows(ext_game_id, game_season)
        if not raw_rows:
            continue
        total_events += len(raw_rows)
        for row in raw_rows:
            event_key = build_event_key(build_signature(row))
            if _upsert_event(conn, identity_code, dataset_name, event_key) == "inserted":
                new_entries += 1
            else:
                updated_entries += 1

    classified = _count_classified(conn, identity_code, dataset_name)
    total_catalog = classified + _count_unreviewed(conn, identity_code, dataset_name)
    classified_pct = (classified / total_catalog * 100) if total_catalog else 0

    return {
        "games_processed": len(games),
        "total_events": total_events,
        "new_entries": new_entries,
        "updated_entries": updated_entries,
        "classified_pct": round(classified_pct, 1),
        "catalog_size": total_catalog,
    }


def _resolve_source(identity_code: str, dataset_name: str):
    from src.definitions.datasets import DATASETS
    from src.sources.registry import get_source_modules
    ds_cfg = DATASETS.get(identity_code, {}).get(dataset_name)
    if not ds_cfg:
        raise ValueError(f"Dataset not found: {identity_code}.{dataset_name}")
    source_name = ds_cfg.get("source")
    if not source_name:
        raise ValueError(f"No source for {identity_code}.{dataset_name}")
    _config_mod, client_mod = get_source_modules(source_name)
    if not hasattr(client_mod, "fetch_raw_rows"):
        raise RuntimeError(f"Source {source_name!r} missing fetch_raw_rows()")
    return client_mod




def _load_games(conn, identity_code, dataset_name, season, game_id):
    from src.definitions.datasets import DATASETS
    if game_id:
        if not season:
            raise ValueError("--game-id requires --season")
        return [(game_id, season)]
    ds_cfg = DATASETS.get(identity_code, {}).get(dataset_name, {})
    min_s, max_s = ds_cfg.get("min_season"), ds_cfg.get("max_season")
    query = "SELECT g.ext_id, g.season FROM staging.games g WHERE g.identity = %s"
    params: list[Any] = [identity_code]
    if season:
        query += " AND g.season = %s"; params.append(season)
    elif min_s and max_s:
        query += " AND g.season >= %s AND g.season <= %s"; params.extend([min_s, max_s])
    elif min_s:
        query += " AND g.season >= %s"; params.append(min_s)
    elif max_s:
        query += " AND g.season <= %s"; params.append(max_s)
    query += " ORDER BY g.season, g.ext_id"
    with conn.cursor() as cur:
        cur.execute(query, params)
        return [(r[0], r[1]) for r in cur.fetchall()]


def _upsert_event(conn, identity_code, dataset_name, event_key):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.pbp_events (identity, dataset, event_key, handling) "
            "VALUES (%s, %s, %s, 'unreviewed') "
            "ON CONFLICT (identity, dataset, event_key) DO NOTHING",
            (identity_code, dataset_name, event_key),
        )
        if cur.rowcount:
            conn.commit()
            return "inserted"
    return "unchanged"


def _count_classified(conn, identity_code, dataset_name):
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM core.pbp_events "
                     "WHERE identity = %s AND dataset = %s AND handling != 'unreviewed'",
                     (identity_code, dataset_name))
        return cur.fetchone()[0]


def _count_unreviewed(conn, identity_code, dataset_name):
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM core.pbp_events "
                     "WHERE identity = %s AND dataset = %s AND handling = 'unreviewed'",
                     (identity_code, dataset_name))
        return cur.fetchone()[0]


def _to_int(val: Any) -> int:
    if val is None or val == "":
        return 0
    try:
        return int(val)
    except (ValueError, TypeError):
        return 0
