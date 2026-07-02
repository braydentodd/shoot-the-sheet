Short term:
- [ ] understand how team level, player level, league level, game level, and pbp level map to db columns
- [ ] understand how staging tables map to core tables
- [ ] understand how games are identified and staged
- [ ] understand how game coverages and season coverages work
- [ ] build pbp parser and dict
- [ ] enforce config validation
- [ ] DRY, config-driven audit; eradicate hardcodes, defaults, unnecessary defensive code, backwards compatibility, inconsistent naming conventions and coding patterns
- [ ] implement shoot_the_sheet data source (with option of sheets or word source)
- [ ] set up github actions

Long term:
- [ ] redesign sheet layout for better visibility and new use-cases (more number context, more condensed, multi-team stats)
- [ ] add player view
- [ ] rewrite publish to be source-agnostic, consistent, and config-driven
- [ ] Find a RAPM source
- [ ] Find a contracts source
- [ ] Find an injuries source
- [ ] set up db column comments
- [ ] rewrite all comments/documentation