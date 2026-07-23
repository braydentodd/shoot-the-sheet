- Official FIBA country codes: https://about.fiba.basketball/en/national-federations
- Country aliases: https://github.com/mledoze/countries/blob/master/countries.json

I want to hold off on adding the dataset. For now, I want to build out the generic phase handling, and the source-agnostice standardization process. I want to wire up all db_columns dataset_mappings for when we add our first nba_id pbp dataset.

How do we define, enforce, transform the standard shape that every pbp dataset needs to get to? What are the steps? Where does it happen? Do we use (a) config(s)? How do we do this consistently, DRYly, config-driven, best practice?