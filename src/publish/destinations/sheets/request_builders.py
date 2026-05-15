from dataclasses import dataclass
from typing import List, Tuple, Union

from src.publish.definitions.layout import SECTIONS_CONFIG
from src.publish.definitions.presentation import COLORS, PRESENTATION_DEFAULTS, WIDTH_CLASSES
from src.publish.lib.row_structure import HEADER_ROWS, ROW_INDEXES
from src.publish.destinations.sheets.config import SHEETS_FORMATTING
from src.publish.destinations.sheets.format_builders import get_border_style
from src.publish.lib.colors import get_color_for_percentile, get_color_for_raw


@dataclass
class SheetContext:
    """Context for building Sheets formatting requests."""
    ws_id: int
    fmt: dict
    n_cols: int
    data_start: int
    total_rows: int
    n_data_rows: int
    n_player_rows: int
    columns_list: List[Tuple]
    tab_type: str
    frozen_columns: int
    column_border_weight: int
    column_header_color: dict
    column_data_color: dict
    data_separator_bg: dict
    wrap_strategy: str

def build_formatting_requests(ws_id: int, columns_list: List[Tuple],
                              header_merges: list, n_data_rows: int,
                              team_name: str,
                              percentile_cells: Union[List[dict], None] = None,
                              n_player_rows: int = 0, link_cells: Union[List[dict], None] = None,
                              tab_type: str = 'team',
                              show_advanced: bool = False,
                              data_only: bool = False) -> list:
    """
    Build ALL Google Sheets batch_update requests for a worksheet.
    Config-driven from PRESENTATION_DEFAULTS (generic) and SHEETS_FORMATTING
    (Sheets-specific).

    show_advanced overrides config default so that syncs respect the
    user's current toggle state.

    Args:
        ws_id: Worksheet ID
        columns_list: The column structure from build_columns
        header_merges: Merge info from build_headers
        n_data_rows: Number of data rows (players + team/opp)
        team_name: Full team name for display
        percentile_cells: List of {row, col, percentile, reverse} for shading
        n_player_rows: Number of player rows (for filter range; team/opp excluded)
        tab_type: 'individual_team', 'all_players', or 'all_teams'
        show_advanced: If True, keep advanced columns visible (override config)

    Returns:
        List of request dicts for spreadsheet.batch_update
    """
    fmt = {**PRESENTATION_DEFAULTS, **SHEETS_FORMATTING}
    n_cols = len(columns_list)
    data_start = ROW_INDEXES['data_start_row']
    
    # Create offset copies to avoid mutating caller's data
    percentile_cells_offset = None
    if percentile_cells:
        percentile_cells_offset = [{**cell, 'row': cell['row'] + data_start} for cell in percentile_cells]
    
    link_cells_offset = None
    if link_cells:
        link_cells_offset = [{**cell, 'row': cell['row'] + data_start} for cell in link_cells]

    total_rows = data_start + n_data_rows
    frozen_columns = fmt.get('frozen_columns', 0)
    column_border_weight = fmt.get('column_border_weight', 1)
    column_header_color = get_color_for_raw(COLORS[fmt.get('column_border_color_header', 'white')])
    column_data_color = get_color_for_raw(COLORS[fmt.get('column_border_color_data', 'black')])
    data_separator_bg = get_color_for_raw(COLORS[fmt.get('data_separator_bg', 'black')])
    wrap_strategy = fmt.get('wrap_strategy', 'CLIP')

    # --- Fast path for partial update (mode / timeframe changes) ---------
    # Skip all structural formatting, resize, and widths; only reapply data-dependent pieces.
    if data_only:
        return build_partial_update_requests(
            ws_id, percentile_cells_offset, link_cells_offset, columns_list,
            data_start, n_player_rows, n_data_rows, tab_type
        )

    # Build context for sub-builders
    ctx = SheetContext(
        ws_id=ws_id,
        fmt=fmt,
        n_cols=n_cols,
        data_start=data_start,
        total_rows=total_rows,
        n_data_rows=n_data_rows,
        n_player_rows=n_player_rows,
        columns_list=columns_list,
        tab_type=tab_type,
        frozen_columns=frozen_columns,
        column_border_weight=column_border_weight,
        column_header_color=column_header_color,
        column_data_color=column_data_color,
        data_separator_bg=data_separator_bg,
        wrap_strategy=wrap_strategy,
    )

    requests = []

    # ---- 1. Grid properties: frozen rows/cols, hide gridlines ----
    requests.append(_build_grid_properties(ctx))

    # ---- 1b. Explicit default row heights (do this before specific divider heights) ----
    requests.extend(_build_row_heights(ctx))

    # ---- 2-5. Header row formatting (section, subsection, column, filter) ----
    requests.extend(_build_header_formatting(ctx))

    # ---- 6-8. Data row formatting (default styling, banding, per-column) ----
    requests.extend(_build_data_row_formatting(ctx))

    # ---- 9-11. Header merges, separators, and borders ----
    requests.extend(_build_separators_and_borders(ctx, header_merges))

    # ---- 14-23. Footer dividers, column widths, visibility, filters, and final touches ----
    requests.extend(_build_footer_divider(ctx))
    requests.extend(_build_column_widths(ctx))
    requests.extend(_build_column_visibility(ctx))
    requests.extend(_build_filter(ctx))
    requests.extend(_build_data_overlays(ctx, percentile_cells_offset, link_cells_offset))
    requests.extend(_build_sheet_resize(ctx))

    return requests


