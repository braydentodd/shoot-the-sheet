I responded to all thoughts and questions thoroughly. As you think and plan out. Update the tracking document. Refer to this doc. Please ask any more questions you have at all or any more thoughts you have at all. Best practice is the goal. Nothing short of that is accepted.

Key design conclusions in the doc

1. **`sort_priority` must be ascending** (lower = earlier). The draft's foul(1)→pot(2)→shot(3)→assist(4)→ft(5) and period_end(9)→player_out(10) ordering only works ascending. But two values are off: `player_in`(11) sorts *before* `period_start`(12), and `poss_start/end` can't be priority-sorted at all (a period-start `fg` would beat `poss_start` at the same sec). Fix: renumber `period_start`=11, `player_in`=12, and **chain-place** poss markers.
2. **`pot_poss_ending_scoring_opp` having `indicate_poss=True` is load-bearing** — it's what keeps pure FT-trip windows countable (foul + FTs contain no other indicate_poss event). Your draft is self-consistent here; I preserved it.
3. **Misses carry no transition** (`fg_miss`/`ft_miss` = `poss_transition: None` in your draft) — that's what prevents the phantom-pair bug from the old review. The rebound (real or synthesized) transitions instead.
4. **The second config (`CHAIN_RULES`)** is sketched with four relationship kinds: attribution (assist→make), structural (FT→foul with and-one skip, rebound→shot), synthesis (team rebounds, jump-ball turnovers, lineup sweeps), and validation (unpaired markers, FT-without-foul → errors).
5. **No-timestamp design:** every derivation rule keys off sequence position (`seq`), never `secs`; `secs` becomes optional metadata + clock-gated fields; game structure (clock/periods/target_score) moves into league/dataset config.

1) yeah I think you might be right, but I'm not sure... I don't mind poss_start/end, player_in/out, and period_start/end being in whatever order... it all kinda feels chicken and the egg... I'm not sure what should come first. If you think you know, I'd be happy to hear. But I think we do need to modify the priority system or add overrides or something... or have some events have conditional configs attached to them... Every poss_start/end pair needs to have an indicate_poss event inside it. Every missed shot needs to be immediately followed by a rebound (well not exactly... a block in between them is permissable. We should not change the timestamp, obviously, if the rebound is recorded a few seconds later. I think we need a clean, but detailed config that lays this all out and how they all work. I'm not sure what that should look like). etc... And we will need to wire everything up, so that the config is authoritative. We do not hardcode in this codebase. We do not violate DRY, config-driven, or best practice design.

2) Yes, agreed

3) correct

4) If that is most effective, while being simplest. I require my dicts to be validated... every entry must have all the same fields even if they aren't used in every entry. No unnecessary fields, or multiple fields if they can be consolidated into one.

5) absolutely, we need to remove timestamp reliance from everything. we need to rely on sequences wherever possible

We need to use consistent (with my current design/layout in other definition files), clean, efficient, best practice config-driven design wherever possible



The questions I most need you to resolve

1. **`indicate_live_shot` is undefined** — you explained the other four fields but not this one, and I couldn't find one reading that fits all its values (`d_reb`="opponent", `o_reb`="team", makes/turnovers="opponent", `period_end`="both", `jump_ball_win`=None). My recommendation: drop it from v1 unless a rule needs it.
2. **`pot_poss_ending` counting:** miss→o_reb→make yields *two* `pot_poss_ending` events under the literal rule (o_reb is indicate_poss and breaks the sequence). Confirm that's intended — it changes the meaning of the `poss_ending_ft_trips`-style counts vs traditional formulas.
3. **`foul` is `indicate_on_court=False`** in the draft — a fouler is on court by definition, and this creates starter-scan gaps when a period opens with a foul. Recommend `True` for both foul types.
4. **Starter scan bounds:** stop at `lineup_size` found or first substitution for the team; players subbed out before any on-court event are inferred starters. Incomplete lineups → warn, not fail? (I recommended warn.)
5. **Intra-FT team o_rebs** (currently filtered): if kept, they split one FT trip into two scoring sequences. I recommended keeping the filter.
6. **Transition/state mismatch** (e.g., `d_reb` by a team that already possessed): recommend hard error (usually means bad rebound classification).



1. yes, indicate_live_shot was something I considered, but went away from. Do not need it for anything

2. A team can absolutely have multiple pot_poss_ending_scoring_opp events in the same possession. It is "potentially" possession ending, meaning the other team "could" get possession with a made shot or a defensive rebound. If the team gets an offensive rebound, they maintain possession. It does not end, but the shot WAS still "potentiall" possession ending. Make sense?

