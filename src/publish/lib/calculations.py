import logging
from typing import Any, Dict, List, Union

from src.core.definitions.db_columns import DB_COLUMNS
from src.publish.definitions.layout import SECTIONS_CONFIG, VALUES_KEY_ENTITY
from src.publish.definitions.stats import STAT_RATES
from src.publish.definitions.view_columns import VIEW_COLUMNS

logger = logging.getLogger(__name__)


# ============================================================================
# FORMULA EVALUATION
# ============================================================================


def evaluate_formula(
    col_key: str,
    entity_data: dict,
    entity_type: str = "player",
    mode: str = "per_possession",
    context: Union[dict, None] = None,
) -> Any:
    """Evaluate a column's value expression against entity data.

    Expression must be a callable: ``lambda row, ctx: ...``
    Any ``TypeError``/``ZeroDivisionError``/``KeyError`` is surfaced as
    None, matching the legacy interpreter's null-propagation contract.
    """
    col_def = VIEW_COLUMNS.get(col_key)
    if not col_def:
        return None

    expr = col_def.get("values", {}).get(entity_type, {}).get("fn")
    if expr is None:
        return None

    if not callable(expr):
        logger.warning(
            "Column %s.%s has non-callable expression: %r",
            col_key,
            entity_type,
            type(expr),
        )
        return None

    try:
        return expr(entity_data, context)
    except (TypeError, ZeroDivisionError, KeyError) as exc:
        logger.debug(
            "Formula %s.%s returned None (%s: %s)",
            col_key,
            entity_type,
            type(exc).__name__,
            exc,
        )
        return None


def _coerce_positive(*candidates: Union[float, None]) -> Union[float, None]:
    """Return the first candidate that is a positive number, else None.

    Drives the domain -> base fallback chain for rate denominators.
    """
    for v in candidates:
        if v is None:
            continue
        try:
            n = float(v)
        except (TypeError, ValueError):
            continue
        if n > 0:
            return n
    return None


def _apply_scaling(
    raw_value: Any,
    mode: str,
    *,
    domain_minutes: Union[float, None],
    base_minutes: Union[float, None],
    domain_possessions: Union[float, None],
    base_possessions: Union[float, None],
) -> Any:
    """Apply mode-based scaling with a strict domain -> base fallback chain.

    A scaled rate is only defined when its denominator is positive.  If both
    the domain denominator and the base denominator are zero/NULL we return
    ``None`` so the consumer renders an empty cell instead of a misleading
    zero.  Scaling factors come from STAT_RATES so changes (e.g. 40 -> 48
    minute base) only require a config update.
    """
    if raw_value is None:
        return None
    if raw_value == 0:
        return 0

    if mode == "per_minute":
        denom = _coerce_positive(domain_minutes, base_minutes)
        if denom is None:
            return None
        return raw_value * STAT_RATES["per_minute"]["rate"] / denom

    if mode == "per_possession":
        denom = _coerce_positive(domain_possessions, base_possessions)
        if denom is None:
            return None
        return raw_value * STAT_RATES["per_possession"]["rate"] / denom

    return raw_value


def calculate_entity_stats(
    entity_data: dict,
    entity_type: str = "player",
    mode: str = "per_possession",
    context: Union[dict, None] = None,
) -> dict:
    """
    Calculate all stat values for an entity in a given mode.

    Returns dict of {col_key: calculated_value} for all applicable columns.
    """
    # Auto-populate seasons_in_query from entity_data when available.
    # Historical/postseason queries store COUNT(DISTINCT s.season) as 'season'.
    if context is None:
        local_context = {}
    else:
        local_context = context.copy()

    if "seasons_in_query" not in local_context:
        season_val = entity_data.get("season")
        if isinstance(season_val, int):
            local_context["seasons_in_query"] = season_val
        elif isinstance(season_val, str):
            # E.g. '2025-26'
            local_context["seasons_in_query"] = 1
        else:
            # None or empty dict
            local_context["seasons_in_query"] = 1

    results = {}

    # Base denominators -- always available on the fact row.
    base_mins_x10 = entity_data.get("mins_x10")
    base_minutes = (base_mins_x10 or 0) / 10.0 if base_mins_x10 is not None else None
    base_possessions = entity_data.get("possessions")

    for col_key, col_def in VIEW_COLUMNS.items():
        values = col_def.get("values", {})
        if entity_type not in values:
            continue

        raw_value = evaluate_formula(
            col_key, entity_data, entity_type, mode, local_context
        )

        if raw_value is None:
            results[col_key] = None
            continue

        rate_domain = col_def.get("rate_domain")

        if rate_domain is None:
            results[col_key] = raw_value
        else:
            # We don't have STAT_DOMAINS anymore, fallback to base
            results[col_key] = _apply_scaling(
                raw_value,
                mode,
                domain_minutes=None,
                base_minutes=base_minutes,
                domain_possessions=None,
                base_possessions=base_possessions,
            )

        if col_def.get("format") == "percentage" and isinstance(
            results[col_key], (int, float)
        ):
            results[col_key] = results[col_key] * 100

    return results


# ============================================================================
# DB HELPERS & FETCH FUNCTIONS — live in league-specific wrappers
# (nba_sheets_lib.py / ncaa_sheets_lib.py) because SQL differs per league.
# ============================================================================