def _range(ws_id: int, start_row: int, end_row: int,
           start_col: int, end_col: int) -> dict:
    """Build a GridRange dict."""
    return {
        'sheetId': ws_id,
        'startRowIndex': start_row,
        'endRowIndex': end_row,
        'startColumnIndex': start_col,
        'endColumnIndex': end_col,
    }


def _build_null_formula_bg_requests(ws_id: int, columns_list: List[Tuple],
                                     data_start: int, n_player_rows: int,
                                     n_data_rows: int) -> list:
    """
    Build requests to set black background on cells where the row's
    formula is None:
      - player rows where values.player is None (team-only columns)
      - team row where values.team is None
      - opponent row where values.opponents is None
    Config-driven: reads formula presence from column definitions.
    """
    black = get_color_for_raw(COLORS['black'])
    requests = []
    # +1 offset accounts for the separator row between players and team/opp
    team_row = data_start + n_player_rows + 1
    opp_row = data_start + n_player_rows + 2

    for idx, entry in enumerate(columns_list):
        col_def = entry[1]
        values = col_def.get('values', {})

        # Black bg on player rows for team-only columns
        if values.get('player') is None and n_player_rows > 0:
            requests.append({
                'repeatCell': {
                    'range': _range(ws_id, data_start, data_start + n_player_rows, idx, idx + 1),
                    'cell': {
                        'userEnteredFormat': {
                            'backgroundColor': black,
                        },
                    },
                    'fields': 'userEnteredFormat.backgroundColor',
                }
            })

        # Team row: black bg if values.team is None
        if values.get('team') is None:
            requests.append({
                'repeatCell': {
                    'range': _range(ws_id, team_row, team_row + 1, idx, idx + 1),
                    'cell': {
                        'userEnteredFormat': {
                            'backgroundColor': black,
                        },
                    },
                    'fields': 'userEnteredFormat.backgroundColor',
                }
            })
        # Opponents row: black bg if values.opponents is None
        if values.get('opponents') is None:
            if opp_row < data_start + n_data_rows:
                requests.append({
                    'repeatCell': {
                        'range': _range(ws_id, opp_row, opp_row + 1, idx, idx + 1),
                        'cell': {
                            'userEnteredFormat': {
                                'backgroundColor': black,
                            },
                        },
                        'fields': 'userEnteredFormat.backgroundColor',
                    }
                })
    return requests


def _build_percentile_shading_requests(ws_id: int,
                                        percentile_cells: List[dict]) -> list:
    """Build cell background color requests for percentile shading.

    NOTE: percentile rank already accounts for reverse_percentile direction
    (get_percentile_rank inverts so high rank = good always).
    Do NOT pass reverse to get_color_for_percentile — that would double-invert.
    """
    requests = []
    for cell in percentile_cells:
        color = get_color_for_percentile(cell['percentile'])
        requests.append({
            'repeatCell': {
                'range': _range(ws_id, cell['row'], cell['row'] + 1,
                                cell['col'], cell['col'] + 1),
                'cell': {
                    'userEnteredFormat': {
                        'backgroundColor': get_color_for_raw(color),
                    },
                },
                'fields': 'userEnteredFormat.backgroundColor',
            }
        })
    return requests


