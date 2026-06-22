"""
Shoot the Sheet - ETL Orchestrator

Sequences the ordered ETL phases for a single league run.  Knows nothing
about HTTP, argparse, or the destination of stdout -- just which phase
runs when, and which library function each phase calls.

Layering:

    src.etl.cli          (argparse + dispatch)
        |
        v
    src.etl.orchestrator  (this module: phase ordering)
        |
        +--> src.core.lib.ddl              (schema bootstrap)
        +--> src.etl.lib.load               (staging + profile writes)
        +--> src.etl.lib.executor           (one API call group)
        +--> src.etl.lib.cleanup            (post-run hygiene)

Each phase is a thin wrapper around the lib function it drives; orchestration
logic that has no business in lib (e.g. resolving the active source, building
ExecutionContext) lives here.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Tuple, Union

from psycopg2.extras import RealDictCursor

from src.core.definitions.leagues import LEAGUES
from src.core.definitions.schema import SEQUENCES, TABLES
from src.core.lib.leagues_resolver import (
    _league_or_raise,
    get_all_canonical_season_types,
    get_current_season,
    get_regular_season_types,
    get_retained_seasons,
)
from src.core.lib.logging import phase_marker
from src.core.lib.postgres import db_connection, quote_col
from src.core.lib.schema_builder import bootstrap_schema
from src.core.lib.season_resolver import parse_season_end_year
from src.etl.definitions.datasets import DATASETS
from src.etl.definitions.pipeline import (
    PIPELINE_PHASES,
)
from src.etl.definitions.sources import SOURCES
from src.etl.lib.call_groups import build_call_groups
from src.etl.lib.cleanup import (
    prune_entities,
    prune_stats_retention,
)
from src.etl.lib.coverage_tracker import (
    prune_coverages,
)
from src.etl.lib.executor import ExecutionContext, execute_group
from src.etl.lib.load import _resolve_league_id, _table_for_scope
from src.etl.lib.season_detector import detect_active_season_types
from src.etl.lib.source_resolver import get_source_season_type_code
from src.etl.sources.registry import get_source_modules

logger = logging.getLogger(__name__)


# ============================================================================
# DYNAMIC SOURCE LOADING
# ============================================================================


def _load_source(source_key: str):
    """Dynamically import a source's config and client modules."""
    if source_key not in SOURCES:
        raise ValueError(
            f"Unknown source {source_key!r}. Registered: {sorted(SOURCES)}"
        )
    return get_source_modules(source_key)


# ============================================================================
# CORE-AWARE LOOKUPS
# ============================================================================


# ============================================================================
# SHARED EXECUTION ENGINE  (drives src.etl.lib.executor for one phase)
# ============================================================================


def _run_groups(
    scope: str,
    entities: List[str],
    seasons: List[str],
    season_type: str,
    season_type_name: str,
    team_ids: Dict[str, int],
    failed: List[Dict[str, Any]],
    *,
    league_key: str,
    source_key: str,
    api_field_names: dict,
    api_config: dict,
    make_fetcher: Callable,
    groups_override: Union[Dict[Tuple[str, str], List[Dict[str, Any]]], None] = None,
    on_entity_finished: Union[
        Callable[[str, str, List[Dict[str, Any]], int, bool, Any], None], None
    ] = None,
    in_season: bool = True,
) -> int:
    """Execute call groups for a given scope across entities and seasons."""
    total_rows = 0

    for season in seasons:
        for entity in entities:
            if groups_override is not None:
                groups = groups_override.get((entity, season), [])
            else:
                groups = build_call_groups(
                    entity,
                    season,
                    source_key,
                    scope=scope,
                    league_key=league_key,
                    in_season=in_season,
                )
            if not groups:
                continue

            logger.info(
                "%s: %s %s -- %d call groups",
                scope,
                entity,
                season,
                len(groups),
            )

            season_end_year = parse_season_end_year(
                season, LEAGUES[league_key]["season_format"]
            )
            ctx = ExecutionContext(
                entity=entity,
                scope=scope,
                season=season,
                season_type=season_type,
                season_type_name=season_type_name,
                entity_id_field=api_field_names["entity_id"][entity],
                db_schema=league_key,
                source_key=source_key,
                api_fetcher=make_fetcher(
                    league_key,
                    season_end_year,
                    season_type_name,
                    entity,
                    identity_key=source_key,
                ),
                team_ids=team_ids,
                max_consecutive_failures=api_config.get("max_consecutive_failures", 5),
                id_aliases=api_field_names.get("id_aliases", {}),
            )

            entity_rows = 0
            failed_before = len(failed)
            succeeded_groups: List[Dict[str, Any]] = []

            for group in groups:
                try:
                    rows = execute_group(group, ctx, failed)
                    entity_rows += rows
                    succeeded_groups.append(group)
                except Exception as exc:
                    logger.exception(
                        "Group %s failed: %s",
                        group["dataset"],
                        exc,
                    )
                    failed.append(
                        {
                            "dataset": group["dataset"],
                            "error": str(exc),
                        }
                    )

            total_rows += entity_rows
            if on_entity_finished is not None:
                with db_connection() as conn:
                    on_entity_finished(
                        entity,
                        season,
                        succeeded_groups,
                        entity_rows,
                        len(failed) > failed_before,
                        conn,
                    )

    return total_rows


