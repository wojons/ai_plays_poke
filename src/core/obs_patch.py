"""
OBS_PATCH v1 — structured patch format for vision model → world state updates.

The vision model outputs patches in this format.  The MapIntegrator
validates and applies them deterministically.  The vision model never
touches canonical state directly — it only proposes patches.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import yaml


# ── Data classes ────────────────────────────────────────────────────────────


@dataclass
class StripUpdate:
    """A single row or column update (edge scroll)."""
    edge: str                         # N | S | E | W — which edge of the viewport
    global_y: int = 0                 # y-coord of this row (for N/S edges)
    global_x: int = 0                 # x-coord of this column (for E/W edges)
    x_start: int = 0                  # starting x (for N/S edges)
    y_start: int = 0                  # starting y (for E/W edges)
    terrain: str = ""                 # single-char string, length = viewport width or height
    objects: str = ""                 # same length
    actors: str = ""                  # actor kind chars, same length


@dataclass
class Movement:
    """Result of the last input."""
    input: str = ""                   # button: UP | DOWN | LEFT | RIGHT | A | B | START | SELECT
    result: str = "unknown"           # moved | blocked | turned_only | dialog | warp | battle | unknown
    player_delta: list[int] = field(default_factory=lambda: [0, 0])
    facing: str = "S"                 # N | E | S | W
    mode: str = "walk"


@dataclass
class ViewportDelta:
    """How the viewport changed."""
    origin_delta: list[int] = field(default_factory=lambda: [0, 0])
    new_edge: str = "none"            # N | S | E | W | none | warp


@dataclass
class EdgeUpdate:
    """A movement edge to record."""
    from_pos: list[int] = field(default_factory=lambda: [0, 0])
    dir: str = "N"                    # N | E | S | W
    outcome: str = "unknown"          # open | blocked | one_way_ledge | warp | npc_block | water_edge
    reason: str = ""


@dataclass
class ActorUpdate:
    """NPC actor update."""
    id: str = ""
    kind: str = "u"
    symbol: str = ""
    pos: list[int] = field(default_factory=lambda: [0, 0])
    facing: str = "S"
    confidence: float = 0.5


@dataclass
class Correction:
    """Correct a previously-written tile."""
    layer: str = "terrain"            # terrain | object | visited
    at: list[int] = field(default_factory=lambda: [0, 0])
    from_char: str = "?"
    to_char: str = "?"
    confidence: float = 0.5
    reason: str = ""


@dataclass
class Resync:
    """Full viewport resync (warp, battle exit, camera jump)."""
    reason: str = ""
    new_map_id: str = ""
    viewport_origin: list[int] = field(default_factory=lambda: [0, 0])
    player_pos: list[int] = field(default_factory=lambda: [0, 0])
    player_facing: str = "S"
    full_viewport: dict[str, list[str]] = field(default_factory=dict)
    # full_viewport keys: terrain, objects, actors (list of strings, one per row)


@dataclass
class ObsPatch:
    """Top-level OBS_PATCH v1 structure."""
    prev_tick: int = 0
    tick: int = 0

    movement: Movement | None = None
    viewport: ViewportDelta | None = None
    strip: StripUpdate | None = None
    visited_add: list[list[int]] = field(default_factory=list)
    edges: list[EdgeUpdate] = field(default_factory=list)
    actor_updates: list[ActorUpdate] = field(default_factory=list)
    corrections: list[Correction] = field(default_factory=list)
    resync: Resync | None = None

    raw: dict[str, Any] = field(default_factory=dict)


# ── Parser ──────────────────────────────────────────────────────────────────


def parse_obs_patch(data: dict[str, Any] | str) -> ObsPatch:
    """Parse OBS_PATCH v1 from dict or YAML/JSON string.

    Returns ObsPatch with validation errors stored in raw['_errors'].
    """
    patch = ObsPatch()

    if isinstance(data, str):
        try:
            data = yaml.safe_load(data)
        except Exception:
            patch.raw["_errors"] = [f"Failed to parse patch: {data[:200]}"]  # type: ignore[index]
            return patch
        if not isinstance(data, dict):
            patch.raw["_errors"] = ["Patch is not a dict"]
            return patch

    patch.raw = data
    errors: list[str] = []

    patch.prev_tick = data.get("prev_tick", 0)
    patch.tick = data.get("tick", 0)

    # Movement
    mov = data.get("movement")
    if isinstance(mov, dict):
        patch.movement = Movement(
            input=mov.get("input", ""),
            result=mov.get("result", "unknown"),
            player_delta=mov.get("player_delta", [0, 0]),
            facing=mov.get("facing", "S"),
            mode=mov.get("mode", "walk"),
        )

    # Viewport
    vp = data.get("viewport")
    if isinstance(vp, dict):
        patch.viewport = ViewportDelta(
            origin_delta=vp.get("origin_delta", [0, 0]),
            new_edge=vp.get("new_edge", "none"),
        )

    # Strip
    strip = data.get("strip")
    if isinstance(strip, dict):
        edge = strip.get("edge", "")
        # Accept terrain_tsv (tab-separated) as an alternative to terrain (packed)
        terrain_raw = strip.get("terrain", "")
        terrain_tsv = strip.get("terrain_tsv", "")
        if terrain_tsv and not terrain_raw:
            from .tile_utils import tsv_to_strip
            terrain_raw = tsv_to_strip(terrain_tsv)

        objects_raw = strip.get("objects", "")
        objects_tsv = strip.get("objects_tsv", "")
        if objects_tsv and not objects_raw:
            from .tile_utils import tsv_to_strip
            objects_raw = tsv_to_strip(objects_tsv)

        actors_raw = strip.get("actors", "")
        actors_tsv = strip.get("actors_tsv", "")
        if actors_tsv and not actors_raw:
            from .tile_utils import tsv_to_strip
            actors_raw = tsv_to_strip(actors_tsv)

        patch.strip = StripUpdate(
            edge=edge,
            global_y=strip.get("global_y", 0),
            global_x=strip.get("global_x", 0),
            x_start=strip.get("x_start", 0),
            y_start=strip.get("y_start", 0),
            terrain=terrain_raw,
            objects=objects_raw,
            actors=actors_raw,
        )

    # Visited
    visited = data.get("visited", data.get("visited_add"))
    if isinstance(visited, dict):
        patch.visited_add = visited.get("add", [])
    elif isinstance(visited, list):
        patch.visited_add = visited

    # Edges
    edges = data.get("edges")
    if isinstance(edges, list):
        for e in edges:
            if isinstance(e, dict):
                patch.edges.append(EdgeUpdate(
                    from_pos=e.get("from", e.get("from_pos", [0, 0])),  # type: ignore[arg-type]
                    dir=e.get("dir", e.get("direction", "N")),  # type: ignore[arg-type]
                    outcome=e.get("outcome", "unknown"),
                    reason=e.get("reason", ""),
                ))

    # Actor updates
    actors = data.get("actor_updates", data.get("actors"))
    if isinstance(actors, list):
        for a in actors:
            if isinstance(a, dict):
                patch.actor_updates.append(ActorUpdate(
                    id=a.get("id", f"actor_{len(patch.actor_updates)}"),
                    kind=a.get("kind", "u"),
                    symbol=a.get("symbol", ""),
                    pos=a.get("pos", [0, 0]),
                    facing=a.get("facing", "S"),
                    confidence=a.get("confidence", 0.5),
                ))

    # Corrections
    corrections = data.get("corrections")
    if isinstance(corrections, list):
        for c in corrections:
            if isinstance(c, dict):
                patch.corrections.append(Correction(
                    layer=c.get("layer", "terrain"),
                    at=c.get("at", [0, 0]),
                    from_char=c.get("from", "?"),
                    to_char=c.get("to", "?"),
                    confidence=c.get("confidence", 0.5),
                    reason=c.get("reason", ""),
                ))

    # Resync
    resync = data.get("resync")
    if isinstance(resync, dict):
        patch.resync = Resync(
            reason=resync.get("reason", ""),
            new_map_id=resync.get("new_map_id", ""),
            viewport_origin=resync.get("viewport_origin", [0, 0]),
            player_pos=resync.get("player_pos", [0, 0]),
            player_facing=resync.get("player_facing", "S"),
            full_viewport=resync.get("full_viewport", {}),
        )

    patch.raw["_errors"] = errors
    return patch


# ── Validator ───────────────────────────────────────────────────────────────


def validate_patch(patch: ObsPatch) -> list[str]:
    """Validate an OBS_PATCH for consistency. Returns list of error messages.

    Empty list = valid.
    """
    errors: list[str] = []

    # Resync patches skip normal validation — they're intentional full rewrites
    if patch.resync:
        return errors

    # Movement must be present for non-resync patches
    if not patch.movement:
        errors.append("Missing 'movement' section (required for non-resync patches)")
        return errors

    mov = patch.movement

    # Movement result checks
    result = mov.result

    if result == "moved":
        # Player must move at most 1 tile
        dx, dy = mov.player_delta
        if abs(dx) > 1 or abs(dy) > 1:
            errors.append(f"Player moved more than 1 tile: delta={mov.player_delta}")

        # If viewport scrolled, strip must be present
        vp = patch.viewport
        if vp and vp.new_edge != "none":
            if not patch.strip:
                errors.append("Viewport scrolled but no 'strip' provided")
            elif not patch.strip.terrain:
                errors.append("Strip has no terrain data")

        # Strip should only contain one new row/column
        if patch.strip and patch.strip.edge and patch.strip.edge.upper() in ("N", "S"):
            if patch.strip.terrain and len(patch.strip.terrain) > 30:
                errors.append(f"Strip terrain too long for single row: {len(patch.strip.terrain)} chars")

    elif result == "blocked":
        # Should not shift viewport
        vp = patch.viewport
        if vp and vp.origin_delta != [0, 0]:
            errors.append("Blocked movement should not shift viewport")
        # Should record blocked edge
        if not patch.edges:
            errors.append("Blocked movement should record at least one blocked edge")

    elif result == "turned_only":
        # Player delta must be [0, 0]
        if mov.player_delta != [0, 0]:
            errors.append("turned_only should have player_delta [0, 0]")

    elif result in ("warp", "battle", "dialog", "menu", "cutscene"):
        # These should trigger a resync, not a normal patch
        if not patch.resync:
            errors.append(f"'{result}' movement result should include 'resync' section")

    return errors