def _build_link_requests(ws_id: int, link_cells: list) -> list:
    """Build cell formula requests for hyperlinks."""
    requests = []
    for cell in link_cells:
        requests.append({
            'updateCells': {
                'range': _range(ws_id, cell['row'], cell['row'] + 1,
                                cell['col'], cell['col'] + 1),
                'rows': [{
                    'values': [{
                        'userEnteredValue': {
                            'formulaValue': f'=HYPERLINK("{cell["uri"]}", "{cell["text"]}")'
                        }
                    }]
                }],
                'fields': 'userEnteredValue',
            }
        })
    return requests


def build_partial_update_requests(ws_id: int, percentile_cells: Union[List[dict], None],
                                   link_cells: Union[List[dict], None], columns_list: List[Tuple],
                                   data_start: int, n_player_rows: int, n_data_rows: int,
                                   tab_type: str) -> list:
    """Build partial update requests for fast sync (mode/timeframe changes only).
    
    Skips structural formatting, resize, and widths; only reapplies data-dependent pieces.
    """
    fast = []
    # Percentile shading
    if percentile_cells:
        fast.extend(_build_percentile_shading_requests(ws_id, percentile_cells))
    # Hyperlinks
    if link_cells:
        fast.extend(_build_link_requests(ws_id, link_cells))
    # Null-formula backgrounds for team/opp rows
    if tab_type == 'individual_team' and n_data_rows > n_player_rows:
        fast.extend(_build_null_formula_bg_requests(
            ws_id, columns_list, data_start, n_player_rows, n_data_rows
        ))
    return fast


def _build_grid_properties(ctx: SheetContext) -> dict:
    """Build grid properties request (frozen rows/cols, hide gridlines)."""
    return {
        'updateSheetProperties': {
            'properties': {
                'sheetId': ctx.ws_id,
                'gridProperties': {
                    'frozenRowCount': ctx.fmt['frozen_rows'],
                    'frozenColumnCount': ctx.frozen_columns,
                    'hideGridlines': True,
                },
            },
            'fields': 'gridProperties(frozenRowCount,frozenColumnCount,hideGridlines)',
        }
    }


def _build_row_heights(ctx: SheetContext) -> list:
    """Build row height requests for all row types."""
    requests = []
    # Default row height
    requests.append({
        'updateDimensionProperties': {
            'range': {'sheetId': ctx.ws_id, 'dimension': 'ROWS', 'startIndex': 0, 'endIndex': ctx.total_rows},
            'properties': {'pixelSize': HEADER_ROWS['columns']['row_height']},
            'fields': 'pixelSize',
        }
    })
    # Section header row
    requests.append({
        'updateDimensionProperties': {
            'range': {'sheetId': ctx.ws_id, 'dimension': 'ROWS', 'startIndex': ROW_INDEXES['section_header_row'], 'endIndex': ROW_INDEXES['section_header_row'] + 1},
            'properties': {'pixelSize': HEADER_ROWS['sections']['row_height']},
            'fields': 'pixelSize',
        }
    })
    # Section divider row
    if 'section_divider_row' in ROW_INDEXES:
        requests.append({
            'updateDimensionProperties': {
                'range': {'sheetId': ctx.ws_id, 'dimension': 'ROWS', 'startIndex': ROW_INDEXES['section_divider_row'], 'endIndex': ROW_INDEXES['section_divider_row'] + 1},
                'properties': {'pixelSize': HEADER_ROWS['sections']['divider_row_weight']},
                'fields': 'pixelSize',
            }
        })
    # Subsection header row
    requests.append({
        'updateDimensionProperties': {
            'range': {'sheetId': ctx.ws_id, 'dimension': 'ROWS', 'startIndex': ROW_INDEXES['subsection_header_row'], 'endIndex': ROW_INDEXES['subsection_header_row'] + 1},
            'properties': {'pixelSize': HEADER_ROWS['subsections']['row_height']},
            'fields': 'pixelSize',
        }
    })
    # Subsection divider row
    if 'subsection_divider_row' in ROW_INDEXES:
        requests.append({
            'updateDimensionProperties': {
                'range': {'sheetId': ctx.ws_id, 'dimension': 'ROWS', 'startIndex': ROW_INDEXES['subsection_divider_row'], 'endIndex': ROW_INDEXES['subsection_divider_row'] + 1},
                'properties': {'pixelSize': HEADER_ROWS['subsections']['divider_row_weight']},
                'fields': 'pixelSize',
            }
        })
    # Filter row
    requests.append({
        'updateDimensionProperties': {
            'range': {'sheetId': ctx.ws_id, 'dimension': 'ROWS', 'startIndex': ROW_INDEXES['filter_row'], 'endIndex': ROW_INDEXES['filter_row'] + 1},
            'properties': {'pixelSize': HEADER_ROWS['filters']['row_height']},
            'fields': 'pixelSize',
        }
    })
    return requests


