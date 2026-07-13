# PBP Tracking Document

> Source of truth for PBP implementation details, decisions, and plans.
> Spec lives in `pbp.md`. This document tracks the engineering decisions
> and implementation plan for building the generic PBP system.

---

## 1. Overview

Play-by-play (PBP) data provides granular, event-level basketball data that
enables stats not available from aggregated sources:

- **Opponent stats**: what the other team scored while a player/team was on court
- **On-court team stats**: what a player's team scored while they were on court
- **Lineup data**: stats for every 5v5 (or 3v3) combination of players
- **Possession-level timing**: offensive/defensive possession seconds

These stats cannot be derived from LeagueGameLog or season-level aggregations.
PBP is the only source.

## 2. Pipeline Position & Purpose

```
maintain_games -> match_games -> seed_game_coverage -> maintain_pbp -> maintain_profiles
```

- `maintain_pbp` runs **after** game discovery/matching (games already in DB)
- `maintain_pbp` runs **before** profiles (no dependency, just ordering)
- PBP is **additive only**: any column already satisfied by `player_game_stats`
  or `team_game_stats` is left alone. PBP fills the gaps.
- PBP has **lower authority** than game_stats due to higher error potential
  from manual PBP parsing. Game_stats is the primary source.
- First-write-wins staging semantics ensure game_stats values are preserved.

## 3. Architecture

The PBP pipeline has 5 stages per game:

```
1. FETCH      -> Source-specific API call per game
2. NORMALIZE  -> Source-specific -> standard PBP event list
3. ACCUMULATE -> Source-agnostic: events -> result_sets
4. EXTRACT    -> Config-driven: db_columns mapping reads result_sets
5. WRITE      -> Bulk upsert to staging tables
```

### Stage 1: Fetch
- Per-game execution tier (new -- no existing dataset does this)
- Source-specific: each source has its own fetch logic
- Rate-limit aware: NBA API is 0.25 req/sec

### Stage 2: Normalize
- Source-specific handler converts raw API response to standard PBP event list
- Output is the **standard PBP format** (defined in Section 4)
- This is the only source-specific code in the entire pipeline

### Stage 3: Accumulate
- Source-agnostic: works on standard PBP events only
- Processes the event list to produce 5 result_sets (Section 6)
- Handles possession tracking, lineup inference, stat accumulation
- Operates entirely in-memory

### Stage 4: Extract
- Reuses existing `extract_columns_from_result` from `src/lib/extract.py`
- Accumulator output is formatted as API-compatible `{headers, rowSet}` dicts
- Config-driven: `db_columns.py` `pbp_data` dataset_mapping determines
  which fields to extract into which tables

### Stage 5: Write
- Batched bulk upserts to `staging.player_games`, `staging.team_games`,
  and (Phase 2) `staging.lineups`
- First-write-wins: PBP values only written if the cell is NULL
  (game_stats already-populated cells are preserved)

## 4. Standard PBP Format

The normalized PBP event list is the source-agnostic contract between the
source-specific normalizer and the generic accumulator.

### 4.1 Event Schema

Each event is a dict with these fields:

| Field       | Type   | Description                                     |
|-------------|--------|-------------------------------------------------|
| `identity`  | str    | Source identity (e.g. `"nba_id"`)               |
| `game_id`   | str    | External game ID                                |
| `secs`      | int    | Total seconds elapsed (accumulated, all periods)|
| `event_id`  | int    | Serial integer per event (internal, 1-based)    |
| `team_id`   | str    | External team ID that performed the event       |
| `player_id` | str    | External player ID (None for context events)    |
| `event`     | str    | Event type (see Section 4.2)                    |

Additional source-specific fields may be present but are not consumed by
the accumulator. The normalizer is responsible for mapping source-specific
timestamp formats to `secs`.

### 4.2 Event Types

**Direct actions** (offensive):

