"""
The Glass - Tabular Layout Definitions

Tabular-specific layout logic for grid-based destinations (Google Sheets,
Excel, HTML tables). Contains row-class formatting, row index computation,
and header building logic.
"""

from typing import Any, Callable, Dict, List, Tuple, Union

from src.publish.definitions.layout import SECTIONS_CONFIG, SUBSECTIONS
from src.publish.lib.formatters import format_section_header


# ============================================================================
# HEADER ROW CLASS FORMATTING
# ============================================================================

HEADER_ROWS: Dict[str, Dict[str, Any]] = {
    'sections': {
        'row_height':                     25,
        'font_size':                      12,
        'description_spacer_count':       None,
        'divider_row_weight':             4,
        'divider_row_direction':          'below',
        'divider_column_weight':          4,
        'divider_column_direction':       'right',
        'column_a_font_size':             15,
        'column_a_divider_column_weight': None,
    },
    'subsections': {
        'row_height':                     21,
        'font_size':                      11,
        'description_spacer_count':       None,
        'divider_row_weight':             2,
        'divider_row_direction':          'below',
        'divider_column_weight':          2,
        'divider_column_direction':       'right',
        'column_a_font_size':             11,
        'column_a_divider_column_weight': None,
    },
    'columns': {
        'row_height':                     21,
        'font_size':                      10,
        'description_spacer_count':       1500,
        'divider_row_weight':             None,
        'divider_row_direction':          None,
        'divider_column_weight':          1,
        'divider_column_direction':       'right',
        'column_a_font_size':             10,
        'column_a_divider_column_weight': None,
    },
    'filters': {
        'row_height':                     12,
        'font_size':                      10,
        'description_spacer_count':       None,
        'divider_row_weight':             None,
        'divider_row_direction':          None,
        'divider_column_weight':          1,
        'divider_column_direction':       'right',
        'column_a_font_size':             10,
        'column_a_divider_column_weight': None,
    },
}


# ============================================================================
# ROW INDEX COMPUTATION
# ============================================================================

def get_row_indexes(header_rows: int = 6) -> Dict[str, int]:
    """Compute row indexes from HEADER_ROWS and header_rows config.

    Args:
        header_rows: Number of header rows (from destination config).

    Returns:
        Dict mapping row type to its index.
    """
    indexes = {}
    current_row = 0
    for row_key, rules in HEADER_ROWS.items():
        if row_key == 'sections':
            indexes['section_header_row'] = current_row
        elif row_key == 'subsections':
            indexes['subsection_header_row'] = current_row
        elif row_key == 'columns':
            indexes['column_header_row'] = current_row
        elif row_key == 'filters':
            indexes['filter_row'] = current_row

        current_row += 1

        if rules.get('divider_row_weight') and rules.get('divider_row_direction') == 'below':
            if row_key == 'sections':
                indexes['section_divider_row'] = current_row
            elif row_key == 'subsections':
                indexes['subsection_divider_row'] = current_row
            current_row += 1

    indexes['data_start_row'] = header_rows
    return indexes


# ============================================================================
# HEADER BUILDING
# ============================================================================

ROW_INDEXES = get_row_indexes()