3. Absolutely not. A coach or a player on the bench could get a technical foul and it does not indicate that they are on the court. And we are also going to separate fouls into standard_fouls and elevated_fouls. I already made the change in db_columns[@db_columns.py](file:///Users/braydentodd/Repos/personal/shoot-the-sheet/src/definitions/db_columns.py) 

4. Invalid lineups are absolutely a fail/error. We cannot have too little or too many players on the court. We can not have invalid data.
 
Lineups are built using any indicate_on_court event. If there is any indicate_on_court event for a player who is not currently on the court, they should always get a player_in event at the start of the period. Even if there are already the max number, they should get the player_in event and an error should trigger. Do you think that is all best practice?

I'm trying to think of the best way to resolve these errored games. I will have to manually review, modify, and update them. I am not sure what is best practice there. It could be code issues... it could be data issues... either way, I will have to correct them. Maybe we have an error status column, and we just store the whole raw pbp data in a massive jsonb column or something and I can modify it if it has bad data? or i can update the code and rerun it if it is a code issue? idk, what is best practice?

5. Yeah, I do not want o_rebs or d_rebs in between shots that are part of the same sequence (and-ones or fts in the same ft trip). Should that be config-driven?

There may be odd cases where elevated fouls occur and they need to act as a blip in time (flagrant/technical foul is assigned, technical/flagrant fts are shot, and it should not be pot_poss_ending_scoring_opp, since it is an elevated foul, not a standard foul; and it should not change possession; once that activity is done, poss returns to the team like normal, resuming wherever they were at).

6. Yeah, I agree. Are there other instances like this that should error out because they are impossible? We should probably make a config for this. Everything should be config-driven. We could probably build most onto our existing configs without having to make a bunch of little configs.

What other questions or thoughts do you have? Ask them all, I will answer anything.

## 9. Open questions

Recommended defaults marked **[R]**.

**Schema / semantics**
1. `indicate_live_shot` in the draft was never defined. Candidate readings:
   - "whose shot does this event correspond to/resolve" -- fits `o_reb`=team,
     `d_reb`=opponent;
   - "whose live possession begins next" -- fits fg makes, turnovers,
     `pot_poss_ending`=opponent, `period_end`=both;

  *response*: do not use, does not exist
   
   Neither fits everything (jump_ball_win=None, fg_miss=opponent). **[R] Drop
   it from v1 unless a rule needs it; revisit when a rule exists.** Confirm.
2. `sort_priority` direction. **[R] Ascending (lower = earlier)**, with the
   renumber in 4.2 (`period_start`=11, `player_in`=12) and chain placement for
   poss markers. Confirm.

  *response*: confirm. I think I answered this above
  
3. `pot_poss_ending` counting semantics. Miss -> o_reb -> make: per-sequence
   gives 2 events (o_reb is `indicate_poss`, breaks the sequence); per-
   possession gives 1. The literal rule + draft config yields 2. **[R] Keep
   the literal rule (per-sequence)** but confirm -- it changes the meaning of
   the `poss_ending_ft_trips`-style counts vs traditional formulas.

  *response*: I think I answered this above
  
4. Missed FTs and "every missed shot has a rebound". **[R] Include FTs.** The
   last-FT-miss-at-period-end case already synthesizes a defensive team
   rebound per the rule. Confirm.

  *response*: absolutely, but only the last shot in a sequence. We can correctly define/decipher that, correctly?
  
5. Intra-FT team offensive rebounds (nba_data artifact). Today
   `_filter_intra_ft_rebounds` deletes them. They are `indicate_poss` events,
   so kept they would split one FT trip into two scoring sequences (2
   `pot_poss_ending` events). **[R] Keep filtering at the source layer; the
   canonical chain rules remain generic.** Confirm.

  *response*: is that the best practice way to that? I want it consistently applied to every pbp source. It should probably be a generic rule applied to every pbp source.
  
6. Foul taxonomy mapping for nba_data: which action types are `elevated_foul`
   (flagrants, technicals, clear path, double fouls, ...)? And do elevated
   fouls count toward team `fouls` / bonus? **[R] Both foul types count toward
   `fouls`; elevated never transitions possession.** Confirm.

  *response*: No. We need to split up fouls into two events/fields: standard_foul and elevated_foul. I already added standard_foul and elevated_foul to db_columns.py. Teams also have fouls split up into standard_fouls and elevated_fouls. We will need to define which fields are assigned to what foul type by source, using our existing field assignment process in pbp_events db table. Are you familiar with that process? Is that best practice?
  
7. `foul` is `indicate_on_court=False` in the draft. A fouler is on court by
   definition. **[R] Make both foul types `indicate_on_court=True`** (avoids
   starter-scan gaps when a period opens with a foul). Confirm.

  *response*: Answered that above. A fouler does not need to be on court.
  
8. Starter scan bounds. **[R]** Stop when `lineup_size` starters are found or
   a substitution for the team is seen; players subbed out before any
   `indicate_on_court` event are inferred starters (their `player_out` row
   proves they were on court). Incomplete lineup at `period_end` or
   `< lineup_size` starters -> **[R] warn loudly, don't fail the game** (data
   gap, not an invariant). Confirm.

  *response*: Answere this above.
  
