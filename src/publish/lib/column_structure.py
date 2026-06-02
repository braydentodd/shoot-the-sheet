from dataclasses import dataclass
from typing import Any, List, Tuple, Union

from src.core.definitions.leagues import LEAGUES
from src.publish.definitions.view_columns import VIEW_COLUMNS
from src.publish.definitions.layout import SECTIONS_CONFIG, SUBSECTIONS
from src.publish.definitions.presentation import PRESENTATION_DEFAULTS
from src.publish.definitions.stats import DEFAULT_STAT_RATE, STAT_RATES


@dataclass(frozen=True)
class ColumnContext:
    """Composite key tagging mode-specific column mappings (rate + timeframe)."""
    base_section: str
    rate:         Union[str, None] = None
    timeframe:    Union[int, None] = None

def _base_section(ctx: Any) -> str:
    """Extract the base section name from a context."""
    if not ctx:
        return ctx

    if isinstance(ctx, ColumnContext):
        return ctx.base_section
    
    ctx_str = str(ctx)
    ctx_prefix = ctx_str.split('__')[0]
    
    # Match the mapped prefix cleanly against registered config sections
    for section in SECTIONS_CONFIG.keys():
        if ctx_prefix.startswith(section):
            return section
            
    return ctx_prefix


def _normalize_subsection_key(subsection: Union[str, None]) -> Union[str, None]:
    """Map subsection keys to canonical SUBSECTIONS keys (case-insensitive)."""
    if subsection is None:
        return None

    raw = str(subsection).strip()
    if not raw:
        return None

    raw_lower = raw.lower()
    for key in SUBSECTIONS.keys():
        if key.lower() == raw_lower:
            return key

    return raw


def _subsection_display_name(subsection: Union[str, None]) -> str:
    """Resolve display name for a subsection key with sensible fallback."""
    key = _normalize_subsection_key(subsection)
    if key is None:
        return ''

    cfg = SUBSECTIONS.get(key, {})
    if 'display_name' in cfg:
        return cfg['display_name']
    return str(key).replace('_', ' ').title()


_SEPARATOR_DEF = {
    'is_separator': True,
    'separator_type': 'section',
    'description': '',
    'sections': [],
    'subsection': None,
    'views': ['all_teams', 'all_players', 'individual_team'],
    'stats_mode': 'both',
    'percentile': None,
    'editable': False,
    'scale_with_rate': False,
    'format': 'text',
    'decimal_places': None,
    'width_class': None,
    'leagues': list(LEAGUES.keys()),
    'default': None,
    'align': 'center',
    'emphasis': None,
    'values': {},
}


def _make_separator(context_key: str, visible: bool, separator_type: str = 'section') -> Tuple:
    """Create a separator column tuple for insertion between groups."""
    sep_def = dict(_SEPARATOR_DEF)
    sep_def['separator_type'] = separator_type
    if separator_type == 'subsection':
        sep_def['width_class'] = PRESENTATION_DEFAULTS.get('subsection_separator_width', 2)
    else:
        sep_def['width_class'] = PRESENTATION_DEFAULTS.get('section_separator_width', 4)
    return ('_sep', sep_def, visible, context_key)

def generate_percentile_columns() -> dict:
    """Auto-generate percentile companion column defs for all columns with percentile set.

    Companion columns are narrow (10px), always visible, and display the
    percentile rank (0-100) with colour shading.  Headers merge across the
    stat + companion pair so the column name spans both.
    """
    pct_columns = {}
    for col_key, col_def in VIEW_COLUMNS.items():
        if not col_def.get('percentile'):
            continue
        pct_key = f"{col_key}_pct"
        pct_columns[pct_key] = _make_companion_def(col_def, col_key, pct_key)
    return pct_columns


def _make_companion_def(base_def: dict, base_key: str,
                        pct_key: str = '') -> dict:
    """Create a percentile companion column definition from a base stat column.

    Used by generate_percentile_columns() for static columns and by
    _insert_opponent_columns() for dynamically-generated opponent columns.
    """
    if not pct_key:
        pct_key = f"{base_key}_pct"
    return {
        'key': pct_key,
        'display_name': '',
        'description': '',
        'sections': base_def.get('sections', ['current_stats']),
        'subsection': base_def.get('subsection'),
        'stats_mode': base_def.get('stats_mode', 'both'),
        'percentile': None,
        'editable': False,
        'scale_with_rate': False,
        'format': 'number',
        'decimal_places': 0,
        'is_generated_percentile': True,
        'is_percentile_companion': True,
        'base_stat': base_key,
        'base_percentile': base_def.get('percentile', 'standard'),
        'values': base_def.get('values', {}),
        'is_opponent_col': base_def.get('is_opponent_col', False),
        'width_class': PRESENTATION_DEFAULTS.get('percentile_companion_width', 10),
        'views': base_def.get('views', ['all_teams', 'all_players', 'individual_team']),
    }


def get_all_columns_with_percentiles() -> dict:
    """Get VIEW_COLUMNS plus auto-generated percentile columns."""
    all_cols = dict(VIEW_COLUMNS)
    all_cols.update(generate_percentile_columns())
    return all_cols


