"""One grid, one legend: the single canonical geometry for BOTH perception channels.

The RAM channel (``RAMReader.render_tile_grid``) and the vision channel (the grid a
model returns for ``prompts/exploration/vision_map_blueprint.md``) describe the same
physical thing — the Game Boy's 160x144 px screen, in 16 px cells — so they must use
the same dimensions, the same origin and the same player cell. Otherwise "cell (c, r)"
means two different places in the two channels and every cell-by-cell verdict is
shifted by construction, which is exactly what happened when three copies of the
geometry disagreed (9x9 anchored on the player, 10x9 measured, 9x9 with the player one
row off).

Geometry is MEASURED, not assumed (specs/_facts.md FACT-06, live Pallet Town frame):

* screen 160x144 px / 16 px per game cell = **10 columns by 9 rows**;
* cell (0, 0) starts at pixel (0, 0): the window IS the whole screen, so no origin
  offset is applied. ``GRID_ORIGIN_X/Y`` stay explicit because a future cropped
  window would set them, and every pixel conversion below goes through them;
* the player sprite's measured screen box on that frame is ``(64, 60)``, i.e. cell
  ``(4, 3)`` — the fifth column from the left and the fourth row down. The player is
  NOT the middle cell: 10 columns is even, so its centre falls between columns.

Readers derive the player cell from the sprite's measured pixel box
(``RAMReader.player_screen_px``); ``PLAYER_CELL`` is the measured nominal anchor they
fall back to when no measurement is available, and the anchor the vision prompt asks
the model to use.

Symbols are shared too (``cls_ram`` / ``cls_vis`` map both channels' glyphs onto one
vocabulary, described in ``docs/specs/SPEC_spatial_blueprint.md``).
"""

from __future__ import annotations

GRID_COLS = 10
GRID_ROWS = 9
CELL_PIXELS = 16

# The full screen, in pixels. Kept derived so the three constants cannot drift apart.
SCREEN_WIDTH_PX = GRID_COLS * CELL_PIXELS  # 160
SCREEN_HEIGHT_PX = GRID_ROWS * CELL_PIXELS  # 144

# Screen pixel of grid cell (0, 0). The window is the whole screen, so this is (0, 0);
# a cropped window would move it and every conversion below follows automatically.
GRID_ORIGIN_X = 0
GRID_ORIGIN_Y = 0

# Measured raw sprite-box entry for the player on a live overworld frame.
PLAYER_SCREEN_PX = (64, 60)
PLAYER_CELL = (
    PLAYER_SCREEN_PX[0] // CELL_PIXELS,
    PLAYER_SCREEN_PX[1] // CELL_PIXELS,
)


def screen_px_to_cell(px: int, py: int) -> tuple[int, int]:
    """The grid cell containing screen pixel ``(px, py)``.

    This is the one conversion both channels use: the RAM renderer anchors its window
    with it, and the vision-side pixel mask crops cells with its inverse.
    """
    return (
        (int(px) - GRID_ORIGIN_X) // CELL_PIXELS,
        (int(py) - GRID_ORIGIN_Y) // CELL_PIXELS,
    )


def cell_pixel_box(col: int, row: int) -> tuple[int, int, int, int]:
    """Pixel box ``(x0, y0, x1, y1)`` of grid cell ``(col, row)`` on the screen."""
    x0 = GRID_ORIGIN_X + int(col) * CELL_PIXELS
    y0 = GRID_ORIGIN_Y + int(row) * CELL_PIXELS
    return (x0, y0, x0 + CELL_PIXELS, y0 + CELL_PIXELS)


def in_grid(col: int, row: int) -> bool:
    """True when ``(col, row)`` is a cell of this grid."""
    return 0 <= col < GRID_COLS and 0 <= row < GRID_ROWS


def cls_ram(ch: str) -> str:
    """Map RAM grid characters to the shared perception classes."""
    if ch == "?":
        return "off-map"
    if ch == "B":
        return "blocked"
    if ch == "D":
        return "doorway"
    if ch in "←↑↓→":
        return "player"
    return "floor"


def cls_vis(ch: str) -> str:
    """Map vision grid characters to the shared perception classes."""
    if ch == "?":
        return "unknown"
    if ch in "←↑↓→":
        return "player"
    if ch == "B":
        return "blocked"
    if ch.isdigit():
        return "object"
    return "floor"
