**PBP handling in Shoot the Sheet**

1. Triggered at the maintain_pbp phase in pipeline.
2. Grabs every dataset with phase = 'maintain_pbp'
3. Uses a source-specific handler to standardize the pbp data into the sts standard, expected pbp format (defined below)
4. Parses the standard pbp format, creating 4 result_sets per game of accumulated values from game (games, teams, players, lineups)
5. db_columns draws values from result_sets, going through the staging --> ready --> core process

standard pbp columns:

- identity
  - nba_id
  - etc

- game_id
  - external game id

- secs
  - parse identity-specific timestamp format
  - total accumulation as the game progresses regardless of period/ot

- event_id
  - serial integer, per event (internal)

- team_id
  - external team id that did the event

- player_id
  - external player id that did the event

- event
  - fg2_make
    - direct action: a made 2-point field goal

  - fg2_miss
    - direct action: a missed 2-point field goal

  - fg3_make
    - direct action: a made 3-point field goal

  - fg3_miss
    - direct action: a missed 3-point field goal

  - ft1_make
    - direct action: a made 1-point free throw
    - complicated: default, but some leagues may have 1 free throw for 2/3 points rather than 2/3 free throws; should be defined in pbp if so, I would think. I believe G-League follow this

  - ft1_miss
    - direct action: a missed 1-point free throw

  - ft2_make
    - direct action: a made 2-point free throw

  - ft2_miss
    - direct action: a missed 2-point free throw

  - ft3_make
    - direct action: a made 3-point free throw

  - ft3_miss
    - direct action: a missed 3-point free throw

  - fg2_assist
    - secondary action to a team fg2_make: an assist (may not be provided in every source)

  - fg3_assist
    - secondary action to a team fg3_make: an assist (may not be provided in every source)

  - turnover
    - direct action: a turnover

  - o_reb
    - direct action: an offensive rebound
    - complicated: includes out_of_bounds directly following missed field goal attempt or free throw that do not trigger a poss_end

  - d_reb
    - direct action: a defensive rebound
    - complicated: includes out_of_bounds directly following missed field goal attempt or free throw that trigger a poss_end

  - block
    - secondary action to an opponent fg_miss: a block (may not be provided in every source)

  - steal
    - secondary action to an opponent turnover: a steal (may not be provided in every source)

  - o_foul_draw
    - secondary action to an opponent offensive foul: a foul draw (may not be provided in every source)

  - foul
    - direct action: a committed foul

  - poss_ending_ft_trip
    - secondary action to a fta: a free throw trip that could potentially end a possession
    - complicated: potentially possession ending due to free throw trip; does not include and-ones, since the field goal attempt iniated the action; does not include ftas where the shooting team automatically retains possession, like technicals or flagrants... we will need to specify ft types by league and I think may by pbp dataset to know which ones to include/look for; if the shooting team gets an o_reb, it is still a poss_ending_ft_trip, as it is could have potentially been possession ending; SO for the NBA at least, this will be standard free throw trips. No and-ones, no technicals, no flagrants)

  - period_start
    - game context: the start of a period

  - period_end
    - game context: the end of a period

  - ot_start
    - game context: the start of overtime

  - ot_end
    - game context: the end of overtime

  - player_in
    - game context: player enters the game
    - complicated: may need to be inferred by parsing ensuing events (players will assuredly either record an event (fg2a, d_reb, player_out, etc) within each period, allowing us to retroactively build the player_in events at the start of each period/ot; the first and last events in each period/ot, should be a player_in and player_out event, respectively, for all players on the court); most sources will not provide lineups at start of periods/ots or at any point

  - player_out
    - game context: player leaves the game
    - complicated: sub outs, ejections, and always all players who were on the court at the end of a period/ot

  - jump_ball_win:
    - game context: a jump ball win

  - poss_start
    - complicated: source may specify who has possession... will need to be decided by source; things that start a possession: jump_ball_win, opponent turnover, d_rebound, out_of_bounds followed by an opponent offensive event, period_start/ot_start (following team offensive event determine what team's poss_start it is)

  - poss_end: 
    - complicated: always directly precedes poss_start, unless it is period_start/ot_start; always at the end of period/ot

  - out_of_bounds
    - game context: ball goes out of bounds (may not be provided in every source, will need to be decided by source... this is not just out of bounds turnovers, but anytime ball goes out of bounds during live play); influences o_reb, d_reb, poss_ending_ft_trips

===========

team event: team_id = external team ID
player event: player_id = external player ID
opp_team event: team_id != external team ID
opp_player event: team_id != player's external team ID within a player's stints
on_player event: team_id = player's external team ID within a player's stints

games result_set (not sure exactly how we get these fields in any kind of consistent manner)
  - game_id
  - home_team_id
  - away_team_id
  - date

teams result_set
  - game_id (external game ID)
  - team_id (external team ID)
  - win = (((sum of fg2_make team events) * 2) + ((sum of fg3_make team events) * 3) + (sum of ft_make team events)) > (((sum of fg2_make opp_team events) * 2) + ((sum of fg3_make opp_team events) * 3) + (sum of ft_make opp_team events))
  - poss = (sum of new_poss team events)
  - secs = (last record's secs amount)
  - o_poss_secs = (sum of secs between poss_start team and poss_end team events)
  - d_poss_secs = (sum of secs between poss_start opp_team and poss_end opp_team events)
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

players result_set
  - game_id (external game ID)
  - player_id (external player ID)
  - win = (((sum of fg2_make team events) * 2) + ((sum of fg3_make team events) * 3) + (sum of ft_make team events)) > (((sum of fg2_make opp_team events) * 2) + ((sum of fg3_make opp_team events) * 3) + (sum of ft_make opp_team events))
  - poss = (sum of poss_start on_player events)
  - secs = (sum of secs in between all player_in player events and player_out player events)
  - o_poss_secs = (sum of secs between poss_start on_team and poss_end on_team events)
  - d_poss_secs = (sum of secs between poss_start opp_player and poss_end opp_player events)
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
  - opp_poss = ((sum of new_poss opp_team events) while in between player_in and player_out player events)
  - opp_fg2m = (sum of fg2_make opp_player events)
  - opp_fg2a = (sum of fg2_make opp_player events) + (sum of fg2_miss opp_player events)
  - opp_fg3m = (sum of fg3_make opp_player events)
  - opp_fg3a = (sum of fg3_make opp_player events) + (sum of fg3_miss opp_player events)
  - opp_ftm = (sum of ft_make opp_player events)
  - opp_fta = (sum of ft_make opp_player events) + (sum of ft_miss opp_player events)
  - opp_poss_ending_ft_trips = (sum of poss_ending_ft_trip opp_player events)
  - opp_turnovers = (sum of turnover opp_player events)
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

lineups result_set:
  - this one is by far the most complicated. I need lineup data. We currently don't have this in our db, it will need to be added. It is a massive undertaking, but for every combination of players on the court between both teams (home and away, so 10 players if a 5x5 league, 6 players if a 3x3 league... this is something that needs added to the leagues config... and actually probably to our leagues db table. we may be missing some fields in there that are in our leagues dict, but should be in there... let's take a look at that.) I would ideally like all of the fields in players_result_set for every player on the court accumulated across the game for each lineup combination (if the same 10 players are on the court for multiple different stints throughout the game, they can be combined). But I have no idea how to do this properly according to best practice, and if it is real feasible, or will just be data explosion. I only have an oracle free tier vm i am hosting this on.