def get_columns_by_filters(section=None, subsection=None, entity=None,
                           stats_mode=None, include_percentiles=False) -> dict:
    """
    Get columns matching specified filters.

    Args:
        section: Filter by section name
        subsection: Filter by subsection name
        entity: 'player', 'team', or 'opponents' — checks values dict
        stats_mode: 'basic', 'advanced', or 'both'
        include_percentiles: Include auto-generated percentile columns
    """
    columns = get_all_columns_with_percentiles() if include_percentiles else VIEW_COLUMNS
    filtered = {}
    subsection_filter = _normalize_subsection_key(subsection) if subsection else None

    for col_key, col_def in columns.items():
        if section and section not in col_def.get('sections', []):
            continue
        col_subsection = _normalize_subsection_key(col_def.get('subsection'))
        if subsection_filter and col_subsection != subsection_filter:
            continue
        if entity:
            if entity not in col_def.get('values', {}):
                continue
        if stats_mode and stats_mode != 'both':
            col_mode = col_def.get('stats_mode', 'both')
            if col_mode != 'both' and col_mode != stats_mode:
                continue
        filtered[col_key] = col_def

    return filtered


def get_columns_for_section_and_entity(section: str, entity: str,
                                       stats_mode: str = 'both',
                                       include_percentiles: bool = False,
                                       view_type: str = None) -> List[Tuple]:
    """
    Get ordered columns for a section and entity.
    All sections with subsection-assigned columns are ordered by SUBSECTIONS;
    columns without a subsection come first in definition order.
    """
    columns = get_columns_by_filters(
        section=section, entity=entity,
        stats_mode=stats_mode, include_percentiles=include_percentiles
    )

    # Convert values object for opponent columns (only in stats sections)
    is_stats_section = SECTIONS_CONFIG.get(section, {}).get('stats_timeframe') is not None
    if view_type in ['all_teams', 'teams'] and is_stats_section:
        opp_columns = {}
        for col_key, col_def in columns.items():
            opp_expr = col_def.get('values', {}).get('opponents', {}).get('fn')
            if opp_expr:
                opp_def = dict(col_def)
                opp_def['display_name'] = f"{col_key}"
                opp_def['values'] = {'team': {'fn': opp_expr}}
                opp_def['is_opponent_col'] = True
                opp_def['percentile'] = 'standard'
                opp_def['subsection'] = 'opponent'
                
                opp_key = f'opp_{col_key}'
                opp_columns[opp_key] = opp_def
                
                # Companion if needed
                if include_percentiles and 'percentile' in opp_def:
                    opp_pct_key = f"{opp_key}_pct"
                    opp_columns[opp_pct_key] = _make_companion_def(opp_def, opp_key, opp_pct_key)

        columns.update(opp_columns)

    # Separate columns with and without subsections
    no_subsec = []
    subsec_groups = {}
    for col_key, col_def in columns.items():
        subsec = _normalize_subsection_key(col_def.get('subsection'))
        if subsec is None:
            no_subsec.append((col_key, col_def))
        else:
            if subsec not in subsec_groups:
                subsec_groups[subsec] = []
            subsec_groups[subsec].append((col_key, col_def))

    # Columns without subsection first, then ordered by SUBSECTIONS
    ordered = list(no_subsec)
    ordered_subsections = set()
    for subsec, cfg in SUBSECTIONS.items():
        # Check if the subsection is applicable for this section and view
        cfg_views = cfg.get('views', [])
        view_match = True
        if view_type:
            if view_type == 'individual_team' and 'team' in cfg_views:
                view_match = True
            elif view_type in cfg_views:
                view_match = True
            else:
                view_match = False

        if section not in cfg.get('sections', []) or not view_match:
            continue
        
        if subsec in subsec_groups:
            ordered.extend(subsec_groups[subsec])
            ordered_subsections.add(subsec)

    # Keep any unmapped subsection columns instead of dropping them.
    for subsec, subsec_cols in subsec_groups.items():
        if subsec not in ordered_subsections:
            ordered.extend(subsec_cols)
    return ordered


