"""DF-AIPP-13-R3: the exploration policy must stop a two-tile seam treadmill.

Measured on HEAD eb23e03 (run df13r3prem): 80 cycles, 562/562 observations in
Pallet Town, 0 map transitions, and 75% of the tile observations split across
only (7,6) and (7,7). Every press moved — movement-progress read 100% — but the
controller kept undoing its own step, so the run backtracked 96% and never left
the map. The dead-end escape routes (DF-AIPP-13/-R2) cannot fire there: no tile
of the pair is a dead end, and the UP press that would leave the seam is
legitimately blocked by collision truth.

The regression arms below are the two traces the row names: a two-tile ping-pong
must be broken, and a trace that crosses the seam once must be left alone.
"""

from __future__ import annotations

from io import StringIO
from typing import Any

import pytest

import cron_runner

PALLET = 0
ROUTE_1 = 12

# Measured Pallet Town geometry around the treadmill (x, y) -> walkable. The
# north seam at x=6..7 is a wall on y=5/y=4; the only column that reaches
# Route 1 is x=8, which is exactly the detour the guard has to find.
_OPEN = {
    (4, 6), (5, 6), (6, 6), (7, 6), (8, 6), (9, 6),
    (4, 7), (5, 7), (6, 7), (7, 7), (8, 7), (9, 7),
    (4, 8), (5, 8), (6, 8), (7, 8), (8, 8), (9, 8),
    (5, 5), (8, 5), (8, 4), (8, 3), (8, 2), (8, 1),
}  # fmt: skip

_DIRECTION_STEP = {"UP": (0, -1), "DOWN": (0, 1), "LEFT": (-1, 0), "RIGHT": (1, 0)}
_OPPOSITE = {"UP": "DOWN", "DOWN": "UP", "LEFT": "RIGHT", "RIGHT": "LEFT"}


class _FakeState:
    """The subset of run state ``_ow_tile_oscillation_guard`` touches."""

    def __init__(self) -> None:
        self._tile_oscillation = cron_runner._TileOscillationState()
        self._memory_navigation_blocks = cron_runner._MemoryNavigationBlockState()
        self.results: list[dict[str, Any]] = []
        self.log_file = StringIO()


def _walkable(x: int, y: int) -> bool:
    return (x, y) in _OPEN


def _collision_grid(x: int, y: int) -> str:
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


def _patch_data(map_id: int, x: int, y: int) -> dict[str, Any]:
    walkability = {
        direction.lower(): "walkable" if _walkable(x + dx, y + dy) else "blocked"
        for direction, (dx, dy) in _DIRECTION_STEP.items()
    }
    return {
        "map_id": map_id,
        "map_name": "Pallet Town" if map_id == PALLET else "Route 1",
        "player_tile_x": x,
        "player_tile_y": y,
        "player_x": x,
        "player_y": y,
        "adjacent": {
            direction.lower(): "floor"
            if walkability[direction.lower()] == "walkable"
            else "wall"
            for direction in _DIRECTION_STEP
        },
        "adjacent_walkability": walkability,
        "collision_grid": _collision_grid(x, y),
        "visible_exits": [],
    }


def _step(map_id: int, x: int, y: int, direction: str) -> tuple[int, int, int]:
    """Apply one press through the fixture's collision truth."""
    dx, dy = _DIRECTION_STEP[direction]
    if not _walkable(x + dx, y + dy):
        return (map_id, x, y)
    next_x, next_y = x + dx, y + dy
    if map_id == PALLET and (next_x, next_y) == (8, 2):
        return (ROUTE_1, 8, 2)  # the Pallet Town -> Route 1 warp
    return (map_id, next_x, next_y)


def _treadmill_plan(last_direction: str, map_id: int, x: int, y: int) -> list[str]:
    """The measured controller: reverse the last step whenever it can."""
    reverse = _OPPOSITE.get(last_direction, "DOWN")
    del map_id, x, y
    return [reverse]


