# PBP Implementation Tracking

Source-of-truth design document for the play-by-play (PBP) subsystem.

---

## 1. Overview

PBP is the third major data ingestion pathway (after box-score stats and profile/roster data). It processes raw play-by-play event logs into per-game accumulated result sets for teams and players, then feeds those results into the existing `db_columns` -> staging -> intermediate -> core pipeline.

**Trigger:** `maintain_pbp` phase in `pipeline.py` (runs after `match_games`, before `maintain_profiles`).

**Flow:**

```
shufinskiy/nba_data tar.xz (one CSV per season)
  -> nbastats normalizer (per Section 3.1)
  -> standard PBPEvent rows (in-memory)
  -> derive_game_context_events (player_in/out, poss_start/end, poss_ending_ft_trip)
  -> accumulator (reads single RESULT_SET_FIELDS dict from pbp.py)
  -> team/player result sets (in-memory)
  -> db_columns mapping -> staging.team_games / staging.player_games
  -> merge_staging -> intermediate -> promote -> core
```

**Source:** `nbastats` from [shufinskiy/nba_data](https://github.com/shufinskiy/nba_data), seasons 2000/01 -- 2024/25.

**Season range:** 2000-01 through 2024-25 (the earliest and latest available in the dataset). Pre-2000 PBP is not available from any credible source.

---

## 2. Current State

| Component | Status |
|---|---|
| `maintain_pbp` in `pipeline.py` Phase literal | DONE |
| `_phase_maintain_pbp` handler in orchestrator | DONE (defined, but has syntax error -- see Known Issues) |
| `_maintain_pbp` orchestrator handler | BROKEN -- hardcoded to playbyplayv3, undefined `parse_api_response`, syntax error in imports |
| PBP dataset in `DATASETS` | DONE (registered, but hardcoded to playbyplayv3 -- needs cleanup) |
| `src/definitions/pbp.py` (event types, unified RESULT_SET_FIELDS, event groupings) | DONE |
| `src/lib/accumulator.py` (accumulate_result_set core, event derivation) | DONE |
| `lineup_size` in `leagues.py` | DONE (5 for NBA) |
| DB column mappings for all PBP-provided columns | DONE (42 columns mapped) |
| nba_data source evaluation | DONE -- Research complete. Attribution mechanisms verified across 5 eras. Source strategy finalized. |
| `min_season` on all DatasetMapping entries | DONE -- 180 entries in `db_columns.py`. `o_fouls_draws` player_games gated at "2005-06". |
| NULL->0 at extraction for stats tables | DONE -- `extract_columns_from_result` defaults None to 0 for `_STATS_TABLES`. |
| Games=0 row gating at merge | DONE -- `where_clause: "s.games > 0"` on `player_seasons` and `team_seasons` in `MERGE_TABLE_CONFIG`. |
| Stats normalization cleanup | REMOVED -- `normalize_intermediate`, `normalize_nulls_zeroes`, `_normalize_table` deleted. |
| Source-specific PBP normalizer | NOT YET -- nbastats normalizer designed but not implemented. |
| Orchestrator source-agnosticism | NOT YET -- `_maintain_pbp` hardcodes playbyplayv3. |

---

## 3. Source Strategy

### 3.1 nbastats Normalizer Design

**Source:** `nbastats` CSV (single file per season from shufinskiy/nba_data tar.xz archives).

**Key columns used:** `GAME_ID`, `EVENTNUM`, `EVENTMSGTYPE`, `EVENTMSGACTIONTYPE`, `PERIOD`, `PCTIMESTRING`, `PLAYER1_ID`, `PLAYER1_TEAM_ID`, `PLAYER2_ID`, `PERSON2TYPE`, `HOMEDESCRIPTION`, `VISITORDESCRIPTION`, `NEUTRALDESCRIPTION`, `SCORE`, `SCOREMARGIN`.

**Detection logic:**

```
For each row in nbastats CSV:
    msgtype = EVENTMSGTYPE
    p1_id   = PLAYER1_ID          # primary actor (shooter, rebounder, fouler, etc.)
    p1_team = PLAYER1_TEAM_ID
    p2_id   = PLAYER2_ID          # secondary actor
    p2_type = PERSON2TYPE         # 0 = no secondary action, 4/5 = secondary present
    desc    = HOMEDESCRIPTION + " " + VISITORDESCRIPTION
    is_3pt  = "3PT" in desc.upper()

    if msgtype == 1:  # Made FG
        emit(FG2_MAKE or FG3_MAKE, p1_id, p1_team)
        if p2_type != "0":
            emit(FG2_ASSIST or FG3_ASSIST, p2_id, p1_team)

    elif msgtype == 2:  # Missed FG
        emit(FG2_MISS or FG3_MISS, p1_id, p1_team)
        if "BLOCK" in desc.upper():
            blocker_name = parse_blocker_from_desc(desc)
            emit(BLOCK, resolve_id(blocker_name), opposing_team)

    elif msgtype == 3:  # Free Throw
        is_missed = "MISS" in desc.upper()
        emit(FT_MAKE or FT_MISS, p1_id, p1_team)

    elif msgtype == 4:  # Rebound
        is_offensive = (p1_team == offensive_team_from_prev_event)
        emit(O_REB or D_REB, p1_id, p1_team)

    elif msgtype == 5:  # Turnover
        emit(TURNOVER, p1_id, p1_team)
        if p2_type != "0":
            emit(STEAL, p2_id, opposing_team)

    elif msgtype == 6:  # Foul
        emit(FOUL, p1_id, p1_team)
        if EVENTMSGACTIONTYPE in ("4", "26"):  # offensive foul or charge
            emit(O_FOUL_DRAW, p2_id, opposing_team)

    elif msgtype == 8:  # Substitution
        # Description: "SUB: {PLAYER2_NAME} FOR {PLAYER1_NAME}"
        #   => PLAYER2 enters, PLAYER1 leaves
        emit(PLAYER_IN,  p2_id, team_from_context)
        emit(PLAYER_OUT, p1_id, team_from_context)

    elif msgtype == 12:  # Period start
        emit(PERIOD_START, ...)
```

**3PT detection:** Description text contains "3PT" for all three-point attempts. Verified 100% accurate across 5 test eras (2000--2024).

**Blocker resolution:** The description names the blocker (e.g. "Ratliff BLOCK") but does not provide a PLAYER2_ID. The normalizer must parse the blocker name and resolve it to a player ID via the team's roster. This is the only description-to-ID resolution needed.

### 3.2 Verified EVENTMSGTYPE Reference

| EVENTMSGTYPE | Meaning | Attribution |
|---|---|---|
| 1 | Made FG | PERSON2TYPE != 0 => assist (PLAYER2_ID = assister) |
| 2 | Missed FG | Parse desc for "BLOCK" to detect blocks |
| 3 | Free Throw (made + missed) | "MISS" in desc => missed FT |
| 4 | Rebound | Off/def by team context |
| 5 | Turnover | PERSON2TYPE != 0 => steal (PLAYER2_ID = stealer) |
| 6 | Foul | PLAYER1 = fouler. ACTIONTYPE 4/26 => offensive. PLAYER2 = fouled player |
| 7 | Violation | -- |
| 8 | Substitution | "SUB: P2 FOR P1" => P2 enters, P1 leaves |
| 9 | Timeout | -- |
| 10 | Jump Ball | -- |
| 12 | Start of Period | -- |
| 13 | End of Period | Always 4 per game. NOT used for missed FTs |
| 18 | End of Game | Appears in 2016+ seasons |

### 3.3 Attribution Summary

| Stat | Detection | Seasons |
|---|---|---|
| FG2/FG3 split | Description contains "3PT" | 2000--2025 |
| Assist | PERSON2TYPE != 0 on MSGTYPE=1 | 2000--2025 |
| Steal | PERSON2TYPE != 0 on MSGTYPE=5 | 2000--2025 |
| Block | Description contains "BLOCK" on MSGTYPE=2 | 2000--2025 |
| Offensive Foul Draw (team) | MSGTYPE=6, ACTIONTYPE IN (4, 26) | 2000--2025 |
| Offensive Foul Draw (player) | MSGTYPE=6, ACTIONTYPE IN (4, 26), PLAYER2_ID | 2005--2025 |
| Rebound (off/def) | MSGTYPE=4, team context | 2000--2025 |
| FT (made/missed) | MSGTYPE=3, "MISS" keyword | 2000--2025 |

---

## 4. Data Gating

### 4.1 Column-level: `min_season`

Every `DatasetMapping` entry in `db_columns.py` has an explicit `min_season`. For most columns it is `None` (available from the dataset's first season). `extract_columns_from_result` skips columns where `season < min_season`. The column stays NULL -- nothing wrote to it.

**`o_fouls_draws`** player_games has `min_season: "2005-06"` because PLAYER2_ID is not populated for offensive fouls in 2000--2004. Team-level is ungated (available from 2000).

### 4.2 Row-level: `games = 0` at merge

`MERGE_TABLE_CONFIG` has `where_clause: "s.games > 0"` on `player_seasons` and `team_seasons`. Rows where the entity played zero games are filtered out during `_merge_staging` and never reach intermediate or core.

### 4.3 NULL->0 for available stats columns

In `extract_columns_from_result`, for stats tables (`player_seasons`, `team_seasons`, `player_games`, `team_games`), if a column passes `min_season` gating but the extracted value is None, it defaults to 0. Non-stats tables preserve NULL for optional fields.

Null-like API values (`None`, `""`, `"NaN"`, complex types) are all handled by `safe_int`'s existing try/except -- they collapse to None, then to 0.

---

## 5. Result Sets

Each game produces 2 result sets. Defined in `src/definitions/pbp.py` as `RESULT_SET_FIELDS`.

### 5.1 Team Result Set

| Field | Operation | Scope / Handler |
|---|---|---|
| Base count fields (17) | count | `team` scope |
| `opp_*` count fields (17) | count | `opp_team` scope |
| `points` | derived | `fg2m*2 + fg3m*3 + ftm` |
| `assist_points` | derived | `fg2_assists*2 + fg3_assists*3` |
| `secs` | special | `team_secs` |
| `o_poss_secs` | special | `team_o_poss_secs` |
| `d_poss_secs` | special | `team_d_poss_secs` |

### 5.2 Player Result Set

| Field | Operation | Scope / Handler |
|---|---|---|
| Base count fields (17) | count | `player` scope |
| `opp_*` count fields (17) | count | `opp_player` scope |
| `on_*` count fields (17) | count | `on_player` scope |
| `win` | special | `player_win` |
| `secs` | special | `player_secs` |
| `o_poss_secs` | special | `player_o_poss_secs` |
| `d_poss_secs` | special | `player_d_poss_secs` |

### 5.3 Full Field List

**Base (17):** `fg2m`, `fg2a`, `fg3m`, `fg3a`, `ftm`, `fta`, `o_rebs`, `d_rebs`, `turnovers`, `steals`, `blocks`, `fouls`, `o_fouls_draws`, `fg2_assists`, `fg3_assists`, `poss`, `poss_ending_ft_trips`

**Opponent mirrors (17):** `opp_fg2m`, `opp_fg2a`, `opp_fg3m`, `opp_fg3a`, `opp_ftm`, `opp_fta`, `opp_o_rebs`, `opp_d_rebs`, `opp_turnovers`, `opp_steals`, `opp_blocks`, `opp_fouls`, `opp_o_fouls_draws`, `opp_fg2_assists`, `opp_fg3_assists`, `opp_poss`, `opp_poss_ending_ft_trips`

**On-court mirrors (17):** `on_fg2m`, `on_fg2a`, `on_fg3m`, `on_fg3a`, `on_ftm`, `on_fta`, `on_o_rebs`, `on_d_rebs`, `on_turnovers`, `on_steals`, `on_blocks`, `on_fouls`, `on_o_fouls_draws`, `on_fg2_assists`, `on_fg3_assists`, `on_poss`, `on_poss_ending_ft_trips`

**Derived (2):** `points`, `assist_points`

**Special (4):** `secs`, `o_poss_secs`, `d_poss_secs`, `win`

---

## 6. Architecture

### 6.1 File Layout

```
src/definitions/
    pbp.py              # Pure config: PBPEvent, PBPEventType, event groupings,
                        #   unified RESULT_SET_FIELDS dict. No functions.

src/lib/
    accumulator.py      # Code: accumulate_result_set(), event derivation,
                        #   special handlers, partitioning logic.

src/sources/nba_data/
    (normalizer)        # TBD -- nbastats CSV -> PBPEvent rows
```

**Convention:** definitions = config/dicts/constants. lib = code. source = source-specific code. No mixing.

### 6.2 `src/definitions/pbp.py` -- Pure Config

Contains:
1. `PBPEventType` -- Literal of all 25 standard event types
2. `PBPEvent` -- TypedDict for the standard event row shape (real contract)
3. Standard event groupings (`FG_MAKE_EVENTS`, `FT_ALL_EVENTS`, etc.)
4. `RESULT_SET_FIELDS` -- single unified dict of every result-set field

No functions. No source-specific constants.

### 6.3 `src/lib/accumulator.py` -- Code

Contains:
1. `accumulate_result_set()` -- single generic core, iterates RESULT_SET_FIELDS
2. `derive_game_context_events()` -- substitution rename + possession derivation
3. Special handlers (`team_secs`, `player_secs`, `player_win`, `*_poss_secs`)
4. Partitioning (`_build_partitions`) and computation helpers

### 6.4 `RESULT_SET_FIELDS` Structure

```python
{
    "op":           "count" | "derived" | "special",
    "result_sets":  {result_set_name: scope_or_handler_or_none},
    # count only:
    "events":       [event_type, ...],
    # derived only:
    "formula":      "fg2m*2 + fg3m*3 + ftm",
    "fields":       ["fg2m", "fg3m", "ftm"],
}
```

All `opp_*` and `on_*` fields are explicit entries. No programmatic generation.

---

## 7. DB Column Mappings

All 42 PBP-relevant columns are mapped in `src/definitions/db_columns.py` with `pbp_stats` dataset entries.

**Base fields (17):** `fg2m`, `fg2a`, `fg3m`, `fg3a`, `ftm`, `fta`, `o_rebs`, `d_rebs`, `turnovers`, `steals`, `blocks`, `fouls`, `o_fouls_draws`, `fg2_assists`, `fg3_assists`, `poss`, `poss_ending_ft_trips`

**Opponent mirrors (17):** `opp_*` variants of all base fields

**On-court mirrors (17):** `on_*` variants of all base fields

**Derived (2):** `points` (team), `assist_points` (team + player)

**Special (4):** `secs`, `o_poss_secs`, `d_poss_secs`, `win`

Every `DatasetMapping` entry has an explicit `min_season`. `o_fouls_draws` player_games is gated at `"2005-06"`. All others are `None`.

---

## 8. Decisions

| # | Decision | Resolution | Status |
|---|---|---|---|
| D-1 | PBP source | `nbastats` from shufinskiy/nba_data, seasons 2000--2025 | DECIDED |
| D-2 | Dataset key | `pbp_stats` | DECIDED |
| D-3 | Standard PBP persistence | In-memory only (PBPEvent never written to DB) | DECIDED |
| D-4 | Execution strategy | Custom `_maintain_pbp` handler, `iterates_by: "game"` | DECIDED |
| D-5 | 3PT detection | Description text "3PT" keyword (not shotdetail join) | DECIDED |
| D-6 | Assist/steal detection | PERSON2TYPE != 0 on EVENTMSGTYPE 1/5 | DECIDED |
| D-7 | Block detection | Description text "BLOCK" keyword + blocker name resolution | DECIDED |
| D-8 | Offensive foul detection | EVENTMSGACTIONTYPE IN (4, 26) | DECIDED |
| D-9 | o_fouls_draws player gap | `min_season: "2005-06"` gates pre-2005 player attribution | DECIDED |
| D-10 | Source season range | 2000-01 to 2024-25 | DECIDED |
| D-11 | Data gating | Column: `min_season`. Row: `where_clause` on merge. NULL->0: extraction time for stats tables. | DECIDED |
| D-12 | Possession tracking | Derived from event sequences | DECIDED |
| D-13 | Player in/out tracking | Infer from EVENTMSGTYPE=8 + `lineup_size` from leagues | DECIDED |
| D-14 | FT trip rules | Per-league config in `leagues.py` | DECIDED |
| D-15 | Definitions/lib boundary | pbp.py = pure config. accumulator.py = code. No mixing. | DECIDED |
| D-16 | League operational config | `lineup_size` added to `League` TypedDict (5 for NBA) | DECIDED |
| D-17 | Result set structure | Single unified `RESULT_SET_FIELDS` dict. All opp/on fields explicit. | DECIDED |

---

## 9. Known Issues

### 9.1 `_maintain_pbp` Syntax Error (orchestrator.py ~L2453)

The import block inside `_maintain_pbp` has a bare `derive_game_context_events,` line that is not inside a `from` statement. This is a syntax error and blocks the function from loading.

### 9.2 `_maintain_pbp` Is Source-Specific

The handler hardcodes:
- `class_name` default to `"playbyplayv3"`
- Direct import from `src.sources.nba_api.client`
- Calls undefined `parse_api_response` function
- NBA-specific params (`"league_id": "00"`)

Needs to be made source-agnostic: delegate fetching to the source module, expect `PBPEvent` rows back.

### 9.3 `datasets.py` PBP Entry Hardcodes playbyplayv3

The `pbp_stats` dataset entry hardcodes `"class_name": "playbyplayv3"` and `"endpoint": "playbyplayv3"`. These should point to the nbastats normalizer instead.

---

## 10. Implementation Phases

### Phase 0: Source Data Research
- [x] Download sample games from nba_data across 5 eras
- [x] Answer all 10 research questions
- [x] Update field confidence table based on findings
- [x] Resolve o_fouls_draws availability (2000-2004 gap identified, min_season solution designed and implemented)

### Phase 0.5: Pre-PBP Cleanup
- [x] Rename `pbp_data` -> `pbp_stats` in all db_columns.py entries
- [x] Implement `row_filters` consumer (extract.py + orchestrator)
- [x] Define `_phase_maintain_pbp` in orchestrator

### Phase 1: PBP Infrastructure
- [x] Create `src/definitions/pbp.py` -- PBPEventType, PBPEvent, unified RESULT_SET_FIELDS, event groupings
- [x] Create `src/lib/accumulator.py` -- accumulate_result_set core, event derivation
- [x] Add `lineup_size` to `League` TypedDict in `leagues.py` (5 for NBA)
- [x] Wire db_columns: all 42 PBP columns mapped
- [x] Add `min_season` to all DatasetMapping entries
- [x] Wire `min_season` gating into `extract_columns_from_result` + executor call sites
- [x] Gate games=0 rows at merge (`where_clause` in MERGE_TABLE_CONFIG)
- [x] Remove stats normalization cleanup (delete `normalize_*` from cleanup.py/pipeline.py/orchestrator.py)

### Phase 1.5: Orchestrator Cleanup
- [ ] Fix syntax error in `_maintain_pbp` import block
- [ ] Remove playbyplayv3 hardcoding from `_maintain_pbp`
- [ ] Remove playbyplayv3 hardcoding from `datasets.py` pbp_stats entry
- [ ] Make `_maintain_pbp` source-agnostic (delegate fetch to source, expect PBPEvent rows)

### Phase 2: Player Result Set + Lineups
- [ ] Implement player_in/player_out inference from event sequences using `lineup_size`
- [ ] Implement on-court event tracking

### Phase 3: Possession Logic
- [ ] Implement `poss_start`/`poss_end` event derivation
- [ ] Implement `poss_ending_ft_trip` with league-specific rules
- [ ] Add FT trip rules to `leagues.py`

### Phase 4: Source Selection + Normalizer
- [x] Finalize source selection: nbastats-only for all seasons 2000--2025
- [ ] Implement nbastats normalizer (Section 3.1)
- [ ] Register nbastats dataset in `DATASETS`
- [ ] Wire `min_season` gating into `_build_pbp_column_map` for PBP path

### Phase 5: Hardening
- [ ] Coverage tracking integration
- [ ] Error handling for incomplete PBP data
- [ ] Performance optimization for full-season backfill
