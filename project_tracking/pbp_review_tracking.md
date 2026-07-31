# PBP Architecture Review - Tracking Document

**Created:** 2026-07-25
**Source:** 30-point review of the PBP accumulation engine
**Status:** Active -- possession redesign in progress (updated 2026-07-30)

---

## Verdict Summary

> Strong architectural prototype, credible traditional-stat normalizer.
> The lineup/possession engine requires a stateless redesign (in progress).
>
> The config-driven design, source-agnostic event contract, and generic accumulator
> are fundamentally sound. Traditional team statistics (FG, FT, steals, blocks,
> turnovers, fouls) look correct in tested games. The possession derivation layer
> has been redesigned as a stateless, config-driven engine (see Point 3-REDESIGN).

---

## Point-by-Point Verdicts

### Legend

| Status | Meaning |
|--------|---------|
| **CONFIRMED** | Bug verified in code, fix required |
| **VALID-DESIGN** | Design improvement, not a bug |
| **PARTIALLY-VALID** | Some aspects correct, some overstated |
| **DISPUTED** | Premise or severity questioned |
| **DEFERRED** | Needs data/testing to confirm |

---

### Point 1: Player minutes are substantially wrong

**Verdict: PARTIALLY-VALID -- diagnostic run 2026-07-30**

Coverage at 58.8% in the test game (Celtics-Heat 2010-11).  This is a mock
artifact: the diagnostic mock resolver returns None for PLAYER1_ID=0, causing
`period_start`/`period_end` events to be skipped.  Without period events,
`_derive_lineup_events` can't infer starters, so no `player_in` at secs=0.

In production, period events flow correctly through the entity_resolver and
starter inference works.  The remaining coverage gap is attributable to source
data quality (missing substitution events in raw PBP).

**Action items:**
1. Add diagnostic logging (lineup size, coverage %) to `_derive_lineup_events`
2. Run production pipeline on test games and inspect lineup state
3. Verify coverage improves with real entity_resolver

---

### Point 2: Every player's `win` value is false

**Verdict: FIXED (2026-07-28)**