def _replay(
    *,
    cycles: int,
    start: tuple[int, int, int],
    plan_for: Any,
    active: bool = False,
) -> tuple[list[tuple[int, int, int]], list[dict[str, Any]], list[str]]:
    """Drive the real guard over ``cycles`` decisions and execute its plans."""
    state = _FakeState()
    position = start
    last_direction = ""
    tiles = [position]
    executed: list[str] = []
    for cycle in range(cycles):
        map_id, x, y = position
        patch_data = _patch_data(map_id, x, y)
        plan = plan_for(cycle, last_direction, map_id, x, y)
        guarded = cron_runner._ow_tile_oscillation_guard(
            state,
            cycle,
            plan,
            {"memory_navigation": None},
            patch_data,
            None if not active else {"active": True},
        )
        executed.append(guarded[0])
        position = _step(map_id, x, y, guarded[0])
        if position != (map_id, x, y):
            last_direction = guarded[0]
        tiles.append(position)
    return tiles, state.results, executed


def test_ping_pong_trace_fails_the_old_policy_and_is_broken():
    """A two-tile ping-pong must not survive the guard (fails pre-fix)."""
    tiles, events, executed = _replay(
        cycles=14,
        start=(PALLET, 7, 6),
        plan_for=lambda cycle, last, *_: _treadmill_plan(last, *_),
    )
    applied = [
        event
        for event in events
        if event.get("replacement_direction") != event.get("planned_direction")
    ]

    # Pre-fix there is no guard at all, so the trace stays on the pair and this
    # is the assertion that fails: the treadmill must be interrupted.
    assert applied, "the two-tile ping-pong was never interrupted"
    assert len({(tile[1], tile[2]) for tile in tiles}) >= 3

    pair_counts: dict[tuple[tuple[int, int], tuple[int, int]], int] = {}
    for source, target in zip(tiles, tiles[1:]):
        key = tuple(sorted({(source[1], source[2]), (target[1], target[2])}))
        if len(key) == 2:
            pair_counts[key] = pair_counts.get(key, 0) + 1
    assert max(pair_counts.values()) <= 6, pair_counts

    # Every replacement has to be legal according to live collision truth.
    for event in applied:
        map_id, x, y = event["tile"]
        dx, dy = _DIRECTION_STEP[event["replacement_direction"]]
        assert _walkable(x + dx, y + dy)


def test_seam_crossing_trace_is_left_alone():
    """A trace that crosses the seam once must never be overridden."""
    crossing = ["RIGHT", "UP", "UP", "UP", "UP"]

    def plan_for(cycle: int, last: str, map_id: int, x: int, y: int) -> list[str]:
        del last, map_id, x, y
        return [crossing[min(cycle, len(crossing) - 1)]]

    tiles, events, executed = _replay(
        cycles=len(crossing), start=(PALLET, 7, 6), plan_for=plan_for
    )
    assert events == []
    assert executed == crossing
    assert {tile[0] for tile in tiles} == {PALLET, ROUTE_1}, "the trace must cross once"


def test_reversal_streak_separates_the_two_traces():
    """The classifier the policy keys on: loop = treadmill, crossing = clean."""
    loop = [
        (PALLET, 7, 6),
        (PALLET, 7, 7),
        (PALLET, 7, 6),
        (PALLET, 7, 7),
        (PALLET, 7, 6),
    ]
    crossing = [
        (PALLET, 7, 6),
        (PALLET, 8, 6),
        (PALLET, 8, 5),
        (PALLET, 8, 4),
        (ROUTE_1, 8, 1),
    ]
    assert cron_runner._reversal_streak(loop) >= cron_runner.TILE_OSCILLATION_REVERSALS
    assert (
        cron_runner._reversal_streak(crossing) < cron_runner.TILE_OSCILLATION_REVERSALS
    )
    assert cron_runner._oscillation_axis(loop) == "VERTICAL"
    assert cron_runner._oscillation_axis(crossing) is None


def test_detour_prefers_the_column_where_the_seam_reopens():
    """At (7,6) the UP seam is walled; only the x=8 column reopens it."""
    tile = (PALLET, 7, 6)
    choice = cron_runner._escape_oscillation_direction(
        tile,
        axis="VERTICAL",
        seam="UP",
        reverse="DOWN",
        walkable=["RIGHT", "DOWN", "LEFT"],
        collision_grid=_collision_grid(7, 6),
        visit_counts={},
    )
    assert choice == "RIGHT"