def _build_header_formatting(ctx: SheetContext) -> list:
    """Build header row formatting requests (section, subsection, column, filter rows)."""
    requests = []
    header_bg = get_color_for_raw(COLORS[ctx.fmt['header_bg']])
    header_fg = get_color_for_raw(COLORS[ctx.fmt['header_fg']])

    # Section header row
    requests.append({
        'repeatCell': {
            'range': _range(ctx.ws_id, ROW_INDEXES['section_header_row'], ROW_INDEXES['section_header_row'] + 1, 0, ctx.n_cols),
            'cell': {
                'userEnteredFormat': {
                    'backgroundColor': header_bg,
                    'textFormat': {
                        'fontFamily': ctx.fmt['header_font'],
                        'fontSize': HEADER_ROWS['sections']['font_size'],
                        'bold': True,
                        'foregroundColor': header_fg,
                    },
                    'horizontalAlignment': 'CENTER',
                    'verticalAlignment': 'MIDDLE',
                    'wrapStrategy': ctx.wrap_strategy,
                },
            },
            'fields': 'userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment,wrapStrategy)',
        }
    })

    # Team name in entities section — centered, larger font
    entities_end = 0
    for idx, entry in enumerate(ctx.columns_list):
        ctx_val = entry[3] if len(entry) > 3 else None
        if ctx_val != 'entities':
            entities_end = idx
            break
    else:
        entities_end = ctx.n_cols
    if entities_end > 0:
        requests.append({
            'repeatCell': {
                'range': _range(ctx.ws_id, ROW_INDEXES['section_header_row'], ROW_INDEXES['section_header_row'] + 1, 0, entities_end),
                'cell': {
                    'userEnteredFormat': {
                        'textFormat': {
                            'fontFamily': ctx.fmt['header_font'],
                            'fontSize': HEADER_ROWS['sections']['column_a_font_size'],
                            'bold': True,
                            'foregroundColor': header_fg,
                        },
                        'horizontalAlignment': 'CENTER',
                    },
                },
                'fields': 'userEnteredFormat(textFormat,horizontalAlignment)',
            }
        })

    # Subsection header row
    requests.append({
        'repeatCell': {
            'range': _range(ctx.ws_id, ROW_INDEXES['subsection_header_row'], ROW_INDEXES['subsection_header_row'] + 1, 0, ctx.n_cols),
            'cell': {
                'userEnteredFormat': {
                    'backgroundColor': header_bg,
                    'textFormat': {
                        'fontFamily': ctx.fmt['header_font'],
                        'fontSize': HEADER_ROWS['subsections']['font_size'],
                        'bold': True,
                        'foregroundColor': header_fg,
                    },
                    'horizontalAlignment': 'CENTER',
                    'verticalAlignment': 'MIDDLE',
                    'wrapStrategy': ctx.wrap_strategy,
                },
            },
            'fields': 'userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment,wrapStrategy)',
        }
    })

    # Column header row
    requests.append({
        'repeatCell': {
            'range': _range(ctx.ws_id, ROW_INDEXES['column_header_row'], ROW_INDEXES['column_header_row'] + 1, 0, ctx.n_cols),
            'cell': {
                'userEnteredFormat': {
                    'backgroundColor': header_bg,
                    'textFormat': {
                        'fontFamily': ctx.fmt['header_font'],
                        'fontSize': HEADER_ROWS['columns']['font_size'],
                        'bold': True,
                        'foregroundColor': header_fg,
                    },
                    'horizontalAlignment': 'CENTER',
                    'verticalAlignment': 'MIDDLE',
                    'wrapStrategy': ctx.wrap_strategy,
                },
            },
            'fields': 'userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment,wrapStrategy)',
        }
    })

    # Filter row
    requests.append({
        'repeatCell': {
            'range': _range(ctx.ws_id, ROW_INDEXES['filter_row'], ROW_INDEXES['filter_row'] + 1, 0, ctx.n_cols),
            'cell': {
                'userEnteredFormat': {
                    'backgroundColor': header_bg,
                    'textFormat': {
                        'fontFamily': ctx.fmt['header_font'],
                        'fontSize': HEADER_ROWS['filters']['font_size'],
                        'foregroundColor': header_fg,
                    },
                    'horizontalAlignment': 'CENTER',
                    'verticalAlignment': 'MIDDLE',
                    'wrapStrategy': ctx.wrap_strategy,
                },
            },
            'fields': 'userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment,wrapStrategy)',
        }
    })

    return requests


