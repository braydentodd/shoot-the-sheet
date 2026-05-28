"""Pure helpers for TAB_COLUMNS value lambdas.

These replace the tuple-tree DSL formerly evaluated by
`calculations.evaluate_expression`. Column lambdas call these directly
so logic lives in real code, not interpreter rules.

Null propagation contract:
    - The evaluator (`evaluate_formula`) wraps each lambda call in a
      boundary that catches TypeError / ZeroDivisionError / KeyError
      and surfaces them as None. This means lambdas can use natural
      Python arithmetic (`r['x'] * 40 / r['y']`) without per-operation
      null guards. A missing field, a None operand, or a zero divisor
      collapses cleanly to None.
    - Helpers below mirror that contract internally for the rare cases
      where callers need an explicit None signal.
"""

from datetime import date, datetime
from typing import Any, Callable, Dict, List, TypedDict, Union


class PublishRow(TypedDict, total=False):
    assists: Any
    birthdate: Any
    blocks: Any
    charges_drawn: Any
    conf: Any
    cont_d_rebs: Any
    cont_fg2a: Any
    cont_fg2m: Any
    cont_fg3a: Any
    cont_fg3m: Any
    cont_o_rebs: Any
    cont_rim_fga: Any
    cont_rim_fgm: Any
    contests: Any
    d_dist_x10: Any
    d_fg2a: Any
    d_fg2m: Any
    d_fg3a: Any
    d_fg3m: Any
    d_reb_pct_x1000: Any
    d_rebs: Any
    d_rim_fga: Any
    d_rim_fgm: Any
    d_rtg_x10: Any
    deflections: Any
    dunks: Any
    fg2a: Any
    fg2m: Any
    fg3a: Any
    fg3m: Any
    fouls: Any
    fta: Any
    ftm: Any
    games: Any
    hand: Any
    height_ins_with_shoes: Any
    jersey_num: Any
    minutes_x10: Any
    name: Any
    notes: Any
    o_dist_x10: Any
    o_reb_pct_x1000: Any
    o_rebs: Any
    o_rtg_x10: Any
    off_d_rtg_x10: Any
    off_o_rtg_x10: Any
    open_fg2a: Any
    open_fg2m: Any
    open_fg3a: Any
    open_fg3m: Any
    open_rim_fga: Any
    open_rim_fgm: Any
    opp_assists: Any
    opp_fg2a: Any
    opp_fg2m: Any
    opp_fg3a: Any
    opp_fg3m: Any
    opp_fouls: Any
    opp_fta: Any
    opp_ftm: Any
    opp_turnovers: Any
    passes: Any
    possessions: Any
    pot_assists: Any
    putbacks: Any
    seasons_exp: Any
    sec_assists: Any
    steals: Any
    team_id: Any
    the_glass_id: Any
    time_on_ball: Any
    touches: Any
    turnovers: Any
    unassisted_fg2m: Any
    unassisted_fg3m: Any
    unassisted_fgm: Any
    unassisted_rim_fgm: Any
    weight_lbs: Any
    wingspan_ins: Any
    wins: Any


class PublishContext(TypedDict, total=False):
    lookup_tables: Dict[str, Dict[Any, Dict[str, Any]]]
    seasons_in_query: int
    team_players: List[PublishRow]


def calculate_age(birthdate: Any) -> Union[float, None]:
    """Age in years rounded to one decimal.

    Accepts datetime, date, or ISO date string. Returns None on null or
    unparseable input. Mirrors the prior interpreter's `calculate_age`
    operator semantics exactly.
    """
    if birthdate is None:
        return None
    if isinstance(birthdate, datetime):
        bdate = birthdate.date()
    elif isinstance(birthdate, date):
        bdate = birthdate
    else:
        try:
            bdate = datetime.fromisoformat(str(birthdate)).date()
        except ValueError:
            return None
    age_years = (date.today() - bdate).days / 365.25
    return round(age_years, 1)


def lookup(key_value: Any, table: str, field: str,
           ctx: Union[PublishContext, None]) -> Any:
    """Resolve a foreign-key style lookup against `ctx['lookup_tables']`.

    Lookup tables are structured `{table_name: {key: {field: value}}}`.
    Returns None when the key is missing or the table/entry is not present.
    """
    if key_value is None:
        return None
    table_data = (ctx or {}).get('lookup_tables', {}).get(table, {})
    entry = table_data.get(key_value)
    return entry.get(field) if entry else None


def seasons_in_query(ctx: Union[PublishContext, None]) -> int:
    """Return the season count from runtime context (default 1)."""
    return (ctx or {}).get('seasons_in_query', 1)


def team_average(value_fn: Callable[[PublishRow, Union[PublishContext, None]], Any],
                 ctx: Union[PublishContext, None]) -> Union[float, None]:
    """Minute-weighted average of `value_fn(player, ctx)` across the team.

    `ctx['team_players']` provides the iterable of player rows. Each player
    contributes `value_fn(player, ctx) * minutes` to the weighted sum, with
    weight equal to the player's minutes. Returns None when no eligible
    player has positive minutes or when `team_players` is empty.

    Exceptions raised by `value_fn` for individual players are caught and
    that player is skipped, mirroring the lambda evaluator's boundary
    behavior so a single malformed row does not break a team aggregate.
    """
    team_players = (ctx or {}).get('team_players', [])
    if not team_players:
        return None
    total_weight = 0.0
    weighted_sum = 0.0
    for player in team_players:
        try:
            value = value_fn(player, ctx)
        except (TypeError, ZeroDivisionError, KeyError):
            continue
        minutes = (player.get('minutes_x10', 0) or 0) / 10.0
        if value is not None and minutes > 0:
            weighted_sum += float(value) * minutes
            total_weight += minutes
    if total_weight == 0:
        return None
    return weighted_sum / total_weight