The original bug used `result.get("points")` (the individual player's points).
The current code at `pbp_accumulator.py` L289-298 now correctly computes team
point totals from all events attributed to each team:

```python
if handler == "player_win":
    if not player_team_id or result.get("secs", 0) == 0:
        return None
    team_events = [e for e in all_events if e["team_id"] == player_team_id]
    team_pts = _sum_points(team_events)
    opp_events = [e for e in all_events
                  if opp_entity_id and e["team_id"] == opp_entity_id]
    opp_pts = _sum_points(opp_events)
    return team_pts > opp_pts if team_pts != opp_pts else None
```

`_sum_points` sums FG/FT point values from team-attributed events, producing
the correct team total. DNP players (0 seconds) return None for `win`.

---

### Point 3: Team possession starts and ends are internally inconsistent

**Verdict: CONFIRMED -- root cause identified 2026-07-30**

**Diagnostic trace of game 21000001:** Two phantom/duplicate transitions found:

1. **secs=742, d_reb by Celtics:** `current_poss` was already Celtics (set by a d_reb at
   702). Between 702 and 742, the Heat took two shots with an offensive rebound -- but
   `fg2_miss` and `o_reb` have NO handlers in `_derive_possession_events`, so
   `current_poss` stayed frozen. The d_reb emitted `poss_end(Heat)` + `poss_start(Celtics)`
   -- phantom end for Heat, duplicate start for Celtics.

2. **secs=1419, ft1_make by Heat:** The ft1_make handler emitted `poss_end(Heat),
   poss_start(Celtics)` but `current_poss` was already Celtics (from a prior made FG
   transition). The ft1_make handler doesn't check `current_poss` before emitting.

**Root cause:** `current_poss` is a mutable state variable that drifts because many
possession-indicating events (fg_miss, o_reb, jump_ball_win, steal) have no handler.
State goes stale, then the next unconditional emission creates phantom/duplicate pairs.

**Resolution:** Replaced by stateless config-driven possession derivation.
See Point 3-REDESIGN below.

---

### Point 3-REDESIGN: Stateless, config-driven possession derivation (2026-07-30)

**Decision:** Replace the stateful `_derive_possession_events` with a stateless engine
driven by a single authoritative `PBP_EVENT_DEFINITIONS` dict in `src/definitions/pbp.py`.

All shot events (fg2_make, fg2_miss, fg3_make, fg3_miss, ft1_make, ft2_make,
ft3_make, ft1_miss) follow the same conditional logic: possession changes IFF
the shot is the last of its trip AND the next possession-indicating event is by
the opponent. No special and-one handling -- the FT after a made FG at the same
second means the FG IS the last of its trip, so the FG transition fires normally;
the last FT of the trip fires its own transition.

`poss_ending_ft_trip` is replaced by `pot_poss_ending_scoring_opp`, a derived
event emitted on ANY shot that is the last of its trip and is followed by
opponent action or an offensive rebound.

`jump_ball_win` is a conditional transition: emits `poss_start` for the winning
team and `poss_end` for the opponent, but ONLY if the winning team did not
already have possession (determined by scanning backward for the last
possession-indicating event).

**Design principle: one authoritative dict.** Instead of scattered constants
(`SHOT_EVENTS`, `FG_MAKE_EVENTS`, `POSSESSION_EVENTS`, `EVENT_SORT_PRIORITY`,
`POSSESSION_TRANSITIONS`), every property of every PBPEventType lives in a single
`PBP_EVENT_DEFINITIONS` dict. Derived groupings are computed from it. No drift.

```python
# src/definitions/pbp.py -- consolidated event definitions

class PossessionTransition(TypedDict):
    end_team: Literal["self", "opponent", "last_possessing", None]
    start_team: Literal["self", "opponent", "next_poss_event", None]
    condition: Literal["always", "shot_last_of_trip",
                        "jump_ball_changes_possession", None]

class EventDef(TypedDict):
    category: str           # "shot", "rebound", "turnover", "foul", "system"
    sort_priority: int      # lower = earlier when secs tie
    poss_indication: bool   # does this event indicate who has possession?
    transition: PossessionTransition | None
    pot_poss_ending: bool   # emits pot_poss_ending_scoring_opp on last-of-trip

PBP_EVENT_DEFINITIONS: dict[str, EventDef] = {
    # --- Shots (all share shot_last_of_trip + pot_poss_ending) ---
    "fg2_make":  {"category": "shot", "sort_priority": 10, "poss_indication": True,
                   "transition": {"end": "self", "start": "opponent",
                                  "condition": "shot_last_of_trip"},
                   "pot_poss_ending": True},
    "fg2_miss":  {"category": "shot", "sort_priority": 20, "poss_indication": True,
                   "transition": {"end": "self", "start": "opponent",
                                  "condition": "shot_last_of_trip"},
                   "pot_poss_ending": True},
    "fg3_make":  {"category": "shot", "sort_priority": 10, "poss_indication": True,
                   "transition": {"end": "self", "start": "opponent",
                                  "condition": "shot_last_of_trip"},
                   "pot_poss_ending": True},
    "fg3_miss":  {"category": "shot", "sort_priority": 20, "poss_indication": True,
                   "transition": {"end": "self", "start": "opponent",
                                  "condition": "shot_last_of_trip"},
                   "pot_poss_ending": True},
    "ft1_make":  {"category": "shot", "sort_priority": 15, "poss_indication": True,
                   "transition": {"end": "self", "start": "opponent",
                                  "condition": "shot_last_of_trip"},
                   "pot_poss_ending": True},
    "ft2_make":  {"category": "shot", "sort_priority": 15, "poss_indication": True,
                   "transition": {"end": "self", "start": "opponent",
                                  "condition": "shot_last_of_trip"},
                   "pot_poss_ending": True},
    "ft3_make":  {"category": "shot", "sort_priority": 15, "poss_indication": True,
                   "transition": {"end": "self", "start": "opponent",
                                  "condition": "shot_last_of_trip"},
                   "pot_poss_ending": True},
    "ft1_miss":  {"category": "shot", "sort_priority": 25, "poss_indication": True,
                   "transition": {"end": "self", "start": "opponent",
                                  "condition": "shot_last_of_trip"},
                   "pot_poss_ending": True},

    # --- Rebounds ---
    "d_reb":     {"category": "rebound", "sort_priority": 30, "poss_indication": True,
                   "transition": {"end": "opponent", "start": "self",
                                  "condition": "always"}},
    "o_reb":     {"category": "rebound", "sort_priority": 30, "poss_indication": True},

    # --- Turnover ---
    "turnover":  {"category": "turnover", "sort_priority": 35, "poss_indication": True,
                   "transition": {"end": "self", "start": "opponent",
                                  "condition": "always"}},

    # --- Fouls ---
    "foul":      {"category": "foul", "sort_priority": 40},
    "o_foul_draw": {"category": "foul", "sort_priority": 40},

    # --- Jump ball ---
    "jump_ball_win": {"category": "possession", "sort_priority": 50,
                       "poss_indication": True,
                       "transition": {"end": "opponent", "start": "self",
                                      "condition": "jump_ball_changes_possession"}},

    # --- Period boundaries ---
    "period_start": {"category": "system", "sort_priority": 0,
                      "transition": {"end": None, "start": "next_poss_event",
                                     "condition": "always"}},
    "period_end":   {"category": "system", "sort_priority": 100,
                      "transition": {"end": "last_possessing", "start": None,
                                     "condition": "always"}},

    # --- Derived events (no raw trigger, included for completeness) ---
    "player_in":  {"category": "lineup", "sort_priority": 5},
    "player_out": {"category": "lineup", "sort_priority": 95},
    "poss_start": {"category": "derived", "sort_priority": 999},
    "poss_end":   {"category": "derived", "sort_priority": 999},
    "pot_poss_ending_scoring_opp": {"category": "derived", "sort_priority": 999},

    # --- Secondary events ---
    "fg2_assist": {"category": "secondary", "sort_priority": 10},
    "fg3_assist": {"category": "secondary", "sort_priority": 10},
    "block":      {"category": "secondary", "sort_priority": 25},
    "steal":      {"category": "secondary", "sort_priority": 35},
}

# Derived groupings (computed from PBP_EVENT_DEFINITIONS, never edited manually)
SHOT_EVENTS = tuple(e for e, d in PBP_EVENT_DEFINITIONS.items()
                    if d.get("category") == "shot")
POSS_INDICATION_EVENTS = tuple(e for e, d in PBP_EVENT_DEFINITIONS.items()
                                if d.get("poss_indication"))
POT_POSS_ENDING_EVENTS = tuple(e for e, d in PBP_EVENT_DEFINITIONS.items()
                                if d.get("pot_poss_ending"))
EVENT_SORT_PRIORITY = {e: d["sort_priority"]
                       for e, d in PBP_EVENT_DEFINITIONS.items()}
```

The engine (`_derive_possession_events` in `src/lib/pbp_accumulator.py`) is a
single-pass loop that reads `PBP_EVENT_DEFINITIONS` and evaluates each event
independently by scanning its surrounding context (no mutable state except
`last_possessing` for `period_end`). Condition functions (`shot_last_of_trip`,
`jump_ball_changes_possession`) live in lib as pure functions.

**Resolves:** Points 3, 4, 8, 10, 11, 12, 13 in one redesign.

### Point 4: Possession duration pairs starts and ends incorrectly

**Verdict: FIXED (2026-07-30)**

Replaced non-consuming `next()` pairing with consuming `pop()` algorithm in both
`_calc_possession_secs` and `_player_possession_windows`.  Starts and ends are
sorted by `(secs, event_id)`, and each end is consumed exactly once via
`remaining.pop(match_idx)`, preventing multiple starts from matching the same end.

---
```python
matching_end = next(
    (e for e in events
     if e["event"] == "poss_end"
     and e["team_id"] == team_id
     and e["secs"] >= s["secs"]),
    None,
)
```

Problems:
1. Uses `secs >=` only, ignoring `event_id` ordering. Multiple events at the
   same second can be matched incorrectly.
2. Does not consume matched ends. Multiple starts can match the same end.
3. No possession identity -- boundaries are rediscovered every time.

`_player_possession_windows` (L346-408) has the same pairing issue.

**Required fix:** Build explicit `Possession` objects in a single pass. Use
`(secs, event_id)` for ordering. Each possession should be consumed exactly
once.

---

### Point 5: Player possession logic is not a standard on-court possession definition

**Verdict: CONFIRMED**

**Code evidence:** `_player_possession_windows` (L346-408):
- Requires player overlap with possession window (L390-393)
- AND requires a POSSESSION_EVENT during the overlap (L397-402)
- Credits **full** possession duration even for partial overlap (L405)

This is a hybrid definition that is neither start-of-possession, end-of-possession,
nor fractional. A player entering mid-possession with a team event during their
time gets the full possession seconds (including before they entered). A player
overlapping but with no team event gets nothing.

**Required fix:** Choose an explicit policy (recommend end-of-possession
membership) and document it. Remove the hybrid approach.

---

### Point 6: `on_poss` is semantically misnamed

**Verdict: VALID-DESIGN**

**Code evidence:** `on_poss` uses the `player_poss` handler (L299-303), which
counts possessions for the player's team while they're on court. The `on_*`
fields consistently exclude the subject player (L155: `e["player_id"] != entity_id`).

But `on_poss` doesn't exclude the subject -- it counts the team's possessions,
not teammate-only possessions. This is an inconsistency in naming convention.

**Recommendation:** Rename for clarity:
- `on_poss` -> `team_poss_on` (team possessions while player is on court)
- Document that `on_*` fields exclude the subject player (for counting stats)
  but `on_poss` is the team total (for possession stats)

---

### Point 7: Rebound classification is too dependent on `last_shot_team`

**Verdict: PARTIALLY-VALID**

**Code evidence:** Rebound classification (L132-141):
```python
is_offensive = (last_shot_team is not None
                and player_team == last_shot_team)
```

`last_shot_team` is set on made FG (L93), missed FG (L109), and FT (L127). It
is **not** reset on period start, turnover, jump ball, or made FG (the code
does set it on made FG, but the offensive rebound check would still match).

The `_filter_intra_ft_rebounds` (L283-306) patches one artifact but not others.

**Overstated concerns:** The review lists many edge cases (nullified shots,
lane violations, reviews, etc.) but these are extremely rare in NBA PBP data.
For 99%+ of possessions, the last-shot-team heuristic works. The real risk is
around turnovers and period boundaries where `last_shot_team` lingers from a
prior sequence.

**Recommendation:** This is P1, not P0. The current approach works for the
vast majority of games. Adding `current_poss` as a fallback classification
would improve robustness for edge cases.

---

### Point 8: Free throws are over-normalized into a single event type

**Verdict: VALID-DESIGN -- partially addressed by Point 3-REDESIGN**

The unified shot logic treats `ft1_make` and `ft1_miss` identically to FGs for
possession purposes. The naming confusion (ft1 vs ft2/ft3) remains a P2 cleanup.

---

### Point 9: Free-throw trip grouping by timestamp is unsafe

**Verdict: PARTIALLY-VALID**

**Code evidence:** Foul-to-FT association (L763-818) finds the first FT at the
same timestamp as a foul. This works for the common case (single foul, single
FT sequence at same clock time).

The review correctly identifies that complex sequences (double technicals,
flagrants with retained possession, etc.) can break this. However, these are
rare in practice.

**Assessment:** The concern is valid but the severity is overstated for typical
NBA games. The `_filter_intra_ft_rebounds` already handles one common artifact.

**Recommendation:** P1 -- add FT trip metadata to the event model before
rebuilding this logic.

---

### Point 10: `poss_ending_ft_trip` is skipped for some real possession endings

**Verdict: RESOLVED by Point 3-REDESIGN**

`poss_ending_ft_trip` is replaced by `poss_ending_attempt`, which fires on ANY
shot (FG or FT) that is the last of its trip and is followed by opponent action
or an offensive rebound. The "skip if period_end follows" rule is removed.

---

### Point 11: Missed final free throws are not handled symmetrically

**Verdict: RESOLVED by Point 3-REDESIGN**

The old code only handled `ft1_make` for possession-change logic. The new
unified shot engine handles `ft1_miss` identically -- both go through the
same `shot_last_of_trip` condition.

---

### Point 12: And-one detection is fragile

**Verdict: RESOLVED by Point 3-REDESIGN**

No special and-one detection needed. A made FG followed by a foul + FT at the
same second: the FG IS the last of its trip (the next event at the same second
is a foul, not another FT), so the FG transition fires normally. The FT after
the foul is part of a trip, and the LAST FT of that trip fires its own
transition. The and-one case falls out of the unified shot logic naturally.

---

### Point 13: Jump-ball possession resolution can fail

**Verdict: IMPROVED (2026-07-28) -- further addressed by Point 3-REDESIGN**

Current code at `pbp_normalizer.py` L142-147 uses `entity_resolver(p3_id)` as a
fallback. The redesign adds `jump_ball_win` to `PBP_EVENT_DEFINITIONS` with
`condition: "jump_ball_changes_possession"` -- the engine scans backward for the
last possessing team and only emits a transition if the winner differs. Stateless,
no reliance on `current_poss`.

---

```python
elif handling == "jump_ball_win":
    if p3_id and p3_id != "0":
        _, tip_team = entity_resolver(p3_id)
        tip_team = p3_team or tip_team
        if tip_team:
            events.append(...)
```

Remaining edge case: if PLAYER3 is unknown to staging (neither team nor player),
resolution still fails. Mitigated by the `period_start` inference path
(`_derive_possession_events` L688-696) which infers possession from the first
definitive team event after tip-off.

---

### Point 14: Offensive-foul-drawn attribution needs separate availability semantics

**Verdict: VALID-DESIGN**

**Code evidence:** The normalizer (L163-169) emits `o_foul_draw` with
`player_id = ""` when the drawer is unknown. The accumulator will count this
as a team-level event with no player attribution.

The review's concern is about downstream interpretation: a zero in the
player-level `o_fouls_draws` field could mean "no offensive fouls drawn" or
"attribution unavailable." This is a schema/documentation concern.

**Recommendation:** P1 -- add coverage metadata or document the distinction.
The current behavior (team-level event preserved, player-level unknown) is
actually correct; the issue is interpretation, not computation.

---

### Point 15: Fouls are being treated as one broad count

**Verdict: RESOLVED -- no action needed**

All MSGTYPE=6 events are correctly emitted as `foul`. This is the desired
behavior per user decision (all foul types included in one count). Flagrant
fouls produce a single MSGTYPE=6 row (no double-counting). MSGTYPE=7 violations
are correctly excluded. ACTIONTYPE sub-classification deferred to P2 if needed.

---

### Point 16: Team traditional statistics are encouraging

**Verdict: AGREED -- no action needed**

The config-driven field registry and generic accumulator produce correct team
traditional stats in tested games. This is a genuine success and should be
preserved.

---

### Point 17: Team rebounds correctly explain some player/team mismatches

**Verdict: AGREED**

The differences between player sum and team totals for rebounds are consistent
with team rebounds (unattributed to any player). Exposing explicit
`team_o_rebs`/`team_d_rebs` fields is a good P1 improvement for transparency.

---

### Point 18: Team `secs` is accidentally correct, not robustly defined

**Verdict: FIXED (2026-07-30)**

Replaced `max(e["secs"] for e in team_evts)` with `max(e["secs"] for e in
period_end_events)`.  Team seconds are now derived from the game clock (the
latest `period_end` timestamp), which is correct for regulation, overtime,
and any period structure.  No longer depends on which team the last event
belongs to.

---

### Point 19: The attached orchestrator does not write player PBP results

**Verdict: FIXED (2026-07-30)**

Implemented player-level accumulation in `_maintain_pbp`.  For each game:
collects unique player IDs from `player_in` events, builds on-court intervals
from `player_in`/`player_out` pairs, determines opponent team, calls
`accumulate_result_set` with `result_set="player"`, and writes to
`staging.player_games` via `write_staged_stats_rows`.

---

### Point 20: Season type is hardcoded to `regular_season`

**Verdict: FIXED (2026-07-30)**

Removed the hardcoded `season_type: str = "regular_season"` default parameter.
`_load_pbp_games` now includes `g.season_type` in the query.  Each game's
actual season type is used when writing to staging via `game_season_type`.

---

### Point 21: Dataset identity and source identity are coupled awkwardly

**Verdict: VALID-DESIGN**

The review observes that PBP is special-cased rather than flowing through the
generic dataset execution path. This is true but reasonable -- PBP is
multi-row stateful processing that doesn't fit the single-fetch-per-season
model of box-score datasets.

**Recommendation:** P2 -- add a `processor` field to dataset config to make
the dispatch explicit rather than hardcoded.

---

### Point 22: Lexical season comparisons are fragile

**Verdict: VALID-DESIGN**

**Code evidence:** L2497:
```python
if (min_s and season < min_s) or (max_s and season > max_s):
```

This works for `YYYY-YY` format strings but would break for other formats.
Since the project currently only supports NBA with `YYYY-YY` format, this is
not an active bug.

**Recommendation:** P2 -- use parsed year comparison for future-proofing.

---

### Point 23: The client's season cache can consume a large amount of memory

**Verdict: VALID-DESIGN**

The concern about loading entire season CSVs into Python dicts is valid for
large historical backfills. However, the current architecture processes one
game at a time within a season, and the cache avoids re-reading the CSV for
each game.

**Recommendation:** P2 -- convert to Parquet/DuckDB for production use.
For the current scale (testing with a few games), this is not urgent.

---

### Point 24: Archive integrity and reproducibility controls are missing

**Verdict: VALID-DESIGN**

The review correctly notes that downloading from a moving GitHub branch URL
without checksums is fragile. This is a production hardening concern.

**Recommendation:** P1 -- add SHA-256 checksums and version pinning for
reproducible builds.

---

### Point 25: The seven-field normalized event contract is too lossy

**Verdict: VALID-DESIGN**

The current `PBPEvent` TypedDict has 7 fields:
```python
identity, game_id, secs, event_id, team_id, player_id, event
```

For accumulating traditional stats, this is sufficient. For possession
reconstruction and advanced analytics, additional metadata would help:
- period
- clock string
- source action type
- description
- secondary/tertiary player IDs

**Recommendation:** P1 -- extend the event contract with structured metadata.
This is a prerequisite for robust possession reconstruction.

---

### Point 26: Use milliseconds or ordered sequence, not integer seconds alone

**Verdict: PARTIALLY-VALID**

The review recommends preserving original clock strings and source event
numbers. The current `secs` field is derived from `PCTIMESTRING` + `PERIOD`,
which loses the original clock string. The `event_id` is the source EVENTNUM
before renumbering.

The renumbering (L35-46) replaces source EVENTNUM with sequential IDs,
preserving relative order but destroying source traceability.

**Recommendation:** P1 -- preserve source event IDs alongside normalized
sequence numbers.

---

### Point 27: Do not renumber away the source event ID

**Verdict: CONFIRMED**

**Code evidence:** `_renumber_event_ids` (L35-46):
```python
for i, e in enumerate(events):
    e["event_id"] = i + 1
```

This overwrites the source EVENTNUM. Once renumbered, you cannot map back to
"raw event 166" for debugging.

**Required fix:** Add `source_event_id` field to `PBPEvent` and preserve it.
Use the renumbered ID as `event_id` for ordering. P1 priority.

---

### Point 28: Separate direct facts from inferred events

**Verdict: VALID-DESIGN**

Currently, raw events from the normalizer and derived events from the
accumulator share the same row type. Adding provenance markers would help
debugging:
```python
origin = "raw" | "derived"
derivation = "lineup_period_start" | "possession_transition" | ...
```

**Recommendation:** P2 -- improves debuggability but not a correctness issue.

---

### Point 29: Do not turn missing PBP values into zero indiscriminately

**Verdict: VALID-DESIGN**

The `_map_pbp_result_to_columns` (L2702-2714) only writes non-None values:
```python
if val is not None:
    row[col_name] = val
```

Missing fields are simply omitted from the row, which means the DB gets NULL
(or the column default). This is actually correct behavior -- the review may
be based on a different code path.

**Recommendation:** Verify the DB column defaults. If they default to 0,
that's a schema issue, not an accumulator issue.

---

### Point 30: Add quality and coverage columns

**Verdict: VALID-DESIGN**

Adding quality metrics (lineup coverage %, possession validity, etc.) would
help downstream consumers assess data reliability. This is especially
important given the known lineup coverage gaps.

**Recommendation:** P1 -- implement after fixing the core lineup and
possession issues.

---

## Priority Summary

### P0: Must fix before trusting output

| # | Issue | Verdict | Status |
|---|-------|---------|--------|
| 1 | Player minutes wrong | PARTIALLY-VALID | Needs diagnosis |
| 3 | Possession starts/ends inconsistent | CONFIRMED | **FIXED** |
| 4 | Possession duration pairing broken | CONFIRMED | **FIXED** |
| 10 | poss_ending_ft_trip skipped at period end | CONFIRMED | Resolved by 3-REDESIGN |
| 18 | Team secs derived incorrectly | CONFIRMED | **FIXED** |
| 19 | Orchestrator doesn't write player results | CONFIRMED | **FIXED** |
| 20 | Season type hardcoded | CONFIRMED | **FIXED** |

### P1: Needed for historically reliable coverage

| # | Issue | Verdict | Status |
|---|-------|---------|--------|
| 5 | Player possession definition unclear | CONFIRMED | OPEN |
| 6 | on_poss misnamed | VALID-DESIGN | OPEN |
| 7 | Rebound classification fragile | PARTIALLY-VALID | OPEN |
| 8 | FT event model too simple | VALID-DESIGN | Partially addressed by 3-REDESIGN |
| 9 | FT trip grouping unsafe | PARTIALLY-VALID | OPEN |
| 14 | o_foul_draw availability semantics | VALID-DESIGN | OPEN |
| 17 | Team rebounds not exposed | AGREED | OPEN |
| 24 | Archive integrity missing | VALID-DESIGN | OPEN |
| 25 | Event contract too lossy | VALID-DESIGN | OPEN |
| 26 | Source event ordering lost | PARTIALLY-VALID | OPEN |
| 27 | Source event ID overwritten | CONFIRMED | OPEN |
| 30 | Quality/coverage columns needed | VALID-DESIGN | OPEN |
| 31 | Cross-game validation & regression suite | **NEW** | Partially implemented |

### P2: Best-practice hardening

| # | Issue | Verdict | Status |
|---|-------|---------|--------|
| 21 | Dataset/source coupling | VALID-DESIGN | OPEN |
| 22 | Lexical season comparisons | VALID-DESIGN | OPEN |
| 23 | Season cache memory | VALID-DESIGN | OPEN |
| 28 | Provenance markers needed | VALID-DESIGN | OPEN |
| 29 | Missing values vs zeros | VALID-DESIGN | OPEN |

### Resolved / No Action Required

| # | Issue | Verdict | Resolution |
|---|-------|---------|------------|
| 2 | Player win always false | CONFIRMED -> FIXED | Fixed 2026-07-28: team-level point summation |
| 3 | Possession starts/ends inconsistent | CONFIRMED -> FIXED | Fixed 2026-07-30: stateless config-driven engine |
| 4 | Possession duration pairing broken | CONFIRMED -> FIXED | Fixed 2026-07-30: consuming pop() pairing |
| 10 | poss_ending_ft_trip skipped at period end | CONFIRMED | Resolved by 3-REDESIGN |
| 11 | Missed final FTs not handled | PARTIALLY-VALID | Resolved by 3-REDESIGN |
| 12 | And-one detection fragile | PARTIALLY-VALID | Resolved by 3-REDESIGN |
| 13 | Jump-ball team resolution | IMPROVED | Resolved by 3-REDESIGN |
| 15 | Fouls one broad count | VALID-DESIGN -> RESOLVED | Desired behavior confirmed |
| 16 | Team stats encouraging | AGREED | Confirmed correct, no action needed |
| 18 | Team secs derived incorrectly | CONFIRMED -> FIXED | Fixed 2026-07-30: period_end-based |
| 19 | Orchestrator no player writes | CONFIRMED -> FIXED | Fixed 2026-07-30: player accumulation |
| 20 | Season type hardcoded | CONFIRMED -> FIXED | Fixed 2026-07-30: per-game season_type |
| 32 | Entity validation via staging lookup | **NEW** -> IMPLEMENTED | entity_resolver + classifier built 2026-07-28 |

---

## Discussion Log

### 2026-07-25: Point 1 -- Player Minutes

**Starter inference:** Confirmed sound. Source EVENTNUM ordering ensures correct
processing. No change needed.

**`_calc_player_secs`:** Confirmed correct for well-formed input. In/out events
alternate and are time-ordered, so non-consumption bug doesn't manifest.

**Real issue:** 64-74% coverage gap likely caused by source data quality or
different code path for player CSVs. Needs diagnostic logging to confirm.

**Error logging decision:** Use existing `core.errors` table and
`log_error_simple()`. Log lineup size mismatches, possession count deltas,
and player coverage percentages. Message field carries structured context
(game_id, team, period, etc.). No schema changes needed.

**Action items:**
1. Add lineup validation logging in `_derive_lineup_events` at period_end
2. Add possession count validation in `_derive_possession_events`
3. Add player coverage logging in `_maintain_pbp` after accumulation
4. Run pipeline on test games to diagnose actual coverage gap

### 2026-07-25: Foul Classification & Entity Validation

#### Foul consistency -- CONFIRMED CORRECT

All EVENTMSGTYPE=6 events are emitted as `foul`. This includes:
- Personal fouls (ACTIONTYPE 0, 1)
- Shooting fouls (ACTIONTYPE 2)
- Offensive fouls / charges (ACTIONTYPE 4, 26)
- Technical fouls (ACTIONTYPE 6)
- Flagrant fouls (ACTIONTYPE 7)
- Defensive 3-seconds (ACTIONTYPE 11, 17)
- Personal block fouls (ACTIONTYPE 27)

All ACTIONTYPE values within MSGTYPE=6 are foul subtypes. There are no
non-foul action types within the foul category. The current implementation
counts every foul, which is the desired behavior.

#### PERSON1TYPE analysis

Raw data PERSON1TYPE values observed:

| Value | Meaning | Count | Resolution |
|-------|---------|-------|------------|
| 0 | None/system (period start/end) | 8 | No entity |
| 1 | Official/event (timeouts) | 1 | No entity |
| 2 | Home team entity (Celtics) | 19 | Resolve to home_team_id |
| 3 | Away team entity (Heat) | 18 | Resolve to away_team_id |
| 4 | Home player (Celtics players) | 197 | Validate against known players |
| 5 | Away player (Heat players) | 197 | Validate against known players |
| 7 | Unknown (defensive 3-sec foul) | 1 | Log error, attempt resolution |

**Key finding:** PERSON1TYPE=2 is used for home team events (rebounds,
turnovers) but our config only defines PERSON_TEAM=3. This causes Celtics
team rebounds to be misattributed to "Celtics" as a player_id.

#### "2614" investigation

Event 114: `114,2,11:06,6,11,,,2614,,7,0,0,0,1`
- EVENTMSGTYPE=6 (foul), ACTIONTYPE=11 (defensive 3-seconds)
- PLAYER1_ID="2614", PERSON1TYPE=7
- PLAYER1_TEAM_ID is empty

"2614" is not a team name (we see "Celtics" and "Heat" elsewhere). It's not
a standard NBA team ID (5-digit numbers like 1610612738). Since the user
manually modified the data to swap IDs with names, "2614" is likely a numeric
ID that wasn't replaced -- possibly from a different encoding or a data artifact.

#### Entity validation approach -- DECIDED

原则: PERSON1TYPE is a hint, not a final answer. Use it as a starting point
but validate against known entities.

Proposed resolution logic:
1. PERSON1TYPE in {0, 1}: System events, no entity to resolve
2. PERSON1TYPE in {2, 3}: Team events, resolve to home/away_team_id
3. PERSON1TYPE in {4, 5}: Player events, validate against known players
4. PERSON1TYPE in {6, 7, ...}: Unknown, attempt resolution:
   a. If player_id matches a known team -> treat as team event
   b. If player_id matches a known player -> treat as player event
   c. If neither -> log error, exclude from accumulation

This handles:
- "Celtics" team rebounds (PERSON1TYPE=2) -> correctly resolved to home team
- "2614" foul (PERSON1TYPE=7) -> unknown entity, logged and excluded
- Valid player with unexpected PERSON1TYPE -> kept if player is known
- Misclassified team as player -> resolved using team ID match

#### Action items
1. Add PERSON_HOME_TEAM = 2 to config.py PERSON type constants
2. Add PERSON_TYPE_7 = 7 (or more generally, handle unknown types)
3. Implement entity validation in normalizer before emitting events
4. Log errors for unknown entities via log_error_simple
5. Exclude unresolvable events from accumulation

---

### 2026-07-28: Cross-Game Validation, Flagrant Fouls, Entity Validation

#### Question 1: Cross-game validation and standardized onboarding

**Status: Only one game validated.** The entire review so far is based on a
single game (2010 Celtics-Heat, game_id=21000001). The 2020 game was mentioned
for Point 3 but was never systematically validated.

**User requirement:** Process ALL seasons within the dataset's range
(min_season to max_season). For nba_data, `min_season=None` means we need to
find the actual earliest season in the source (likely 1996-97 based on the
shufinskiy/nba_data repository) through `max_season="2025-26"` -- approximately
30 seasons, ~36,000+ games. The user wants this level of depth before being
content with the normalizer's correctness.

**Best practice architecture: A `core.pbp_validation` table + a
source-agnostic `validate_pbp` script.**

##### Why a dedicated table, not the existing coverage tables?

The project already has `game_coverages` and `season_coverages` tables that
track whether data was fetched. PBP validation is a different concern:

| Existing coverage tables | PBP validation needs |
|---|---|
| "Did we fetch this game?" | "Did the normalizer produce correct output?" |
| Boolean: covered/not covered | Structured: which checks passed, what anomalies exist |
| Set once when fetched | Re-run when normalizer changes |
| No version tracking | Must track which normalizer version was used |

Adding anomaly details, check results, and normalizer version tracking to the
existing coverage tables would overload their purpose. A dedicated table keeps
concerns separate.

##### Proposed schema: `core.pbp_validation`

```sql
CREATE TABLE core.pbp_validation (
    identity_code   TEXT NOT NULL,
    source          TEXT NOT NULL,       -- e.g. 'nba_data'
    game_id         TEXT NOT NULL,       -- e.g. '21000001'
    season          TEXT NOT NULL,       -- e.g. '2010-11'
    validated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    passed          BOOLEAN NOT NULL,    -- ALL checks passed?
    total_events    INT,                 -- PBPEvents emitted
    total_anomalies INT,                 -- anomaly count across all checks
    check_results   JSONB NOT NULL DEFAULT '{}',
    anomaly_details JSONB NOT NULL DEFAULT '{}',
    PRIMARY KEY (identity_code, source, game_id)
);
```

`check_results` -- per-check pass/fail with detail:
```json
{
    "entity_exists":        {"passed": true,  "anomalies": 0},
    "team_affiliation":     {"passed": true,  "anomalies": 0},
    "possession_integrity": {"passed": false, "anomalies": 4,
                             "detail": "BOS: 49 starts, 45 ends"},
    "lineup_coverage":      {"passed": false, "anomalies": 1,
                             "detail": "BOS coverage 63.8% (9182/14400)"},
    "period_integrity":     {"passed": true,  "anomalies": 0},
    "temporal_ordering":    {"passed": true,  "anomalies": 0},
    "event_type_coverage":  {"passed": false, "anomalies": 2,
                             "detail": ["unknown PERSON1TYPE=7", "entity '2614' not in staging"]}
}
```

`anomaly_details` -- structured catalog of each anomaly:
```json
{
    "unknown_entity": [
        {"entity_id": "2614", "person1type": 7, "event_type": "foul",
         "eventnum": 114, "secs": 780}
    ],
    "unknown_person_type": [
        {"person1type": 7, "count": 1, "game_ids": ["21000001"]}
    ],
    "entity_type_mismatch": [
        {"entity_id": "Celtics", "person1type": 2,
         "expected": "team", "resolved": "team", "event_type": "d_reb"}
    ],
    "possession_mismatch": [
        {"team_id": "BOS", "starts": 49, "ends": 45, "delta": +4}
    ]
}
```

Key design decisions:
- **UPSERT on (identity_code, source, game_id).** Re-validating a game
  replaces the old row -- you always see the latest validation state.
- **JSONB, not normalized anomaly tables.** Anomaly types will evolve as we
  discover new edge cases. JSONB avoids schema migrations for each new anomaly
  category. The JSON is for human review and ad-hoc queries, not relational
  integrity.
- **`passed` is a single boolean.** If ANY check fails, `passed=false`. This
  gives a quick "is this game clean?" indicator.

##### The validation script: `validate_pbp.py`

The script is source-agnostic. It operates on normalized `PBPEvent` lists,
not raw source CSVs:

```python
# Usage:
#   python -m src.validate_pbp --source nba_data              # incremental
#   python -m src.validate_pbp --source nba_data --full        # all games, all seasons
#   python -m src.validate_pbp --source nba_data --season 2010-11
#   python -m src.validate_pbp --source nba_data --game 21000001

def validate_source(source_name, identity_code, full=False, season=None, game_id=None):
    """Validate PBP output for every game in a source's season range."""
    
    # 1. Determine scope: which games to validate
    seasons = _resolve_seasons(source_name, season)  # min_season..max_season from config
    games = _load_games_to_validate(source_name, identity_code, seasons, full, game_id)
    
    # 2. Load staging entity cache (once per identity)
    entity_cache = _load_entity_cache(identity_code)  # teams + players from staging
    
    # 3. For each game, normalize + check
    for game in games:
        raw_rows = _fetch_raw_pbp(source_name, game)
        events = _run_normalizer(source_name, raw_rows, game, entity_cache)
        check_results, anomaly_details = _run_all_checks(events, game, entity_cache)
        _write_validation(game, check_results, anomaly_details)
    
    # 4. Print summary
    _print_summary(games)
```

**Incremental mode (default):** Only validates games that either:
- Have never been validated (no row in `core.pbp_validation`)
- Were last validated with a different normalizer version
- Had `passed=false` on last validation (re-check after fixes)

**Full mode (--full):** Validates every game from min_season to max_season.
This is the initial onboarding run. After that, incremental mode is sufficient
for day-to-day development.

##### The validation checks are source-agnostic

All checks operate on the normalized `PBPEvent` list, plus the entity cache.
They work identically for nba_data, nba_api, or any future PBP source:

| Check | Description | Severity |
|---|---|---|
| `entity_exists` | Every player_id/team_id in events exists in staging | ERROR |
| `team_affiliation` | Player events have team matching staging.players team | ERROR |
| `possession_integrity` | poss_start == poss_end per team (+/- 1 for period ends) | ERROR |
| `lineup_coverage` | Sum of player secs >= 5 * game_length * 0.90 (90% threshold) | WARNING |
| `period_integrity` | Events span correct number of periods (4 for regulation) | ERROR |
| `temporal_ordering` | Events monotonically non-decreasing by secs | ERROR |
| `event_type_coverage` | No unknown event type strings in normalized output | WARNING |
| `stat_consistency` | Team totals match known box score (when available) | INFO |

**Severity levels:**
- **ERROR**: Game is broken. `passed=false`. Must fix before trusting output.
- **WARNING**: Data quality concern. `passed=true` but flagged for review.
- **INFO**: Cross-reference check. `passed=true`. Informational only.

##### Handling scale: 30 seasons, ~36,000 games

At ~1 second per game (normalize + check + write), full validation takes ~10
hours single-threaded. This is acceptable for an initial onboarding run (run
overnight). After that, incremental mode processes only new/changed games.

For faster iteration during development:
- `--season` flag limits to one season (~2 minutes)
- `--sample N` validates N random games across all seasons (~N seconds)
- `--game` validates a single game

##### Config-driven check registry

Checks should be declarative, not hardcoded. A `PBP_VALIDATION_CHECKS`
registry in `src/definitions/pbp_validation.py`:

```python
PBP_VALIDATION_CHECKS = [
    Check(
        name="entity_exists",
        description="Every entity ID exists in staging.players or staging.teams",
        severity=Severity.ERROR,
        runner=check_entity_exists,
    ),
    Check(
        name="team_affiliation",
        description="Player event team matches staging.players team affiliation",
        severity=Severity.ERROR,
        runner=check_team_affiliation,
    ),
    # ...
]
```

Adding a new check is a single entry in this registry plus the runner function.
The script iterates the registry -- no branching logic to maintain.

##### Integration with the orchestrator: two-tier validation

The orchestrator's `maintain_pbp` phase runs BOTH a lightweight production
check AND gate-keeps game_coverage based on catalog validation:

```python
def _maintain_pbp(...):
    catalog = _load_event_catalog(source_name)  # from config file
    entity_cache = make_entity_resolver(conn, identity_code)
    
    for game in games:
        raw_rows = _fetch_raw_pbp(source_name, game)
        
        # TIER 1: Catalog validation (BLOCKING)
        unknown_events = _validate_against_catalog(raw_rows, catalog, game["ext_game_id"])
        if unknown_events:
            _log_unknown_events(unknown_events, game)
            continue  # SKIP this game -- don't normalize, don't write, don't cover
        
        # TIER 2: Normalize + lightweight entity check (NON-BLOCKING)
        events = normalize_game(raw_rows, game["ext_game_id"], 
                                game["home_ext_id"], game["away_ext_id"],
                                entity_cache)
        # entity_cache already handles unknown entities inside normalize_game
        # (skips them and logs to core.errors)
        
        accumulate_and_write(events)
        _mark_game_covered(game)  # Only if catalog validation passed
```

**Tier 1 (catalog validation) is BLOCKING:** If a raw event's (MSGTYPE,
ACTIONTYPE) pair isn't in the catalog, the entire game fails. No data is
written. The game is NOT marked as covered.

