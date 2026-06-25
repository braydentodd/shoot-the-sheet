"""
Shoot the Sheet — PBP Pipeline Configuration  (``pbp.py``)

Two-layer config, both read at runtime — nothing hardcoded in the parser.

Layer 1 — SOURCE_NORMALIZERS
    Per-source rules for converting raw API responses to canonical events.
    Add a source = add an entry here.  The parser never touches this layer.

Layer 2 — ACCUM_RULES
    Stat accumulation rules applied to canonical events.  Source-agnostic.

CANONICAL EVENT FORMAT
----------------------
Every event dict has exactly these keys.  Use ``None`` for absent values.
Do not omit keys — the parser expects all of them.

    action_type       str       MadeShot, MissedShot, FreeThrow, Rebound,
                                Turnover, Foul, Substitution, JumpBall,
                                Period, Timeout, Violation, Block, Steal,
                                Ejection, EndOfPeriod
    period            int       1-4 (regulation), 5+ (OT)
    clock             str       original clock string (debugging)
    clock_seconds     float     seconds elapsed in period
    team_id           int|None
    player_id         int|None  primary player
    shot_made         bool|None
    shot_value        int|None  2 or 3 for FGs, 1 for FTs
    is_field_goal     int|None  1 for FG, None otherwise
    is_free_throw     int|None  1 for FT, None otherwise
    assist_player_id  int|None
    rebound_type      str|None  "offensive" | "defensive"  (Rebound only)
    foul_type         str|None  "offensive"|"shooting"|"personal"|...  (Foul only)
    turnover_type     str|None  "bad_pass"|"lost_ball"|...  (Turnover only)
    block_player_id   int|None
    steal_player_id   int|None
    substitution_in   int|None
    substitution_out  int|None
    description       str       raw text, never parsed by parser

NOTE: rebound_type, foul_type, and turnover_type are separate fields
rather than a single ``sub_type`` because each only appears on its
respective event type.  Keeping them separate means ACCUM_RULES never
needs action_type context to disambiguate values — a ``rebound_type`` of
``"offensive"`` can only mean an offensive rebound.
"""

from typing import Any, Dict, List

# ═══════════════════════════════════════════════════════════════════════════
# LAYER 1 — Source normalizers
# ═══════════════════════════════════════════════════════════════════════════

