from typing import Literal, TypedDict

class Possessionposs_transition(TypedDict):
    end_team: Literal["self", "opponent", "last_possessing"] | None
    start_team: Literal["self", "opponent", "next_poss_event"] | None
    condition: Literal["always", "live_shot", "jump_ball_changes_possession"] | None

class EventDef(TypedDict):
    sort_priority: int
    indicate_poss: bool
    indicate_on_court: bool
    shot: bool
    poss_transition: Possessionposs_transition | None

PBP_EVENTS: dict[str, EventDef] = {
    "d_reb": {
        "sort_priority": 0,
        "indicate_poss": True,
        "indicate_on_court": True,
        "shot": False,
        "poss_transition": {"end_team": "opponent", "start_team": "self", "condition": "always"},
    },
    "o_reb": {
        "sort_priority": 0,
        "indicate_poss": True,
        "indicate_on_court": True,
        "shot": False,
        "poss_transition": None,
    },
    "foul": {
        "sort_priority": 1,
        "indicate_poss": False,
        "indicate_on_court": False,
        "shot": False,
        "poss_transition": None,
    },
    "pot_poss_ending_scoring_opp": {
        "sort_priority": 2,
        "indicate_poss": True,
        "indicate_on_court": False,
        "shot": False,
        "poss_transition": None
    },
    "fg2_make": {
        "sort_priority": 3,
        "indicate_poss": True,
        "indicate_on_court": True,
        "shot": True,
        "poss_transition": {"end_team": "self", "start_team": "opponent", "condition": "live_shot"},
    },
    "fg2_miss": {
        "sort_priority": 3,
        "indicate_poss": True,
        "indicate_on_court": True,
        "shot": True,
        "poss_transition": None,
    },
    "fg3_make": {
        "sort_priority": 3,
        "indicate_poss": True,
        "indicate_on_court": True,
        "shot": True,
        "poss_transition": {"end_team": "self", "start_team": "opponent", "condition": "live_shot"},
    },
    "fg3_miss": {
        "sort_priority": 3,
        "indicate_poss": True,
        "indicate_on_court": True,
        "shot": True,
        "poss_transition": None,
    },
    "turnover": {
        "sort_priority": 3,
        "indicate_poss": True,
        "indicate_on_court": True,
        "shot": False,
        "poss_transition": {"end_team": "self", "start_team": "opponent", "condition": "always"}
    },
    "fg2_assist": {
        "sort_priority": 4,
        "indicate_poss": False,
        "indicate_on_court": True,
        "shot": False,
        "poss_transition": None,
    },
    "fg3_assist": {
        "sort_priority": 4,
        "indicate_poss": False,
        "indicate_on_court": True,
        "shot": False,
        "poss_transition": None,
    },
    "block": {
        "sort_priority": 4,
        "indicate_poss": False,
        "indicate_on_court": True,
        "shot": False,
        "poss_transition": None,
    },
    "steal": {
        "sort_priority": 4,
        "indicate_poss": False,
        "indicate_on_court": True,
        "shot": False,
        "poss_transition": None
    },
    "ft1_make": {
        "sort_priority": 5,
        "indicate_poss": False,
        "indicate_on_court": True,
        "shot": True,
        "poss_transition": {"end_team": "self", "start_team": "opponent", "condition": "live_shot"},
    },
    "ft2_make": {
        "sort_priority": 5,
        "indicate_poss": False,
        "indicate_on_court": True,
        "shot": True,
        "poss_transition": {"end_team": "self", "start_team": "opponent", "condition": "live_shot"},
    },
    "ft3_make": {
        "sort_priority": 5,
        "indicate_poss": False,
        "indicate_on_court": True,
        "shot": True,
        "poss_transition": {"end_team": "self", "start_team": "opponent", "condition": "live_shot"},
    },
    "ft1_miss": {
        "sort_priority": 5,
        "indicate_poss": False,
        "indicate_on_court": True,
        "shot": True,
        "poss_transition": None,
    },
    "o_foul_draw": {
        "sort_priority": 8,
        "indicate_poss": False,
        "indicate_on_court": True,
        "shot": False,
        "poss_transition": None
    },
    "period_end": {
        "sort_priority": 9,
        "indicate_poss": False,
        "indicate_on_court": False,
        "shot": False,
        "poss_transition": {"end_team": "last_possessing", "start_team": None, "condition": "always"}
    },
    "player_out": {
        "sort_priority": 10,
        "indicate_poss": False,
        "indicate_on_court": True,
        "shot": False,
        "poss_transition": None
    },
    "player_in": {
        "sort_priority": 11,
        "indicate_poss": False,
        "indicate_on_court": False,
        "shot": False,
        "poss_transition": None
    },
    "period_start": {
        "sort_priority": 12,
        "indicate_poss": False,
        "indicate_on_court": False,
        "shot": False,
        "poss_transition": {"end_team": None, "start_team": "next_poss_event", "condition": "always"}
    },
    "jump_ball_win": {
        "sort_priority": 13,
        "indicate_poss": True,
        "indicate_on_court": True,
        "shot": False,
        "poss_transition": {"end_team": "opponent", "start_team": "self", "condition": "jump_ball_changes_possession"}
    },
    "poss_start": {
        "sort_priority": 14,
        "indicate_poss": False,
        "indicate_on_court": False,
        "shot": False,
        "poss_transition": None
    },
    "poss_end": {
        "sort_priority": 15,
        "indicate_poss": False,
        "indicate_on_court": False,
        "shot": False,
        "poss_transition": None
    },
}