standard pbp columns:

- identity
  - nba_id
  - etc

- game_id
  - external game id

- period
  - 1
  - 2
  - 3
  - 4
  - OT1
  - OT2
  - etc

- secs_remaining
  - parse identity-specific timestamp format
  - nba_id: PT10M27.00S --> 627

- event_id
  - serial integer, per event (internal)

- team_id
  - external team id

- player_id
  - external player id

- event
  - fg2_make
  - fg2_miss
  - fg3_make
  - fg3_miss
  - ft_make
  - ft_miss
  - o_reb
  - d_reb
  - fg2_assist
  - fg3_assist
  - turnover
  - block
  - steal
  - period_start
  - period_end
  - sub_in
  - sub_out
  - jump_ball_win
  - jump_ball_lose
  - foul_commit
  - foul_draw_no_ft
  - foul_draw_1_ft
  - foul_draw_2_ft
  - foul_draw_3_ft
  - foul_draw_tov
  - period_end

- poss_team_id

- poss_change
  - boolean

- home_player_1_id

- home_player_2_id

- home_player_3_id

- home_player_4_id

- home_player_5_id

- away_player_1_id

- away_player_2_id

- away_player_3_id

- away_player_4_id

- away_player_5_id

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
  - secs = (sum of ((secs_remaining @ period_start) - (secs_remaining @ period_end)) for every period value)
  - poss = (sum of every consecutive event segment of team team_poss_id until poss_change = true)
  - o_poss_secs = (sum of ((secs_remaining @ first_record) - (secs_remaining @ last_record)) for every team poss)
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
  - secs = (sum of ((secs_remaining @ first_record) - (secs_remaining @ last_record)) for every consecutive event segment of player home/away_player_1/2/3/4/5_id for every period value)
  - poss = (sum of every consecutive event segment of on_player team_poss_id until poss_change = true)
  - o_poss_secs = (sum of ((secs_remaining @ first_record) - (secs_remaining @ last_record)) for every on_player poss)
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
  - poss = (sum of every consecutive event segment of opp_team team_poss_id until poss_change = true)
  - o_poss_secs = (sum of ((secs_remaining @ first_record) - (secs_remaining @ last_record)) for every opp_team poss)
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
  - poss = (sum of every consecutive event segment of opp_player team_poss_id until poss_change = true)
  - o_poss_secs = (sum of ((secs_remaining @ first_record) - (secs_remaining @ last_record)) for every opp_player poss)
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
  - poss = (sum of every consecutive event segment of on_player team_poss_id until poss_change = true)
  - o_poss_secs = (sum of ((secs_remaining @ first_record) - (secs_remaining @ last_record)) for every on_player poss)
  - poss_ending_ft_trips = (sum of foul_draw_2_ft on_player events) + (sum of foul_draw_3_ft on_player events)