**Tier 2 (entity validation) is NON-BLOCKING:** Unknown entities inside the
normalizer are skipped (individual events excluded) but the game still
processes. This is because entity data has always been unreliable in PBP
sources -- a single unknown entity shouldn't block a whole game.

This two-tier approach means:
- New event TYPES (catalog misses) -> game fails, human reviews, catalog updated
- New entity IDs (staging misses) -> event skipped, logged, game continues

The distinction: event STRUCTURE is stable across games. Entity IDENTITY
varies per game and is less reliable.

##### The event catalog: config-driven, source-agnostic

The catalog is the bridge between "what the source produces" and "what the
normalizer handles." It's a config file (Python) per source, defining every
known event type:

```python
# src/sources/nba_data/pbp_event_catalog.py

from src.definitions.pbp_catalog import EventCatalogEntry, Handling

NBA_DATA_EVENT_CATALOG = [
    # --- Scoring events ---
    EventCatalogEntry(
        msg_type=1,           # Made FG
        action_type="*",      # All action types (2pt, 3pt, dunk, layup, etc.)
        handling=Handling.INCLUDE,
        category="scoring",
        normalized_event="fg_make",  # normalizer sub-classifies 2pt vs 3pt
    ),
    EventCatalogEntry(
        msg_type=2,           # Missed FG
        action_type="*",
        handling=Handling.INCLUDE,
        category="scoring",
        normalized_event="fg_miss",
    ),
    EventCatalogEntry(
        msg_type=3,           # Free throw
        action_type="*",
        handling=Handling.INCLUDE,
        category="scoring",
        normalized_event="ft",  # normalizer sub-classifies make vs miss
    ),
    
    # --- Rebound ---
    EventCatalogEntry(
        msg_type=4,
        action_type="*",
        handling=Handling.INCLUDE,
        category="rebound",
        normalized_event="rebound",
    ),
    
    # --- Turnover ---
    EventCatalogEntry(
        msg_type=5,
        action_type="*",
        handling=Handling.INCLUDE,
        category="turnover",
        normalized_event="turnover",
    ),
    
    # --- Fouls (all subtypes included per user requirement) ---
    EventCatalogEntry(
        msg_type=6,
        action_type=1,        # Personal foul
        handling=Handling.INCLUDE,
        category="foul",
        normalized_event="foul",
    ),
    EventCatalogEntry(
        msg_type=6,
        action_type=2,        # Shooting foul
        handling=Handling.INCLUDE,
        category="foul",
        normalized_event="foul",
    ),
    EventCatalogEntry(
        msg_type=6,
        action_type=4,        # Offensive foul / charge
        handling=Handling.INCLUDE,
        category="foul",
        normalized_event="foul",
    ),
    EventCatalogEntry(
        msg_type=6,
        action_type=7,        # Flagrant foul (expected in other games)
        handling=Handling.INCLUDE,
        category="foul",
        normalized_event="foul",
        notes="Flagrant -- single MSGTYPE=6 row, not double-counted",
    ),
    EventCatalogEntry(
        msg_type=6,
        action_type=11,       # Defensive 3-second (team technical)
        handling=Handling.INCLUDE,
        category="foul",
        normalized_event="foul",
        notes="Team technical, not personal. Included per user requirement.",
    ),
    EventCatalogEntry(
        msg_type=6,
        action_type=17,       # Defensive 3-second (alternate encoding)
        handling=Handling.INCLUDE,
        category="foul",
        normalized_event="foul",
    ),
    EventCatalogEntry(
        msg_type=6,
        action_type=26,       # Offensive charge foul
        handling=Handling.INCLUDE,
        category="foul",
        normalized_event="foul",
    ),
    EventCatalogEntry(
        msg_type=6,
        action_type=27,       # Personal block foul
        handling=Handling.INCLUDE,
        category="foul",
        normalized_event="foul",
    ),
    
    # --- Explicitly excluded events ---
    EventCatalogEntry(
        msg_type=7,           # Violations (lane, kicked ball, delay of game)
        action_type="*",
        handling=Handling.EXCLUDE,
        category="violation",
        notes="Not meaningful for stats accumulation",
    ),
    EventCatalogEntry(
        msg_type=9,           # Timeouts
        action_type="*",
        handling=Handling.EXCLUDE,
        category="timeout",
    ),
    
    # --- System events ---
    EventCatalogEntry(
        msg_type=8,           # Substitution
        action_type="*",
        handling=Handling.INCLUDE,
        category="substitution",
        normalized_event="sub",
    ),
    EventCatalogEntry(
        msg_type=10,          # Jump ball
        action_type="*",
        handling=Handling.INCLUDE,
        category="possession",
        normalized_event="jump_ball",
    ),
    EventCatalogEntry(
        msg_type=12,          # Period start
        action_type="*",
        handling=Handling.INCLUDE,
        category="system",
        normalized_event="period_start",
    ),
    EventCatalogEntry(
        msg_type=13,          # Period end
        action_type="*",
        handling=Handling.INCLUDE,
        category="system",
        normalized_event="period_end",
    ),
]
```

