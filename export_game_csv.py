"""
Standalone PBP game exporter -- no DB required.

Normalizes and derives one game, then writes three review CSVs:

  data/review/pbp_raw_{game_id}.csv          -- the raw source rows
  data/review/pbp_standardized_{game_id}.csv -- normalized + derived
      canonical PBPEvent rows (the contract columns, plus player/team
      names appended for review convenience)
  data/review/pbp_box_score_{game_id}.csv    -- the PBP-derived team and
      player box scores (accumulated result sets; NOT official box
      scores -- they come from the PBP pipeline)

Reuses the diagnostic harness (``diagnose_pbp``) for downloading,
entity resolution, and classification so the export matches exactly what
``diagnose_pbp.py`` inspects.

Usage:
    python export_game_csv.py [game_id] [season]

Defaults to the Celtics-Heat 2010-11 game (21000001).
"""
import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from diagnose_pbp import MockClassifier, build_mock_resolver, ensure_csv, load_game_rows
from src.definitions.pbp import RESULT_SET_FIELDS
from src.lib.pbp_accumulator import accumulate_result_set, player_on_court_intervals
from src.lib.pbp_deriver import derive_game_context_events
from src.sources.nba_data.pbp_normalizer import normalize_game

OUT_DIR = os.path.join("data", "review")

# Canonical PBPEvent contract columns, in order.
PBP_COLUMNS = [
    "identity", "game_id", "event_id", "seq", "secs", "period",
    "team_id", "player_id", "event", "chain_id", "fouled_player_id",
    "source",
]


def _name_maps(raw_rows: list[dict]):
    """Build player_id -> name and team_id -> name maps from raw rows."""
    player_names: dict[str, str] = {}
    team_names: dict[str, str] = {}
    for row in raw_rows:
        for pid_key, name_key in (("PLAYER1_ID", "PLAYER1_NAME"),
                                  ("PLAYER2_ID", "PLAYER2_NAME"),
                                  ("PLAYER3_ID", "PLAYER3_NAME")):
            pid = str(row.get(pid_key, "")).strip()
            name = str(row.get(name_key, "")).strip()
            if pid and pid != "0" and name:
                player_names.setdefault(pid, name)
        for tid_key, city_key, nick_key, abbr_key in (
            ("PLAYER1_TEAM_ID", "PLAYER1_TEAM_CITY",
             "PLAYER1_TEAM_NICKNAME", "PLAYER1_TEAM_ABBREVIATION"),
        ):
            tid = str(row.get(tid_key, "")).strip()
            if tid and tid != "0":
                city = str(row.get(city_key, "")).strip()
                nick = str(row.get(nick_key, "")).strip()
                abbr = str(row.get(abbr_key, "")).strip()
                name = " ".join(p for p in (city, nick) if p) or abbr
                if name:
                    team_names.setdefault(tid, name)
    return player_names, team_names


def _write_csv(path: str, columns: list[str], rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"  wrote {path} ({len(rows)} rows)")


def export_game(game_id: str, season: str) -> None:
    csv_path = ensure_csv(season)
    raw_rows = load_game_rows(game_id, csv_path)
    print(f"Game {game_id} ({season}): {len(raw_rows)} raw events")

    resolver, home, away = build_mock_resolver(raw_rows)
    classifier = MockClassifier()
    events = normalize_game(
        raw_rows, game_id, home, away,
        entity_resolver=resolver, classifier=classifier, identity="nba_id",
    )
    derive_result = derive_game_context_events(events, home, away, lineup_size=5)
    events = derive_result.events
    print(f"Normalized {len(events)} events after derivation; "
          f"{len(derive_result.errors)} derive errors")
    for err in derive_result.errors:
        print(f"    - {err.rule}: {err.message}")

    os.makedirs(OUT_DIR, exist_ok=True)
    player_names, team_names = _name_maps(raw_rows)

    # 1. Raw PBP.
    _write_csv(
        os.path.join(OUT_DIR, f"pbp_raw_{game_id}.csv"),
        list(raw_rows[0].keys()) if raw_rows else [],
        raw_rows,
    )

    # 2. Standardized PBP (contract columns + review names).
    std_columns = PBP_COLUMNS + ["team_name", "player_name"]
    std_rows = []
    for e in events:
        row = {c: e.get(c) for c in PBP_COLUMNS}
        row["team_name"] = team_names.get(e["team_id"], "")
        row["player_name"] = player_names.get(e["player_id"], "")
        std_rows.append(row)
    _write_csv(
        os.path.join(OUT_DIR, f"pbp_standardized_{game_id}.csv"),
        std_columns, std_rows,
    )

    # 3. PBP-derived box score (team + player result sets).
    box_columns = ["scope", "entity_id", "entity_name", "team_id", "team_name"] \
        + list(RESULT_SET_FIELDS.keys())
    box_rows: list[dict] = []

    for team in (home, away):
        opp = away if team == home else home
        for scope in ("team", "opp_team"):
            result = accumulate_result_set(
                events, scope, team, opp_entity_id=opp,
            )
            row = {"scope": scope, "entity_id": team,
                   "entity_name": team_names.get(team, ""),
                   "team_id": team, "team_name": team_names.get(team, "")}
            row.update(result)
            box_rows.append(row)

    player_teams: dict[str, str] = {}
    for e in events:
        if e["event"] == "player_in" and e.get("player_id"):
            player_teams.setdefault(e["player_id"], e["team_id"])
    for pid, team in sorted(player_teams.items()):
        opp = away if team == home else home
        intervals = player_on_court_intervals(events, pid)
        for scope in ("player", "opp_player", "on_player"):
            result = accumulate_result_set(
                events, scope, pid, opp_entity_id=opp,
                player_team_id=team, on_court_intervals=intervals,
            )
            row = {"scope": scope, "entity_id": pid,
                   "entity_name": player_names.get(pid, ""),
                   "team_id": team, "team_name": team_names.get(team, "")}
            row.update(result)
            box_rows.append(row)

    _write_csv(
        os.path.join(OUT_DIR, f"pbp_box_score_{game_id}.csv"),
        box_columns, box_rows,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game_id", nargs="?", default="21000001")
    parser.add_argument("season", nargs="?", default="2010-11")
    args = parser.parse_args()
    export_game(args.game_id, args.season)
