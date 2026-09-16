"""Almond Standard Report visual constants.

Restrained financial-services styling: white page, dark charcoal text,
a single Almond-orange accent, generous whitespace. No gradients, no
decorative graphics.
"""

from __future__ import annotations

from reportlab.lib import colors

COLOR_CHARCOAL = colors.HexColor("#2B2B2B")
COLOR_MUTED = colors.HexColor("#6B7280")
COLOR_ORANGE = colors.HexColor("#F15A24")
COLOR_HEADER_BAND = colors.HexColor("#1F2933")
COLOR_TABLE_HEADER_BG = colors.HexColor("#FBE7CF")
COLOR_TABLE_GRID = colors.HexColor("#D8DCE1")
COLOR_WHITE = colors.white

FONT_REGULAR = "Helvetica"
FONT_BOLD = "Helvetica-Bold"

SIZE_TITLE = 20
SIZE_H1 = 15
SIZE_H2 = 13
SIZE_H3 = 11.5
SIZE_BODY = 10
SIZE_SMALL = 8
