## 11. Open questions

### 11.1 Round 1 -- resolved (recorded in Section 2)

D1-D5 and Q1-Q6 all resolved 2026-08-02. No open items remain from Round 1.

### 11.2 Round 3 -- open (awaiting user)

Recommended defaults marked **[R]**.

**Scoring-opportunity semantics (Section 7.3 model)**
1. Confirm the sequence model: (a) a standard-foul FT trip is always its own
   fresh sequence -> `pot_poss_ending_scoring_opp` before its first FT;
   (b) an **and-one make is absorbed** into its trip (no `pot_poss_ending`
   before the make; the trip carries the single attempt); (c) miss +
   loose-ball foul + FTs = TWO attempts (the miss's + the trip's) -- this is
   what makes the miss's synthesized team `o_reb` work (Round-1 Q4).
   Consequences table in 7.3. Confirm all three.
2. Miss + **shooting** foul (foul on the shooter, not loose-ball). **[R]**
   Absorb the miss into the trip (1 attempt, symmetric with the and-one -- the
   foul was on the shot). Consequence: the miss is not sequence-final -> no
   rebound synthesis for it; the trip's last shot carries the rebound
   obligation. Alternative: every miss is its own attempt (2 total). Which?
3. Elevated-foul trips: transparent to scoring-sequence tracking (neither
   start nor continue a sequence) -- confirm. `pot_poss_ending_scoring_opp`
   never fires for them.

**Naming / schema**
4. Result fields: `pot_poss_ending_scoring_opps` /
   `opp_pot_poss_ending_scoring_opps` / `on_pot_poss_ending_scoring_opps`
   replace `poss_ending_ft_trips` / `opp_poss_ending_ft_trips` /
   `on_poss_ending_ft_trips`. DB columns: keep `pot_poss_ending_scoring_opp`
   (singular, exists) with field `pot_poss_ending_scoring_opps`; rename
   `opp_poss_ending_ft_trips` -> `opp_pot_poss_ending_scoring_opps` and
   `on_poss_ending_ft_trips` -> `on_pot_poss_ending_scoring_opps` (schema
   migration). Confirm.
5. `fouls` result field: drop entirely (verified dead -- no DB column maps
   it). `standard_fouls` + `elevated_fouls` replace it; add a `pbp_stats`
   mapping to the `standard_fouls` DB column. Confirm.
6. FT `points` (`ft1_make=1`, `ft2_make=2`, `ft3_make=3`): confirm the
   contract. Note: an FT is always worth 1 point; `2/3` would overstate points
   if a source ever emits `ft2_make`/`ft3_make`. Keep the attempt-index
   contract as decided, or normalize to 1?

**Fouls / FTs / possession**
7. Same-period foul/FT rule. **[R]** Re-anchor the foul to sit immediately
   before its first FT; the trip lives in the period where the FTs were shot
   (if the foul was logged at the end of period N and the FTs at the start of
   N+1, both sit at the start of N+1). Confirm.
8. FT chain `required=True` uniformly on all four FT events (`ft1_make`,
   `ft2_make`, `ft3_make`, `ft1_miss`). Confirm.
9. `poss_start` placement (Section 7.2). **[R]** `poss_start` is placed
   immediately before the window's first `indicate_poss` event and sets
   `current_poss` at placement; for mid-game transitions the transition event
   is INSIDE the window it closes (`poss_end` after the event). The first
   `indicate_poss` of a period may be a `pot_poss_ending_scoring_opp`, a
   `jump_ball_win`, or a `turnover` -- not a shot. Synthesized events inherit
   the anchor event's timestamp (or None for untimed sources). Confirm.
10. Jump-ball turnover (7.6). **[R]** When `current_poss` is set and an
    opponent `jump_ball_win` occurs: synthesize a team-only turnover for the
    possessor placed immediately BEFORE the `jump_ball_win`; the synthesized
    turnover's `always` transition handles the handoff and the jump-ball's own
    transition is skipped. If a real turnover already exists in the window: no
    synthesis and no jump-ball transition. Opening tip excluded (`current_poss`
    unset). Confirm.

**Lineups / invariants / process**
11. On-court invariant: exempt `standard_foul`/`elevated_foul` (the committer
    may be off court, on the bench, or a coach). `o_foul_draw` (the fouled
    player) stays under the check. Over/under-lineup rare-but-legitimate cases
    still error and become manually-reviewed games. Confirm.
12. Catalog migration mechanics: run `discover-pbp` over MSG=6 action types,
    review each, set `standard_foul`/`elevated_foul`; existing
    `handling='foul'` rows are replaced (no `foul` fallback). Confirm.
13. Errored-game mechanics (Section 10): confirm (a) status home -- **[R]** a
    new `core.pbp_game_status` table rather than a column on `staging.games`;
    (b) scope -- an errored game keeps ALL its staging rows (LeagueGameLog +
    PBP) in staging and excludes them from `_merge_staging` until reviewed;
    (c) `core.errors` extension columns (`game_id`, `identity`, `dataset`,
    `event_id`, `seq`, `event`); (d) the PBP phase re-processes games whose
    status is `error`/`pending` on rerun (coverage interplay). Confirm or
    adjust.


1. (a) correct, (b) yes an and-one has one pot_poss_ending_scoring_opp before the fg_make; does not matter if the ft is a make or miss, (c) yes absolutely 2 attempts
2. There should never be a fg miss event on a shot that is fouled. That is an impossible event. If there is it should be removed. We don't record a miss, since they were fouled. So it would be only one pot_poss_ending_scoring_event
3. confirm. It does not impact pot_poss_ending_scoring_opps or poss_start/ends
4. confirm
5. confirm and to all other db_columns that are missing mappings to provided pbp data fields
6. keep as is. Certain leagues award 2pt fts and 3pt fts rather than 2/3 1pt fts. So those events will be assigned in pbp_events when we come across them.
7. confirm
8. confirm I think? not sure what that means
9. No. poss_start should always be placed immediately after and at the same secs (if necessary) as the previous poss_end. If there is not a previous poss_end in the period, then the first poss_start goes at period_start. Confirm.
10. Confirm. So jumpballs itself does not do possession change, but it can trigger turnovers, which does change possession
11. Confirm
12. Confirm. Ensure that this is following the standard, source-agnostic discovery process we created. Once everything is settled, we will run this.
13. We don't need a new table do we? Don't we have an existing column or something that we use? What is best practice? Do we need a new table? What should the error/review/correct/rerun process be according to best practice.

Go ahead and implement what has been confirmed. Then go ahead and clean up the tracking documents so that we can focus on the remaining topics more focusedly. Always use absolute best practice. Do not cut corners. Implement fully. DRY, config-driven design. Do not hardcode. No hacky solutions. No antipractices. No backwards compatability. Please ensure all of these are followed.

Any more questions/thoughts at all, please share.