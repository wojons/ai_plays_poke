"""DF-AIPP-13-R3 wall sweep: the measured Pallet Town fence row and its gap.

Geometry measured from the ROM block map on the S0 boot state (2026-11-21,
`_MapDB.tile_walkability(0, x, y)` over the full 20x18 tile grid):

  y=0   walkable x=0,1,2,4,5,6,7,8,10,11,13,14,15,16,17,19   (connection row)
  y=1   walkable ONLY x=10,11                               (the north gap)
  y=2   walkable x=1..18                                    (fence row / town)

So the route to Route 1 is: walk the y=2 row east or west until x=10..11, then
press UP twice. Every other column's UP is legitimately blocked, which is what
run df13r3repro pressed 41 times while it treadmilled on the seam tiles.
"""

from __future__ import annotations

from io import StringIO
from typing import Any

import cron_runner

PALLET = 0
ROUTE_1 = 12

_FENCE_ROW = {0: {0, 1, 2, 4, 5, 6, 7, 8, 10, 11, 13, 14, 15, 16, 17, 19}}
_GAP_ROW = {1: {10, 11}}
_FENCE_ROW_2 = {2: set(range(1, 19))}
_BODY = {row: set(range(1, 19)) for row in range(3, 9)}

_OPEN: set[tuple[int, int]] = set()
for _rows in (_FENCE_ROW, _GAP_ROW, _FENCE_ROW_2, _BODY):
    for _y, _columns in _rows.items():
        for _x in _columns:
            _OPEN.add((_x, _y))

_STEP = {"UP": (0, -1), "DOWN": (0, 1), "LEFT": (-1, 0), "RIGHT": (1, 0)}
_OPPOSITE = {"UP": "DOWN", "DOWN": "UP", "LEFT": "RIGHT", "RIGHT": "LEFT"}


class _State:
    def __init__(self) -> None:
        self._tile_oscillation = cron_runner._TileOscillationState()
        self._memory_navigation_blocks = cron_runner._MemoryNavigationBlockState()
        self.results: list[dict[str, Any]] = []
        self.log_file = StringIO()


def _walkable(x: int, y: int) -> bool:
    return (x, y) in _OPEN


def _grid(x: int, y: int) -> str:
    rows = []
    for dy in range(-2, 3):
        cells = []
        for dx in range(-2, 3):
            if dx == 0 and dy == 0:
                cells.append("↑")
            else:
                cells.append("." if _walkable(x + dx, y + dy) else "#")
        rows.append("".join(cells))
    return "\n".join(rows)


def _patch(x: int, y: int) -> dict[str, Any]:
    walk = {
        name.lower(): "walkable" if _walkable(x + dx, y + dy) else "blocked"
        for name, (dx, dy) in _STEP.items()
    }
    return {
        "map_id": PALLET,
        "map_name": "Pallet Town",
        "player_tile_x": x,
        "player_tile_y": y,
        "player_x": x,
        "player_y": y,
        "adjacent": {
            name.lower(): "floor" if walk[name.lower()] == "walkable" else "wall"
            for name in _STEP
        },
        "adjacent_walkability": walk,
        "collision_grid": _grid(x, y),
        "visible_exits": [],
    }


def _step(x: int, y: int, direction: str) -> tuple[int, int, int]:
    dx, dy = _STEP[direction]
    nx, ny = x + dx, y + dy
    if not _walkable(nx, ny):
        return (PALLET, x, y)
    if (nx, ny) == (10, 0) or (nx, ny) == (11, 0):
        return (ROUTE_1, nx, ny)  # the Pallet Town -> Route 1 connection
    return (PALLET, nx, ny)


def test_sweep_walks_the_fence_row_to_the_north_gap():
    """From the treadmill's own tiles the policy must reach x=10 and cross."""
    state = _State()
    x, y = 7, 6
    last = ""
    trail: list[tuple[int, int, int]] = []
    for cycle in range(60):
        patch = _patch(x, y)
        plan = [_OPPOSITE.get(last, "UP")]
        guarded = cron_runner._ow_tile_oscillation_guard(
            state, cycle, plan, {"memory_navigation": None}, patch, None
        )
        moved = _step(x, y, guarded[0])
        trail.append(moved)
        if moved != (PALLET, x, y):
            last = guarded[0]
            x, y = moved[1], moved[2]
        if moved[0] == ROUTE_1:
            break
    assert trail[-1][0] == ROUTE_1, f"never crossed the north gap: tail={trail[-8:]}"