def test_seam_step_is_taken_once_the_detour_rounds_the_wall():
    """From (8,6) the seam is open, so the commitment turns north."""
    tile = (PALLET, 8, 6)
    choice = cron_runner._escape_oscillation_direction(
        tile,
        axis="VERTICAL",
        seam="UP",
        reverse="LEFT",
        walkable=["UP", "RIGHT", "DOWN"],
        collision_grid=_collision_grid(8, 6),
        visit_counts={},
    )
    assert choice == "UP"


def test_no_legal_escape_declines_and_keeps_the_plan():
    """With the reversal as the only walkable press the guard must decline."""
    assert (
        cron_runner._escape_oscillation_direction(
            (PALLET, 0, 0),
            axis="VERTICAL",
            seam="UP",
            reverse="DOWN",
            walkable=["DOWN"],
            collision_grid="#####\n#####\n##↑##\n##.##\n#####",
            visit_counts={},
        )
        is None
    )


@pytest.mark.parametrize("active_context", [True])
def test_navigation_hold_outranks_the_commitment(active_context):
    """HOLD-1's held edge owns the step; a policy commitment must stand down."""
    tiles, events, executed = _replay(
        cycles=8,
        start=(PALLET, 7, 6),
        plan_for=lambda cycle, last, *_: _treadmill_plan(last, *_),
        active=active_context,
    )
    assert events == []
    assert all(plan == executed[0] for plan in executed[:1])


def test_reversing_path_memory_route_is_overridden_and_stamped():
    """A memory route that undoes itself is the treadmill, not an authority.

    Measured in run df13r3repro: the stored Pallet Town -> Route 1 route planned
    DOWN at (9,2) while the controller planned UP at (9,3), and the two halves
    held the pair for 15 cycles.
    """
    state = _FakeState()
    hit = {"result": "hit", "route_key": "/world/path/Pallet-Town->Route-1"}
    position = (PALLET, 7, 6)
    last = ""
    for cycle in range(8):
        map_id, x, y = position
        plan = _OPPOSITE.get(last, "DOWN")
        guarded = cron_runner._ow_tile_oscillation_guard(
            state,
            cycle,
            [plan],
            {"memory_navigation": hit},
            _patch_data(map_id, x, y),
            None,
        )
        moved_to = _step(map_id, x, y, guarded[0])
        if moved_to != position:
            last = guarded[0]
            position = moved_to
    events = state.results
    assert events, "a reversing path-memory route was never interrupted"
    assert all(event["overrode_path_memory"] for event in events)
    assert len({(tile[1], tile[2]) for tile in state._tile_oscillation.trail}) >= 3


def test_wider_circle_is_a_pocket_not_free_roam():
    """The measured treadmill circled 5 tiles; a strict A,B,A,B test misses it.

    Run df13r3repro: 16 distinct tiles over 80 cycles but 75% of the tile
    observations sat on two of them with 96% backtrack, and the strict
    trailing-reversal counter never fired after cycle 5. A pocket of up to
    ``TILE_OSCILLATION_POCKET_TILES`` tiles plus a reversing press is the
    signal, so a six-tile circuit must still be treated as a treadmill.
    """
    circle = [(PALLET, 7, 6), (PALLET, 8, 6), (PALLET, 9, 6), (PALLET, 9, 7),
              (PALLET, 8, 7), (PALLET, 7, 7)]  # fmt: skip
    state = _FakeState()
    position = circle[0]
    last = ""
    for cycle in range(18):
        map_id, x, y = position
        plan = _OPPOSITE.get(last, "RIGHT")
        guarded = cron_runner._ow_tile_oscillation_guard(
            state,
            cycle,
            [plan],
            {"memory_navigation": None},
            _patch_data(map_id, x, y),
            None,
        )
        moved_to = _step(map_id, x, y, guarded[0])
        if moved_to != position:
            last = guarded[0]
            position = moved_to
    events = state.results
    assert events, "a six-tile circuit was accepted as free roam"
    assert any(
        event["pocket_tiles"] <= cron_runner.TILE_OSCILLATION_POCKET_TILES
        for event in events
    )