# ============================================================================
# ETL PHASE HANDLERS
# ============================================================================


def _get_role_datasets(role: str) -> Dict[str, List[str]]:
    """Return ``{identity_key: [dataset_name, ...]}`` for a pipeline role."""
    result: Dict[str, List[str]] = {}
    for identity_key, datasets in DATASETS.items():
        for ds_name, ds_def in datasets.items():
            if ds_def.get("role") == role:
                result.setdefault(identity_key, []).append(ds_name)
    return result


def _load_team_ids(league_key: str) -> Dict[str, int]:
    """Return ``{ext_id: int(ext_id)}`` for teams in staging, used by per-team API calls."""
    table = _table_for_scope("team", "staging")
    with db_connection() as conn:
        league_val = _resolve_league_id(conn, league_key)
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT ext_id FROM {table} WHERE league_code = %s",
                (league_val,),
            )
            return {r[0]: int(r[0]) for r in cur.fetchall() if r[0] is not None}


# ---------------------------------------------------------------------------
# season_detector
# ---------------------------------------------------------------------------


def _season_detector(
    league_key: str,
    season: str,
) -> List[str]:
    """Detect active season types. Called once per league, before identity loop."""
    role_datasets = _get_role_datasets("season_detector")
    # Build id-prefixed refs: identity.dataset_name
    dataset_refs = [
        f"{identity_key}.{ds_name}"
        for identity_key, ds_names in role_datasets.items()
        for ds_name in ds_names
    ]
    if not dataset_refs:
        return get_all_canonical_season_types(league_key)
    return detect_active_season_types(league_key, dataset_refs, season)


# ---------------------------------------------------------------------------
# team_discoverer / player_discoverer
# ---------------------------------------------------------------------------


def _discover_entities(
    league_key: str,
    season: str,
    role: str,
    identity_key: str,
    source_key: str,
    season_type: str,
    season_type_name: str,
    failed: List[Dict[str, Any]],
    team_ids: Dict[str, int] = None,
) -> int:
    """Generic entity discovery handler. Calls datasets assigned to *role*."""
    if team_ids is None:
        team_ids = {}
    total_rows = 0
    dataset_names = _get_role_datasets(role).get(identity_key, [])
    if not dataset_names:
        return 0

    config_mod, client_mod = _load_source(source_key)
    entities = ["player"] if role == "player_discoverer" else ["team"]

    for dataset_name in dataset_names:
        logger.info(
            phase_marker(
                role, f"dataset={identity_key}.{dataset_name} source={source_key}"
            )
        )
        # Both discoverers extract profile columns and roster relationships.
        scopes = ["profiles"]
        if role == "player_discoverer":
            scopes.append("rosters")
        for scope in scopes:
            total_rows += _run_groups(
                scope=scope,
                entities=entities,
                seasons=[season],
                season_type=season_type,
                season_type_name=season_type_name,
                team_ids=team_ids,
                failed=failed,
                league_key=league_key,
                source_key=identity_key,
                api_field_names=config_mod.API_FIELD_NAMES
                if hasattr(config_mod, "API_FIELD_NAMES")
                else {},
                api_config=config_mod.API_CONFIG
                if hasattr(config_mod, "API_CONFIG")
                else {},
                make_fetcher=client_mod.make_fetcher,
                in_season=True,
            )
    return total_rows