def calculate_all_percentiles(
    all_entities: List[dict],
    entity_type: str,
    mode: str = "per_possession",
    context: Union[dict, None] = None,
    context_fn=None,
) -> dict:
    """
    Calculate minute-weighted percentile populations for all stat columns.

    Columns in stats sections are weighted by minutes played.
    Non-stats columns (profile), etc.) use weight = 1.

    Args:
        context_fn: Optional callable(entity_dict) -> context_dict.
                    Used for team entities that need per-entity context
                    (e.g. team_average requires team_players).

    Returns:
        Dict of {col_key: sorted list of (value, weight) tuples}
    """
    all_calculated = []
    for entity in all_entities:
        entity_ctx = context_fn(entity) if context_fn else context
        stats = calculate_entity_stats(entity, entity_type, mode, entity_ctx)
        all_calculated.append((entity, stats))

    percentiles = {}
    for col_key, col_def in VIEW_COLUMNS.items():
        if not col_def.get("percentile"):
            continue

        is_stats = any(
            SECTIONS_CONFIG.get(s, {}).get("stats_timeframe")
            for s in col_def.get("sections", [])
        )

        entries = []
        for entity, stats in all_calculated:
            val = stats.get(col_key)
            if val is None or not isinstance(val, (int, float)):
                continue

            if is_stats:
                raw_minutes = (entity.get("mins_x10", 0) or 0) / 10.0
                if raw_minutes <= 0:
                    continue
                entries.append((val, raw_minutes))
            else:
                entries.append((val, 1.0))

        if entries:
            percentiles[col_key] = sorted(entries, key=lambda x: x[0])

    return percentiles


def get_percentile_rank(
    value: Any, sorted_weighted: List, reverse: bool = False
) -> float:
    """
    Calculate minute-weighted percentile rank.

    Uses weighted CDF: for each entry below the value, accumulate its weight.
    Ties get the midpoint of their cumulative weight range.

    Args:
        value: The value to rank
        sorted_weighted: Sorted list of (value, weight) tuples
        reverse: True if lower is better (turnovers, fouls)

    Returns:
        Percentile rank 0-100
    """
    if not sorted_weighted or value is None or not isinstance(value, (int, float)):
        return 50.0

    n = len(sorted_weighted)
    if n == 1:
        return 50.0

    total_weight = sum(w for _, w in sorted_weighted)
    if total_weight <= 0:
        return 50.0

    weight_below = 0.0
    weight_equal = 0.0
    for v, w in sorted_weighted:
        if v < value:
            weight_below += w
        elif v == value:
            weight_equal += w
        elif v > value:
            break

    midpoint = weight_below + weight_equal / 2.0
    percentile = (midpoint / total_weight) * 100

    if reverse:
        percentile = 100 - percentile

    return max(0, min(100, percentile))


# ============================================================================
# FIELD DERIVATION (consolidated from field_derivation.py)
# ============================================================================


def derive_db_fields(
    league: str = None, stats_sections: frozenset = None, computed_fields: set = None
) -> Dict[str, set]:
    """Derive the DB column sets needed by publish queries from VIEW_COLUMNS.

    Dependency resolution looks at the ``fields`` tuple in each ``values`` declaration.
    Fields are explicitly prefixed with SQL aliases ('p.', 't.', 's.', 'tr.') to route
    them to the appropriate query bucket.

    Returns a dict with keys:
        player_entity_fields, team_entity_fields, stat_fields, team_stat_fields
    """
    stats_sections = stats_sections or frozenset()
    computed_fields = computed_fields or set()

    player_entity = set()
    team_entity = set()
    player_stats = set()
    team_stats = set()

    for col_def in VIEW_COLUMNS.values():
        if league and league not in col_def.get("leagues", []):
            continue

        inputs = col_def.get("values")
        if inputs is not None:
            for values_key, spec in inputs.items():
                default_entity_type = VALUES_KEY_ENTITY.get(values_key)
                if default_entity_type is None:
                    continue
                fields = set(spec.get("fields", ()))

                for raw_field in fields:
                    if "." not in raw_field:
                        # Fallback for any unprefixed fields (should be none)
                        prefix, field = None, raw_field
                    else:
                        prefix, field = raw_field.split(".", 1)

                    if prefix == "p":
                        player_entity.add(field)
                    elif prefix == "t":
                        team_entity.add(field)
                    elif prefix == "tr":
                        player_entity.add(field)
                    elif prefix == "s":
                        if default_entity_type == "player":
                            player_stats.add(field)
                        else:
                            team_stats.add(field)
                    else:
                        # Fallback for untagged fields
                        if default_entity_type == "player":
                            player_entity.add(field)
                        else:
                            team_entity.add(field)

    return {
        "player_entity_fields": player_entity - computed_fields,
        "team_entity_fields": team_entity - computed_fields,
        "stat_fields": player_stats,
        "team_stat_fields": team_stats,
    }


# ============================================================================
# PERCENTILE POPULATION BUILDER
# ============================================================================


def compute_pct_by_rate(section_data: dict, entity_type: str, context_fn=None) -> dict:
    """Compute percentile populations for all stat rates.

    Args:
        section_data: ``{base_section: data_list}`` e.g.
            ``{'current_stats': [...], 'historical_stats': [...], ...}``
        entity_type: ``'player'``, ``'team'``, or ``'opponents'``
        context_fn: Optional callable ``(entity_dict) -> context_dict``.
            Required for team entities whose profile columns use
            ``team_average`` (needs per-entity ``team_players`` context).

    Returns:
        ``{rate: {base_section: {col_key: sorted_values}}}``
    """
    result = {}
    for rate in STAT_RATES:
        result[rate] = {}
        for section, data_list in section_data.items():
            if data_list:
                result[rate][section] = calculate_all_percentiles(
                    data_list,
                    entity_type,
                    rate,
                    context_fn=context_fn,
                )
            else:
                result[rate][section] = {}
    return result
