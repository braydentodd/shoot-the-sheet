"""
Standalone PBP diagnostic -- no DB required.

Downloads one season of nba_data, normalizes a game, derives possession
events, and prints stats to diagnose secs/possession bugs.

Usage:
    python diagnose_pbp.py [game_id] [season] [home_team_id] [away_team_id]

Defaults to the Celtics-Heat 2010-11 game from the original review.
"""
import csv
import os
import sys
import tarfile
import urllib.request
from collections import Counter

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ARCHIVE_URL = "https://github.com/shufinskiy/nba_data/raw/main/datasets/nbastats_{start_year}.tar.xz"
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "nba_data")
ARCHIVE_DIR = os.path.join(DATA_DIR, "archives")
EXTRACTED_DIR = os.path.join(DATA_DIR, "extracted")

# Diagnostics-only foul taxonomy: MSG=6 action type -> canonical foul
# event.  Mirrors the reviewed ``core.pbp_events`` catalog rows so this
# DB-less harness can classify without a database; it is NOT a
# production authority (the catalog is).  Keep in sync when re-reviewing
# the catalog during the MSG=6 migration.
FOUL_ACTIONTYPE_MAP: dict[int, str] = {
    1: "d_standard_foul",  # personal
    2: "d_standard_foul",  # shooting
    3: "d_standard_foul",  # loose ball
    4: "o_standard_foul",  # offensive
    5: "d_standard_foul",  # inbound
    6: "elevated_foul",    # away from play
    9: "elevated_foul",    # clear path
    10: "d_standard_foul", # double personal
    11: "elevated_foul",   # technical
    12: "elevated_foul",   # non-unsportsmanlike (bench technical)
    13: "elevated_foul",   # hanging tech
    14: "elevated_foul",   # flagrant 1
    15: "elevated_foul",   # flagrant 2
    16: "elevated_foul",   # double technical
    17: "elevated_foul",   # defensive 3 seconds
    18: "elevated_foul",   # team foul
    19: "elevated_foul",   # taunting
    26: "o_standard_foul", # offensive charge
    27: "d_standard_foul", # personal block
    28: "d_standard_foul", # personal take
    29: "d_standard_foul", # shooting block
}


# ---------------------------------------------------------------------------
# Download + extract
# ---------------------------------------------------------------------------
def ensure_csv(season: str) -> str:
    start_year = season[:4]
    dir_name = f"nbastats_{start_year}"
    csv_path = os.path.join(EXTRACTED_DIR, dir_name, f"{dir_name}.csv")
    if os.path.isfile(csv_path):
        return csv_path

    archive_path = os.path.join(ARCHIVE_DIR, f"{dir_name}.tar.xz")
    if not os.path.isfile(archive_path):
        os.makedirs(ARCHIVE_DIR, exist_ok=True)
        url = ARCHIVE_URL.format(start_year=start_year)
        print(f"Downloading {url} ...")
        urllib.request.urlretrieve(url, archive_path)
        print(f"  -> {archive_path}")

    tmp_dir = os.path.join(EXTRACTED_DIR, dir_name + ".tmp")
    if os.path.isdir(tmp_dir):
        import shutil
        shutil.rmtree(tmp_dir)
    os.makedirs(tmp_dir, exist_ok=True)
    print(f"Extracting {archive_path} ...")
    with tarfile.open(archive_path, "r:xz") as tar:
        tar.extractall(path=tmp_dir)
    os.rename(tmp_dir, os.path.join(EXTRACTED_DIR, dir_name))
    return csv_path


