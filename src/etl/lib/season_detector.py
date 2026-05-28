import logging

from src.core.definitions.leagues import LEAGUES

logger = logging.getLogger(__name__)


def is_league_in_season(league_key: str) -> bool:
    """
    Check if a league is currently 'in season' based on recent activity.

    Uses the `season_detector` block from the league's source_roles config.
    Auto-detects the appropriate source from config. Dynamically delegates
    to the source client's ``check_activity`` function if one is registered;
    defaults to ``True`` if no implementation exists.
    """
    league = LEAGUES.get(league_key)
    if not league:
        raise ValueError(f"Unknown league_key: {league_key}")

    detector_configs = league.get('source_roles', {}).get('season_detector', {})
    if not detector_configs:
        logger.warning(
            "No season_detector registered for league='%s'. "
            "Defaulting to in_season=True",
            league_key,
        )
        return True
    
    # Use the first configured season_detector source
    source_key = next(iter(detector_configs.keys()))
    detector_def = detector_configs[source_key]

    dataset = detector_def['dataset']
    params = detector_def.get('params', {})
    activity_window_days = params.get('activity_window_days', 8)

    import importlib

    try:
        client_module = importlib.import_module(f"src.etl.sources.{source_key}.client")
        if hasattr(client_module, 'check_activity'):
            return client_module.check_activity(dataset, activity_window_days)
        logger.warning(
            "season_detector not implemented for source '%s'. Defaulting to in_season=True",
            source_key,
        )
        return True
    except ImportError as e:
        logger.error("Could not import client module for source '%s': %s", source_key, e)
        return True
    except Exception as e:
        logger.error("Failed to run season_detector for '%s': %s", source_key, e)
        return True