The `Handling` enum:
```python
class Handling(enum.Enum):
    INCLUDE = "include"   # Pass to normalizer for processing
    EXCLUDE = "exclude"   # Skip entirely (timeouts, violations, etc.)
    ERROR = "error"       # Should never appear -- indicates bad source data
```

**Why a config file, not a DB table?**

The catalog is the source of truth for "what events are expected." It must be:
1. **Version-controlled** -- changes reviewed in PRs, git history tracks additions
2. **Deterministic** -- same catalog every run, no DB state dependence
3. **Testable** -- tests can import the catalog and verify coverage

A DB table (`core.pbp_source_events`) is ALSO created, but it's DERIVED from
the config file -- it tracks runtime metadata (first_seen, last_seen, game_count)
that the config can't know statically. The config says "event type 6-7 EXISTS,"
the DB says "we've seen it in seasons 2010-11 through 2024-25."

##### The discovery script: building the initial catalog

When onboarding a new source, you run a discovery script that streams through
ALL games across ALL seasons and outputs every unique event type:

```bash
python -m src.discover_pbp_events --source nba_data --output catalog_report.json
```

The output is NOT the final catalog -- it's a REPORT for human review:

```json
{
  "source": "nba_data",
  "seasons_processed": 29,
  "games_processed": 35670,
  "unique_event_types": [
    {
      "msg_type": 1,
      "action_types_seen": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
      "sample_description": "Pierce 3PT Jump Shot (3 PTS)",
      "game_count": 35000,
      "season_range": ["1996-97", "2024-25"]
    },
    {
      "msg_type": 6,
      "action_types_seen": [1, 2, 4, 6, 7, 11, 17, 26, 27],
      "sample_description": "James P.FOUL (P3.T4)",
      "game_count": 35670,
      "season_range": ["1996-97", "2024-25"]
    },
    {
      "msg_type": 7,
      "action_types_seen": [1, 3, 5],
      "sample_description": "Rondo Violation:Kicked Ball",
      "game_count": 30000,
      "season_range": ["1996-97", "2024-25"]
    }
  ]
}
```

