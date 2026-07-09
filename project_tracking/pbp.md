**PBP handling in Shoot the Sheet**

1. Triggered at the maintain_pbp phase in pipeline.
2. Grabs every dataset with phase = 'maintain_pbp'
3. Uses a source-specific handler to standardize the pbp data into the sts standard, expected pbp format (defined below)
4. Parses the standard pbp format, creating 6 result_sets (game, team, player, opp_team, opp_player, on_player, lineup)

standard pbp columns:

- identity
  - nba_id
  - etc

- game_id
  - external game id

- secs
  - parse identity-specific timestamp format
  - acccumulates 
  - nba_id format: PT10M27.00S (in first quarter) --> 93, PT10M27.00S (in second quarter) --> 813

- event_id
  - serial integer, per event (internal)

- team_id
  - external team id that did the event

- player_id
  - external player id that did the event

- event
  - fg2_make (a made 2-point field goal)
  - fg2_miss (a missed 2-point field goal)
  - fg3_make (a made 3-point field goal)
  - fg3_miss (a missed 3-point field goal)
  - ft_make (a made free throw)
  - ft_miss (a missed free throw)
  - fg2_assist (a 2-point field goal assist)
  - fg3_assist (a 3-point field goal assist)
  - turnover (a turnover)
  - o_reb (an offensive rebound)
  - d_reb (a defensive rebound)
  - block (a block)
  - steal (a steal)
  - o_foul_draw (an offensive foul drawn)
  - foul (a foul)
  - period_start (start of a period)
  - overtime_start (start of an overtime)
  - sub_in (substitution in, will include one at 0 secs at the start of each period for all players on the court; if not provided at the start of periods, then will be backfilled when players record their first event whether it is a fg2m, turnover, foul, or sub_out etc, which will trigger a sub_in event to be added to the start of the period if they did not already have a sub_in event previously in the period)
  - sub_out (substitution out, will include one at 0 secs at the end of each period for all players on the court; includes ejections)
  - jump_ball_win (jump ball win)
  - jump_ball_lose (jump ball lose)
  - poss_ending_ft_trip (foul draw that directly results in potentially possession ending free throw attempts (not counting and-ones, because the fg attempt drives it being potentially possession ending; ft trips followed by a change of possession, rebound, or out of bounds... so essentially just all free throws except and-ones, flagrants or technicals, since the shooting team automatically maintains possession on those after shooting)
  - new_poss (new possession for a team; turnover, d_reb, period_start, overtime_start, jump_ball_win if didn't have possession previously)

===========

team event: team_id = external team ID
player event: player_id = external player ID
opp_team event: team_id != external team ID
opp_player event: team_id != player's external team ID within a player's stints
on_player event: team_id = player's external team ID within a player's stints

team data
  - team_id (external team ID)
  - win = ((team fg2m * 2) + (team fg3m * 3) + (team ftm)) > ((opp_team fg2m * 2) + (opp_team fg3m * 3) + (opp_team ftm))
  - secs = (secs value at final record in pbp)
  - poss = (sum of new_poss team events)
  - o_poss_secs = (secs value at new_poss for opp_team) - (secs value at new_poss for team) for every team poss)
  - d_poss_secs = (secs value at new_poss for team) - (secs value at preceeding new_poss for opp_team) for every opp_team poss)
  - fg2m = (sum of fg2_make team events)
  - fg2a = (sum of fg2_make team events) + (sum of fg2_miss team events)
  - fg3m = (sum of fg3_make team events)
  - fg3a = (sum of fg3_make team events) + (sum of fg3_miss team events)
  - ftm = (sum of ft_make team events)
  - fta = (sum of ft_make team events) + (sum of ft_miss team events)
  - poss_ending_ft_trips = (sum of poss_ending_ft_trip team events)
  - fg2_assists = (sum of fg2_assist team events)
  - fg3_assists = (sum of fg3_assist team events)
  - turnovers = (sum of turnover team events)
  - o_rebs = (sum of o_reb team events)
  - d_rebs = (sum of d_reb team events)
  - blocks = (sum of block team events)
  - o_fouls_draws = (sum of o_foul_draw team events)
  - steals = (sum of steal team events)
  - fouls = (sum of foul team events)
  - opp_poss = (sum of new_poss opp_team events)
  - opp_fg2m = (sum of fg2_make opp_team events)
  - opp_fg2a = (sum of fg2_make opp_team events) + (sum of fg2_miss opp_team events)
  - opp_fg3m = (sum of fg3_make opp_team events)
  - opp_fg3a = (sum of fg3_make opp_team events) + (sum of fg3_miss opp_team events)
  - opp_ftm = (sum of ft_make opp_team events)
  - opp_fta = (sum of ft_make opp_team events) + (sum of ft_miss opp_team events)
  - opp_poss_ending_ft_trips = (sum of poss_ending_ft_trip opp_team events)
  - opp_turnovers = (sum of turnover opp_team events)
  - opp_o_rebs = (sum of o_reb opp_team events)
  - opp_d_rebs = (sum of d_reb opp_team events)

