"""
Shoot the Sheet - Coverage Tracker

Single ``coverage`` table tracks fetch state for every dataset, season,
type, target, and column combination.  ``coverage_level`` distinguishes
season-level vs game-level granularity.

Table: ``core.coverage``
PK:    (identity, league_code, coverage_level, game_id, target, season,
       season_type, dataset, col_name)
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

_COVERAGE_META = get_table("core.coverage")
_COVERAGE_SCHEMA = "core"
_COVERAGE_TABLE = f"{_COVERAGE_SCHEMA}.coverage"
_COVERAGE_PK_COLS = _COVERAGE_META.get("primary_key") or []
_COVERAGE_CONFLICT = ", ".join(quote_col(c) for c in _COVERAGE_PK_COLS)

# Sentinel game_id for season-level coverage (all games in season).
_SEASON_GAME_ID = "0"


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

    game_filter = "AND game_id = %s" if game_id else ""
    params: list = [
        identity_code,
        league_code,
        coverage_level,
        target,
        season,
        season_type,
        dataset,
        col_names,
    ]
    if game_id:
        params.insert(7, game_id)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT col_name
              FROM {_COVERAGE_TABLE}
             WHERE identity = %s
               AND league_code = %s
               AND coverage_level = %s
               AND target   = %s
               AND season   = %s
               AND season_type = %s
               AND dataset  = %s
               {game_filter}
               AND covered  = true
               AND col_name = ANY(%s)
            """,
            params,
        )
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
    game_id: str = _SEASON_GAME_ID,
) -> None:
    """Upsert coverage rows for every col_name in this call group."""
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
                    identity, league_code, coverage_level, game_id,
                    target, season, season_type, dataset, col_name,
                    updated_at, covered
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), true)
                ON CONFLICT ({_COVERAGE_CONFLICT})
                DO UPDATE SET updated_at = NOW(), covered = true
                """,
                (
                    identity_code,
                    league_code,
                    coverage_level,
                    game_id,
                    target,
                    season,
                    season_type,
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

    inserted = 0
    all_types = get_all_canonical_season_types(league_code)

    with db_connection() as conn:
        with conn.cursor() as cur:
            for season in seasons:
                for st_key in all_types:
                    # Discover games for game-level coverage
                    game_ids: List[str] = [str(_SEASON_GAME_ID)]
                    if coverage_level == "game":
                        cur.execute(
                            """SELECT game_id FROM core.games
                                    WHERE league_code = %s AND season = %s
                                      AND season_type = %s""",
                            (league_code, season, st_key),
                        )
                        game_ids = [str(row[0]) for row in cur.fetchall()]
                        if not game_ids:
                            continue

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

                                        for game_id in game_ids:
                                            cur.execute(
                                                f"""
                                                INSERT INTO {_COVERAGE_TABLE} (
                                                    identity, league_code,
                                                    coverage_level, game_id,
                                                    target, season, season_type,
                                                    dataset, col_name, covered
                                                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,false)
                                                ON CONFLICT ({_COVERAGE_CONFLICT}) DO NOTHING
                                                """,
                                                (
                                                    identity_code,
                                                    league_code,
                                                    coverage_level,
                                                    game_id,
                                                    target,
                                                    season,
                                                    st_key,
                                                    ds_name,
                                                    col_name,
                                                ),
                                            )
                                            inserted += cur.rowcount
            conn.commit()

    return inserted


# ============================================================================
# Prune
# ============================================================================


def prune_coverage(league_code: str) -> int:
    """Delete coverage rows that are no longer valid.

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
                f"FROM {_COVERAGE_TABLE} WHERE league_code = %s",
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
                    DELETE FROM {_COVERAGE_TABLE}
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
        logger.info("Pruned %d stale coverage rows for %s", deleted, league_code)
    return deleted
