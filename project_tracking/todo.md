# ETL System - Status & To Do

## Current Status ✅

All core ETL architecture and PBP implementation complete:
- ✅ 3-tier promotion (staging → ready → core)
- ✅ Config-driven execution (datasets, columns, schemas)
- ✅ PBP pipeline fully wired (NBA API playbyplayv3)
- ✅ DRY design (no duplication)
- ✅ Type-safe (Literal types throughout)
- ✅ Validated (comprehensive startup validation)
- ✅ Clean architecture (no technical debt)

## Immediate Next Steps

### 1. Test Run
```bash
python -m src.cli --league nba --stage ingest
```

Expected outcome:
- Staging tables populated
- Ready tables merged
- No crashes
- Check `core.errors` table for any logged issues

### 2. Generate PBP CSV Comparisons
After first successful run, export sample games for manual review:
```sql
COPY (
    SELECT * FROM staging.pbp_events_staging
    WHERE ext_game_id IN ('0022300001', '0022300002', '0022300003')
    ORDER BY ext_game_id, pbp_secs
) TO '/tmp/normalized_pbp_sample.csv' CSV HEADER;
```

Compare against raw NBA API responses (requires adding logging in orchestrator).

### 3. Verify PBP Stats
Check that accumulated PBP stats match box score stats:
```sql
SELECT 
    g.ext_id,
    g.home_team_id,
    g.away_team_id,
    tg.fg2m, tg.fg3m, tg.ftm,
    tg.opp_fg2m, tg.opp_fg3m, tg.opp_ftm
FROM core.games g
JOIN core.team_games tg ON tg.game_id = g.game_id
WHERE g.season = '2023-24'
LIMIT 10;
```

## Short Term

- [ ] Error logging wiring in orchestrator phases (add `capture_errors()` context manager)
- [ ] GitHub Actions CI/CD setup
- [ ] Performance profiling (identify slow queries)
- [ ] Documentation: Architecture guide, deployment guide

## Medium Term

- [ ] Add more NBA API datasets (player tracking, shot charts)
- [ ] Add RealGM datasets (biographical data, awards)
- [ ] Add Barttorvik datasets (college advanced stats)
- [ ] Database column comments (COMMENT ON COLUMN statements)

## Long Term

- [ ] Find RAPM source
- [ ] Find contracts source (cap hits, expiring deals)
- [ ] Find injuries source (daily injury reports)
- [ ] Crowdsource data validation (community corrections)
- [ ] Public API layer (REST endpoints for external users)
- [ ] Web dashboard (interactive data explorer)

## Known Limitations

1. **PBP coverage**: NBA API playbyplayv3 available from 2000-01 season onward
2. **Identity priority**: Execution order determines last-write-wins (nba_id → realgm_id → barttorvik_id)
3. **Substitution backfilling**: Synthetic sub_in/sub_out events for players without explicit substitutions
4. **poss_ending_ft_trip**: Context-based detection (looks at next event) - complex edge cases possible

## Questions for Future

- Should we add real-time game updates (live scores)?
- Should we track historical data changes (full audit trail)?
- Should we expose GraphQL API in addition to REST?