SOURCE_NORMALIZERS: Dict[str, Dict[str, Any]] = {
    "nba_api": {
        # Field mapping: raw v3 field → canonical field.
        # Values are canonical key names.  ``None`` means special handling.
        "field_map": {
            "actionType": "action_type",
            "period": "period",
            "clock": "clock",
            "personId": "player_id",
            "teamId": "team_id",
            "shotResult": None,  # special: "Made" → shot_made=True
            "shotValue": "shot_value",
            "isFieldGoal": "is_field_goal",
            "subType": None,  # special: parsed for rebound/foul/turnover type
            "description": "description",
            "location": None,  # special: "h"/"v" → home_team_id/away_team_id
        },
        # actionType value mapping: raw v3 value → canonical action_type
        "action_types": {
            "Made Shot": "MadeShot",
            "Missed Shot": "MissedShot",
            "Free Throw": "FreeThrow",
            "Rebound": "Rebound",
            "Turnover": "Turnover",
            "Foul": "Foul",
            "Substitution": "Substitution",
            "Jump Ball": "JumpBall",
            "period": "Period",
            "Timeout": "Timeout",
            "Violation": "Violation",
            "Ejection": "Ejection",
        },
        # Foul subType → canonical foul_type
        "foul_types": {
            "Offensive": "offensive",
            "Shooting": "shooting",
            "Personal": "personal",
            "Technical": "technical",
            "Loose Ball": "loose_ball",
            "Away From Play": "away_from_play",
            "Flagrant Type 1": "flagrant_1",
            "Flagrant Type 2": "flagrant_2",
            "Double Technical": "double_technical",
            "Personal Take": "personal",
        },
        # Turnover subType → canonical turnover_type
        "turnover_types": {
            "Bad Pass": "bad_pass",
            "Lost Ball": "lost_ball",
            "Traveling": "traveling",
            "Offensive Foul": "offensive_foul",
            "Shot Clock": "shot_clock",
            "8 Second": "8_second",
            "Out of Bounds": "out_of_bounds",
            "Backcourt": "backcourt",
            "Illegal Assist": "illegal_assist",
            "Palming": "palming",
            "Double Dribble": "double_dribble",
            "Kicked Ball": "kicked_ball",
            "Step Out of Bounds": "step_out_of_bounds",
            "3 Second": "3_second",
            "Inbound": "inbound",
            "5 Second": "5_second",
        },
        # Description parsing patterns → canonical fields.
        # Each pattern is a regex with named groups that map to canonical keys.
        "description_patterns": {
            "assist": {
                "regex": r"\((?P<name>\w+)\s+\d+\s+AST\)",
                "maps_to": "assist_player_id",
                "resolve": "player_name",
            },
            "block": {
                "regex": r"(?P<name>\w+)\s+BLOCK",
                "maps_to": "block_player_id",
                "resolve": "player_name",
            },
            "substitution": {
                "regex": r"SUB:\s*(?P<in>\w+)\s+FOR\s+(?P<out>\w+)",
                "maps_to": ["substitution_in", "substitution_out"],
                "resolve": "player_name",
            },
        },
        # Rebound typing: subType contains "Off" or "Def"
        "rebound_off_keywords": ["off", "Off"],
        "rebound_def_keywords": ["def", "Def"],
        # Home/away identification: location field values
        "home_location": "h",
        "away_location": "v",
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# LAYER 2 — Stat accumulation rules  (source-agnostic)
# ═══════════════════════════════════════════════════════════════════════════

# Each rule: when canonical event matches ``action_type``, apply this
# accumulation.  ``target`` is who gets the stat, ``value`` is how much.
#
# Special value tokens (resolved at runtime from the event):
#   "shot_value_2"  → 1 if shot_value == 2 else 0
#   "shot_value_3"  → 1 if shot_value == 3 else 0
#   "shot_value"    → event["shot_value"]
#   "shot_made_1"   → 1 if shot_made else 0
#   "rebound_offensive" → 1 if rebound_type == "offensive" else 0
#   "rebound_defensive" → 1 if rebound_type == "defensive" else 0
#
# Targets:
#   "player"              — event["player_id"]
#   "assister"            — event["assist_player_id"]
#   "team"                — event["team_id"]
#   "on_court"            — every active player on event["team_id"]
#   "defending_team"      — the OTHER team (not event["team_id"])
#   "defending_on_court"  — every active player on the defending team

ACCUM_RULES: Dict[str, List[Dict[str, Any]]] = {
    "MadeShot": [
        {"stat": "fg2m", "target": "player", "value": "shot_value_2"},
        {"stat": "fg3m", "target": "player", "value": "shot_value_3"},
        {"stat": "fg2a", "target": "player", "value": "shot_value_2"},
        {"stat": "fg3a", "target": "player", "value": "shot_value_3"},
        {"stat": "assists", "target": "assister", "value": 1},
        {"stat": "assist_points", "target": "assister", "value": "shot_value"},
        {"stat": "fg2m", "target": "team", "value": "shot_value_2"},
        {"stat": "fg3m", "target": "team", "value": "shot_value_3"},
        {"stat": "fg2m", "target": "on_court", "value": "shot_value_2"},
        {"stat": "fg3m", "target": "on_court", "value": "shot_value_3"},
    ],
    "MissedShot": [
        {"stat": "fg2a", "target": "player", "value": "shot_value_2"},
        {"stat": "fg3a", "target": "player", "value": "shot_value_3"},
        {"stat": "fg2a", "target": "team", "value": "shot_value_2"},
        {"stat": "fg3a", "target": "team", "value": "shot_value_3"},
        {"stat": "fg2a", "target": "on_court", "value": "shot_value_2"},
        {"stat": "fg3a", "target": "on_court", "value": "shot_value_3"},
    ],
    "FreeThrow": [
        {"stat": "fta", "target": "player", "value": 1},
        {"stat": "ftm", "target": "player", "value": "shot_made_1"},
        {"stat": "fta", "target": "team", "value": 1},
        {"stat": "ftm", "target": "team", "value": "shot_made_1"},
        {"stat": "fta", "target": "on_court", "value": 1},
        {"stat": "ftm", "target": "on_court", "value": "shot_made_1"},
    ],
    "Rebound": [
        {"stat": "o_rebs", "target": "player", "value": "rebound_offensive"},
        {"stat": "d_rebs", "target": "player", "value": "rebound_defensive"},
        {"stat": "o_rebs", "target": "team", "value": "rebound_offensive"},
        {"stat": "d_rebs", "target": "team", "value": "rebound_defensive"},
        {"stat": "o_rebs", "target": "on_court", "value": "rebound_offensive"},
        {"stat": "d_rebs", "target": "on_court", "value": "rebound_defensive"},
    ],
    "Turnover": [
        {"stat": "turnovers", "target": "player", "value": 1},
        {"stat": "turnovers", "target": "team", "value": 1},
        {"stat": "turnovers", "target": "on_court", "value": 1},
    ],
    "Steal": [
        {"stat": "steals", "target": "player", "value": 1},
    ],
    "Block": [
        {"stat": "blocks", "target": "player", "value": 1},
        {"stat": "blocks", "target": "team", "value": 1},
        {"stat": "blocks", "target": "on_court", "value": 1},
    ],
    "Foul": [
        {"stat": "fouls", "target": "player", "value": 1},
        {"stat": "fouls", "target": "team", "value": 1},
        {"stat": "fouls", "target": "on_court", "value": 1},
    ],
    "OffensiveFoul": [
        {"stat": "o_fouls_drawn", "target": "defending_team", "value": 1},
        {"stat": "o_fouls_drawn", "target": "defending_on_court", "value": 1},
    ],
}


# ═══════════════════════════════════════════════════════════════════════════
# Possession change rules
# ═══════════════════════════════════════════════════════════════════════════

POSSESSION_END: Dict[str, str] = {
    "MadeShot": "rebound",
    "Turnover": "other_team",
    "DefensiveRebound": "this_team",
    "EndOfPeriod": "period_start",
}

# Free throws: only the LAST FT of a trip ends the possession.
FT_TRIP_END_SUBTYPES = {"2 of 2", "3 of 3", "1 of 1"}


# ═══════════════════════════════════════════════════════════════════════════
# Derived stat computations  (multi-event, stateful)
# ═══════════════════════════════════════════════════════════════════════════

DERIVED: Dict[str, Dict[str, Any]] = {
    "poss": {
        "compute": "count_possessions",
        "level": "team",
    },
    "secs": {
        "compute": "track_stints",
        "level": "player",
    },
    "o_poss_secs": {
        "compute": "track_possession_time",
        "side": "offense",
        "level": "team",
    },
    "d_poss_secs": {
        "compute": "track_possession_time",
        "side": "defense",
        "level": "team",
    },
    "poss_ending_ft_trips": {
        "compute": "count_ft_trip_possessions",
        "level": "team",
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# Opponent auto-mirror  (post-processing)
# ═══════════════════════════════════════════════════════════════════════════
# After all team stats are computed, every team-level counting stat is
# mirrored to the opponent as ``opp_<stat>``.  Team A's ``opp_fg3m`` =
# Team B's ``fg3m``.  No config needed — the parser mirrors ALL team stats.
#
# Stats excluded from mirroring (possessions):
#   "poss" — already has explicit ``opp_poss`` via DERIVED
#   "o_poss_secs", "d_poss_secs" — these ARE the split, no need to mirror
#   Derived stats that are already per-side

# Team-level stats that should NOT be auto-mirrored (already handled or
# meaningless to mirror):
OPPONENT_MIRROR_EXCLUDE = frozenset(
    {
        "poss",  # has explicit DERIVED["opp_poss"]
        "o_poss_secs",  # offense possession time
        "d_poss_secs",  # defense possession time
    }
)


# ═══════════════════════════════════════════════════════════════════════════
# Stat registries — derived from ACCUM_RULES + DERIVED at import time
# ═══════════════════════════════════════════════════════════════════════════


def _collect_stats() -> Dict[str, List[str]]:
    """Collect all stat names from ACCUM_RULES and DERIVED configs."""
    player: set[str] = set()
    team: set[str] = set()
    on_court: set[str] = set()

    for rules in ACCUM_RULES.values():
        for rule in rules:
            stat = rule["stat"]
            target = rule["target"]
            if target in ("player", "assister"):
                player.add(stat)
            elif target in ("team", "defending_team"):
                team.add(stat)
            elif target in ("on_court", "defending_on_court"):
                on_court.add(f"on_{stat}")

    for name, cfg in DERIVED.items():
        if cfg.get("level") == "player":
            player.add(name)
        elif cfg.get("level") == "team":
            team.add(name)

    return {
        "PLAYER": sorted(player),
        "TEAM": sorted(team),
        "ON_COURT": sorted(on_court),
    }


_STAT_REGISTRY: Dict[str, List[str]] = _collect_stats()