def _build_data_row_formatting(ctx: SheetContext) -> list:
    """Build data row formatting requests (default styling, banding, per-column alignment)."""
    requests = []
    
    # Default styling
    if ctx.n_data_rows > 0:
        requests.append({
            'repeatCell': {
                'range': _range(ctx.ws_id, ctx.data_start, ctx.total_rows, 0, ctx.n_cols),
                'cell': {
                    'userEnteredFormat': {
                        'textFormat': {
                            'fontFamily': ctx.fmt['data_font'],
                            'fontSize': HEADER_ROWS['columns']['font_size'],
                        },
                        'horizontalAlignment': ctx.fmt['horizontal_align'],
                        'verticalAlignment': ctx.fmt['vertical_align'],
                        'wrapStrategy': ctx.wrap_strategy,
                    },
                },
                'fields': 'userEnteredFormat(textFormat,horizontalAlignment,verticalAlignment,wrapStrategy)',
            }
        })

    # Clear stale borders
    if ctx.n_data_rows > 0:
        requests.append({
            'updateBorders': {
                'range': _range(ctx.ws_id, ctx.data_start, ctx.total_rows, 0, ctx.n_cols),
                'top': {'style': 'NONE'},
                'bottom': {'style': 'NONE'},
                'left': {'style': 'NONE'},
                'right': {'style': 'NONE'},
                'innerHorizontal': {'style': 'NONE'},
                'innerVertical': {'style': 'NONE'},
            }
        })

    # Header divider rows
    divider_bg = get_color_for_raw(COLORS[ctx.fmt.get('header_divider_bg', 'white')])
    divider_height = ctx.fmt.get('header_divider_height', 2)
    for row_key in ('section_divider_row', 'subsection_divider_row'):
        row_idx = ROW_INDEXES.get(row_key)
        if row_idx is None:
            continue
        requests.append({
            'repeatCell': {
                'range': _range(ctx.ws_id, row_idx, row_idx + 1, 0, ctx.n_cols),
                'cell': {
                    'userEnteredFormat': {
                        'backgroundColor': divider_bg,
                        'textFormat': {'fontSize': 2},
                    },
                },
                'fields': 'userEnteredFormat(backgroundColor,textFormat)',
            }
        })
        requests.append({
            'updateDimensionProperties': {
                'range': {
                    'sheetId': ctx.ws_id,
                    'dimension': 'ROWS',
                    'startIndex': row_idx,
                    'endIndex': row_idx + 1,
                },
                'properties': {'pixelSize': divider_height},
                'fields': 'pixelSize',
            }
        })

    # Alternating row colors
    if ctx.n_data_rows > 0:
        requests.append({
            'addBanding': {
                'bandedRange': {
                    'range': _range(ctx.ws_id, ctx.data_start, ctx.data_start + ctx.n_data_rows, 0, ctx.n_cols),
                    'rowProperties': {
                        'firstBandColor': get_color_for_raw(COLORS[ctx.fmt['data_row_even_bg']]),
                        'secondBandColor': get_color_for_raw(COLORS[ctx.fmt['data_row_odd_bg']]),
                    },
                },
            }
        })

    # Per-column alignment and emphasis
    if ctx.n_data_rows > 0:
        for idx, entry in enumerate(ctx.columns_list):
            col_def = entry[1]
            col_align = col_def.get('align', 'center').upper()
            col_emphasis = col_def.get('emphasis')
            col_font_size = col_def.get('font_size')

            if col_align != ctx.fmt['horizontal_align']:
                requests.append({
                    'repeatCell': {
                        'range': _range(ctx.ws_id, ctx.data_start, ctx.total_rows, idx, idx + 1),
                        'cell': {
                            'userEnteredFormat': {'horizontalAlignment': col_align},
                        },
                        'fields': 'userEnteredFormat.horizontalAlignment',
                    }
                })

            if col_emphasis == 'bold' or col_font_size is not None:
                text_format = {}
                fields = []
                if col_emphasis == 'bold':
                    text_format['bold'] = True
                    fields.append('userEnteredFormat.textFormat.bold')
                if col_font_size is not None:
                    text_format['fontSize'] = col_font_size
                    fields.append('userEnteredFormat.textFormat.fontSize')

                requests.append({
                    'repeatCell': {
                        'range': _range(ctx.ws_id, ctx.data_start, ctx.total_rows, idx, idx + 1),
                        'cell': {
                            'userEnteredFormat': {
                                'textFormat': text_format,
                            },
                        },
                        'fields': ','.join(fields),
                    }
                })

    return requests


