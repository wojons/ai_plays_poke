"""
Map Integrator — validates and applies OBS_PATCH patches to canonical WorldState.

This is the deterministic middle layer between:
- Vision model (proposes patches)
- Controller model (reads composed views)

The integrator enforces safety rules:
- Rejects patches with impossible movement
- Won't overwrite high-confidence terrain with low-confidence
- Validates patch consistency before applying
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .obs_patch import ObsPatch, validate_patch
from .world_state import Actor, MovementEdge, WorldState


class MapIntegrator:
    """Applies vision model patches to canonical world state."""

    def __init__(self, world: WorldState | None = None, world_dir: Path | None = None):
        """Initialise with an existing WorldState or a directory to load from."""
        if world:
            self.world = world
        elif world_dir:
            self.world = WorldState.load(world_dir)
        else:
            self.world = WorldState()
            self.world.init_blank(200, 200)  # generous default

        self._patch_count: int = 0
        self._rejected_count: int = 0
        self._rejections: list[dict[str, Any]] = []

    # ── Public API ──────────────────────────────────────────────────────

    def apply(self, patch_data: dict[str, Any] | str) -> bool:
        """Parse, validate, and apply a patch. Returns True on success."""
        # Parse
        if isinstance(patch_data, str):
            patch_data = _parse_raw(patch_data)
        patch = _dict_to_patch(patch_data)

        # Validate
        errors = validate_patch(patch)
        if errors:
            self._rejected_count += 1
            self._rejections.append({"tick": patch.tick, "errors": errors, "patch": patch_data})
            return False

        # Apply
        try:
            self._apply_patch(patch)
            self._patch_count += 1
            return True
        except Exception as exc:
            self._rejected_count += 1
            self._rejections.append({"tick": patch.tick, "errors": [str(exc)], "patch": patch_data})
            return False

    def compose_for_controller(self) -> str:
        """Return the compact composed view for the non-vision controller."""
        return self.world.composed_view_compact()

    def save(self, directory: Path) -> None:
        """Persist current world state."""
        self.world.save(directory)

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "patches_applied": self._patch_count,
            "patches_rejected": self._rejected_count,
            "total_patches": self._patch_count + self._rejected_count,
            "rejection_rate": (
                self._rejected_count / max(1, self._patch_count + self._rejected_count)
            ),
            "recent_rejections": self._rejections[-5:],
        }

    # ── Internal ────────────────────────────────────────────────────────

    def _apply_patch(self, patch: ObsPatch) -> None:
        w = self.world

        # Full resync
        if patch.resync:
            self._apply_resync(patch)
            return

        # Corrections (apply before movement — fixes old mistakes)
        for corr in patch.corrections:
            self._apply_correction(corr)

        # Movement
        if patch.movement:
            mov = patch.movement
            w.last_button = mov.input
            w.last_result = mov.result
            w.player.facing = mov.facing
            w.player.mode = mov.mode

            if mov.result == "moved":
                w.player.pos = (
                    w.player.pos[0] + mov.player_delta[0],
                    w.player.pos[1] + mov.player_delta[1],
                )
                # Mark visited
                self._mark_visited(w.player.pos[0], w.player.pos[1], "@")
                if patch.visited_add:
                    for vpos in patch.visited_add:
                        self._mark_visited(vpos[0], vpos[1], "+")

        # Viewport
        if patch.viewport:
            vp = patch.viewport
            w.viewport.origin = (
                w.viewport.origin[0] + vp.origin_delta[0],
                w.viewport.origin[1] + vp.origin_delta[1],
            )

        # Strip (new row/column)
        if patch.strip:
            self._apply_strip(patch.strip)

        # Edges
        for edge in patch.edges:
            w.set_edge(
                edge.from_pos[0], edge.from_pos[1],
                edge.dir, edge.outcome, edge.reason, patch.tick,
            )

        # Actor updates
        for au in patch.actor_updates:
            self._apply_actor_update(au, patch.tick)

        w.tick = patch.tick

    def _apply_resync(self, patch: ObsPatch) -> None:
        """Full resync — clear and rebuild from full_viewport."""
        resync = patch.resync
        w = self.world

        w.map_id = resync.new_map_id or w.map_id
        w.player.pos = tuple(resync.player_pos)
        w.player.facing = resync.player_facing
        w.viewport.origin = tuple(resync.viewport_origin)

        fv = resync.full_viewport
        if "terrain" in fv:
            w.terrain = [list(row) for row in fv["terrain"]]
            h = len(w.terrain)
            w2 = len(w.terrain[0]) if h > 0 else 0
            w.objects = [[" " for _ in range(w2)] for _ in range(h)]
            w.visited = [["?" for _ in range(w2)] for _ in range(h)]
            self._mark_visited(w.player.pos[0], w.player.pos[1], "@")

        if "objects" in fv:
            for y, row in enumerate(fv["objects"]):
                if y < len(w.objects):
                    w.objects[y] = list(row)

        # Clear movement edges — new map, new rules
        w.edges.clear()

        w.tick = patch.tick

    def _apply_strip(self, strip) -> None:
        """Apply a single row/column of new data."""
        w = self.world
        edge = strip.edge.upper()

        if edge in ("N", "S"):
            y = strip.global_y
            if strip.terrain:
                for i, ch in enumerate(strip.terrain):
                    x = strip.x_start + i
                    if 0 <= y < len(w.terrain) and 0 <= x < len(w.terrain[0]):
                        if ch != "?" or w.terrain[y][x] == "?":
                            w.terrain[y][x] = ch
            if strip.objects:
                for i, ch in enumerate(strip.objects):
                    x = strip.x_start + i
                    if 0 <= y < len(w.objects) and 0 <= x < len(w.objects[0]):
                        if ch != " " or w.objects[y][x] == " ":
                            w.objects[y][x] = ch

        elif edge in ("E", "W"):
            x = strip.global_x
            if strip.terrain:
                for i, ch in enumerate(strip.terrain):
                    y = strip.y_start + i
                    if 0 <= y < len(w.terrain) and 0 <= x < len(w.terrain[0]):
                        if ch != "?" or w.terrain[y][x] == "?":
                            w.terrain[y][x] = ch
            if strip.objects:
                for i, ch in enumerate(strip.objects):
                    y = strip.y_start + i
                    if 0 <= y < len(w.objects) and 0 <= x < len(w.objects[0]):
                        if ch != " " or w.objects[y][x] == " ":
                            w.objects[y][x] = ch

    def _apply_correction(self, corr) -> None:
        """Apply a correction to a previously-written tile."""
        w = self.world
        x, y = corr.at

        # Only overwrite if confidence is reasonable
        if corr.confidence < 0.5:
            return

        existing = "?"
        if corr.layer == "terrain":
            existing = w.terrain_at(x, y)
            # Don't overwrite high-confidence known terrain with low-confidence
            if existing != "?" and corr.confidence < 0.7 and corr.to_char == "?":
                return
            w.set_terrain(x, y, corr.to_char)
        elif corr.layer == "object":
            existing = w.object_at(x, y)
            if existing != " " and corr.confidence < 0.7 and corr.to_char == " ":
                return
            if 0 <= y < len(w.objects) and 0 <= x < len(w.objects[0]):
                w.objects[y][x] = corr.to_char
        elif corr.layer == "visited":
            self._mark_visited(x, y, corr.to_char)

    def _apply_actor_update(self, au, tick: int) -> None:
        """Update or create an actor."""
        w = self.world
        aid = au.id or f"actor_{au.pos[0]}_{au.pos[1]}"

        if aid in w.actors:
            actor = w.actors[aid]
            if au.pos:
                actor.pos = tuple(au.pos)
            if au.facing:
                actor.facing = au.facing
            if au.kind:
                actor.kind = au.kind
            actor.confidence = au.confidence
            actor.last_seen_tick = tick
        else:
            w.actors[aid] = Actor(
                id=aid,
                kind=au.kind,
                pos=tuple(au.pos),
                facing=au.facing,
                confidence=au.confidence,
                last_seen_tick=tick,
                symbol=au.symbol,
            )

    def _mark_visited(self, x: int, y: int, state: str) -> None:
        """Mark a tile in the visited map."""
        w = self.world
        if 0 <= y < len(w.visited) and 0 <= x < len(w.visited[0]):
            current = w.visited[y][x]
            # Priority: @ > + > . > ?
            priority = {"@": 4, "+": 3, ".": 2, "?": 1}
            if priority.get(state, 0) > priority.get(current, 0):
                w.visited[y][x] = state


# ── Internal helpers ────────────────────────────────────────────────────────


def _parse_raw(raw: str) -> dict[str, Any]:
    """Parse raw OBS_PATCH text (YAML or JSON)."""
    import json
    import yaml as _yaml

    raw = raw.strip()
    # Strip markdown fences
    if raw.startswith("```"):
        lines = raw.split("\n")
        lines = lines[1:] if lines else []
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines)

    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        pass

    try:
        return _yaml.safe_load(raw) or {}
    except Exception:
        return {}


def _dict_to_patch(data: dict[str, Any]) -> ObsPatch:
    """Convert a raw dict to an ObsPatch (shim to avoid circular imports)."""
    from .obs_patch import parse_obs_patch
    return parse_obs_patch(data)


# Re-export for convenience
__all__ = ["MapIntegrator", "ObsPatch", "WorldState"]
