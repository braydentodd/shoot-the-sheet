"""
The Glass - Google Sheets API Format Builders

Helpers that build Google Sheets API format objects (textFormat, cellFormat,
border descriptions). These are Sheets-specific and convert presentation
configuration into Sheets API request format.
"""

from src.publish.definitions.presentation import COLORS
from src.publish.lib.colors import get_color_for_raw


def create_text_format(font_family=None, font_size=None, bold=False,
                       foreground_color='white') -> dict:
    """Helper to create a Sheets API textFormat dict."""
    fmt = {
        'foregroundColor': get_color_for_raw(COLORS[foreground_color]),
        'bold': bold,
    }
    if font_family:
        fmt['fontFamily'] = font_family
    if font_size:
        fmt['fontSize'] = font_size
    return fmt


def create_cell_format(background_color='white', text_format=None,
                       h_align='CENTER', v_align='MIDDLE', wrap='CLIP') -> dict:
    """Helper to create a Sheets API cellFormat dict."""
    fmt = {
        'backgroundColor': get_color_for_raw(COLORS[background_color]),
        'horizontalAlignment': h_align,
        'verticalAlignment': v_align,
        'wrapStrategy': wrap,
    }
    if text_format:
        fmt['textFormat'] = text_format
    return fmt


def get_border_style(weight: int, color: dict) -> dict:
    """Create a Sheets API border description."""
    if weight == 1:
        return {'style': 'SOLID', 'color': color}
    elif weight == 2:
        return {'style': 'SOLID_MEDIUM', 'color': color}
    elif weight >= 3:
        return {'style': 'SOLID_THICK', 'color': color}
    return {'style': 'NONE'}
