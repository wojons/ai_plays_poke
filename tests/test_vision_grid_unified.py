"""One grid, one legend: the RAM channel and the vision channel describe ONE window.

Board row VISION-GRID-UNIFY. Three definitions of the same geometry had drifted apart:

* ``src/core/vision_grid.py`` — 9x9 with ``PLAYER_CELL = (4, 4)``;
* ``src/core/ram_reader.py::render_tile_grid`` — 10x9 measured from the sprite box;
* ``scripts/vision_people_probe.py`` — 9x9 with ``PLAYER_CELL = (4, 3)``.

Rendering one frame through those produced the player arrow on different cells (RAM
rows 0-1 vs vision rows 1-2), so every cell-by-cell verdict was shifted by
construction. These tests pin the unification: one definition site, one shape, and one
player cell shared by the RAM renderer, the vision-side pixel geometry, and the prompt
the vision model is actually given.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.core import vision_grid
from src.core.vision_grid import (
    CELL_PIXELS,
    GRID_COLS,
    GRID_ORIGIN_X,
    GRID_ORIGIN_Y,
    GRID_ROWS,
    PLAYER_CELL,
    PLAYER_SCREEN_PX,
    cell_pixel_box,
    screen_px_to_cell,
)

REPO = Path(__file__).resolve().parents[1]
PROMPT = REPO / "prompts/exploration/vision_map_blueprint.md"
CANONICAL = REPO / "src" / "core" / "vision_grid.py"
GEOMETRY_NAMES = ("GRID_COLS", "GRID_ROWS", "PLAYER_CELL", "CELL_PIXELS")
GRID_GLYPHS = set(".GBWTDMN?↑↓←→@123456789")


@pytest.fixture
def mock_emu() -> MagicMock:
    """An emulator stub: the renderer's inputs are monkeypatched per test."""
    emu = MagicMock()
    emu.read_u8.return_value = 0
    return emu


def _grid_rows(text: str) -> list[str]:
    """The rendered grid rows of a ``render_tile_grid`` body, in order."""
    rows: list[str] = []
    for line in text.splitlines():
        if not line.startswith("  "):
            continue
        body = line.strip()
        if body and all(ch in GRID_GLYPHS for ch in body):
            rows.append(body)
    return rows


def _reader(
    mock_emu: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    screen_px: list[int] | None,
    tile: tuple[int, int] = (8, 8),
) -> Any:
    """A RAMReader whose map is an open floor and whose sprite box is ``screen_px``."""
    from src.core.ram_reader import RAMReader

    with patch("src.core.ram_reader._MapDB") as mapdb_cls:
        db = mapdb_cls.return_value
        db.get_map.return_value = {
            "width": 8,
            "height": 8,
            "tileset": 4,
            "block_data": [0x0F] * 64,
        }
        db.tile_walkability.return_value = True
        db.classify_block.return_value = "wall"
        reader = RAMReader(mock_emu, "/fake/rom.gb")

    monkeypatch.setattr(reader, "current_map_id", lambda: 0)
    monkeypatch.setattr(reader, "current_map_name", lambda: "Test Town")
    monkeypatch.setattr(reader, "player_tile_x", lambda: tile[0])
    monkeypatch.setattr(reader, "player_tile_y", lambda: tile[1])
    monkeypatch.setattr(reader, "player_facing", lambda: "up")
    monkeypatch.setattr(reader, "player_screen_px", lambda: screen_px)
    return reader


def test_geometry_has_exactly_one_definition_site() -> None:
    """AC1 as a durable guard: only vision_grid.py may DEFINE the grid geometry."""
    pattern = re.compile(r"(%s)\s*(?::[^=]+)?=" % "|".join(GEOMETRY_NAMES))
    offenders: list[str] = []
    for directory in ("src", "scripts"):
        for path in sorted((REPO / directory).rglob("*.py")):
            if path == CANONICAL:
                continue
            for lineno, line in enumerate(path.read_text().splitlines(), 1):
                if pattern.match(line):
                    offenders.append(
                        f"{path.relative_to(REPO)}:{lineno}: {line.strip()}"
                    )
    assert offenders == [], (
        "grid geometry must be defined only in src/core/vision_grid.py; "
        f"other definition sites: {offenders}"
    )


def test_constants_describe_the_whole_screen() -> None:
    """160x144 px at 16 px per cell: 10 columns, 9 rows, measured player cell."""
    assert (GRID_COLS, GRID_ROWS, CELL_PIXELS) == (10, 9, 16)
    assert (GRID_COLS * CELL_PIXELS, GRID_ROWS * CELL_PIXELS) == (160, 144)
    assert (GRID_ORIGIN_X, GRID_ORIGIN_Y) == (0, 0)
    # The measured sprite box is what the RAM renderer anchors on; the cell must be
    # the same one the vision side is told to use.
    assert PLAYER_SCREEN_PX == (64, 60)
    assert screen_px_to_cell(*PLAYER_SCREEN_PX) == PLAYER_CELL == (4, 3)