def _build_separators_and_borders(ctx: SheetContext, header_merges: list) -> list:
    """Build header merge, separator column, and border requests."""
    requests = []
    header_separator_bg = get_color_for_raw(COLORS[ctx.fmt.get('header_separator_bg', 'white')])
    data_separator_bg = get_color_for_raw(COLORS[ctx.fmt.get('data_separator_bg', 'black')])

    # Header merge cells
    for merge in header_merges:
        row = merge['row']
        s, e = merge['start_col'], merge['end_col']
        if e - s <= 1:
            continue
        if s < ctx.frozen_columns < e:
            if ctx.frozen_columns - s > 1:
                requests.append({
                    'mergeCells': {
                        'range': _range(ctx.ws_id, row, row + 1, s, ctx.frozen_columns),
                        'mergeType': 'MERGE_ALL',
                    }
                })
            if e - ctx.frozen_columns > 1:
                requests.append({
                    'mergeCells': {
                        'range': _range(ctx.ws_id, row, row + 1, ctx.frozen_columns, e),
                        'mergeType': 'MERGE_ALL',
                    }
                })
        else:
            requests.append({
                'mergeCells': {
                    'range': _range(ctx.ws_id, row, row + 1, s, e),
                    'mergeType': 'MERGE_ALL',
                }
            })

    # Separator columns
    for idx, entry in enumerate(ctx.columns_list):
        col_def = entry[1]
        if not col_def.get('is_separator'):
            continue
        separator_type = col_def.get('separator_type', 'section')
        separator_width = ctx.fmt.get('subsection_separator_width', 2) if separator_type == 'subsection' else ctx.fmt.get('section_separator_width', 4)
        
        requests.append({
            'updateDimensionProperties': {
                'range': {'sheetId': ctx.ws_id, 'dimension': 'COLUMNS', 'startIndex': idx, 'endIndex': idx + 1},
                'properties': {'pixelSize': separator_width},
                'fields': 'pixelSize',
            }
        })
        requests.append({
            'repeatCell': {
                'range': _range(ctx.ws_id, 0, ctx.data_start, idx, idx + 1),
                'cell': {'userEnteredFormat': {'backgroundColor': header_separator_bg}},
                'fields': 'userEnteredFormat.backgroundColor',
            }
        })
        if ctx.n_data_rows > 0:
            requests.append({
                'repeatCell': {
                    'range': _range(ctx.ws_id, ctx.data_start, ctx.total_rows, idx, idx + 1),
                    'cell': {'userEnteredFormat': {'backgroundColor': data_separator_bg}},
                    'fields': 'userEnteredFormat.backgroundColor',
                }
            })

    # Column borders
    header_border_end = ROW_INDEXES['filter_row'] + 1
    for col_idx in range(1, ctx.n_cols):
        left_def = ctx.columns_list[col_idx - 1][1]
        right_def = ctx.columns_list[col_idx][1]
        if col_idx == ctx.frozen_columns or right_def.get('is_generated_percentile'):
            continue
        if left_def.get('is_separator') or right_def.get('is_separator'):
            continue

        requests.append({
            'updateBorders': {
                'range': _range(ctx.ws_id, 0, header_border_end, col_idx, col_idx + 1),
                'left': get_border_style(ctx.column_border_weight, ctx.column_header_color),
            }
        })
        if ctx.n_data_rows > 0:
            requests.append({
                'updateBorders': {
                    'range': _range(ctx.ws_id, ctx.data_start, ctx.total_rows, col_idx, col_idx + 1),
                    'left': get_border_style(ctx.column_border_weight, ctx.column_data_color),
                }
            })

    # Clear borders on divider rows
    for row_key in ('section_divider_row', 'subsection_divider_row'):
        row_idx = ROW_INDEXES.get(row_key)
        if row_idx is None:
            continue
        requests.append({
            'updateBorders': {
                'range': _range(ctx.ws_id, row_idx, row_idx + 1, 0, ctx.n_cols),
                'top': {'style': 'NONE'},
                'bottom': {'style': 'NONE'},
                'left': {'style': 'NONE'},
                'right': {'style': 'NONE'},
                'innerHorizontal': {'style': 'NONE'},
                'innerVertical': {'style': 'NONE'},
            }
        })

    return requests