def load_game_rows(game_id: str, csv_path: str) -> list[dict]:
    rows = []
    with open(csv_path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if str(row.get("GAME_ID", "")) == game_id:
                rows.append(row)
    rows.sort(key=lambda r: int(r.get("EVENTNUM", 0)))
    return rows


# ---------------------------------------------------------------------------
# Smart mock resolver -- builds player->team map from CSV data
# ---------------------------------------------------------------------------
def build_mock_resolver(rows: list[dict]):
    """Scan CSV rows to build a player->team mapping.

    Uses PLAYER1_TEAM_ID from the CSV as the canonical team ID.
    Detects which raw team IDs are home vs away from PERSON1TYPE.
    Returns (resolver, home_numeric_id, away_numeric_id).
    """
    # Collect all player->team mappings from raw CSV
    player_teams: dict[str, str] = {}
    # Track team IDs by PERSON1TYPE (2=home team, 3=away team)
    home_team_ids: set[str] = set()
    away_team_ids: set[str] = set()
    # Track which IDs are team-level entities (PERSON1TYPE 2 or 3)
    team_entities: set[str] = set()

    for row in rows:
        p1_type = str(row.get("PERSON1TYPE", "")).strip()
        p1_id = str(row.get("PLAYER1_ID", "")).strip()
        p1_team = str(row.get("PLAYER1_TEAM_ID", "")).strip()

        # Track team IDs by person type
        if p1_type == "2" and p1_id and p1_id != "0":
            home_team_ids.add(p1_id)
            team_entities.add(p1_id)
        elif p1_type == "3" and p1_id and p1_id != "0":
            away_team_ids.add(p1_id)
            team_entities.add(p1_id)

        # Build player -> team mapping
        for pid_key, tid_key in [
            ("PLAYER1_ID", "PLAYER1_TEAM_ID"),
            ("PLAYER2_ID", "PLAYER2_TEAM_ID"),
            ("PLAYER3_ID", "PLAYER3_TEAM_ID"),
        ]:
            pid = str(row.get(pid_key, "")).strip()
            tid = str(row.get(tid_key, "")).strip()
            if pid and pid != "0" and tid:
                player_teams[pid] = tid

    # Determine canonical home/away numeric IDs
    home_numeric = sorted(home_team_ids)[0] if home_team_ids else "0"
    away_numeric = sorted(away_team_ids)[0] if away_team_ids else "0"

    # Also register numeric team IDs as self-mapping (for team events)
    for tid in (home_numeric, away_numeric):
        if tid and tid != "0":
            player_teams[tid] = tid

    print(f"Mock resolver: {len(player_teams)} entities mapped")
    print(f"  Home team (PERSON1TYPE=2): {home_numeric}")
    print(f"  Away team (PERSON1TYPE=3): {away_numeric}")

    def resolver(entity_id: str) -> tuple:
        if not entity_id or entity_id == "0":
            return None, None
        if entity_id in player_teams:
            team = player_teams[entity_id]
            # If entity_id is a known team entity, treat as team
            if entity_id in team_entities:
                return ("team", team)
            return ("player", team)
        return None, None

    return resolver, home_numeric, away_numeric


# ---------------------------------------------------------------------------
# Mock classifier -- reads event descriptions to sub-classify 2pt/3pt
# ---------------------------------------------------------------------------
class MockClassifier:
    """Produces handling values the normalizer expects, using description text."""

    def classify(self, row: dict):
        msgtype = int(row.get("EVENTMSGTYPE", 0))
        actiontype = int(row.get("EVENTMSGACTIONTYPE", 0))
        desc = " ".join(
            str(row.get(k, ""))
            for k in ("HOMEDESCRIPTION", "NEUTRALDESCRIPTION", "VISITORDESCRIPTION")
        )
        desc_upper = desc.upper()

        handling = None
        if msgtype == 1:   # Made FG
            handling = "fg3_make" if "3PT" in desc_upper else "fg2_make"
        elif msgtype == 2:  # Missed FG
            handling = "fg3_miss" if "3PT" in desc_upper else "fg2_miss"
        elif msgtype == 3:  # Free throw
            # FT misses are consolidated into a single ft_miss event; a
            # make defaults to ft1_make (multi-point FT leagues emit the
            # matching indexed make event).
            handling = "ft_miss" if "MISS" in desc_upper else "ft1_make"
        elif msgtype == 4:  handling = "rebound"
        elif msgtype == 5:  handling = "turnover"
        elif msgtype == 6:  handling = FOUL_ACTIONTYPE_MAP.get(actiontype, "d_standard_foul")
        elif msgtype == 8:  handling = "substitution"
        elif msgtype == 10: handling = "jump_ball_win"
        elif msgtype == 12: handling = "period_start"
        elif msgtype == 13: handling = "period_end"
        else:               handling = "ignore"

        class _C:
            pass
        c = _C()
        c.handling = handling
        c.is_ignore = (handling == "ignore")
        return c


# ---------------------------------------------------------------------------
# Main diagnostic
# ---------------------------------------------------------------------------
def diagnose(game_id: str, season: str, home_team_id: str, away_team_id: str):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    from src.sources.nba_data.pbp_normalizer import normalize_game
    from src.lib.pbp_accumulator import accumulate_result_set
    from src.lib.pbp_deriver import derive_game_context_events

    # 1. Load raw data
    csv_path = ensure_csv(season)
    raw_rows = load_game_rows(game_id, csv_path)
    print(f"\nGame {game_id} ({season}): {len(raw_rows)} raw events")

    # 2. Build mock resolver from CSV data
    resolver, home_team_id, away_team_id = build_mock_resolver(raw_rows)
    if home_team_id == "0" or away_team_id == "0":
        print("ERROR: Could not determine team IDs from CSV. Check PERSON1TYPE values.")
        return
    classifier = MockClassifier()
    print(f"  Using: home={home_team_id}, away={away_team_id}")

    # 3. Normalize
    events = normalize_game(
        raw_rows, game_id, home_team_id, away_team_id,
        entity_resolver=resolver,
        classifier=classifier,
        identity="nba_id",
    )
    print(f"Normalized: {len(events)} events")

    # 4. Derive context events (possessions, lineups)
    derive_result = derive_game_context_events(
        events, home_team_id, away_team_id, lineup_size=5,
    )
    events = derive_result.events
    if derive_result.errors:
        print(f"  DERIVE ERRORS: {len(derive_result.errors)}")
        for err in derive_result.errors:
            print(f"    - {err.rule}: {err.message}")
    print(f"After derivation: {len(events)} events\n")

    # ==================================================================
    # POSSESSION START/END CONSISTENCY (Point 3)
    # ==================================================================
    print("=" * 65)
    print("POINT 3: Possession start/end consistency")
    print("=" * 65)

    poss_starts = [e for e in events if e["event"] == "poss_start"]
    poss_ends = [e for e in events if e["event"] == "poss_end"]

    print(f"  poss_start:       {len(poss_starts)}")
    print(f"  poss_end:         {len(poss_ends)}")

    for team_id in sorted(set(
        e["team_id"] for e in poss_starts + poss_ends if e["team_id"]
    )):
        starts = [e for e in poss_starts if e["team_id"] == team_id]
        ends = [e for e in poss_ends if e["team_id"] == team_id]
        delta = len(starts) - len(ends)
        flag = " *** MISMATCH ***" if delta != 0 else ""
        print(f"  {team_id[:30]:30s}  starts={len(starts):3d}  ends={len(ends):3d}  delta={delta:+d}{flag}")

    # Show ALL poss_start/poss_end in chronological order with team
    all_poss_events = sorted(
        [e for e in events if e["event"] in ("poss_start", "poss_end")],
        key=lambda e: (e["secs"], e["event_id"]),
    )
    if len(all_poss_events) <= 60:
        print(f"\n  All {len(all_poss_events)} possession events:")
        for e in all_poss_events:
            print(f"    secs={e['secs']:5d}  id={e['event_id']!s:>4}  {e['event']:22s}  team={e['team_id'][:25]}")
    else:
        print(f"\n  First 30 possession events (of {len(all_poss_events)}):")
        for e in all_poss_events[:30]:
            print(f"    secs={e['secs']:5d}  id={e['event_id']!s:>4}  {e['event']:22s}  team={e['team_id'][:25]}")
        print(f"  ... and {len(all_poss_events) - 30} more")

    # ==================================================================
    # POSSESSION DURATION PAIRING (Point 4)
    # ==================================================================
    print(f"\n{'=' * 65}")
    print("POINT 4: Possession duration pairing")
    print("=" * 65)

    from src.lib.pbp_accumulator import _calc_possession_secs
    for team_id in sorted(set(e["team_id"] for e in poss_starts if e["team_id"])):
        team_starts = [e for e in poss_starts if e["team_id"] == team_id]
        team_ends = [e for e in poss_ends if e["team_id"] == team_id]
        computed = _calc_possession_secs(events, team_id)

        # Manual correct pairing: match each start to its next end
        # (consuming ends as we go)
        remaining_ends = sorted(team_ends, key=lambda e: (e["secs"], e["event_id"]))
        paired_total = 0
        pair_count = 0
        for s in sorted(team_starts, key=lambda e: (e["secs"], e["event_id"])):
            for idx, e in enumerate(remaining_ends):
                if (e["secs"], e["event_id"]) > (s["secs"], s["event_id"]):
                    paired_total += e["secs"] - s["secs"]
                    pair_count += 1
                    remaining_ends.pop(idx)
                    break

        print(f"  {team_id[:30]}: starts={len(team_starts)} ends={len(team_ends)}")
        print(f"    computed (non-consuming): {computed}s")
        print(f"    correct  (consuming):    {paired_total}s  ({pair_count} pairs)")

    # ==================================================================
    # TEAM SECS (Point 18)
    # ==================================================================
    print(f"\n{'=' * 65}")
    print("POINT 18: Team secs derivation")
    print("=" * 65)

    period_ends = [e for e in events if e["event"] == "period_end"]
    if period_ends:
        game_length = max(e["secs"] for e in period_ends)
        print(f"  Game length (max period_end secs): {game_length}")
    else:
        game_length = max(e["secs"] for e in events)
        print(f"  Game length (max any event secs): {game_length}")

    for team_id in (home_team_id, away_team_id):
        team_evts = [e for e in events if e["team_id"] == team_id]
        max_team_secs = max(e["secs"] for e in team_evts) if team_evts else 0
        last_team_event = max(team_evts, key=lambda e: e["secs"]) if team_evts else None
        last_evt_name = last_team_event["event"] if last_team_event else "N/A"
        diff = game_length - max_team_secs
        print(f"  {team_id[:30]}: max(team_events)={max_team_secs}s  ({last_evt_name})  game={game_length}s  diff={diff}s")

    # ==================================================================
    # ACCUMULATED RESULT SETS
    # ==================================================================
    print(f"\n{'=' * 65}")
    print("Accumulated Team Result Sets")
    print("=" * 65)
    for team_id in (home_team_id, away_team_id):
        opp_id = away_team_id if team_id == home_team_id else home_team_id
        result = accumulate_result_set(events, "team", team_id, opp_entity_id=opp_id)
        opp_result = accumulate_result_set(events, "opp_team", team_id, opp_entity_id=opp_id)
        print(f"  {team_id[:30]}:")
        for k in ("secs", "poss", "o_poss_secs", "points", "win"):
            print(f"    {k:20s} = {result.get(k)}")
        for k in ("poss", "o_poss_secs", "points"):
            print(f"    {'opp_' + k:20s} = {opp_result.get(k)}")

    # ==================================================================
    # POINT 1: Player minutes and coverage
    # ==================================================================
    print(f"\n{'=' * 65}")
    print("POINT 1: Player minutes and lineup coverage")
    print("=" * 65)

    player_in_events = [e for e in events if e["event"] == "player_in"]
    player_out_events = [e for e in events if e["event"] == "player_out"]
    player_teams: dict[str, str] = {}
    for e in player_in_events:
        pid = e.get("player_id", "")
        if pid and pid != "0":
            player_teams[pid] = e["team_id"]

    from src.lib.pbp_accumulator import _calc_player_secs
    total_player_secs = 0
    print(f"\n  {'Player':30s} {'Team':15s} {'Secs':>6s} {'Started':>8s}")
    print(f"  {'-'*30} {'-'*15} {'-'*6} {'-'*8}")
    for player_id, team in sorted(player_teams.items(), key=lambda x: x[1]):
        secs = _calc_player_secs(events, player_id)
        if secs is not None:
            total_player_secs += secs
        in_events = [e for e in player_in_events if e.get("player_id") == player_id]
        out_events = [e for e in player_out_events if e.get("player_id") == player_id]
        started = any(e["secs"] == 0 for e in in_events)
        print(f"  {player_id[:30]:30s} {team[:15]:15s} {secs or 0:6d} {str(started):>8s}")

    lineup_size = 5
    period_ends_list = [e for e in events if e["event"] == "period_end"]
    if period_ends_list:
        game_length_secs = max(e["secs"] for e in period_ends_list)
    else:
        game_length_secs = max(e["secs"] for e in events)
    expected_secs = lineup_size * game_length_secs * 2  # 5 players x game_len x 2 teams
    coverage_pct = (total_player_secs / expected_secs * 100) if expected_secs else 0

    print(f"\n  Total player secs:     {total_player_secs}")
    print(f"  Expected (5 x {game_length_secs}s x 2):  {expected_secs}")
    print(f"  Coverage:              {coverage_pct:.1f}%")
    print(f"  Players tracked:       {len(player_teams)}")

    # ==================================================================
    # EVENT TYPE COUNTS
    # ==================================================================
    print(f"\n{'=' * 65}")
    print("Event Type Summary")
    print("=" * 65)
    type_counts = Counter(e["event"] for e in events)
    for evt, count in sorted(type_counts.items()):
        print(f"  {evt:25s} {count:5d}")

    # ==================================================================
    # PERIOD BOUNDARY ANALYSIS
    # ==================================================================
    print(f"\n{'=' * 65}")
    print("Period Boundaries")
    print("=" * 65)
    for e in events:
        if e["event"] in ("period_start", "period_end"):
            print(f"  secs={e['secs']:5d}  id={e['event_id']!s:>4}  {e['event']}")

    return events


if __name__ == "__main__":
    game_id = sys.argv[1] if len(sys.argv) > 1 else "21000001"
    season = sys.argv[2] if len(sys.argv) > 2 else "2010-11"
    home = sys.argv[3] if len(sys.argv) > 3 else "Celtics"
    away = sys.argv[4] if len(sys.argv) > 4 else "Heat"

    diagnose(game_id, season, home, away)
