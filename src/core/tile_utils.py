"""
Tile utilities for the cartographer pipeline.

Provides:
- TSV strip format conversion (packed string ↔ tab-separated values)
- Tile extraction from screenshots for vision model consumption
- Viewport dimension constants for Game Boy Pokémon titles

The vision model can output terrain strips as tab-separated values
instead of packed strings.  For E/W movement, vertical tile columns
are extracted from screenshots and presented as horizontal strips so
the model always reads one horizontal row regardless of direction.
"""

from __future__ import annotations

import numpy as np

# ── Viewport constants ───────────────────────────────────────────────────────

# Game Boy screen: 160 × 144 pixels.
# Pokémon overworld tiles: 16 × 16 pixels (2 × 2 of 8×8 hardware tiles).
# Visible viewport: 160/16 = 10 tiles wide, 144/16 = 9 tiles tall.
# NOTE: world_state.Viewport defaults to (15, 11) which is larger than the
# actual GB screen — that width/height includes off-screen tiles for map
# composition purposes.  Tile-extraction uses the physical screen dimensions.

GB_SCREEN_PX: tuple[int, int] = (160, 144)   # width, height in pixels
GB_TILE_PX: int = 16                          # Pokémon overworld tile size
GB_VIEWPORT_TILES: tuple[int, int] = (10, 9)  # actual visible tiles (w, h)

# The composed map viewport (used in world_state) is larger — 15 × 11.
# This accounts for partial tiles at screen edges and is the canonical
# strip length for OBS_PATCH.
VIEWPORT_TILE_WIDTH: int = 15   # strip length used in OBS_PATCH v1
VIEWPORT_TILE_HEIGHT: int = 11  # viewport rows


# ── TSV conversion ───────────────────────────────────────────────────────────

def strip_to_tsv(packed: str) -> str:
    """Convert a packed terrain string to tab-separated values.

    Args:
        packed: Single-char-per-tile string, e.g. ``"TTT....ggg....T"``.

    Returns:
        Tab-separated string, e.g. ``"T\\tT\\tT\\t.\\t.\\t.\\t.\\tg\\tg\\tg\\t.\\t.\\t.\\t.\\tT"``.

    This is unambiguous — no confusion between ``"."`` (walkable tile)
    and ``" "`` (space/empty).  Both formats are accepted by MapIntegrator.
    """
    return "\t".join(packed)


def tsv_to_strip(tsv: str) -> str:
    """Convert a tab-separated terrain string back to a packed string.

    Args:
        tsv: Tab-separated tile chars, e.g. ``"T\\tT\\tT\\t.\\t.\\t."``.

    Returns:
        Packed single-char-per-tile string.

    Each token between tabs is used as-is — whitespace within tokens
    (e.g. ``" "`` for "no object") is preserved.
    """
    return "".join(tsv.split("\t"))


def normalize_strip_terrain(raw: str) -> str:
    """Accept either packed or TSV format and return packed form.

    If the input contains tab characters, treat it as TSV.  Otherwise,
    return as-is (assumed packed).  This lets MapIntegrator accept both
    formats transparently.

    Args:
        raw: Terrain string in either packed or TSV format.

    Returns:
        Packed single-char-per-tile string.
    """
    if "\t" in raw:
        return tsv_to_strip(raw)
    return raw


# ── Tile extraction from screenshots ─────────────────────────────────────────

def extract_tile_strip(
    screenshot: np.ndarray,
    edge: str,
    y_or_x: int,
    start: int = 0,
    length: int = VIEWPORT_TILE_WIDTH,
    *,
    tile_px: int = GB_TILE_PX,
) -> np.ndarray | None:
    """Extract a horizontal strip of tiles from a numpy screenshot.

    For N/S movement (horizontal strips on the map), extract one row of
    tiles.  For E/W movement (vertical strips on the map), extract one
    column of tiles and arrange them as a horizontal strip so the vision
    model always reads left-to-right.

    Args:
        screenshot: RGB numpy array (height, width, 3), uint8, typically
            144 × 160 (GB screen dimensions).
        edge: ``"N"``, ``"S"``, ``"E"``, or ``"W"`` — direction of movement.
            For N/S edges, ``y_or_x`` is the y pixel coordinate of the row.
            For E/W edges, ``y_or_x`` is the x pixel coordinate of the column.
        y_or_x: Pixel coordinate of the row (N/S) or column (E/W) to extract.
        start: Starting tile index within that row/column (in tile units,
            not pixels).  Default 0 (first tile).
        length: Number of tiles to extract.  Default VIEWPORT_TILE_WIDTH (15).
        tile_px: Tile size in pixels.  Default 16 (GB overworld tiles).

    Returns:
        A numpy array of shape (tile_px, length * tile_px, 3) — a horizontal
        strip of tile images laid out left-to-right, or *None* if the
        requested region is out of bounds.
    """
    h, w = screenshot.shape[:2]

    edge_upper = edge.upper()

    if edge_upper in ("N", "S"):
        # Horizontal strip: extract one row of tiles
        row_px = y_or_x
        if row_px < 0 or row_px + tile_px > h:
            return None

        full_row = screenshot[row_px : row_px + tile_px, :, :]
        tiles: list[np.ndarray] = []
        for i in range(start, start + length):
            x_px = i * tile_px
            if x_px < 0 or x_px + tile_px > w:
                break
            tiles.append(full_row[:, x_px : x_px + tile_px, :])

        if not tiles:
            return None
        return np.concatenate(tiles, axis=1)

    elif edge_upper in ("E", "W"):
        # Vertical strip: extract one column of tiles, arrange horizontally
        col_px = y_or_x
        if col_px < 0 or col_px + tile_px > w:
            return None

        tiles = []
        for i in range(start, start + length):
            y_px = i * tile_px
            if y_px < 0 or y_px + tile_px > h:
                break
            tile = screenshot[y_px : y_px + tile_px, col_px : col_px + tile_px, :]
            tiles.append(tile)

        if not tiles:
            return None
        return np.concatenate(tiles, axis=1)

    return None


def pad_strip_terrain(chars: str, target_length: int = VIEWPORT_TILE_WIDTH) -> str:
    """Pad a terrain strip to exactly ``target_length`` tiles.

    Pads with ``"?"`` (unknown) on the right if the strip is shorter.
    Truncates if longer (should not happen).

    Args:
        chars: Packed terrain string (single char per tile).
        target_length: Desired strip length.  Default 15 (viewport width).

    Returns:
        Padded string of exactly ``target_length`` chars.
    """
    if len(chars) >= target_length:
        return chars[:target_length]
    return chars + "?" * (target_length - len(chars))


# ── Strip template for prompts ──────────────────────────────────────────────

SAMPLE_STRIP_TSV = (
    "T\tT\tT\t.\t.\t.\t.\tg\tg\tg\t.\t.\t.\t.\tT"
)

SAMPLE_STRIP_PACKED = "TTT....ggg....T"