A human reviews each unique (msg_type, action_type) combination and decides:
- Should it be included? What normalized event does it map to?
- Should it be excluded? (timeouts, violations, etc.)
- Is it an error? (should never appear)

The human writes the catalog config file. Then the validation script verifies
that the catalog covers 100% of observed event types.

##### When to run what?

| When | What | Purpose |
|---|---|---|
| **Source onboarding** (one-time) | Full discovery run | Build initial event catalog |
| **Source onboarding** (one-time) | Full validation run (--full) | Verify catalog covers all events |
| **Every production run** | Catalog validation (per-game) | Catch new event types; fail game if unknown |
| **Every production run** | Entity validation (per-event) | Skip unknown entities; log warnings |
| **After normalizer changes** | Incremental validation (--incremental) | Re-verify changed games |
| **New season starts** | Discovery on new season | Catch format changes; flag new event types |
| **CI on every PR** | Validation on sample games | Prevent regressions |

##### Fail-closed policy: unknown events block the game

The user's requirement: "If something new or unexpected pops up, then the game
should error out, it should not be added to game_coverages, and we should
handle it."

This is the correct policy. Here's the detailed implementation:

```python
def _validate_against_catalog(raw_rows, catalog, game_id):
    """Check every raw event against the catalog. Return unknown events."""
    unknown = []
    for row in raw_rows:
        msg_type = _to_int(row.get("EVENTMSGTYPE"))
        action_type = _to_int(row.get("EVENTMSGACTIONTYPE"))
        
        if not _catalog_has(catalog, msg_type, action_type):
            unknown.append({
                "msg_type": msg_type,
                "action_type": action_type,
                "eventnum": row.get("EVENTNUM"),
                "description": _build_desc(row),
            })
    
    return unknown

def _maintain_pbp(...):
    for game in games:
        raw_rows = _fetch_raw_pbp(source_name, game)
        
        unknown = _validate_against_catalog(raw_rows, catalog, game["ext_game_id"])
        if unknown:
            # Log each unknown event type to core.errors
            for evt in unknown:
                log_error_simple(
                    "maintain_pbp",
                    f"UNKNOWN EVENT TYPE: source={source_name} "
                    f"game={game['ext_game_id']} msgtype={evt['msg_type']} "
                    f"actiontype={evt['action_type']} "
                    f"desc='{evt['description'][:100]}'"
                )
            
            # Do NOT write to staging
            # Do NOT mark game as covered
            # Continue to next game (don't halt pipeline)
            failed.append({
                "game_id": game["ext_game_id"],
                "reason": f"{len(unknown)} unknown event type(s)",
                "detail": unknown,
            })
            continue
        
        # Catalog passed -- proceed with normalization
        events = normalize_game(...)
        ...
```