# ---------------------------------------------------------------------------
# stats_maintainer
# ---------------------------------------------------------------------------


def _maintain_stats(
    league_key: str,
    season_range: List[str],
    season: str,
    identity_key: str,
    source_key: str,
    failed: List[Dict[str, Any]],
    in_season: bool = True,
) -> int:
    """Backfill + maintain stats datasets across all season types.

    Coverage tracking gates re-fetching for past seasons.  The current
    season is always refreshed when ``in_season`` is True (games may have
    been played since the last run).  When off-season the current season
    is also coverage-gated since no new data is expected.

    Call groups are partitioned by source so that datasets from different
    sources (e.g. ``nba_api`` and ``pbp_stats`` within the same identity)
    each use their own API fetcher.
    """
    from src.core.lib.leagues_resolver import (
        get_all_canonical_season_types,
        get_season_type_def,
    )
    from src.etl.lib.coverage_tracker import (
        is_group_coverage_current,
        upsert_group_coverage,
    )

    total_rows = 0
    dataset_names = _get_role_datasets("stats_maintainer").get(identity_key, [])
    if not dataset_names:
        return 0

    team_ids = _load_team_ids(league_key)
    is_current = season
    all_season_types = get_all_canonical_season_types(league_key)

    for season_label in season_range:
        for st_key in all_season_types:
            from src.core.lib.leagues_resolver import is_season_type_valid_for

            if not is_season_type_valid_for(league_key, st_key, season_label):
                continue

            st_def = get_season_type_def(league_key, st_key)
            season_type_name = get_source_season_type_code(
                source_key, league_key, st_key
            )

            for entity in ["team", "team_opp", "player", "player_opp", "player_on"]:
                groups = build_call_groups(
                    entity,
                    season_label,
                    identity_key,
                    scope="stats",
                    league_key=league_key,
                    in_season=in_season,
                )
                if not groups:
                    continue

                # Filter out already-covered groups — skip for backfill/always.
                season_is_current = season_label == is_current
                skip_coverage = any(
                    DATASETS.get(identity_key, {}).get(g["dataset"], {}).get("coverage")
                    in ("all_years", "current")
                    for g in groups
                )
                if season_is_current and in_season or skip_coverage:
                    filtered_groups = groups
                else:
                    with db_connection() as conn:
                        filtered_groups = [
                            g
                            for g in groups
                            if not is_group_coverage_current(
                                conn,
                                league_key,
                                entity,
                                season_label,
                                st_key,
                                identity_key,
                                g,
                            )
                        ]

                if not filtered_groups:
                    logger.info(
                        "stats_maintainer: %s/%s/%s — all groups covered, skipping",
                        entity,
                        season_label,
                        identity_key,
                    )
                    continue

                # Partition call groups by their dataset's source so that
                # each source uses its own fetcher (e.g. nba_api vs pbp_stats).
                groups_by_source: Dict[str, List[Dict[str, Any]]] = {}
                for g in filtered_groups:
                    ds_cfg = DATASETS.get(identity_key, {}).get(g["dataset"], {})
                    src = ds_cfg.get("source", source_key)
                    groups_by_source.setdefault(src, []).append(g)

                logger.info(
                    phase_marker(
                        "stats_maintainer",
                        f"entity={entity} season={season_label} "
                        f"season_type={st_key} "
                        f"sources={sorted(groups_by_source.keys())} "
                        f"groups={len(filtered_groups)}",
                    )
                )

                for src_key, src_groups in groups_by_source.items():
                    config_mod, client_mod = _load_source(src_key)

                    # Coverage upsert callback: mark each succeeded group as covered.
                    def _on_coverage(
                        entity,
                        season_label,
                        succeeded_groups,
                        _rows,
                        _had_failures,
                        conn,
                        _league_key=league_key,
                        _season_type=st_key,
                        _source_key=identity_key,
                    ):
                        for g in succeeded_groups:
                            upsert_group_coverage(
                                conn,
                                _league_key,
                                entity,
                                season_label,
                                _season_type,
                                _source_key,
                                g,
                            )

                    total_rows += _run_groups(
                        scope="stats",
                        entities=[entity],
                        seasons=[season_label],
                        season_type=st_key,
                        season_type_name=season_type_name,
                        team_ids=team_ids
                        if entity in ("player", "player_opp", "player_on")
                        else {},
                        failed=failed,
                        league_key=league_key,
                        source_key=identity_key,
                        api_field_names=config_mod.API_FIELD_NAMES
                        if hasattr(config_mod, "API_FIELD_NAMES")
                        else {},
                        api_config=config_mod.API_CONFIG
                        if hasattr(config_mod, "API_CONFIG")
                        else {},
                        make_fetcher=client_mod.make_fetcher,
                        in_season=in_season,
                        groups_override={(entity, season_label): src_groups},
                        on_entity_finished=_on_coverage,
                    )

    return total_rows