| Event         | Description                     | Points |
|---------------|---------------------------------|--------|
| `fg2_make`    | Made 2-point field goal         | 2      |
| `fg2_miss`    | Missed 2-point field goal       | 0      |
| `fg3_make`    | Made 3-point field goal         | 3      |
| `fg3_miss`    | Missed 3-point field goal       | 0      |
| `ft1_make`    | Made 1-point free throw         | 1      |
| `ft1_miss`    | Missed 1-point free throw       | 0      |
| `ft2_make`    | Made 2-point free throw         | 2      |
| `ft2_miss`    | Missed 2-point free throw       | 0      |
| `ft3_make`    | Made 3-point free throw         | 3      |
| `ft3_miss`    | Missed 3-point free throw       | 0      |
| `turnover`    | Turnover                        | 0      |
| `foul`        | Committed foul                  | 0      |

**Direct actions** (rebounding):

| Event   | Description                                                        |
|---------|--------------------------------------------------------------------|
| `o_reb` | Offensive rebound (includes OOB after miss FT/FG that don't end possession) |
| `d_reb` | Defensive rebound (includes OOB after miss FT/FG that end possession)      |

**Secondary actions** (may not be provided by every source):

| Event          | Description                                    |
|----------------|------------------------------------------------|
| `fg2_assist`   | Assist on a made 2-point FG                    |
| `fg3_assist`   | Assist on a made 3-point FG                    |
| `block`        | Block on an opponent's missed FG               |
| `steal`        | Steal from an opponent's turnover              |
| `o_foul_draw`  | Drew an offensive foul from an opponent         |

**Possession events**:

| Event                 | Description                                                               |
|-----------------------|---------------------------------------------------------------------------|
| `poss_start`          | Possession begins                                                         |
| `poss_end`            | Possession ends (always precedes poss_start, except at period/OT start)   |
| `poss_ending_ft_trip` | Standard FT trip that could end possession (no and-ones, no techs, no flagrants) |

**Game context events**:

| Event          | Description                                    |
|----------------|------------------------------------------------|
| `period_start` | Start of a regulation period                   |
| `period_end`   | End of a regulation period                     |
| `ot_start`     | Start of overtime                              |
| `ot_end`       | End of overtime                                |
| `jump_ball_win`| Jump ball won                                  |
| `out_of_bounds`| Ball goes out of bounds (live play only)       |
| `player_in`    | Player enters the game (may be inferred)       |
| `player_out`   | Player leaves the game (may be inferred)       |

### 4.3 Event Roles

When accumulating stats, each event is classified by its role relative to
the entity being measured:

| Role         | Definition                                                              |
|--------------|-------------------------------------------------------------------------|
| `team`       | `team_id` matches the team being measured                               |
| `player`     | `player_id` matches the player being measured                           |
| `opp_team`   | `team_id` does NOT match the team being measured                        |
| `opp_player` | `player_id` belongs to the opposing team (within player's on-court stints) |
| `on_player`  | `player_id` belongs to the same team (within player's on-court stints)      |

## 5. Source Handler Interface

Each source provides a handler that fetches and normalizes PBP for one game.

```
src/sources/<source>/pbp_handler.py  ->  fetch_and_normalize(game_id) -> List[Event]
```

### 5.1 Handler Requirements

The handler must:
- Accept a game identifier (external game ID)
- Return a list of event dicts in standard PBP format (Section 4)
- Parse source-specific timestamps into cumulative `secs`
- Assign sequential `event_id` values
- Map source-specific event codes to standard event types
- Infer `player_in`/`player_out` events if not provided by source
- Emit `poss_start`/`poss_end` events when the source provides possession data;
  otherwise leave them for the accumulator to infer

### 5.2 Source-Specific Considerations

The handler is the only place source-specific logic lives. The accumulator
and all downstream code is source-agnostic.

NBA considerations (for future implementation):
- Which endpoint: TBD (`playbyplayv2`, `playbyplayv3`, live API)
- FT trip classification: identify standard FTs vs and-ones vs technicals
  vs flagrants. Source may provide this directly or it may need inference.
- Possession attribution: source may or may not provide explicit data

## 6. Result Sets

The accumulator produces 5 result sets from the standard event list.
These are formatted as API-compatible `{headers, rowSet}` dicts so the
existing `extract_columns_from_result` can consume them directly.

### 6.1 `games` Result Set

One row per game. Provides game metadata from PBP context. Primarily used
for validation and for the accumulator's internal logic (home/away team
resolution). Not currently mapped to any `db_columns` entries (game
metadata comes from `maintain_games`).

| Column         | Description                    |
|----------------|--------------------------------|
| `GAME_ID`      | External game ID               |
| `HOME_TEAM_ID` | Home team external ID          |
| `AWAY_TEAM_ID` | Away team external ID          |
| `DATE`         | Game date                      |

### 6.2 `team` Result Set

One row per team per game. Written to `staging.team_games`.

| Column                | Source                                                              |
|-----------------------|---------------------------------------------------------------------|
| `TEAM_ID`             | External team ID                                                    |
| `win`                 | Team total points > opponent total points (weighted FT values)      |
| `poss`                | Count of `poss_start` events where `team_id` matches                |
| `secs`                | Last event's `secs` value                                           |
| `o_poss_secs`         | Sum of secs between `poss_start` team and `poss_end` team events    |
| `d_poss_secs`         | Sum of secs between `poss_start` opp_team and `poss_end` opp_team   |
| `fg2m` / `fg2a`       | Count of `fg2_make` / (`fg2_make` + `fg2_miss`) team events        |
| `fg3m` / `fg3a`       | Count of `fg3_make` / (`fg3_make` + `fg3_miss`) team events        |
| `ftm` / `fta`         | Sum of ft_make / (ft_make + ft_miss) team events                    |
| `poss_ending_ft_trips`| Count of `poss_ending_ft_trip` team events                          |
| `fg2_assists`         | Count of `fg2_assist` team events                                   |
| `fg3_assists`         | Count of `fg3_assist` team events                                   |
| `turnovers`           | Count of `turnover` team events                                     |
| `o_rebs` / `d_rebs`   | Count of `o_reb` / `d_reb` team events                             |
| `blocks`              | Count of `block` team events                                        |
| `steals`              | Count of `steal` team events                                        |
| `o_fouls_draws`       | Count of `o_foul_draw` team events                                  |
| `fouls`               | Count of `foul` team events                                         |
| `opp_poss`            | Count of `poss_start` opp_team events                               |
| `opp_fg2m` ... `opp_turnovers` | Same stat logic but scoped to opp_team events          |

**Win calculation**: Points are computed as:
`sum(fg2_make * 2) + sum(fg3_make * 3) + sum(ft1_make * 1) + sum(ft2_make * 2) + sum(ft3_make * 3)`

FT events carry their point value (`ft1_make` = 1pt, `ft2_make` = 2pt,
`ft3_make` = 3pt). This is more precise than the simplified formula in
`pbp.md` which assumes uniform 1pt free throws.

### 6.3 `player` Result Set

One row per player per game. Written to `staging.player_games`.

Includes all stat columns from the `team` result set (scoped to the
player's individual events), plus:

| Column                | Source                                                              |
|-----------------------|---------------------------------------------------------------------|
| `PLAYER_ID`           | External player ID                                                  |
| `TEAM_ID`             | Player's team for this game                                         |
| `win`                 | Same as team win (player's team's score > opponent's)               |
| `poss`                | Count of `poss_start` on_player events (possessions while on court) |
| `secs`                | Sum of durations across all player stints                           |
| `o_poss_secs`         | Sum of secs for on_team possessions during player stints            |
| `d_poss_secs`         | Sum of secs for opp_player possessions during player stints         |
| `opp_fg2m` ... `opp_turnovers` | Opponent player stats while target is on court          |

### 6.4 `opp_player` Result Set

One row per player per game. Written to `staging.player_games`.

These are the opponent *team's* aggregate stats while the target player
was on court (not individual opponent player stats).

| Column     | Source                                                         |
|------------|----------------------------------------------------------------|
| `PLAYER_ID`| Player being measured                                          |
| `fg2m` ... `turnovers` | Opponent team's stats during player's on-court stints |

### 6.5 `on_player` Result Set

One row per player per game. Written to `staging.player_games`.

These are the target player's *team's* aggregate stats while the player
was on court (not just the player's own stats).

| Column     | Source                                                         |
|------------|----------------------------------------------------------------|
| `PLAYER_ID`| Player being measured                                          |
| `fg2m` ... `turnovers` | Player's team's stats during player's on-court stints  |

### 6.6 `lineup` Result Set

One row per player per unique lineup combination per game. Written to
`staging.lineups` (new table).

A "lineup" is defined as a unique set of players on court simultaneously
(home side + away side). If the same 10 players appear in multiple stints,
their stats are combined into one lineup row per player.

| Column     | Source                                                         |
|------------|----------------------------------------------------------------|
| `PLAYER_ID`| Player being measured                                          |
| `TEAM_ID`  | Player's team                                                  |
| `LINEUP_ID`| Surrogate key for the unique player combination                |
| `SECS`     | Duration this specific lineup was on court                     |
| `fg2m` ... `turnovers` | Player's stats within this lineup combination      |
| `opp_fg2m` ... `opp_turnovers` | Opponent stats within this lineup       |

See Section 9 for full lineup design.

## 7. Dataset Definition

### 7.1 Naming Decision

The existing `db_columns.py` uses `"pbp_data"` as the dataset name in all
PBP mappings (~40+ references). The dataset in `datasets.py` should use the
same name for consistency.

**Decision**: Dataset name = `"pbp_data"`, identity = `"nba_id"`.

### 7.2 Dataset Entry

```python
# In DATASETS["nba_id"]
"pbp_data": {
    "min_season": None,
    "max_season": None,
    "source": "nba_api",           # source-specific handler
    "phase": "maintain_pbp",
    "coverage": "current",
    "execution_tier": "per_game",  # new tier -- one call per game
    "row_filters": None,
    "target_tables": [
        "staging.player_games",
        "staging.team_games",
    ],
    "prune_tables": None,
    "source_mapping": {
        # Source-specific: which PBP endpoint to use
        # TBD when endpoint is chosen
    },
},
```

**Note**: `execution_tier: "per_game"` is a new tier not currently in the
`ExecutionTier` literal. This needs to be added to `datasets.py`.

### 7.3 Execution Tier

The existing tiers are: `per_league`, `per_team`, `per_player`, `per_game`.

Adding `per_game` requires:
1. Update `ExecutionTier` literal in `datasets.py`
2. Implement per-game iteration in the orchestrator phase handler

## 8. db_columns Integration

### 8.1 Current State

PBP column mappings already exist in `db_columns.py` using the `pbp_data`
dataset name. These map to result_sets: `player`, `team`, `opp_player`,
`opp_team`, `on_player`.

Columns with existing PBP mappings:
- `poss_ending_ft_trips` (player, team, opp_player, opp_team, on_player)
- All `opp_*` columns (opp_player, opp_team)
- All `on_*` columns (on_player)

### 8.2 Columns Needing PBP Mappings

These columns currently have NO per-game source or could benefit from PBP:

| Column          | Current Source                    | PBP Result Set |
|-----------------|-----------------------------------|----------------|
| `o_poss_secs`   | `dataset_mapping: None`           | `team`, `player` |
| `d_poss_secs`   | `dataset_mapping: None`           | `team`, `player` |
| `o_fouls_draws` | `dataset_mapping: None`           | `team`, `player` |
| `fg2_assists`   | Not yet in db_columns (new col)   | `team`, `player` |
| `fg3_assists`   | Not yet in db_columns (new col)   | `team`, `player` |

### 8.3 Additive-Only Rule

Columns that already have `player_game_stats` or `team_game_stats` mappings
keep those as-is. PBP does NOT add duplicate mappings for:
- `fg2m`, `fg2a`, `fg3m`, `fg3a`, `ftm`, `fta`
- `o_rebs`, `d_rebs`, `assists`, `turnovers`, `blocks`, `steals`, `fouls`
- `poss`

PBP only fills columns that have no per-game source, or provides
opponent/on-court variants that game_stats cannot supply.

## 9. Lineup Tracking

### 9.1 Feasibility Assessment

**Storage**: 
- ~15-25 substitutions per NBA game -> ~10-20 unique lineups per game
- 10 rows per lineup (one per player on court)
- ~100-200 lineup rows per game
- Per season (~1200 games): ~120K-240K rows
- 20 years: ~2.4-4.8M rows
- Oracle free tier (20GB): well under 1GB with indexes. **Feasible.**

**Computation**:
- Lineup inference is O(n) where n = events per game (~400-500)
- Accumulation per lineup is O(m) where m = stints per lineup (~2-5)
- Total per game: trivial. **Feasible.**

### 9.2 Lineup Inference Algorithm

Most sources do not provide lineup data. The accumulator must infer
who is on the court at any given time from the event stream.

**Algorithm**:

1. **Track active roster** from `player_in`/`player_out` events
2. **Infer period start lineups**: at `period_start`/`ot_start`, scan
   subsequent events to determine which 5 (or N) players from each team
   record the first events. Retroactively emit `player_in` events for
   them at the period start.
3. **Infer period end lineups**: at `period_end`/`ot_end`, emit
   `player_out` events for all players still on court.
4. **Track stints**: between each pair of substitution events, record
   the 10 (or 2N) players on court and accumulate their events.
5. **Merge stints**: if the same 10-player combination appears in
   multiple stints, combine their stats.

**Key assumption**: every player who plays in a period will record at
least one event (shot, rebound, foul, turnover, etc.) within that period.
This allows retroactive lineup construction.

### 9.3 Lineups Table Schema

New table: `staging.lineups`

```
Primary key: [league_code, game_id, lineup_id, player_id]
Foreign keys: game_id -> core.games, player_id -> core.players,
              team_id -> core.teams, league_code -> core.leagues
```

| Column      | Type      | Description                                  |
|-------------|-----------|----------------------------------------------|
| identity    | TEXT      | Source identity                               |
| league_code | TEXT      | League code                                  |
| ext_game_id | TEXT      | External game ID                             |
| game_id     | BIGINT    | Resolved core game ID                        |
| lineup_id   | TEXT      | Hash/surrogate for the player combination    |
| player_id   | BIGINT    | Resolved core player ID                      |
| team_id     | BIGINT    | Resolved core team ID                        |
| ext_player_id | TEXT    | External player ID                           |
| ext_team_id | TEXT      | External team ID                             |
| secs        | SMALLINT  | Duration this lineup was on court            |
| fg2m ... fouls | SMALLINT | Player's individual stats within this lineup |
| opp_fg2m ... opp_turnovers | SMALLINT | Opponent stats while this lineup was on court |

### 9.4 Lineup ID Generation

The lineup ID represents a unique combination of players on court. Options:

- **Option A**: Sort all player IDs (home + away), join with `-`, hash.
  e.g. `"abc-def-ghi-jkl-mno-pqr-stu-vwx-yz1-234"`
- **Option B**: Separate home and away lineups (5+5). ID = sorted home IDs
  + sorted away IDs.
- **Option C**: Surrogate integer key per game.

**Recommendation**: Option A for simplicity and debuggability. The hash
is the natural key; a surrogate `lineup_id` integer can be generated if
needed for FK performance.

### 9.5 League Config Addition

```python
# In LEAGUES["NBA"]
"players_per_side": 5,  # 5 for 5v5, 3 for 3x3
```

This controls:
- How many players per team on court at once
- Lineup ID generation (5+5 = 10 player combo, or 3+3 = 6)
- Lineup table column count

## 10. League Config & Schema Changes

### 10.1 League Config Additions

```python
# In LEAGUES[league_code]
"players_per_side": 5,           # 5 for 5v5, 3 for 3x3
"ft_trip_types": {               # which FT types are "standard" (poss-ending)
    "standard": True,            # regular free throws
    "and_one": False,            # FTA after made FG
    "technical": False,          # technical FTs
    "flagrant": False,           # flagrant FTs
},
```

### 10.2 Schema Changes

**New table**: `staging.lineups` (see Section 9.3)

**No changes** to existing `staging.player_games` or `staging.team_games`
tables -- all new columns are already defined in `db_columns.py` schema.

### 10.3 New db_columns Entries

Two new columns to add:

```python
"fg2_assists": {
    "type": "SMALLINT",
    "tables": ["team_games", "player_games"],
    "nullable": True,
    "default": None,
    "dataset_mapping": {
        "NBA": {
            "nba_id": {
                "player_games": {
                    "pbp_data": {"field": "fg2_assists", "result_set": "player"},
                },
                "team_games": {
                    "pbp_data": {"field": "fg2_assists", "result_set": "team"},
                },
            }
        }
    },
},
"fg3_assists": {
    "type": "SMALLINT",
    "tables": ["team_games", "player_games"],
    "nullable": True,
    "default": None,
    "dataset_mapping": {
        "NBA": {
            "nba_id": {
                "player_games": {
                    "pbp_data": {"field": "fg3_assists", "result_set": "player"},
                },
                "team_games": {
                    "pbp_data": {"field": "fg3_assists", "result_set": "team"},
                },
            }
        }
    },
},
```

## 11. Execution Model

### 11.1 Orchestrator Phase Handler

`_phase_maintain_pbp` (currently referenced but undefined) needs to:

1. Find all games that need PBP processing (from game_coverages or
   staging.games where game is complete)
2. Load the source handler for the identity's source
3. For each game (respecting rate limits):
   a. Call source handler -> get standard event list
   b. Run accumulator -> get result_sets
   c. Format as API-compatible response
   d. Extract columns via `extract_columns_from_result`
4. Batch write extracted rows to staging tables

### 11.2 Rate Limiting Strategy

NBA API: 0.25 req/sec (4 seconds between requests).

For a season with ~1200 games:
- Fetch time: ~1200 * 4sec = ~80 minutes
- Accumulation: negligible (in-memory)
- Write: batched, fast

Optimization: accumulate results for N games in memory before writing.
This reduces DB round trips without increasing API pressure.

### 11.3 Batch Size

Recommended: accumulate 50-100 games worth of results before flushing to DB.
This keeps memory usage low (~50-100 games * ~200 rows * ~50 columns = ~5MB)
while reducing DB write frequency.

## 12. Source-Agnostic Design

### Where Source-Specific Code Lives

Only ONE place: `src/sources/<source>/pbp_handler.py`

Everything else is generic:
- Standard PBP format: source-agnostic (Section 4)
- Accumulator: source-agnostic (works on standard events)
- Result set production: source-agnostic
- db_columns extraction: source-agnostic (config-driven)
- Orchestrator phase handler: source-agnostic (dispatches to handler)

### Adding a New Source

To add PBP support for a new source:
1. Create `src/sources/<new_source>/pbp_handler.py`
2. Implement `fetch_and_normalize(ext_game_id) -> List[Event]`
3. Register in `src/sources/registry.py`
4. Add dataset entry in `datasets.py` with `source: "new_source"`
5. No changes to accumulator, db_columns, or orchestrator needed

## 13. File Changes Summary

| File | Change | Phase |
|------|--------|-------|
| `src/definitions/datasets.py` | Add `pbp_data` dataset, add `per_game` tier | 1 |
| `src/definitions/db_columns.py` | Add `fg2_assists`, `fg3_assists` columns; add PBP mappings to `o_poss_secs`, `d_poss_secs`, `o_fouls_draws` | 1 |
| `src/definitions/leagues.py` | Add `players_per_side`, `ft_trip_types` | 1 |
| `src/definitions/pipeline.py` | No change (already has `maintain_pbp`) | - |
| `src/orchestrator.py` | Implement `_phase_maintain_pbp` | 1 |
| `src/sources/nba_api/pbp_handler.py` | New: NBA PBP standardization | 2 |
| `src/sources/registry.py` | Register PBP handler | 2 |
| `src/lib/pbp/` | New package: accumulator, events, lineups, possessions | 1 |
| `src/definitions/schema.py` | Add `staging.lineups` table | 1 |

## 14. Decisions Log

| ID | Decision | Status | Resolution |
|----|----------|--------|------------|
| D1 | Dataset name: `pbp_data` vs `pbp_stats` | **DECIDED** | `pbp_data` -- matches existing db_columns wiring |
| D2 | Intermediate PBP storage | **DECIDED** | In-memory only. No staging table for raw events. |
| D3 | Lineup scope | **DECIDED** | Tackle from start. Feasible on Oracle free tier. |
| D4 | Possession source | **DECIDED** | Inference by default; source-provided when available |
| D5 | Batch vs sequential | **DECIDED** | Fetch sequential (rate limits), accumulate per-game, write batched |
| D6 | PBP vs game_stats authority | **DECIDED** | Additive only. game_stats is primary. PBP fills gaps. |
| D7 | `assist` column strategy | **OPEN** | See Section 15 |
| D8 | Possession model details | **OPEN** | See Section 15 |
| D9 | PBP data retention | **OPEN** | See Section 15 |

## 15. Open Questions

### Q1: `assists` vs `fg2_assists` + `fg3_assists`

The existing `assists` column maps to NBA API game stats. PBP provides
`fg2_assist` and `fg3_assist` as separate events.

**Options**:
- A: Add `fg2_assists` and `fg3_assists` columns. Keep existing `assists`
  from game_stats. (PBP doesn't provide a generic assist count.)
- B: Add `fg2_assists` and `fg3_assists`. Also map `assists` to PBP as
  `fg2_assists + fg3_assists` (derived). This would duplicate game_stats.

**Recommendation**: Option A -- don't add a PBP mapping for `assists`
since game_stats already covers it. Only add the new granular columns.

### Q2: Possession Inference Fallback

When the source handler doesn't emit `poss_start`/`poss_end` events,
should the accumulator infer them?

**Options**:
- A: Accumulator has a built-in heuristic (score changes + turnovers +
  rebounds = possession change indicators)
- B: Raise an error / skip possession-dependent stats
- C: Source handler is ALWAYS responsible (if source can't provide,
  handler must infer before returning)

**Recommendation**: Option C -- keep possession logic in the source
handler where source-specific knowledge is available. The accumulator
consumes standard events only.

### Q3: PBP Data Retention

Should raw PBP events be persisted for debugging?

**Options**:
- A: Purely in-memory, never persisted (current plan)
- B: Write to `staging.pbp_events`, truncate after processing
- C: Write to `staging.pbp_events`, retain for audit

**Recommendation**: Start with A. Add B later if debugging needs arise.
The schema for `staging.pbp_events` is straightforward and can be added
retroactively.

### Q4: `ftm`/`fta` Weighted or Counted

For `ftm` and `fta` in the result sets, should these be:
- A: Simple counts of FT make/miss events (regardless of point value)
- B: Weighted by point value (ft1=1, ft2=2, ft3=3)

**Recommendation**: Option A -- `ftm`/`fta` are counts (standard box score
convention). Point-weighted scoring is only for the `win` calculation.

---

## Implementation Phases

### Phase 1: Core Pipeline (Generic PBP System)

- [ ] Add `per_game` execution tier to `datasets.py`
- [ ] Add `pbp_data` dataset entry to `datasets.py`
- [ ] Create `src/lib/pbp/` package:
  - [ ] `events.py` -- event type constants, role classification
  - [ ] `accumulator.py` -- stat accumulation logic
  - [ ] `possessions.py` -- possession tracking from events
  - [ ] `lineups.py` -- lineup inference and tracking
- [ ] Implement `_phase_maintain_pbp` in orchestrator
- [ ] Add `staging.lineups` table to schema.py
- [ ] Add `players_per_side` and `ft_trip_types` to leagues.py
- [ ] Add `fg2_assists`, `fg3_assists` columns to db_columns.py
- [ ] Add PBP mappings to `o_poss_secs`, `d_poss_secs`, `o_fouls_draws`
- [ ] Write unit tests for accumulator and lineup inference

### Phase 2: NBA Source Handler

- [ ] Choose PBP endpoint (playbyplayv2/v3, live API)
- [ ] Create `src/sources/nba_api/pbp_handler.py`
- [ ] Register handler in registry.py
- [ ] Implement NBA-specific event code mapping
- [ ] Implement NBA-specific timestamp parsing
- [ ] Implement NBA-specific FT trip classification
- [ ] Integration testing with real NBA game data

### Phase 3: Lineup Table & db_columns Wiring

- [ ] Implement lineup result_set production in accumulator
- [ ] Add lineup db_columns entries (if needed)
- [ ] Wire lineup write path in orchestrator
- [ ] Test lineup inference accuracy
- [ ] Validate storage impact on Oracle free tier