def test_ram_and_vision_agree_on_the_player_cell(
    mock_emu: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC2: same row count, same row width, arrow on the same cell in both channels."""
    reader = _reader(mock_emu, monkeypatch, [*PLAYER_SCREEN_PX], tile=(8, 8))
    rows = _grid_rows(reader.render_tile_grid())

    # The RAM renderer's shape.
    assert len(rows) == GRID_ROWS, f"RAM rendered {len(rows)} rows: {rows}"
    assert {len(row) for row in rows} == {GRID_COLS}, (
        f"widths: {[len(r) for r in rows]}"
    )

    # Where RAM put the player arrow.
    ram_cell = {
        (c, r) for r, row in enumerate(rows) for c, ch in enumerate(row) if ch == "↑"
    }
    assert ram_cell == {PLAYER_CELL}, f"RAM arrow at {ram_cell}, expected {PLAYER_CELL}"

    # Where the vision channel's contract puts it: the same measured cell, expressed in
    # the same screen-pixel geometry the RAM grid crops with.
    vision_cell = screen_px_to_cell(*PLAYER_SCREEN_PX)
    assert vision_cell == PLAYER_CELL == next(iter(ram_cell))

    # And the two grids are the same window: every cell maps to the pixel box the RAM
    # window's column/row offsets describe.
    assert cell_pixel_box(*PLAYER_CELL) == (64, 48, 80, 64), (
        "the player cell must cover the measured sprite box"
    )
    assert all(
        cell_pixel_box(*PLAYER_CELL)[i]
        <= PLAYER_SCREEN_PX[j]
        < cell_pixel_box(*PLAYER_CELL)[i + 2]
        for i, j in ((0, 0), (1, 1))
    ), "the measured sprite box must fall inside the player cell"


def test_ram_arrow_follows_the_measured_sprite_box(
    mock_emu: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The anchor is the measurement: move the sprite and the arrow moves with it."""
    moved = _reader(mock_emu, monkeypatch, [64 + 2 * CELL_PIXELS, 60])
    rows = _grid_rows(moved.render_tile_grid())
    assert rows[PLAYER_CELL[1]].index("↑") == PLAYER_CELL[0] + 2


def test_ram_grid_falls_back_to_the_shared_player_cell(
    mock_emu: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No sprite box available: the fallback is PLAYER_CELL, not a guessed midpoint."""
    reader = _reader(mock_emu, monkeypatch, None)
    rows = _grid_rows(reader.render_tile_grid())
    assert len(rows) == GRID_ROWS
    assert rows[PLAYER_CELL[1]].index("↑") == PLAYER_CELL[0]


def test_vision_prompt_declares_the_same_grid() -> None:
    """The model is told the shape the code validates against — no second legend."""
    text = PROMPT.read_text()
    width = re.search(r'"width":\s*(\d+)', text)
    height = re.search(r'"height":\s*(\d+)', text)
    player = re.search(r'"player_cell":\s*\[(\d+),\s*(\d+)\]', text)
    assert width and int(width.group(1)) == GRID_COLS, f"prompt width: {width}"
    assert height and int(height.group(1)) == GRID_ROWS, f"prompt height: {height}"
    assert player and (int(player.group(1)), int(player.group(2))) == PLAYER_CELL, (
        f"prompt player_cell: {player}"
    )
    assert f"exactly **{GRID_ROWS}** strings" in text
    assert f"exactly **{GRID_COLS}** characters" in text


def test_vision_mask_renders_the_same_grid_as_ram(tmp_path: Path) -> None:
    """The vision-side renderer emits the same shape, over the same pixel boxes.

    ``pixel_mask`` crops the frame with the shared cell boxes, so a mask cell and a RAM
    cell are the same place. The old player-centred window cropped boxes that ran off
    the screen (negative coordinates on the left/top), which is how the two channels
    ended up one row apart.
    """
    from PIL import Image

    from scripts.perception_diff import pixel_mask

    black = tmp_path / "black.png"
    Image.new("L", (160, 144), 0).save(black)
    mask = pixel_mask(black)
    assert len(mask) == GRID_ROWS, mask
    assert {len(row) for row in mask} == {GRID_COLS}, [len(r) for r in mask]
    assert set("".join(mask)) == {"?"}, "a black frame must be unknown in every cell"

    # Lighting exactly one cell's pixel box must flip exactly that cell.
    mixed = tmp_path / "mixed.png"
    img = Image.new("L", (160, 144), 0)
    x0, y0, x1, y1 = cell_pixel_box(1, 7)
    for x in range(x0, x1):
        for y in range(y0, y1):
            img.putpixel((x, y), 255)
    img.save(mixed)
    lit = pixel_mask(mixed)
    assert lit[7][1] == "."
    assert sum(row.count(".") for row in lit) == 1, lit


def test_cell_boxes_tile_the_whole_screen() -> None:
    """The vision-side mask boxes and the RAM cell offsets cover one and the same grid."""
    boxes = [cell_pixel_box(c, r) for r in range(GRID_ROWS) for c in range(GRID_COLS)]
    assert boxes[0] == (0, 0, CELL_PIXELS, CELL_PIXELS)
    assert boxes[-1] == (
        160 - CELL_PIXELS,
        144 - CELL_PIXELS,
        160,
        144,
    )
    # Row 0 runs left to right with no gap, and each row starts below the last.
    for col in range(GRID_COLS - 1):
        assert cell_pixel_box(col, 0)[2] == cell_pixel_box(col + 1, 0)[0]
    for row in range(GRID_ROWS - 1):
        assert cell_pixel_box(0, row)[3] == cell_pixel_box(0, row + 1)[1]
    assert vision_grid.in_grid(GRID_COLS - 1, GRID_ROWS - 1) is True
    assert vision_grid.in_grid(GRID_COLS, 0) is False
