"""Canonical player-centred pixel geometry for vision/RAM grid comparison."""

GRID_COLS = 9
GRID_ROWS = 9
CELL_PIXELS = 16
GRID_ORIGIN_X = 72
GRID_ORIGIN_Y = 64
PLAYER_CELL = (4, 4)


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