player result_set (record per player)
  - player_id (external player ID)
  - win = (((sum of fg2_make team events) * 2) + ((sum of fg3_make team events) * 3) + (sum of ft_make team events)) > (((sum of fg2_make opp_team events) * 2) + ((sum of fg3_make opp_team events) * 3) + (sum of ft_make opp_team events))
  - poss = ((sum of new_poss team events) while in between sub_in and sub_out player events)
  - secs = ((secs value at sub_out player event) - (secs value at preceeding sub_in player event) for every sub_out player event)
  - o_poss_secs = (secs value at new_poss for opp_team) - (secs value at preceeding new_poss for team) while in between sub_in and sub_out player events)
  - d_poss_secs = (secs value at new_poss for team) - (secs value at preceeding new_poss for opp_player) for every opp_player poss)
  - fg2m = (sum of fg2_make player events)
  - fg2a = (sum of fg2_make player events) + (sum of fg2_miss player events)
  - fg3m = (sum of fg3_make player events)
  - fg3a = (sum of fg3_make player events) + (sum of fg3_miss player events)
  - ftm = (sum of ft_make player events)
  - fta = (sum of ft_make player events) + (sum of ft_miss player events)
  - poss_ending_ft_trips = (sum of poss_ending_ft_trip player events)
  - fg2_assists = (sum of fg2_assist player events)
  - fg3_assists = (sum of fg3_assist player events)
  - turnovers = (sum of turnover player events)
  - o_rebs = (sum of o_reb player events)
  - d_rebs = (sum of d_reb player events)
  - blocks = (sum of block player events)
  - steals = (sum of steal player events)
  - o_fouls_draws = (sum of o_foul_draw player events)
  - fouls = (sum of foul player events)
  - opp_poss = ((sum of new_poss opp_team events) while in between sub_in and sub_out player events)
  - opp_fg2m = (sum of fg2_make opp_player events)
  - opp_fg2a = (sum of fg2_make opp_player events) + (sum of fg2_miss opp_player events)
  - opp_fg3m = (sum of fg3_make opp_player events)
  - opp_fg3a = (sum of fg3_make opp_player events) + (sum of fg3_miss opp_player events)
  - opp_ftm = (sum of ft_make opp_player events)
  - opp_fta = (sum of ft_make opp_player events) + (sum of ft_miss opp_player events)
  - opp_poss_ending_ft_trips = (sum of poss_ending_ft_trip opp_player events)
  - opp_turnovers = (sum of turnover opp_player events)
  - opp_o_rebs = (sum of o_reb opp_player events)
  - d_rebs = (sum of d_reb opp_player events)
  - on_fg2m = (sum of fg2_make on_player events)
  - on_fg2a = (sum of fg2_make on_player events) + (sum of fg2_miss on_player events)
  - on_fg3m = (sum of fg3_make on_player events)
  - on_fg3a = (sum of fg3_make on_player events) + (sum of fg3_miss on_player events)
  - on_ftm = (sum of ft_make on_player events)
  - on_fta = (sum of ft_make on_player events) + (sum of ft_miss on_player events)
  - on_poss_ending_ft_trips = (sum of poss_ending_ft_trip on_player events)
  - on_turnovers = (sum of turnover on_player events)
  - on_o_rebs = (sum of o_reb on_player events)
  - on_d_rebs = (sum of d_reb on_player events)