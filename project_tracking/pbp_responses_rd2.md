Three corrections I made to the pre-Round-1 draft

1. **And-one `pot_poss_ending` lands on the FT, not the make.** Your draft has `fg2_make: indicate_poss=True` — the make breaks the scoring sequence, so the FT is the first shot of the next sequence. The old doc had this wrong.
2. **`o_foul_draw` priority 8 → 4** (it's a secondary attribution, belongs with steal/block, not after FTs).
3. **"Every missed shot has a rebound" is scoped to sequence-final shots.** An `ft1_miss → ft2_make` is one trip; the mid-trip miss is exempt, and the rebound suppression rule you confirmed (no o_rebs/d_rebs between same-sequence shots) becomes a chain behavior that runs *before* possession derivation so artifacts never act as `indicate_poss`.

1. Okay... yeah so help me out here, I'm not sure what is best. What I need is this:

pot_poss_ending_scoring_attempts:
- a field goal attempt
- a field goal attempt + ft attempt (and-one; should be 1 pot_poss_ending_scoring_attempt, not two)
- sequence of free throws triggered by standard foul

these should all equate to a single pot_poss_ending_scoring_attempt.

What should not:
- a sequence of free throws triggered by an elevated foul
- shots with an indicate_poss event in between (rebound, turnover, etc)

so maybe shots shouldn't be indicate_poss, but we should let pot_poss_ending_scoring_attempt events drive that?

2. sounds right
3. that sounds good

Four code-level findings I verified while updating

1. **`validate_all()` silently discards `validate_config()` errors** (`config_validation.py` L666) — new PBP config validators won't surface at CLI startup until this is fixed.
2. **Naming drift is a real bug**: DB column `pot_poss_ending_scoring_opp` maps field `"pot_poss_ending_scoring_opp"`, but `RESULT_SET_FIELDS` only has `poss_ending_ft_trips` — so the player/team column **silently never populates** (confirmed through `_build_pbp_column_map` / `_map_pbp_result_to_columns`).
3. **`standard_fouls` DB column has no `pbp_stats` mapping** — needs one when the result field is added.
4. **`_maintain_pbp` catches only `(ConnectionError, OSError, TimeoutError, ValueError)`** around normalize, and unclassified events `break` the whole phase. New derive errors must subclass `ValueError`, and I'd recommend per-game fail (record + continue) instead of phase-halt.

1. yeah we should ensure all of our configs and config validators are validated and enforced in the same, consistent way across the entire codebase
2. All drift absolutely needs to be fixed. We are using pot_poss_ending_scoring_opp, standard_foul, and elevated_foul
3. yeah, you are correct. And we also have several other columns in db_columns that are missing their pbp_stats mappings. Some will have a player/team_game_stats dataset source as well, which is fine. It is fine to have two sources.
4. Hmm yeah I think per_game fails are better.

## 11. Open questions

### 11.1 Round 1 -- resolved (recorded in Section 2)

D1-D5 and Q1-Q6 all resolved 2026-08-02. No open items remain from Round 1.

### 11.2 Round 2 -- open (awaiting user)

Recommended defaults marked **[R]**.

**Ordering / placement**
1. Priority ordering (user asked for our call). **[R]** `period_end`(9) ->
   `player_out`(10) -> `period_start`(11) -> `player_in`(12) ->
   `jump_ball_win`(13) -> `poss_end`(14) -> `poss_start`(15), with poss markers
   chain-placed (close-before-open within a transition). Confirm.
2. Rebound anchoring. **[R]** Sequence-adjacent only: shot -> [block] ->
   rebound (`skip=(block,)`, `max_gap=2`); any other event between = hard
   error. A rebound logged seconds later keeps its timestamp; the chain still
   binds. Rebound off/def derived from the chain (rebounder vs shooter team);
   source classification treated as input; mismatch = anomaly log (not error).
   Confirm.
3. Scoring-sequence scope + and-one placement. **[R]** (a) "Every missed shot
   has a rebound" applies to **sequence-final** shots only; intra-trip FT
   misses are exempt. (b) Rebounds anchored to non-final sequence shots are
   suppressed (config `suppress`). (c) And-one `pot_poss_ending` fires on the
   **FT** (the make is `indicate_poss` and breaks the sequence) -- this
   corrects the old draft's "on the make". Confirm all three.
4. Miss -> loose-ball foul -> FTs (no rebound). **[R]** Literal rule: the next
   `indicate_poss` is the trip's `pot_poss_ending_scoring_opp` (same team) =>
   synthesized team `o_reb`. Confirm, or prefer no rebound in this rare case.

**Fouls / FTs**
5. nba_data foul taxonomy. **[R]** Run discovery over `MSG=6` action types,
   then propose the elevated list (flagrant 1/2, technical, clear path,
   away-from-play, ...) for review. Also: elevated-foul FTs may chain **across
   a period boundary** (technical at the buzzer shot next period) ->
   `cross_period=True` for elevated FTA chains. And: `fouls` = standard +
   elevated (both count). Confirm.
6. Errored-game remediation (user asked "what is best practice?"). **[R]** The
   Section 10 design: immutable raw archive + per-game status + extended
   `core.errors` + declarative `PBP_CORRECTIONS` config (no jsonb hand-editing)
   + per-game fail instead of phase halt. Confirm or adjust.

**Invariants**
7. Impossible-state list (user asked). **[R]** Hard errors: FT without foul;
   double-open possession; `poss_end` with no open window; transition team
   mismatch (e.g., `d_reb` by already-possessing team); possession change
   without a transition event; rebound with no anchor shot; `player_in` for an
   on-court player; `player_out` for an off-court player; lineup too small;
   lineup too large; on-court activity by a player not in the derived lineup;
   activity after final `period_end`. Which (if any) should be `warn` instead
   of `error`?
8. Uniform `EventDef` schema. **[R]** `{sort_priority, indicate_poss,
   indicate_on_court, shot, points, poss_transition}` as a `total=True`
   TypedDict; drop `category`; FT `points` = 1 for all makes. Confirm.

**Scope / config home**
9. Game-structure config home. **[R]** Extend `LEAGUES` with a `game` block
   (`clock`, `periods`, `period_length`, `overtime`, `target_score`);
   per-dataset override only if a league ever has two PBP structures. Confirm.
10. Naming drift fix. **[R]** Rename `RESULT_SET_FIELDS` key
    `poss_ending_ft_trips` -> `pot_poss_ending_scoring_opp` (un-breaks the
    player/team DB mapping); also rename `opp_poss_ending_ft_trips` /
    `on_poss_ending_ft_trips` DB columns to `opp_pot_poss_ending_scoring_opp`
    / `on_pot_poss_ending_scoring_opp` (schema migration). Confirm.
11. Catalog migration. Existing reviewed `core.pbp_events` rows with
    `handling='foul'` must split into `standard_foul`/`elevated_foul`.
    **[R]** Re-review at migration time per action type (discovery over MSG=6
    first); keep `foul` only as an unreviewed/fallback key. Confirm.
12. Player possession qualification. **[R]** Unchanged from the old Q11:
    seq-based on-court interval overlap with a window `indicate_poss`. Confirm.
13. Between-period substitutions. **[R]** A sub pair appearing before the
    team's first non-substitution on-court event is a boundary sub: sub-in =
    starter, sub-out = not a starter (no inferred `player_in` for the departing
    player). Confirm the trigger.
14. And-one transition gating. **[R]** The and-one make's `live_shot`
    transition is suppressed while FTs follow (trip continues); the trip's last
    FT transitions. Confirm.

**Process**
15. `validate_all()` silently discards `validate_config()` errors
    (config_validation.py L666). **[R]** Fix in Phase 1 so PBP config
    validation actually surfaces. Confirm it's in scope.
16. Error exit path: new derivation errors should subclass `ValueError` (or
    widen the catch tuple in `_maintain_pbp`) and fail **per game** (record
    status + `core.errors`, continue the phase) rather than halting. Confirm.


1. that sounds good I think
2. Yeah, I think. This is where shots get confusing... I want the first shot in a sequence to be the one that triggers pot_poss_ending_scoring_opp event, but only if it is not triggered by an elevated foul... and only the last shot in a sequence should have a rebound. And only on misses. I don't know how to define that best... We shouldn't ever mess with/adjust the timestamps of events. but if we add a timestamp of a missing event (like a rebound), they can receive the timestamp of the event that triggers it (the shot)
3. correct, only the final shot as discussed above, and only on misses.
4. hmm yeah good thought. I think this follows the same pattern. if a rebound is not given, then it is inferred and assignedby the next indicate_poss event. So yes, there should be a rebound
5. I don't know if anything should ever need to chain across periods. Would there be a way to just stick the foul and free throws at the start of the next period or end of the previous period (depending on when they actually take place)? they should both be in the same period. We are not tracking anything called "fouls" anymore. We are tracking all fouls separately: standard_fouls and elevated_fouls. All free throws do need to be triggered by a foul, so yes standard_fouls and elevated_fouls are both considered "fouls" in that sense, but they invoke very different rules for the free throws and context. Does that make sense?
6. I don't think I like this design at all. I think this is YAGNI for now. Let's just use the system that we have in place and trust the data that we have for now. If we get errors due to bad data, we will deal with it then. Or maybe I'll just keep thinking more about a better way to manage it. It should be light and easy.
7. Okay yeah that all sounds good I think. I do want to keep in mind that off-court players can still receive fouls. And I do want to keep in mind that there are extremely rare instances where teams do legitimately have too many players on the court at once and they will be assigned a foul. I'm not sure how to handle that properly. And there will be extremely rare instances where teams do legitimately have too few players on the court at once, due to having not enough eligble players, and they are still allowed to play on without issue. Maybe we can't actually enforce player_ins and player_outs to pair? Or maybe we still do, but I manually review/approve the very rare instances that do and error out. Please ensure that when we have a game error out, we still collect all the data for the game, but we don't send it to intermediate, it stays in staging and avoids the cleanup process. It needs to stay in staging. How should we handle that? This might be the key to me manually fixing all error record, just using a status flag and manually approving/fixing data on games and game stats that have errors. What do you think?
8. yes drop category. FT points does NOT equal 1 for all makes. ft1_make = 1 point, ft2_make = 2 points, ft3_make = 3 points.
9. no, why would we need this. Why do we need to expect a certain number of periods or ots. Don't we just intake whatever is given? We don't need to expect a certain period length. what do you mean? what do we need these for?
10. yes use pot_poss_ending_scoring_opps
11. do not keep foul as fallback. We do not do backwards compatability. We will not support foul as an event type, only standard_foul and elevated_foul
12. yes
13. yes I think I follow, I think that sounds right
14. yes
15. yes absolutely
16. yes absolutely. But we should finish the game first if possible. Is that best practice?