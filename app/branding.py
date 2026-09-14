"""Terminal branding: pixelated ALMOND wordmark shown on launch.

The real Almond Financial site uses a plain sans-serif wordmark with no
graphic mark, so this mirrors that restraint rather than inventing a logo:
just the name, rendered as blocky terminal pixels. The colour gradient runs
pale husk (top) into toasted orange (base), an almond in cross-section.
"""

from __future__ import annotations

from rich.console import Console

_FONT: dict[str, list[str]] = {
    "A": [" ### ", "#   #", "#####", "#   #", "#   #"],
    "L": ["#    ", "#    ", "#    ", "#    ", "#####"],
    "M": ["#   #", "## ##", "# # #", "#   #", "#   #"],
    "O": [" ### ", "#   #", "#   #", "#   #", " ### "],
    "N": ["#   #", "##  #", "# # #", "#  ##", "#   #"],
    "D": ["#### ", "#   #", "#   #", "#   #", "#### "],
    " ": ["     ", "     ", "     ", "     ", "     "],
}

_WORD = "ALMOND"
_PIXEL = "██"  # full-block, doubled for a chunkier pixel
_INDENT = "     "

# Row-by-row gradient: pale husk fading into toasted-almond orange.
_ROW_COLORS = ["#FDF8F2", "#FBE7CF", "#FFA94D", "#F2801E", "#C4600E"]

_DIVIDER = "░▒▓" * 23  # dithered pixel-art rule


def _wordmark_rows() -> list[str]:
    rows = []
    for row_index in range(5):
        glyph_row = " ".join(_FONT[letter][row_index] for letter in _WORD)
        rows.append("".join(_PIXEL if cell == "#" else "  " for cell in glyph_row))
    return rows


def render(console: Console | None = None) -> None:
    """Print the pixelated ALMOND wordmark and tagline."""
    console = console or Console()
    for row, color in zip(_wordmark_rows(), _ROW_COLORS, strict=True):
        console.print(f"{_INDENT}[bold {color}]{row}[/]")
    console.print()
    console.print(f"{_INDENT}[italic #C9BEB2]local-first financial assistant[/]")
    console.print(f"{_INDENT}[#F2801E]{_DIVIDER}[/]")
    console.print(f'{_INDENT}[#FDF8F2]type "almond --help" to begin[/]')


if __name__ == "__main__":
    render()