def _build_footer_divider(ctx: SheetContext) -> list:
    """Build footer divider row requests."""
    requests = []
    if ctx.n_player_rows > 0 and ctx.n_data_rows > ctx.n_player_rows:
        sep_row = ctx.data_start + ctx.n_player_rows
        divider_bg = ctx.data_separator_bg if ctx.tab_type == 'individual_team' else get_color_for_raw(COLORS[ctx.fmt.get('footer_divider_bg', 'black')])
        divider_height = ctx.fmt.get('footer_divider_height', 4)
        requests.append({
            'repeatCell': {
                'range': _range(ctx.ws_id, sep_row, sep_row + 1, 0, ctx.n_cols),
                'cell': {'userEnteredFormat': {'backgroundColor': divider_bg, 'textFormat': {'fontSize': 2}}},
                'fields': 'userEnteredFormat(backgroundColor,textFormat)',
            }
        })
        requests.append({
            'updateDimensionProperties': {
                'range': {'sheetId': ctx.ws_id, 'dimension': 'ROWS', 'startIndex': sep_row, 'endIndex': sep_row + 1},
                'properties': {'pixelSize': divider_height}, 'fields': 'pixelSize',
            }
        })
        requests.append({
            'updateBorders': {
                'range': _range(ctx.ws_id, sep_row, sep_row + 1, 0, ctx.n_cols),
                'top': {'style': 'NONE'}, 'bottom': {'style': 'NONE'},
                'left': {'style': 'NONE'}, 'right': {'style': 'NONE'},
                'innerHorizontal': {'style': 'NONE'}, 'innerVertical': {'style': 'NONE'},
            }
        })
    return requests


def _build_column_widths(ctx: SheetContext) -> list:
    """Build column width requests."""
    requests = []
    pct_font_size = ctx.fmt.get('percentile_companion_font_size', 5)
    pct_width = ctx.fmt.get('percentile_companion_width', 10)

    for idx, entry in enumerate(ctx.columns_list):
        col_def = entry[1]
        if col_def.get('is_separator'):
            continue
        is_pct_companion = col_def.get('is_generated_percentile', False)
        wc = col_def.get('width_class')

        if is_pct_companion:
            requests.append({
                'updateDimensionProperties': {
                    'range': {'sheetId': ctx.ws_id, 'dimension': 'COLUMNS', 'startIndex': idx, 'endIndex': idx + 1},
                    'properties': {'pixelSize': pct_width}, 'fields': 'pixelSize',
                }
            })
            if ctx.n_data_rows > 0:
                requests.append({
                    'repeatCell': {
                        'range': _range(ctx.ws_id, ctx.data_start, ctx.total_rows, idx, idx + 1),
                        'cell': {'userEnteredFormat': {'textFormat': {'fontSize': pct_font_size}, 'verticalAlignment': 'MIDDLE', 'wrapStrategy': 'CLIP'}},
                        'fields': 'userEnteredFormat(textFormat.fontSize,verticalAlignment,wrapStrategy)',
                    }
                })
            continue

        pixel_width = int(wc) if isinstance(wc, (int, float)) else (WIDTH_CLASSES.get(wc) if isinstance(wc, str) else None)
        if pixel_width is None:
            requests.append({'autoResizeDimensions': {'dimensions': {'sheetId': ctx.ws_id, 'dimension': 'COLUMNS', 'startIndex': idx, 'endIndex': idx + 1}}})
        else:
            requests.append({
                'updateDimensionProperties': {
                    'range': {'sheetId': ctx.ws_id, 'dimension': 'COLUMNS', 'startIndex': idx, 'endIndex': idx + 1},
                    'properties': {'pixelSize': pixel_width}, 'fields': 'pixelSize',
                }
            })
    return requests