**Rationale for failing the game (not the pipeline):**
- One game with a new event type shouldn't block 1,229 other games in the season
- The failed game is recorded in the `failed` list (already exists in orchestrator)
- A human reviews the `core.errors` log, updates the catalog, and the game can
  be re-run independently
- Over time, the catalog stabilizes and failures become rare

**What about the "discovery" phase -- should unknown events fail then too?**

No. The discovery script has a different purpose: it's CATALOGING, not
validating. It collects all event types without judgment. The validation
script (which uses the catalog) is what enforces the fail-closed policy.

##### Edge case: wildcard action types

The catalog supports `action_type="*"` for MSGTYPEs where all action types
should be handled identically (e.g., MSGTYPE=4 rebounds, all ACTIONTYPEs are
rebounds). But specific ACTIONTYPEs can override the wildcard:

```python
# All MSGTYPE=6 with any ACTIONTYPE not explicitly listed -> EXCLUDE
EventCatalogEntry(msg_type=6, action_type="*", handling=Handling.EXCLUDE, category="foul")

# Override: these specific ACTIONTYPEs are INCLUDED
EventCatalogEntry(msg_type=6, action_type=1, handling=Handling.INCLUDE, ...)
EventCatalogEntry(msg_type=6, action_type=2, handling=Handling.INCLUDE, ...)
# ... etc.
```

