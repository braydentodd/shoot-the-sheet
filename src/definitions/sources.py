"""Shoot the Sheet - Source Registry

Declarative registry of every external data source.

``leagues`` maps league keys to source-specific metadata:
    - ``id``: the source's identifier for this league (e.g. ``"00"`` for NBA)
    - ``season_types``: canonical key -> parameter value the source expects
      for the season_type API parameter (e.g. ``"play_in"`` -> ``"PlayIn"``).

Season parameter format is declared per-dataset in
:data:`src.definitions.datasets.SourceMapping.season_param_format`.

All other source-specific operational settings (rate limits, API parameters,
field name mappings) live in each source's own config module under
``src/etl/sources/<source>/config.py``.

Helpers that resolve source assignments per league/entity live in
:mod:`src.lib.source_resolver`.


Source Contracts
================

Every source registers a ``(config, client)`` module pair in
``src.sources.registry.SOURCE_MODULES``.  The client module must
expose methods matching its dispatch type.

Box-score sources (API-based, per-season iteration)
---------------------------------------------------
Dispatched via ``_run_groups`` -> ``make_fetcher``.

Required:
    make_fetcher(league_code, season_end_year, season_type_name,
                 identity_code) -> Callable

        The returned callable accepts ``(dataset, extra_params)`` and
        returns a raw API result dict (with ``resultSets``).  Rate
        limiting and retry are handled inside the fetcher.

Optional:
    detect_recent_games(dataset_name, league_code, season,
                        season_type_name, lookback_days, identity_code)
        -> Union[Dict, None]

        Only needed if this source participates in season activity
        detection.  Register in ``season_detector._SEASON_DETECTORS``.

PBP sources (file-based, per-game iteration)
---------------------------------------------
Dispatched via ``_maintain_pbp`` -> ``fetch_game_pbp``.

Required:
    fetch_game_pbp(game_id, season, home_team_id, away_team_id,
                   identity) -> List[PBPEvent]

        Returns normalized PBP events for a single game.

    cleanup_season_files(season) -> int
        Only required when ``local_files=True`` in the source registry.
        Deletes all local files for the given season.

All sources
-----------

The config module should expose:
    API_CONFIG: dict (optional)
        Rate limit and timeout settings.  Used by ``_execute_stats_groups``
        if present.

    API_FIELD_NAMES: dict (optional)
        Source-specific field name mappings.  Passed as ``source_config``
        to ``_run_groups``.
"""

from typing import TypedDict


class LeagueEntry(TypedDict):
    """Per-league configuration for a source.

    Attributes:
        id: Source-specific league identifier.
        season_types: Mapping from canonical season_type to source parameter value.
    """

    id: str
    season_types: dict[str, str]


class Source(TypedDict):
    """Complete source definition.

    Attributes:
        leagues: Mapping from league_code to league entry configuration.
        local_files: Whether this source produces local files that need
            cleanup after processing (e.g. downloaded archives, extracted CSVs).
            The orchestrator calls ``client_mod.cleanup_season_files(season)``
            after each season is processed when this is True.
    """

    leagues: dict[str, LeagueEntry]
    local_files: bool


SOURCES: dict[str, Source] = {
    "nba_api": {
        "leagues": {
            "NBA": {
                "id": "00",
                "season_types": {
                    "regular_season": "Regular Season",
                    "playoffs": "Playoffs",
                    "play_in": "PlayIn",
                },
            },
        },
        "local_files": False,
    },
    "nba_data": {
        "leagues": {
            "NBA": {
                "id": "00",
                "season_types": {
                    "regular_season": "Regular Season",
                    "playoffs": "Playoffs",
                    "play_in": "PlayIn",
                },
            },
        },
        "local_files": True,
    },
}


# ============================================================================
# DERIVED VALUE SETS
# ============================================================================

VALID_SOURCES = frozenset(SOURCES.keys())