# ---------------------------------------------------------------------------
# profile_maintainer
# ---------------------------------------------------------------------------


def _maintain_profiles(
    league_key: str,
    season: str,
    identity_key: str,
    source_key: str,
    season_type: str,
    season_type_name: str,
    failed: List[Dict[str, Any]],
    team_ids: Dict[str, int] = None,
) -> int:
    """Update profile fields for entities already in staging."""
    if team_ids is None:
        team_ids = {}
    total_rows = 0
    dataset_names = _get_role_datasets("profile_maintainer").get(identity_key, [])
    if not dataset_names:
        return 0

    config_mod, client_mod = _load_source(source_key)

    for dataset_name in dataset_names:
        for entity in ["team", "player"]:
            logger.info(
                phase_marker(
                    "profile_maintainer",
                    f"dataset={identity_key}.{dataset_name} entity={entity}",
                )
            )
            total_rows += _run_groups(
                scope="profiles",
                entities=[entity],
                seasons=[season],
                season_type=season_type,
                season_type_name=season_type_name,
                team_ids=team_ids,
                failed=failed,
                league_key=league_key,
                source_key=identity_key,
                api_field_names=config_mod.API_FIELD_NAMES
                if hasattr(config_mod, "API_FIELD_NAMES")
                else {},
                api_config=config_mod.API_CONFIG
                if hasattr(config_mod, "API_CONFIG")
                else {},
                make_fetcher=client_mod.make_fetcher,
                in_season=True,
            )

    return total_rows


# ============================================================================
# ENTITY MATCHING & UPSERT
# ---------------------------------------------------------------------------
# match_entities / upsert_entities (stubs — user handles matching logic)
# ---------------------------------------------------------------------------


def _match_entities(
    league_key: str,
    failed: List[Dict[str, Any]],
) -> int:
    """Resolve staged identities to existing sts_ids.

    For each staging row, look up (identity, entity) in
    ``identities_entities``.  If found, set ``matched_sts_id``.  If not
    found, leave NULL for manual review.

    This runs every ETL, so newly reviewed entities get matched on the
    next pass.
    """
    logger.info(phase_marker("match_entities"))
    total_matched = 0

    # Derive the identities_entities table from the schema registry.
    ie_meta = TABLES["identities_entities"]
    identities_table = f"{ie_meta['schema']}.identities_entities"

    staging_entities = [
        ("player", _table_for_scope("player", "staging")),
        ("team", _table_for_scope("team", "staging")),
    ]

    with db_connection() as conn:
        with conn.cursor() as cur:
            for entity, staging_table in staging_entities:
                sql = f"""
                    UPDATE {staging_table} s
                       SET matched_sts_id = ie.entity_id
                      FROM {identities_table} ie
                     WHERE s.identity = ie.identity AND s.ext_id = ie.ext_id
                       AND ie.entity = %s
                       AND s.matched_sts_id IS NULL
                """
                cur.execute(sql, (entity,))
                matched = cur.rowcount
                total_matched += matched
                if matched:
                    logger.info(
                        "Matched %d staged %ss to existing sts_ids", matched, entity
                    )
        conn.commit()

    return total_matched