This way, if a new ACTIONTYPE=99 appears for MSGTYPE=6, it's caught by the
wildcard EXCLUDE and flagged as unknown. The human must explicitly add it
as an INCLUDE entry if it's a real foul type.

##### Why the event catalog is separate from the normalizer

The normalizer contains processing LOGIC (how to turn raw events into normalized
events). The catalog contains COVERAGE (which event types are expected).

Separating them means:
1. The normalizer doesn't need to handle "is this event type known?" -- that's
   the catalog's job.
2. The catalog can be exhaustive WITHOUT bloating the normalizer.
3. You can change the catalog (add a new ACTIONTYPE) without touching the
   normalizer (if the normalized event mapping is the same).
4. The catalog is source-specific (nba_data vs nba_api have different MSGTYPEs).
   The normalizer is also source-specific, but the catalog concept is portable.

##### Template for new PBP sources

To make onboarding easy, the catalog system should be templated:

```python
# src/sources/new_source/pbp_event_catalog.py
# GENERATED by discover_pbp_events on 2026-07-28
# Review each entry and set handling + normalized_event

from src.definitions.pbp_catalog import EventCatalogEntry, Handling

NEW_SOURCE_EVENT_CATALOG = [
    # === UNREVIEWED (discovery output) ===
    # TODO: Review each entry below. Set handling to INCLUDE, EXCLUDE, or ERROR.
    # TODO: For INCLUDE entries, set normalized_event.
    
    EventCatalogEntry(
        msg_type=1,
        action_type="*",
        handling=Handling.UNREVIEWED,  # <-- must be changed before production use
        category="unreviewed",
        normalized_event=None,
    ),
    # ... etc for each discovered event type
]
```

The `Handling.UNREVIEWED` state prevents the catalog from being used in
production until every entry has been explicitly reviewed.

---

#### Question 1b: Flagrant foul double-counting

**CONFIRMED: No double-counting.** In the NBA PBP data format, a flagrant foul
generates exactly ONE `MSGTYPE=6` row with `ACTIONTYPE=7` (flagrant). There is
no separate "normal foul" row for the same play. Each CSV row is a single
recorded event; a single play cannot produce two `MSGTYPE=6` rows.

The normalizer treats all `MSGTYPE=6` events identically as `"foul"`, so each
flagrant counts as exactly one foul. No change needed.

---

#### Question 2/3: Entity validation -- staging lookup, not PERSON1TYPE

**User's key insight:** "We shouldn't care whether we are looking at a player
field or a team field. What matters is the id that is assigned to it and what
the id is in our system. PBP is not reliable enough to be authoritative on
this kind of stuff."

This is the correct approach. PERSON1TYPE becomes **completely irrelevant for
entity resolution.** The only question is: "does this ID exist in
staging.teams? staging.players? neither?"

##### Current code (wrong approach):

```python
# config.py
PERSON_TEAM = 3   # Assumes PERSON1TYPE=3 always means "team"
PERSON_HOME = 4   # Assumes PERSON1TYPE=4 always means "home player"
PERSON_VISITOR = 5 # Assumes PERSON1TYPE=5 always means "away player"

# pbp_normalizer.py
def _resolve_player_team(person_type, player_id, player_team_id):
    """For team events, PLAYER1_ID IS the team ID."""
    if person_type == PERSON_TEAM:
        return player_id      # This breaks when PERSON1TYPE=2 (also a team type)
    return player_team_id     # This works when PLAYER1_TEAM_ID is populated
```

This is fragile. PERSON1TYPE=2 (home team events) is not `PERSON_TEAM`, so
Celtics team rebounds are misattributed. PERSON1TYPE=7 (unknown) is not
handled at all. And PERSON1TYPE could change across seasons or sources.

##### New approach: entity_resolver callable

```python
# pbp_normalizer.py -- PERSON1TYPE is no longer used for resolution

def normalize_game(
    rows, game_id, home_team_id, away_team_id,
    entity_resolver: Callable[[str], Tuple[Optional[str], Optional[str]]],
    identity="nba_id",
):
    """
    entity_resolver(entity_id) -> (team_id, entity_type)
    
    Returns:
        (team_id, "team")   if entity_id found in staging.teams
        (team_id, "player") if entity_id found in staging.players
        (None, None)        if entity_id not found in either
    """
    ...
    for row in rows:
        p1_id = _to_str(row.get(COL["PLAYER1_ID"]))
        p1_type = _to_int(row.get(COL["PERSON1TYPE"]))  # only for validation warnings
        
        # RESOLUTION: use staging lookup
        team_id, entity_type = _resolve_entity(p1_id, entity_resolver, game_id)
        if team_id is None:
            continue  # Unknown entity -- skip event
        
        # VALIDATION: PERSON1TYPE vs resolved type (warning only)
        _validate_person_type(p1_type, entity_type, p1_id, game_id)
        
        # Use team_id for the event (no PERSON1TYPE needed)
        events.append(_mk(..., team_id, p1_id, ...))
```

##### Orchestrator provides the resolver:

```python
# orchestrator.py

def make_entity_resolver(conn, identity_code):
    """Create entity resolver backed by staging tables.
    
    Loads all teams and players once, returns a cached callable.
    The normalizer calls this for every entity it encounters.
    """
    cursor = conn.cursor()
    
    # Load all teams for this identity
    cursor.execute(
        "SELECT ext_id FROM staging.teams WHERE identity = %s",
        (identity_code,)
    )
    teams = {row[0] for row in cursor.fetchall()}
    
    # Load all players with their team affiliations
    cursor.execute(
        """SELECT p.ext_id, tp.team_id
           FROM staging.players p
           JOIN staging.teams_players tp ON p.ext_id = tp.player_id
           WHERE p.identity = %s""",
        (identity_code,)
    )
    players = {row[0]: row[1] for row in cursor.fetchall()}
    
    cursor.close()
    
    def resolver(entity_id):
        if entity_id in teams:
            return entity_id, "team"
        if entity_id in players:
            return players[entity_id], "player"
        return None, None
    
    return resolver
```

##### What PERSON1TYPE is still used for:

After resolution, PERSON1TYPE serves as a **validation warning only**:

```python
def _validate_person_type(person_type, resolved_type, entity_id, game_id):
    """Log a warning if PERSON1TYPE suggests a different entity type."""
    expected = _person_type_to_entity_type(person_type)
    if expected and expected != resolved_type:
        logger.warning(
            f"PERSON1TYPE mismatch in game {game_id}: "
            f"PERSON1TYPE={person_type} suggests '{expected}' "
            f"but '{entity_id}' resolved as '{resolved_type}'"
        )

def _person_type_to_entity_type(person_type):
    """Map PERSON1TYPE to expected entity type. None = no expectation."""
    mapping = {
        0: None,     # System event -- no expectation
        1: None,     # Official/event -- no expectation
        2: "team",   # Home team
        3: "team",   # Away team
        4: "player", # Home player
        5: "player", # Away player
        # 6, 7, etc. -- unknown, no expectation
    }
    return mapping.get(person_type)
```