def build_view_columns(entity: str = 'player', stats_mode: str = 'both',
                        view_type: str = 'individual_team',
                        default_mode: str = DEFAULT_STAT_RATE,
                        league: str = None,
                        default_timeframe: int = 3) -> List[Tuple]:
    """
    Build complete column structure for a view with rate tripling.

    Returns list of (column_key, column_def, visible, context_section) tuples.

    Stats sections are tripled — each appears once per STAT_RATE with a composite
    context key like 'current_stats__per_possession'. Only the default_mode variant
    is visible; others are hidden for instant rate switching via column show/hide.

    Percentile columns are interleaved immediately after their base stat column.
    Columns are filtered by their 'views' array and 'leagues' list.
    """
    fmt = PRESENTATION_DEFAULTS
    hide_advanced = fmt.get('hide_advanced_columns', True)

    _view_TYPE_KEY = {
        'individual_team': 'individual_team',
        'team': 'individual_team',
        'all_players': 'all_players',
        'players': 'all_players',
        'all_teams': 'all_teams',
        'teams': 'all_teams',
    }
    view_key = _view_TYPE_KEY.get(view_type, 'team')
    pct_columns = generate_percentile_columns()

    def _normalize_views(col_def):
        col_views = col_def.get('views', ['all_teams', 'all_players', 'individual_team'])
        if isinstance(col_views, str):
            return [col_views]
        return col_views

    def _skip_column(col_def):
        """Return True if this column should be skipped for the current context."""
        if view_key not in _normalize_views(col_def):
            return True
        if league and league not in col_def.get('leagues', []):
            return True
        if view_key == 'all_teams':
            vals = col_def.get('values', {})
            if 'all_teams' not in vals and 'teams' not in vals and 'team' not in vals:
                return True
        return False

    def _append_section_columns(section, context_key, mode_visible):
        """Append columns for a section with given context key and base visibility."""
        section_cols = get_columns_for_section_and_entity(
            section=section, entity=None,
            stats_mode='both', include_percentiles=False,
            view_type=view_key
        )
        prev_subsection_key = None
        for col_key, col_def in section_cols:
            if _skip_column(col_def):
                continue

            subsection_key = _normalize_subsection_key(col_def.get('subsection')) or '__none__'
            if prev_subsection_key is not None and subsection_key != prev_subsection_key:
                all_columns.append(_make_separator(context_key, mode_visible, 'subsection'))
            prev_subsection_key = subsection_key

            col_stats_mode = col_def.get('stats_mode', 'both')
            visible = mode_visible
            if hide_advanced and col_stats_mode == 'advanced':
                visible = False
            elif not hide_advanced and col_stats_mode == 'basic':
                visible = False

            all_columns.append((col_key, col_def, visible, context_key))

            pct_key = f"{col_key}_pct"
            if col_def.get('percentile'):
                pct_def = pct_columns.get(pct_key)
                if not pct_def:
                    pct_def = _make_companion_def(col_def, col_key, pct_key)
                all_columns.append((pct_key, pct_def, visible, context_key))

    all_columns = []
    
    sections = list(SECTIONS_CONFIG.keys())

    for idx, section in enumerate(sections):
        section_cfg = SECTIONS_CONFIG.get(section, {})
        is_last_section = (idx == len(sections) - 1)

        if section_cfg.get('stats_timeframe'):
            # Current stats just use the normal rate tripling
            if section == 'current_stats':
                for stat_rate in STAT_RATES:
                    context_key = ColumnContext(base_section=section, rate=stat_rate)
                    mode_visible = (stat_rate == default_mode)

                    _append_section_columns(section, context_key, mode_visible)
                    if not is_last_section:
                        all_columns.append(_make_separator(context_key, mode_visible, 'section'))
            else:
                # Historical and Postseason expand by rate AND timeframe
                from src.publish.definitions.stats import HISTORICAL_TIMEFRAMES
                supported_years = list(HISTORICAL_TIMEFRAMES.keys())
                for y in supported_years:
                    for stat_rate in STAT_RATES:
                        context_key = ColumnContext(base_section=section, timeframe=int(y), rate=stat_rate)
                        mode_visible = (stat_rate == default_mode and y == default_timeframe)
                        
                        _append_section_columns(section, context_key, mode_visible)
                        if not is_last_section:
                            all_columns.append(_make_separator(context_key, mode_visible, 'section'))

        else:
            # Non-stats sections: single copy, always visible
            context_key = ColumnContext(base_section=section)
            _append_section_columns(section, context_key, True)
            if not is_last_section and section != 'entities':
                all_columns.append(_make_separator(context_key, True, 'section'))

    return all_columns


def build_column_index_map(columns_list: List[Tuple]) -> dict:
    """
    Build an O(1) lookup dictionary for column indices.
    Keys are either just the column_key, or a tuple of (column_key, context_section).
    """
    idx_map = {}
    for idx, entry in enumerate(columns_list):
        col_key = entry[0]
        col_ctx = entry[3] if len(entry) > 3 else None
        
        # Save both exact context matches and "first seen" contextless matches
        # Allows mapped lookup by map.get((col_key, ctx)) or map.get(col_key)
        if (col_key, col_ctx) not in idx_map:
            idx_map[(col_key, col_ctx)] = idx
        if col_key not in idx_map:
            idx_map[col_key] = idx
            
    return idx_map

def get_column_index(column_key: str, columns_list: List[Tuple],
                     context_section: Union[str, None] = None) -> Union[int, None]:
    """
    Legacy wrapper. In high-frequency loops, prefer building the index map directly
    via build_column_index_map() instead.
    """
    idx_map = build_column_index_map(columns_list)
    if context_section is not None:
        return idx_map.get((column_key, context_section))
    return idx_map.get(column_key)


# ============================================================================
# HEADER BUILDING
# ============================================================================

# build_headers moved to src.publish.lib.tabular_layout (tabular-specific)