def _upsert_entities(
    league_key: str,
    failed: List[Dict[str, Any]],
) -> int:
    """Promote staged rows to core tables.

    On cold start (no ``identities_entities`` entries for this league),
    all staged entities with a ``name`` are auto-promoted.  On subsequent
    runs, only rows with ``matched_sts_id IS NOT NULL`` or ``reviewed = True``
    are promoted.  Unmatched / unreviewed rows remain for manual review.
    """
    logger.info(phase_marker("upsert_entities"))
    total_promoted = 0

    # Derive the identities_entities table reference from the schema registry.
    ie_meta = TABLES["identities_entities"]
    identities_table = f"{ie_meta['schema']}.identities_entities"
    # Core roster tables used during promotion.
    teams_players_table = _table_for_scope("player", "rosters")
    countries_players_table = _table_for_scope("country", "rosters")
    leagues_teams_table = _table_for_scope("team", "rosters")

    with db_connection() as conn:
        for entity in ["team", "player"]:
            staging_table = _table_for_scope(entity, "staging")
            core_table = _table_for_scope(entity, "profiles")

            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    f"""
                    SELECT *
                      FROM {staging_table}
                     WHERE (matched_sts_id IS NOT NULL OR reviewed = True)
                       AND league_code = %s
                    """,
                    (league_key,),
                )
                promotable = list(cur.fetchall())

            if not promotable:
                continue

            # Separate: rows with matched_sts_id (existing entity) vs
            # new entities (cold start or reviewed)
            existing = []
            new_entities = []
            for row_data in promotable:
                if row_data.get("matched_sts_id"):
                    existing.append(row_data)
                else:
                    new_entities.append(row_data)

            # Create new sts_ids for new entities
            if new_entities:
                with conn.cursor() as cur:
                    sts_seq = next(
                        k for k, v in SEQUENCES.items() if v["schema"] == "profiles"
                    )
                    for row_data in new_entities:
                        cur.execute(f"SELECT nextval('{sts_seq}')")
                        new_id = cur.fetchone()[0]
                        row_data["matched_sts_id"] = new_id
                        # Register identity mapping
                        cur.execute(
                            f"""
                            INSERT INTO {identities_table}
                                (identity, code, entity, entity_id)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (identity, code, entity) DO UPDATE
                                SET entity_id = EXCLUDED.entity_id
                            """,
                            (
                                row_data["identity"],
                                row_data["ext_id"],
                                entity,
                                new_id,
                            ),
                        )
                        existing.append(row_data)
                conn.commit()

            # Upsert to core table
            promoted_ids = []
            # Derive column list from db_columns — only columns that
            # belong to the core table AND are not system columns
            from src.core.definitions.db_columns import DB_COLUMNS as _COLS

            profile_cols = {
                col_name: col_def
                for col_name, col_def in _COLS.items()
                if entity in (col_def.get("tables") or [])
                and col_def.get("dataset_mapping") is not None
            }

            for row_data in existing:
                sts_id = row_data["matched_sts_id"]

                # Collect only profile columns that have values
                cols = {
                    k: v
                    for k, v in row_data.items()
                    if k in profile_cols and v is not None
                }
                if cols:
                    set_clause = ", ".join(
                        f"{quote_col(k)} = COALESCE(%s, {quote_col(k)})" for k in cols
                    )
                    values = list(cols.values()) + [sts_id]
                    with conn.cursor() as cur:
                        cur.execute(
                            f"""
                            UPDATE {core_table}
                               SET {set_clause}, updated_at = NOW()
                             WHERE sts_id = %s
                            """,
                            values,
                        )
                        if cur.rowcount:
                            promoted_ids.append(sts_id)

            # Roster relationships for players
            if entity == "player" and promoted_ids:
                with conn.cursor() as cur:
                    for row_data in existing:
                        sts_id = row_data.get("matched_sts_id")
                        if sts_id not in promoted_ids:
                            continue
                        ext_team_id = row_data.get("ext_team_id")
                        if ext_team_id:
                            cur.execute(
                                f"""
                                SELECT entity_id
                                  FROM {identities_table}
                                 WHERE code = %s
                                   AND entity = 'team'
                                """,
                                (ext_team_id,),
                            )
                            team_row = cur.fetchone()
                            if team_row:
                                cur.execute(
                                    f"""
                                    INSERT INTO {teams_players_table}
                                        (league_code, team_id, player_id)
                                    VALUES (%s, %s, %s)
                                    ON CONFLICT (league_code, team_id, player_id)
                                    DO NOTHING
                                    """,
                                    (league_key, team_row[0], sts_id),
                                )
                        # Country resolution: read from countries_players_staging
                        # where country_code was written during player discovery.
                        cp_staging = _table_for_scope("country", "rosters_staging")
                        cur.execute(
                            f"""
                            SELECT country_code
                              FROM {cp_staging}
                             WHERE ext_player_id = %s
                            """,
                            (row_data["ext_id"],),
                        )
                        for (country_code,) in cur.fetchall():
                            if country_code:
                                cur.execute(
                                    f"""
                                    INSERT INTO {countries_players_table}
                                        (country_code, player_id)
                                    VALUES (%s, %s)
                                    ON CONFLICT (country_code, player_id)
                                    DO NOTHING
                                    """,
                                    (country_code, sts_id),
                                )

            # League-team relationships for teams
            if entity == "team" and promoted_ids:
                with conn.cursor() as cur:
                    for sts_id in promoted_ids:
                        cur.execute(
                            f"""
                            INSERT INTO {leagues_teams_table}
                                (league, team_id)
                            VALUES (%s, %s)
                            ON CONFLICT (league, team_id) DO NOTHING
                            """,
                            (league_key, sts_id),
                        )

            # Delete promoted rows from staging
            if promoted_ids:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        DELETE FROM {staging_table}
                         WHERE matched_sts_id = ANY(%s)
                        """,
                        (promoted_ids,),
                    )
                deleted = cur.rowcount
                total_promoted += deleted
                logger.info(
                    "Promoted %d %ss to core, deleted from staging", deleted, entity
                )

        conn.commit()

    return total_promoted


# ============================================================================
# PUBLIC ENTRY
# ============================================================================


def run_etl(
    league_key: Union[str, None] = None,
) -> None:
    """Run all ETL phase clusters for a league or all leagues.

    Args:
        league_key:  Registered league key (e.g. ``'nba'``). If None,
                     runs all leagues in sorted order.

    Caller (the CLI) is expected to have already configured logging and run
    config validation; this function never touches stdout directly.
    """
    clusters = ["execution_start", "per_identity", "execution_end"]

    # Multi-league execution
    if not league_key:
        leagues_to_run = list(LEAGUES)

        for cluster in clusters:
            handlers = PIPELINE_PHASES.get(cluster, [])
            if not handlers:
                continue

            logger.info("=" * 80)
            logger.info("Phase cluster: %s", cluster)
            logger.info("=" * 80)

            for lkey in leagues_to_run:
                try:
                    _run_league_phases(lkey, handlers, cluster, season_range=None)
                except KeyboardInterrupt:
                    logger.warning("Interrupted by user.")
                    raise
                except Exception as exc:
                    logger.exception(
                        "ETL run failed for league %s in cluster %s.", lkey, cluster
                    )
        return

    if league_key not in LEAGUES:
        raise ValueError(
            f"Unknown league {league_key!r}. Registered: {sorted(LEAGUES)}"
        )

    # Single-league path
    for cluster in clusters:
        handlers = PIPELINE_PHASES.get(cluster, [])
        if not handlers:
            continue
        _run_league_phases(league_key, handlers, cluster)


def _run_league_phases(
    league_key: str,
    handlers: List[str],
    phase: str,
    season_range: Union[List[str], None] = None,
) -> int:
    """Run per-league handlers for a single league. Returns total rows written."""
    _league_or_raise(league_key)
    season = get_current_season(league_key)
    if season_range is None:
        season_range = get_retained_seasons(league_key, season)

    logger.info(
        "ETL starting: league=%s phase=%s season=%s",
        league_key,
        phase,
        season,
    )

    failed: List[Dict[str, Any]] = []
    total_rows = 0
    in_season = False
    active_types: List[str] = []

    for handler in handlers:
        if handler == "build_schema":
            logger.info(phase_marker("build_schema"))
            with db_connection() as conn:
                bootstrap_schema(league_key, conn=conn)

        elif handler == "season_detector":
            logger.info(phase_marker("season_detector"))
            active_types = _season_detector(league_key, season)
            in_season = bool(active_types)
            logger.info(
                "Season detector result: active=%s in_season=%s",
                active_types,
                in_season,
            )

        elif handler in ("team_discoverer", "player_discoverer"):
            logger.info(phase_marker(handler))
            team_ids = (
                _load_team_ids(league_key) if handler == "player_discoverer" else {}
            )

            for identity_key in DATASETS:
                role_datasets = _get_role_datasets(handler).get(identity_key, [])
                if not role_datasets:
                    continue
                source_key = DATASETS[identity_key][role_datasets[0]]["source"]
                if league_key not in SOURCES[source_key].get("leagues", {}):
                    continue
                logger.info(
                    "  identity=%s source=%s datasets=%s",
                    identity_key,
                    source_key,
                    role_datasets,
                )
                reg_st = get_regular_season_types(league_key)[0]
                reg_code = get_source_season_type_code(source_key, league_key, reg_st)
                total_rows += _discover_entities(
                    league_key,
                    season,
                    handler,
                    identity_key,
                    source_key,
                    reg_st,
                    reg_code,
                    failed,
                    team_ids=team_ids,
                )

        elif handler == "stats_maintainer":
            logger.info(phase_marker("stats_maintainer", f"in_season={in_season}"))

            for identity_key in DATASETS:
                role_datasets = _get_role_datasets(handler).get(identity_key, [])
                if not role_datasets:
                    continue
                source_key = DATASETS[identity_key][role_datasets[0]]["source"]
                if league_key not in SOURCES[source_key].get("leagues", {}):
                    continue
                total_rows += _maintain_stats(
                    league_key,
                    season_range,
                    season,
                    identity_key,
                    source_key,
                    failed,
                    in_season=in_season,
                )

        elif handler == "profile_maintainer":
            logger.info(phase_marker("profile_maintainer"))

            for identity_key in DATASETS:
                role_datasets = _get_role_datasets(handler).get(identity_key, [])
                if not role_datasets:
                    continue
                source_key = DATASETS[identity_key][role_datasets[0]]["source"]
                if league_key not in SOURCES[source_key].get("leagues", {}):
                    continue
                team_ids = _load_team_ids(league_key)
                reg_st = get_regular_season_types(league_key)[0]
                reg_code = get_source_season_type_code(source_key, league_key, reg_st)
                total_rows += _maintain_profiles(
                    league_key,
                    season,
                    identity_key,
                    source_key,
                    reg_st,
                    reg_code,
                    failed,
                    team_ids=team_ids,
                )

        elif handler == "match_entities":
            total_rows += _match_entities(league_key, failed)

        elif handler == "upsert_entities":
            total_rows += _upsert_entities(league_key, failed)

        elif handler == "prune_stats_retention":
            logger.info(phase_marker(handler))
            total_rows += prune_stats_retention(league_key, season)

        elif handler == "prune_entities":
            logger.info(phase_marker(handler))
            result = prune_entities()
            total_rows += result.get("players", 0) + result.get("teams", 0)

        elif handler == "prune_coverages":
            logger.info(phase_marker(handler))
            total_rows += prune_coverages(league_key)

        else:
            raise ValueError(
                f"Unknown ETL stage handler {handler!r} for league {league_key!r}"
            )

    logger.info("ETL complete: %d total rows written/pruned", total_rows)

    if failed:
        logger.warning("%d failures:", len(failed))
        for f in failed:
            logger.warning("  %s", f)