9. Redundant sub-out at the same position/sec as the `period_end` sweep.
   **[R] Drop the redundant source `player_out` silently (log debug), keep the
   sweep.** Confirm.

  *response*: With our new improved system, this shouldn't happen. We do a player_out sweep at the end of periods for all players on court. If a source already does this for us, subs out any or all players at the end of a period, then they should already not be considered on court before we do our sweep. Does that make sense? If we still do have duplicate events such as this, then it should error out.
  
10. Transition fired while `current_poss != end_team` (e.g., a `d_reb` by a
    team that already possessed, implying a bad rebound classification).
    **[R] Raise as a data-integrity error** (fail closed), because it usually
    means the source classified o_reb/d_reb wrong. Confirm.

  *response*: Answered above. yes that should be an error along with any other data integrity violations such as this. We should define this in a config-driven manner.
  
11. Player possession qualification stays "on court during window + an
    `indicate_poss` event in their on-court span" -- now seq-based. Confirm.

  *response*: Absolutely. If a player is on court for part of a possession, but ann indicate_poss event doesn't happen in their time, then it should not count as a possession for them. And if a poss_start/poss_end window does not have an indicate_poss event inside, then it should be an error unless the window is ended by a period_end.
  
12. `points` on `PBP_EVENTS` replaces `_sum_points`; NBA FTs are 1 point each
    (`ft2_make`/`ft3_make` = attempt index, not points). The current
    `ft2_make`->2 / `ft3_make`->3 branches are vestigial. **[R] points = 1 for
    all FT makes.** Confirm.

  *response*: Yeah, that's correct. But we do need the optionality for events to be defined as ft2_make and ft3_make, as the G League is doing this. But yes, we should be tracking points as an accumulated field as well.
  
13. Rename `poss_ending_ft_trips` -> e.g. `poss_ending_scoring_opps`? It counts
    `pot_poss_ending_scoring_opp` (includes FGAs). Confirm.

  *response*: Confirm. Does the logic of it make sense? considering elevated fouls (technicals/flagrants), and-ones, normal fts, 2 & 3 pt free throws, etc... do you get what I am trying to quantify? Are we doing it right?
  
14. Empty-window cleanup removes only the `poss_start`/`poss_end` markers; the
    events inside stay. Confirm.

  *response*: Confirm... talked about this some in #11 as well.
  

**Scope / process**
15. Pairing/synthesis errors: raise -> orchestrator catches -> `core.errors`
    + game fails. Consistent with existing fail-closed policy. Confirm.

  *response*: Yes we should always be consistent with existing processes, unless it is not best practice. Then we should change it and improve.
  
16. Catalog migration: existing reviewed `core.pbp_events` rows with
    `handling='foul'` need remapping to `standard_foul`/`elevated_foul`.
    **[R] Split at review time; keep `foul` as a classifier fallback only.**
    Confirm.

  *response*: I do not use fallbacks or legacy code or backwards compatability or anything like that. Do not ever do it and if you see it report it. fouls is no longer an event. Only standard_foul and elevated_foul are used.
  
17. Keep `category` on `EventDef`? **[R] Drop it** (flags + CHAIN_RULES cover
    the needs). Confirm.

  *response*: Yeah if a field is not used or can be combined with another field drop it. I want minimal, clean fields for maximum customizability without having to adjust code everytime.
  
18. Neutral events (timeouts, coach events, ...) -- needed in v1? **[R] Out of
    scope; classifier continues to `ignore` them.**

  *response*: Ignore them. We should send them to the pbp_events table and I will assign them as events that we ignore.
  
19. Event model: keep source `event_id` intact, add `seq` + optional
    `chain_id`, derived events namespaced. Confirm.

  *response*: Don't want seq or chain_id. Just event_id. We don't need the other ones, do we? What is best practice? Or should we have a chain_id or something like that?
  
20. Game structure: add `clock`/`periods`/`target_score`/`overtime` to
    league/dataset config; clock-gate the minute/possession-seconds fields.
    Confirm.

  *response*: No... we don't need to add those fields, do we? What would they be used for? what would be the benefit?
  
21. Jump-ball turnover: confirm "opponent won a jump ball while we possessed"
    == team turnover for us, opening tip excluded, same-sec turnover guard.
    Confirm.

  *response*: Absolutely. But we don't need to make the opening tip a special case. At the beginning of a period, possession should always be reset. So the jump-ball cannot be a turnover in that case. Does that make sense?
  