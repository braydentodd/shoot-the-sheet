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
  - o_reb (an offensive rebound)
  - d_reb (a defensive rebound)
  - fg2_assist (an assist on a 2-point field goal)
  - fg3_assist (an assist on a 3-point field goal)
  - turnover (a turnover; includes offensive violations)
  - block (a block)
  - steal (a steal)
  - period_start (start of a period)
  - overtime_start (start of an overtime)
  - sub_in (substitution in, will include one at 0 secs at the start of each period for all players on the court; if not provided at the start of periods, then will be backfilled when players record their first event whether it is a fg2m, turnover, foul, or sub_out etc, which will trigger a sub_in event to be added to the start of the period if they did not already have a sub_in event previously in the period)
  - sub_out (substitution out, will include one at 0 secs at the end of each period for all players on the court; includes ejections)
  - jump_ball_win (jump ball win)
  - jump_ball_lose (jump ball lose)
  - foul_commit (foul commit; personal, technical, flagrant, any kind of foul)
  - foul_draw_no_ft (foul draw no free throw; foul that does not lead to free throws)
  - foul_draw_1_ft (foul draw 1 free throw; foul that leads to 1 free throw)
  - foul_draw_2_ft (foul draw 2 free throws; foul that leads to 2 free throws)
  - foul_draw_3_ft (foul draw 3 free throws; foul that leads to 3 free throws)
  - foul_draw_tov (foul draw turnover; foul that leads to a turnover)
  - new_poss (new possession for a team; turnover, d_reb, period_start, overtime_start, jump_ball_win if didn't have possession previously)

===========

standard pbp events --> standard game stats mapping:

team: events where team_id = ext_team_id
player: events where player_id = ext_player_id
opp_team: events where team_id != ext_team_id
opp_player: events where team_id != ext_team_id and 1 of home_player_1/2/3/4/5_id or away_player_1/2/3/4/5_id = ext_player_id
on_player: events where team_id = ext_team_id and 1 of home_player_1/2/3/4/5_id or away_player_1/2/3/4/5_id = ext_player_id

team domain
  - fg2m = (sum of fg2_make team events)
  - fg2a = (sum of fg2_make team events) + (sum of fg2_miss team events)
  - fg3m = (sum of fg3_make team events)
  - fg3a = (sum of fg3_make team events) + (sum of fg3_miss team events)
  - ftm = (sum of ft_make team events)
  - fta = (sum of ft_make team events) + (sum of ft_miss team events)
  - o_rebs = (sum of o_reb team events)
  - d_rebs = (sum of d_reb team events)
  - turnovers = (sum of turnover team events)
  - win = ((team fg2m * 2) + (team fg3m * 3) + (team ftm)) > ((opp_team fg2m * 2) + (opp_team fg3m * 3) + (opp_team ftm))
  - secs = (secs value at final record in pbp)
  - poss = (sum of new_poss team events)
  - o_poss_secs = (secs value at new_poss for opp_team) - (secs value at new_poss for team) for every team poss)
  - poss_ending_ft_trips = (sum of foul_draw_2_ft team events) + (sum of foul_draw_3_ft team events)

player domain
  - fg2m = (sum of fg2_make player events)
  - fg2a = (sum of fg2_make player events) + (sum of fg2_miss player events)
  - fg3m = (sum of fg3_make player events)
  - fg3a = (sum of fg3_make player events) + (sum of fg3_miss player events)
  - ftm = (sum of ft_make player events)
  - fta = (sum of ft_make player events) + (sum of ft_miss player events)
  - o_rebs = (sum of o_reb player events)
  - d_rebs = (sum of d_reb player events)
  - assists = (sum of fg2_assist player events) + (sum of fg3_assist player events)
  - assist_points = ((sum of fg2_assist player events) * 2) + ((sum of fg3_assist player events) * 3)
  - turnovers = (sum of turnover player events)
  - blocks = (sum of block player events)
  - steals = (sum of steal player events)
  - fouls = (sum of foul player events)
  - win = (((sum of fg2_make team events) * 2) + ((sum of fg3_make team events) * 3) + (sum of ft_make team events)) > (((sum of fg2_make opp_team events) * 2) + ((sum of fg3_make opp_team events) * 3) + (sum of ft_make opp_team events))
  - o_fouls_drawn = (sun of foul_draw_tov player events)
  - secs = ((secs value at sub_out player event) - (secs value at preceeding sub_in player event) for every sub_out player event)
  - poss = ((sum of new_poss team events) while in between sub_in and sub_out player events)
  - o_poss_secs = (secs value at new_poss for opp_team) - (secs value at preceeding new_poss for team) for every player poss)
  - poss_ending_ft_trips = (sum of foul_draw_2_ft player events) + (sum of foul_draw_3_ft player events)

opp_team domain
  - fg2m = (sum of fg2_make opp_team events)
  - fg2a = (sum of fg2_make opp_team events) + (sum of fg2_miss opp_team events)
  - fg3m = (sum of fg3_make opp_team events)
  - fg3a = (sum of fg3_make opp_team events) + (sum of fg3_miss opp_team events)
  - ftm = (sum of ft_make opp_team events)
  - fta = (sum of ft_make opp_team events) + (sum of ft_miss opp_team events)
  - o_rebs = (sum of o_reb opp_team events)
  - d_rebs = (sum of d_reb opp_team events)
  - turnovers = (sum of turnover opp_team events)
  - poss = (sum of new_poss opp_team events)
  - o_poss_secs = (secs value at new_poss for team) - (secs value at preceeding new_poss for opp_team) for every opp_team poss)
  - poss_ending_ft_trips = (sum of foul_draw_2_ft opp_team events) + (sum of foul_draw_3_ft opp_team events)

opp_player domain
  - fg2m = (sum of fg2_make opp_player events)
  - fg2a = (sum of fg2_make opp_player events) + (sum of fg2_miss opp_player events)
  - fg3m = (sum of fg3_make opp_player events)
  - fg3a = (sum of fg3_make opp_player events) + (sum of fg3_miss opp_player events)
  - ftm = (sum of ft_make opp_player events)
  - fta = (sum of ft_make opp_player events) + (sum of ft_miss opp_player events)
  - o_rebs = (sum of o_reb opp_player events)
  - d_rebs = (sum of d_reb opp_player events)
  - turnovers = (sum of turnover opp_player events)
  - poss = ((sum of new_poss opp_team events) while in between sub_in and sub_out player events)
  - o_poss_secs = (secs value at new_poss for team) - (secs value at preceeding new_poss for opp_player) for every opp_player poss)
  - poss_ending_ft_trips = (sum of foul_draw_2_ft opp_player events) + (sum of foul_draw_3_ft opp_player events)

on_player domain
  - fg2m = (sum of fg2_make on_player events)
  - fg2a = (sum of fg2_make on_player events) + (sum of fg2_miss on_player events)
  - fg3m = (sum of fg3_make on_player events)
  - fg3a = (sum of fg3_make on_player events) + (sum of fg3_miss on_player events)
  - ftm = (sum of ft_make on_player events)
  - fta = (sum of ft_make on_player events) + (sum of ft_miss on_player events)
  - o_rebs = (sum of o_reb on_player events)
  - d_rebs = (sum of d_reb on_player events)
  - turnovers = (sum of turnover on_player events)
  - poss_ending_ft_trips = (sum of foul_draw_2_ft on_player events) + (sum of foul_draw_3_ft on_player events)