def test_gap_row_pocket_turns_north_instead_of_sideways():
    """Live failure from run df13r3fix: at (10,1) the run answered its own UP
    with DOWN, the breaker replaced that with RIGHT (sideways along the gap
    row) and the run ping-ponged between (10,1) and (11,1) for 37 cycles
    without ever pressing UP again. The straight continuation must win.
    """
    state = _State()
    x, y = 10, 1
    last = "UP"  # arrived by pressing UP from (10,2)
    trail: list[tuple[int, int, int]] = []
    for cycle in range(8):
        guarded = cron_runner._ow_tile_oscillation_guard(
            state,
            cycle,
            [_OPPOSITE.get(last, "DOWN")],
            {"memory_navigation": None},
            _patch(x, y),
            None,
        )
        moved = _step(x, y, guarded[0])
        trail.append(moved)
        if moved != (PALLET, x, y):
            last = guarded[0]
            x, y = moved[1], moved[2]
        if moved[0] == ROUTE_1:
            break
    assert trail[-1][0] == ROUTE_1, f"never pressed UP through the gap: {trail}"
    assert any(event["replacement_direction"] == "UP" for event in state.results)


def test_pocket_on_the_fence_row_is_not_accepted_as_free_roam():
    """A two-tile pocket at the fence still counts as a treadmill."""
    state = _State()
    x, y = 7, 2
    last = ""
    for cycle in range(12):
        guarded = cron_runner._ow_tile_oscillation_guard(
            state,
            cycle,
            [_OPPOSITE.get(last, "DOWN")],
            {"memory_navigation": None},
            _patch(x, y),
            None,
        )
        moved = _step(x, y, guarded[0])
        if moved != (PALLET, x, y):
            last = guarded[0]
            x, y = moved[1], moved[2]
    assert state.results, "the fence-row pocket was never interrupted"
    outcomes = {event["outcome"] for event in state.results}
    assert outcomes & {"sweep_start", "sweep", "sweep_seam", "applied", "novelty"}


def test_door_press_from_open_ground_is_vetoed():
    """Measured run df13r3fix crossed into Red's House 1F at cycle 60 while
    Pallet Town still had unexplored ground, then spent 21 cycles pinned on
    two indoor tiles (11 of 80 on one adjacent pair). A door press from open
    ground must yield to a non-door step.
    """
    state = _State()
    # Prime the trail with open-ground history (free roam, not a pocket) and
    # spend the run's door budget, so further entries are vetoed.
    state._tile_oscillation.trail = [(PALLET, x, 6) for x in range(1, 9)]
    state._tile_oscillation.map_entries = cron_runner.TILE_OSCILLATION_DOOR_BUDGET
    x, y = 5, 6  # Pallet Town door tile: UP walks into the house
    patch = _patch(x, y)
    patch["adjacent"]["up"] = "door"
    guarded = cron_runner._ow_tile_oscillation_guard(
        state, 0, ["UP"], {"memory_navigation": None}, patch, None
    )
    assert guarded != ["UP"], "the door press was not vetoed"
    assert state.results and state.results[-1]["outcome"] == "door_veto"


def test_door_press_is_allowed_when_the_run_is_stuck():
    """A trapped run may take the only door left: veto is not a prohibition."""
    state = _State()
    x, y = 5, 6
    patch = _patch(x, y)
    patch["adjacent"]["up"] = "door"
    # Make every non-door step illegal.
    for direction in ("down", "left", "right"):
        patch["adjacent"][direction] = "wall"
        patch["adjacent_walkability"][direction] = "blocked"
    guarded = cron_runner._ow_tile_oscillation_guard(
        state, 0, ["UP"], {"memory_navigation": None}, patch, None
    )
    assert guarded == ["UP"]
