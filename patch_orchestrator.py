import re

with open('src/etl/orchestrator.py', 'r') as f:
    text = f.read()

# remove it from outside the loop
text = re.sub(r"""        stage_include_columns: Union\[Set\[str\], None\] = None\n        stage_exclude_columns: Union\[Set\[str\], None\] = None\n        if handler == 'discover_entities':\n            stage_include_columns = identity_columns\n        elif handler == 'populate_profiles':\n            stage_exclude_columns = identity_columns\n""", '', text)

# put it inside the inner loop
inner = """                    stage_source_kw = dict(
                        league_key=league_key,
                        source_key=stage_source_key,
                        datasets=stage_bundle['datasets'],
                        api_field_names=stage_bundle['api_field_names'],
                        api_config=stage_bundle['api_config'],
                        make_fetcher=stage_bundle['client_mod'].make_fetcher,
                    )
                    
                    stage_include_columns: Union[Set[str], None] = None
                    stage_exclude_columns: Union[Set[str], None] = None
                    if handler == 'discover_entities':
                        stage_include_columns = {THE_GLASS_ID_COLUMN, get_source_id_column(stage_source_key)}
                    elif handler == 'populate_profiles':
                        stage_exclude_columns = {THE_GLASS_ID_COLUMN, get_source_id_column(stage_source_key)}
"""
text = re.sub(r"""                    stage_source_kw = dict\(
                        league_key=league_key,
                        source_key=stage_source_key,
                        datasets=stage_bundle\['datasets'\],
                        api_field_names=stage_bundle\['api_field_names'\],
                        api_config=stage_bundle\['api_config'\],
                        make_fetcher=stage_bundle\['client_mod'\]\.make_fetcher,
                    \)""", inner, text)

with open('src/etl/orchestrator.py', 'w') as f:
    f.write(text)
