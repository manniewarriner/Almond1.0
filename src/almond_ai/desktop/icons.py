"""Flat, recolorable nut icons for the desktop app.

Each SVG on disk is a monochrome silhouette with a `__FILL__` placeholder
instead of a literal colour -- `nut_icon()` substitutes the requested
accent colour at load time and rasterizes it once per (name, colour,
size), so one small vector asset per bot serves any accent colour at any
requested pixel size instead of needing a raster export per case.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_ASSETS_DIR = Path(__file__).resolve().parent / "assets" / "icons"

# Bot id -> nut identity. Pistachio is defined for parity with the
# terminal's Coding bot but is never shown in the staff desktop UI.
NUT_FOR_BOT = {
    "calculator": "walnut",
    "drafting": "hazelnut",
    "document": "almond",
    "coding": "pistachio",
}


@cache
def _template(nut: str) -> str:
    path = _ASSETS_DIR / f"{nut}.svg"
    return path.read_text(encoding="utf-8")


# Rendered this many times larger than requested, then reported to Qt as a
# high-devicePixelRatio pixmap. Without this, a pixmap built at exactly the
# requested logical size looks fine on a standard 96 DPI screen but blurs on
# any scaled display (125%/150%/200% -- the Windows default on most laptops)
# because Qt has nothing to downsample from when compositing it into the
# actual (higher-resolution) physical framebuffer.
_OVERSAMPLE = 4


def _render_svg(svg: str, size: int) -> QPixmap:
    """Rasterize an SVG string at `_OVERSAMPLE`x, reported to Qt as a
    high-devicePixelRatio pixmap of logical size `size` (see _OVERSAMPLE's
    docstring for why). Shared by every SVG source in this module -- the
    nut icons and the hand-traced brand mark alike -- so there is exactly
    one place that knows how to turn SVG markup into a pixmap.
    """
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    physical = size * _OVERSAMPLE
    pixmap = QPixmap(QSize(physical, physical))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    try:
        renderer.render(painter)
    finally:
        painter.end()
    pixmap.setDevicePixelRatio(_OVERSAMPLE)
    return pixmap


@cache
def _pixmap(nut: str, color: str, size: int) -> QPixmap:
    svg = _template(nut).replace("__FILL__", color)
    return _render_svg(svg, size)


def nut_pixmap(nut: str, color: str, size: int = 32) -> QPixmap:
    """Rasterize `nut` (walnut/hazelnut/almond/pistachio) filled with `color`."""
    return _pixmap(nut, color, size)


def nut_icon(nut: str, color: str, size: int = 32) -> QIcon:
    return QIcon(nut_pixmap(nut, color, size))


def bot_icon(bot_id: str, color: str, size: int = 32) -> QIcon | None:
    """Icon for a specialist bot id, or None for bots with no nut identity (General Chat)."""
    nut = NUT_FOR_BOT.get(bot_id)
    return nut_icon(nut, color, size) if nut else None


# Almond Financial brand mark (three overlapping leaf strokes), traced from
# the official almondfinancial.co.uk mask-icon. Kept here (rather than loaded
# from a file) so the welcome-screen hero can rasterize it at any size/colour
# without shipping another asset. The inner group reproduces that source
# file's own translate/scale unchanged so its raw path data is pasted
# verbatim, avoiding hand-transformed coordinates.
_MARK_BODY_PATHS = (
    "M788 1494 c-60 -31 -156 -217 -199 -381 -23 -91 -35 -249 -24 -319 l7 -49 17 70 "
    "c47 192 131 344 269 487 l75 77 -18 28 c-22 35 -65 82 -85 93 -9 5 -26 2 -42 -6z",
    "M955 1107 c-164 -113 -314 -318 -330 -452 -27 -213 222 -331 362 -171 88 99 117 363 "
    "65 585 -9 41 -22 76 -27 77 -6 2 -37 -16 -70 -39z",
)

# The thin cross-strokes over the leaf body -- rendered in a second colour
# (white, by default) so they read as distinct highlight lines rather than
# blending into the solid body fill.
_MARK_LINE_PATHS = (
    "M1092 1430 c-24 -11 -56 -29 -72 -40 l-29 -20 32 -75 c17 -42 34 -74 37 -73 "
    "3 2 38 17 78 33 l74 30 -6 43 c-8 59 -42 122 -66 122 -3 0 -24 -9 -48 -20z",
    "M880 1264 c-91 -95 -162 -207 -207 -323 -37 -99 -42 -131 -12 -81 62 102 213 252 "
    "312 310 20 12 37 29 37 38 -1 10 -13 43 -28 76 l-27 58 -75 -78z",
    "M1285 1263 c-19 -3 -20 -12 -21 -131 -2 -184 -39 -339 -121 -501 -23 -47 -41 -86 "
    "-39 -88 5 -6 105 106 151 169 121 163 225 463 186 537 -10 18 -20 21 -74 20 "
    "-34 -1 -71 -4 -82 -6z",
    "M1146 1215 c-32 -13 -63 -28 -68 -33 -5 -5 -2 -33 6 -67 28 -103 39 -226 33 -345 "
    "-6 -110 -6 -114 9 -80 54 119 91 276 94 390 3 111 0 160 -7 160 -5 0 -35 -11 -67 -25z",
)

# Kept for anything still importing the flat, single-colour path list.
_MARK_PATHS = _MARK_BODY_PATHS + _MARK_LINE_PATHS


@cache
def _brand_mark_pixmap(color: str, size: int, line_color: str | None = None) -> QPixmap:
    body = "".join(f'<path d="{d}"/>' for d in _MARK_BODY_PATHS)
    lines = "".join(f'<path d="{d}"/>' for d in _MARK_LINE_PATHS)
    line_fill = line_color or color
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">'
        '<g transform="translate(16,10) scale(1.14)">'
        '<g transform="translate(0,192) scale(0.1,-0.1)">'
        f'<g fill="{color}">{body}</g>'
        f'<g fill="{line_fill}">{lines}</g>'
        "</g></g></svg>"
    )
    return _render_svg(svg, size)


def brand_mark_pixmap(color: str, size: int = 96, line_color: str | None = None) -> QPixmap:
    """The Almond Financial mark alone (no background), for the welcome hero.

    `line_color` recolours the thin cross-strokes separately from the solid
    leaf body (`color`) -- pass white to make them stand out, or omit it to
    keep the mark a single flat colour.
    """
    return _brand_mark_pixmap(color, size, line_color)


# Simple flat cog/gear glyph, drawn as a single filled path so it can be
# recoloured and resized the same way as the nut icons above.
_GEAR_PATH = (
    "M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 0 0 2.573 1.066c"
    "1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 0 0 1.065 2.572c1.756.426 1.756 "
    "2.924 0 3.35a1.724 1.724 0 0 0-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 "
    "1.724 0 0 0-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 0 0-2.573"
    "-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 0 0-1.065-2.572c-1.756"
    "-.426-1.756-2.924 0-3.35a1.724 1.724 0 0 0 1.066-2.573c-.94-1.543.826-3.31 "
    "2.37-2.37c1 .608 2.296.07 2.572-1.065ZM12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z"
)


@cache
def _gear_pixmap(color: str, size: int) -> QPixmap:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        f'<path fill-rule="evenodd" clip-rule="evenodd" fill="{color}" d="{_GEAR_PATH}"/>'
        "</svg>"
    )
    return _render_svg(svg, size)


def gear_pixmap(color: str, size: int = 20) -> QPixmap:
    """Flat cog/gear glyph, e.g. for the sidebar's Settings row."""
    return _gear_pixmap(color, size)
