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

from typing import Any, Dict

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