def _build_column_visibility(ctx: SheetContext) -> list:
    """Build column visibility requests (merged loops for visibility flags and section visibility)."""
    requests = []
    for idx, entry in enumerate(ctx.columns_list):
        col_vis = entry[2]
        col_ctx = entry[3] if len(entry) > 3 else None
        base_sec = getattr(col_ctx, 'base_section', str(col_ctx)) if col_ctx else str(col_ctx)
        sec_cfg = SECTIONS_CONFIG.get(base_sec, {})
        
        should_hide = not col_vis or not sec_cfg.get('visible_by_default', True)
        if should_hide:
            requests.append({
                'updateDimensionProperties': {
                    'range': {'sheetId': ctx.ws_id, 'dimension': 'COLUMNS', 'startIndex': idx, 'endIndex': idx + 1},
                    'properties': {'hiddenByUser': True}, 'fields': 'hiddenByUser',
                }
            })
    return requests


def _build_filter(ctx: SheetContext) -> list:
    """Build auto-filter request."""
    filter_end = ctx.data_start + ctx.n_player_rows if ctx.n_player_rows > 0 else ctx.total_rows
    return [{'setBasicFilter': {'filter': {'range': _range(ctx.ws_id, ROW_INDEXES['filter_row'], filter_end, 0, ctx.n_cols)}}}]


def _build_data_overlays(ctx: SheetContext, percentile_cells: Union[List[dict], None], link_cells: Union[List[dict], None]) -> list:
    """Build data overlay requests (percentile shading, hyperlinks, null formula backgrounds, bottom border)."""
    requests = []
    
    if percentile_cells:
        requests.extend(_build_percentile_shading_requests(ctx.ws_id, percentile_cells))
    
    if link_cells:
        requests.extend(_build_link_requests(ctx.ws_id, link_cells))
    
    if ctx.n_data_rows > 0:
        requests.append({
            'updateBorders': {
                'range': _range(ctx.ws_id, ctx.total_rows - 1, ctx.total_rows, 0, ctx.n_cols),
                'bottom': get_border_style(2, get_color_for_raw(COLORS['black']))
            }
        })
    
    if ctx.tab_type == 'individual_team' and ctx.n_data_rows > ctx.n_player_rows:
        requests.extend(_build_null_formula_bg_requests(ctx.ws_id, ctx.columns_list, ctx.data_start, ctx.n_player_rows, ctx.n_data_rows))
    
    return requests


def _build_sheet_resize(ctx: SheetContext) -> list:
    """Build sheet resize request."""
    return [{
        'updateSheetProperties': {
            'properties': {'sheetId': ctx.ws_id, 'gridProperties': {'rowCount': ctx.total_rows, 'columnCount': ctx.n_cols}},
            'fields': 'gridProperties(rowCount,columnCount)',
        }
    }]


def _build_percentile_shading_requests(ws_id: int, percentile_cells: list) -> list:
    """Build cell background color requests for percentile shading.

    NOTE: percentile rank already accounts for reverse_percentile direction
    (get_percentile_rank inverts so high rank = good always).
    Do NOT pass reverse to get_color_for_percentile — that would double-invert.
    """
    requests = []
    for cell in percentile_cells:
        color = get_color_for_percentile(cell['percentile'])
        requests.append({
            'repeatCell': {
                'range': _range(ws_id, cell['row'], cell['row'] + 1,
                                cell['col'], cell['col'] + 1),
                'cell': {
                    'userEnteredFormat': {
                        'backgroundColor': get_color_for_raw(color),
                    },
                },
                'fields': 'userEnteredFormat.backgroundColor',
            }
        })
    return requests