def build_headers(columns_list: List[Tuple], mode: str = 'per_possession',
                  team_name: str = '',
                  current_season: int = 0,
                  historical_config: Union[dict, None] = None,
                  season_format_fn: Callable[[int], str] = str) -> dict:
    """
    Build header rows for tabular destinations (4-row layout).

    Row 0: Section headers (one merge per section/mode variant)
    Row 1: Subsection headers (hidden by default)
    Row 2: Column names
    Row 3: Empty filter row

    Composite context keys like 'current_stats__per_possession' produce
    mode-specific section headers (e.g. "2024-25 Stats (per 100 Poss)").
    """
    row1, row2, row3, row3_clean = [], [], [], []
    merges = []

    cur_section = None
    sec_start = 0
    cur_subsection = None
    sub_start = 0

    def _base_section(ctx: Any) -> str:
        """Extract the base section name from a context."""
        if not ctx:
            return ctx

        if isinstance(ctx, str):
            ctx_str = ctx
            ctx_prefix = ctx_str.split('__')[0]
            
            # Match the mapped prefix cleanly against registered config sections
            for section in SECTIONS_CONFIG.keys():
                if ctx_prefix.startswith(section):
                    return section
                    
            return ctx_prefix
        return str(ctx)

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

    def _get_display(section):
        base = _base_section(section)
        if base == 'entities':
            return team_name
        
        if isinstance(section, str) and '__' in section:
            sec_mode = section.split('__')[1] if isinstance(section, str) else mode
            local_hist_config = historical_config
        else:
            sec_mode = mode
            local_hist_config = historical_config
            
        base_cfg = SECTIONS_CONFIG.get(base, {})
        if base_cfg.get('stats_timeframe') and current_season:
            return format_section_header(
                base, current_season=current_season,
                historical_config=local_hist_config,
                is_postseason=(base == 'postseason_stats'),
                mode=sec_mode,
                season_format_fn=season_format_fn)
        
        return base_cfg.get('display_name', str(section))

    for idx, entry in enumerate(columns_list):
        col_key, col_def = entry[0], entry[1]
        section = entry[3] if len(entry) > 3 else (col_def.get('sections', ['unknown'])[0])
        subsection = _normalize_subsection_key(col_def.get('subsection'))

        # Separator columns break merges and emit empty cells
        if col_def.get('is_separator'):
            sep_type = col_def.get('separator_type', 'section')
            if sep_type == 'section':
                if cur_section is not None and sec_start < idx:
                    merges.append({'row': ROW_INDEXES['section_header_row'], 'start_col': sec_start, 'end_col': idx, 'value': _get_display(cur_section)})
                cur_section = None
                sec_start = idx + 1
            if cur_subsection is not None and sub_start < idx:
                merges.append({'row': ROW_INDEXES['subsection_header_row'], 'start_col': sub_start, 'end_col': idx, 'value': _subsection_display_name(cur_subsection)})
            cur_subsection = None
            sub_start = idx + 1
            if sep_type == 'section':
                row1.append('')
            else:
                row1.append('')
            row2.append('')
            row3.append('')
            continue

        # Row 0: Section headers (grouped by section)
        if section != cur_section:
            if cur_section is not None and sec_start < idx:
                display = _get_display(cur_section)
                merges.append({'row': ROW_INDEXES['section_header_row'], 'start_col': sec_start, 'end_col': idx, 'value': display})
            # Close pending subsection merge before switching sections
            if cur_subsection is not None and sub_start < idx:
                sub_display = _subsection_display_name(cur_subsection)
                merges.append({'row': ROW_INDEXES['subsection_header_row'], 'start_col': sub_start, 'end_col': idx, 'value': sub_display})
            cur_section = section
            sec_start = idx
            row1.append(_get_display(section))
            # Reset subsection tracking on section change
            cur_subsection = None
            sub_start = idx
        else:
            row1.append('')

        # Row 1: Subsection headers (all sections with subsections)
        if subsection:
            if subsection != cur_subsection:
                if cur_subsection is not None and sub_start < idx:
                    sub_display = _subsection_display_name(cur_subsection)
                    merges.append({'row': ROW_INDEXES['subsection_header_row'], 'start_col': sub_start, 'end_col': idx, 'value': sub_display})
                cur_subsection = subsection
                sub_start = idx
                row2.append(_subsection_display_name(subsection))
            else:
                row2.append('')
        else:
            # Close pending subsection merge when entering a column with no subsection
            if cur_subsection is not None and sub_start < idx:
                sub_display = _subsection_display_name(cur_subsection)
                merges.append({'row': ROW_INDEXES['subsection_header_row'], 'start_col': sub_start, 'end_col': idx, 'value': sub_display})
            cur_subsection = None
            row2.append('')

        # Row 2: Column display names
        if isinstance(section, str) and '__' in section:
            col_mode = section.split('__')[1]
        else:
            col_mode = mode
        override = col_def.get('mode_overrides', {}).get(col_mode)
        active_def = override if override else col_def
        description = active_def.get('description', col_def.get('description', ''))
        header_key = active_def.get('display_name', col_key)
        if col_def.get('is_generated_percentile', False):
            row3.append('')
            row3_clean.append('')
        elif description:
            spacer = ' ' * HEADER_ROWS['columns'].get('description_spacer_count', 100)
            row3.append(f"{description}{spacer}{header_key}{spacer}{description}")
            row3_clean.append(header_key)
        else:
            row3.append(header_key)
            row3_clean.append(header_key)

    # Close final merges
    n = len(columns_list)
    if cur_section:
        display = _get_display(cur_section)
        merges.append({'row': ROW_INDEXES['section_header_row'], 'start_col': sec_start, 'end_col': n, 'value': display})
    if cur_subsection:
        sub_display = _subsection_display_name(cur_subsection)
        merges.append({'row': ROW_INDEXES['subsection_header_row'], 'start_col': sub_start, 'end_col': n, 'value': sub_display})

    # ---- Merge column header (row 2) across stat + companion pairs ----
    col_header_row = ROW_INDEXES['column_header_row']
    filter_row_idx = ROW_INDEXES['filter_row']
    for idx, entry in enumerate(columns_list):
        col_def = entry[1]
        if col_def.get('is_generated_percentile', False) and idx > 0:
            # Merge column header: stat name spans stat + companion
            merges.append({
                'row': col_header_row,
                'start_col': idx - 1,
                'end_col': idx + 1,
                'value': row3[idx - 1],  # stat's display name
            })
            # Merge filter row too (keeps auto-filter dropdown only on stat col)
            merges.append({
                'row': filter_row_idx,
                'start_col': idx - 1,
                'end_col': idx + 1,
                'value': '',
            })

    return {
        'row1': row1, 'row2': row2, 'row3': row3, 'row3_clean': row3_clean,
        'merges': merges
    }