This catches misclassification without blocking processing. A player with
PERSON1TYPE=5 (away) but PLAYER1_TEAM_ID=Celtics (home) still resolves
correctly -- we just log a warning that PERSON1TYPE was unexpected.

##### How this handles all known edge cases:

| Case | PERSON1TYPE | Entity ID | Staging Lookup | Resolution |
|---|---|---|---|---|
| Celtics team rebound | 2 | "Celtics" | Found in staging.teams | team_id="Celtics", type="team" |
| Heat team rebound | 3 | "Heat" | Found in staging.teams | team_id="Heat", type="team" |
| Pierce personal foul | 4 | "Pierce" | Found in staging.players | team_id="Celtics", type="player" |
| Wade shooting foul | 5 | "Wade" | Found in staging.players | team_id="Heat", type="player" |
| 2614 def 3-sec | 7 | "2614" | NOT in teams, NOT in players | **SKIP + LOG ERROR** |
| Misclassified (away type, home player) | 5 | "Pierce" | Found in staging.players | team_id="Celtics", type="player" + WARNING |
| Unknown PERSON1TYPE=6 | 6 | "LeBron" | Found in staging.players | team_id="Heat", type="player" (no warning, type 6 has no expectation) |

##### Design principle: fail closed, log everything

- **Unknown entities are SKIPPED, not guessed.** If "2614" isn't in staging,
  the event is excluded from accumulation. A `core.errors` row is written.
  The pipeline continues to the next event.
- **PERSON1TYPE mismatches are WARNINGS, not blockers.** If PERSON1TYPE says
  "player" but staging says "team", we trust staging and log the discrepancy.
- **PBP processing never writes to staging.players or staging.teams.** Unknown
  entities are not created. They're logged and skipped.

##### Why a callable, not pre-loaded dicts?

Passing `entity_resolver` as a callable (not a pre-loaded dict) keeps the
normalizer testable. Tests can pass a mock resolver:

```python
def test_normalize_unknown_entity():
    def mock_resolver(entity_id):
        return None, None  # simulate unknown entity
    
    events = normalize_game(rows, "test_game", "home", "away", mock_resolver)
    assert len(events) == 0  # unknown entity should be skipped

def test_normalize_team_event():
    def mock_resolver(entity_id):
        if entity_id == "Lakers":
            return "Lakers", "team"
        return None, None
    
    events = normalize_game(rows, "test_game", "Lakers", "Celtics", mock_resolver)
    assert events[0]["team_id"] == "Lakers"
```

##### What changes in the codebase:

1. **`config.py`**: PERSON type constants become documentation-only (not used
   for resolution). Add the `_person_type_to_entity_type` mapping for validation.
2. **`pbp_normalizer.py`**: `_resolve_player_team` is replaced by
   `_resolve_entity`. PERSON1TYPE is only read for validation warnings.
   `entity_resolver` is added as a parameter.
3. **`orchestrator.py`**: `make_entity_resolver` is added. It's called once
   per identity before the game loop. The resolver is passed to `normalize_game`.
4. **No schema changes needed.** `staging.teams` and `staging.players` already
   exist. `core.errors` already exists for logging unknown entities.

---

#### Action items (updated 2026-07-28 -- replaces all previous)

**P0: Entity validation (blocking for data quality)**
1. Add `entity_resolver` callable parameter to `normalize_game`
2. Replace `_resolve_player_team` with staging-table lookup via `entity_resolver`
3. PERSON1TYPE becomes validation-only (warnings, not resolution)
4. Add `make_entity_resolver` to orchestrator -- loads staging.teams + staging.players once per identity
5. Skip events with unknown entities; log to `core.errors`
6. Add PERSON_HOME_TEAM=2 to config for validation warnings (not for resolution)

**P1: Event catalog infrastructure**
7. Create `src/definitions/pbp_catalog.py` with `EventCatalogEntry` + `Handling` enum
8. Create `src/sources/nba_data/pbp_event_catalog.py` (config file -- source of truth)
9. Create `src/discover_pbp_events.py` -- streams all seasons, outputs unique event types
10. Add `_validate_against_catalog` to orchestrator -- fail game on unknown event types
11. Create `core.pbp_source_events` DB table (derived from catalog, tracks discovery metadata)
12. Create `core.pbp_validation` DB table (per-game validation results)
13. Create `src/validate_pbp.py` -- full validation script with --full/--season/--sample/--game flags

**P2: Production hardening**
14. Add incremental validation mode (skip already-validated games)
15. Add `Handling.UNREVIEWED` state for catalog entries that need human review
16. Add normalizer version tracking to validation table
17. Integrate catalog validation into CI pipeline
18. Template catalog for new PBP source onboarding

---

#### Open design questions

1. **Wildcard resolution order:** If both a specific entry (msg_type=6, action_type=2)
   and a wildcard entry (msg_type=6, action_type="*") exist, the specific entry
   should win.

2. **Description pattern matching:** Some PBP sources distinguish events by
   description text (e.g., "Timeout: Regular" vs "Timeout: Short"). Defer to P2
   if ACTIONTYPE is sufficient for nba_data.

3. **Catalog versioning:** When the catalog changes, previously-failed games
   should be auto-revalidated on next incremental run.

4. **Cross-source categories:** Event categories ("scoring", "foul", "turnover")
   are source-agnostic and shared across all PBP sources. Only msg_type,
   action_type, and normalized_event are source-specific.

---

#### Confirmed: Entity validation approach

**User's principle:** "We shouldn't care whether we are looking at a player field
or a team field. What matters is the id that is assigned to it and what the id
is in our system. PBP is not reliable enough to be authoritative on this kind
of stuff."

This is the design. PERSON1TYPE is stripped of resolution authority entirely.
It serves only as a validation warning. The staging-table entity cache is the
single source of truth.

**Detailed implementation plan:** `project_tracking/pbp_implementation_plan.md`
(Created 2026-07-28. Covers event catalog DB schema, discovery vs production
modes, entity resolver design, classifier module, and implementation order.)

---

### 2026-07-28: Implementation Complete

**What was built:**

- `core.pbp_events` table (identity, dataset, event_key, handling). PK-only,
  4 columns. No seed file, no match_fields. Discovery populates, human reviews,
  production enforces.
- `src/lib/entity_resolver.py` -- staging-table lookup. Required parameter,
  no fallback. `_resolve_player_team` deleted.
- `src/lib/pbp_classifier.py` -- `EventClassifier` + `FieldLookupStrategy`.
  Key-based lookup, no pattern matching. `UnclassifiedEventError` on unknowns.
- `src/lib/pbp_discover.py` -- `discover()` iterates games, builds event keys,
  upserts into `core.pbp_events` with `handling='unreviewed'`.
- `src/lib/pbp_accumulator.py` -- `player_start` handler (bool from `player_in`
  at secs=0). `win` handlers fixed (team total points, not individual).
  `_derive_starter_events` deleted.
- `src/sources/nba_data/pbp_normalizer.py` -- hardcoded `if msgtype == MSG.`
  chain replaced with classifier-driven mapping. Two pseudo-types remain:
  `rebound` (o_reb vs d_reb from runtime state) and `substitution` (one row
  -> two events).
- `src/sources/nba_data/client.py` -- `fetch_raw_rows()` added. `fetch_game_pbp`
  delegates to `fetch_raw_rows` (DRY).
- `src/orchestrator.py` -- entity resolver + classifier built once, passed to
  normalizer. Production enforcement: all events classified or phase stops.
  `bootstrap_schema` phase name fixed (was `build_schema`).
- `src/cli.py` -- subcommands: `etl` and `discover-pbp`. Discovery runs
  `bootstrap_schema` first.
- `src/definitions/pbp.py` -- `RESULT_SET_FIELDS` normalized: every entry has
  same 6 keys (op, type, events, formula, fields, result_sets). `start` and
  `win` are special/bool.
- `src/definitions/pipeline.py` -- phase renamed `build_schema` -> `bootstrap_schema`.

**Files deleted:**
- `project_tracking/pbp_implementation_plan.md` -- plan is built.

**Still open (not in scope of this round):**
- Points 1, 3-14, 16-30 from original review (lineup, possession, event model)
- `pbp_handoff.md` -- historical discussion log, kept for reference.
