"""
World State — canonical layered map for the AI Plays Pokémon agent.

Layers (each stored as a file):
  state.yaml       — player position, facing, mode, lighting, viewport
  terrain.map      — base terrain grid (2D array of single chars)
  objects.map      — static objects grid (2D array)
  visited.map      — exploration tracking grid
  actors.yaml      — dynamic NPC list with confidence
  movement_edges.yaml — directed movement edges (open/blocked/warp)

The vision model outputs OBS_PATCH patches.  The MapIntegrator
(in map_integrator.py) validates and applies them.  This module
holds the canonical state and renders composed views.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .symbols import (
    terrain_to_ascii,
    object_to_ascii,
    actor_to_ascii,
    facing_ascii,
)


# ── Data classes ────────────────────────────────────────────────────────────


@dataclass
class PlayerState:
    """Position, facing, and mode of the player character."""
    pos: tuple[int, int] = (0, 0)       # global [x, y]
    facing: str = "S"                    # N | E | S | W
    screen_pos: tuple[int, int] = (0, 0)  # position within viewport
    mode: str = "walk"                   # walk | bike | surf | menu | battle | dialog | cutscene


@dataclass
class Viewport:
    """Visible area of the game world."""
    size: tuple[int, int] = (15, 11)     # width, height in tiles
    origin: tuple[int, int] = (0, 0)     # global coord of top-left tile


@dataclass
class Actor:
    """Dynamic NPC or entity in the world."""
    id: str
    kind: str = "u"                      # see symbols.ACTOR_EMOJI keys
    pos: tuple[int, int] = (0, 0)
    facing: str = "S"
    blocks_movement: bool = True
    mobility: str = "static"             # static | wanders | patrol | scripted
    confidence: float = 0.5
    last_seen_tick: int = 0
    symbol: str = ""  # overridden kind char


@dataclass
class MovementEdge:
    """Directed movement edge from a tile in a direction."""
    from_pos: tuple[int, int]
    direction: str                       # N | E | S | W
    outcome: str                         # open | blocked | one_way_ledge | warp | npc_block | water_edge
    reason: str = ""
    tick: int = 0


@dataclass
class WorldState:
    """Canonical world state across all layers."""

    tick: int = 0
    map_id: str = "unknown"

    # Player
    player: PlayerState = field(default_factory=PlayerState)

    # Viewport
    viewport: Viewport = field(default_factory=Viewport)

    # Lighting
    lighting: str = "normal"             # normal | dark | flash | indoor | cave
    visibility_radius: int = 0           # 0 = unlimited, >0 = dark/cave

    # Layers (grids as 2D lists of single-char strings)
    terrain: list[list[str]] = field(default_factory=list)
    objects: list[list[str]] = field(default_factory=list)
    visited: list[list[str]] = field(default_factory=list)

    # Dynamic
    actors: dict[str, Actor] = field(default_factory=dict)
    edges: dict[tuple[tuple[int, int], str], MovementEdge] = field(default_factory=dict)

    # Last input
    last_button: str = ""
    last_result: str = "unknown"         # moved | blocked | turned_only | dialog | warp | battle | unknown

    def init_blank(self, width: int, height: int) -> None:
        """Initialise all grids to unknown (?)."""
        self.terrain = [["?" for _ in range(width)] for _ in range(height)]
        self.objects = [[" " for _ in range(width)] for _ in range(height)]
        self.visited = [["?" for _ in range(width)] for _ in range(height)]

    # ── Grid helpers ────────────────────────────────────────────────────

    def terrain_at(self, x: int, y: int) -> str:
        if 0 <= y < len(self.terrain) and 0 <= x < len(self.terrain[0]):
            return self.terrain[y][x]
        return "?"

    def set_terrain(self, x: int, y: int, char: str) -> None:
        if 0 <= y < len(self.terrain) and 0 <= x < len(self.terrain[0]):
            self.terrain[y][x] = char

    def object_at(self, x: int, y: int) -> str:
        if 0 <= y < len(self.objects) and 0 <= x < len(self.objects[0]):
            return self.objects[y][x]
        return " "

    def actor_at(self, x: int, y: int) -> Actor | None:
        for a in self.actors.values():
            if a.pos == (x, y):
                return a
        return None

    def edge_at(self, x: int, y: int, direction: str) -> MovementEdge | None:
        return self.edges.get(((x, y), direction))

    def set_edge(self, x: int, y: int, direction: str, outcome: str, reason: str = "", tick: int = 0) -> None:
        self.edges[((x, y), direction)] = MovementEdge(
            from_pos=(x, y), direction=direction,
            outcome=outcome, reason=reason, tick=tick or self.tick,
        )

    # ── Composed view ───────────────────────────────────────────────────

    def composed_view(self, *, use_ascii: bool = True) -> str:
        """Render a composed grid combining terrain, objects, actors, and player.

        Args:
            use_ascii: If True, render compact ASCII for the controller LLM.
                       If False, render emoji-rich for debugging.
        """
        vp = self.viewport
        rows: list[str] = []

        for vy in range(vp.size[1]):
            global_y = vp.origin[1] + vy
            row_chars: list[str] = []
            for vx in range(vp.size[0]):
                global_x = vp.origin[0] + vx

                # Player?
                if (global_x, global_y) == self.player.pos:
                    if use_ascii:
                        row_chars.append(facing_ascii(self.player.facing))
                    else:
                        from .symbols import facing_emoji
                        row_chars.append(facing_emoji(self.player.facing))
                    continue

                # Actor?
                actor = self.actor_at(global_x, global_y)
                if actor:
                    row_chars.append(
                        actor_to_ascii(actor.kind) if use_ascii
                        else actor.symbol or actor_to_ascii(actor.kind)
                    )
                    continue

                # Object?
                obj = self.object_at(global_x, global_y)
                if obj and obj != " ":
                    row_chars.append(
                        object_to_ascii(obj) if use_ascii else obj
                    )
                    continue

                # Terrain
                ter = self.terrain_at(global_x, global_y)
                if use_ascii:
                    row_chars.append(terrain_to_ascii(ter))
                else:
                    from .symbols import terrain_to_emoji
                    row_chars.append(terrain_to_emoji(ter))

            rows.append("".join(row_chars))

        return "\n".join(rows)

    def composed_view_compact(self) -> str:
        """Return a ~300-token summary for injection into the controller prompt."""
        edges_n = self.edge_at(self.player.pos[0], self.player.pos[1], "N")
        edges_s = self.edge_at(self.player.pos[0], self.player.pos[1], "S")
        edges_e = self.edge_at(self.player.pos[0], self.player.pos[1], "E")
        edges_w = self.edge_at(self.player.pos[0], self.player.pos[1], "W")

        lines = [
            f"MAP: {self.map_id}  POS: {self.player.pos}  FACING: {self.player.facing}",
            f"MODE: {self.player.mode}  LIGHT: {self.lighting}  TICK: {self.tick}",
            "",
            "LOCAL MAP:",
            self.composed_view(),
            "",
            "MOVEMENT EDGES from current position:",
            f"  N: {edges_n.outcome if edges_n else 'unknown'}{' (' + edges_n.reason + ')' if edges_n and edges_n.reason else ''}",
            f"  S: {edges_s.outcome if edges_s else 'unknown'}{' (' + edges_s.reason + ')' if edges_s and edges_s.reason else ''}",
            f"  E: {edges_e.outcome if edges_e else 'unknown'}{' (' + edges_e.reason + ')' if edges_e and edges_e.reason else ''}",
            f"  W: {edges_w.outcome if edges_w else 'unknown'}{' (' + edges_w.reason + ')' if edges_w and edges_w.reason else ''}",
        ]

        # Actors in viewport
        vp = self.viewport
        visible_actors = [
            a for a in self.actors.values()
            if vp.origin[0] <= a.pos[0] < vp.origin[0] + vp.size[0]
            and vp.origin[1] <= a.pos[1] < vp.origin[1] + vp.size[1]
        ]
        if visible_actors:
            lines.append("")
            lines.append("VISIBLE ACTORS:")
            for a in visible_actors:
                rel_x = a.pos[0] - vp.origin[0]
                rel_y = a.pos[1] - vp.origin[1]
                lines.append(
                    f"  {actor_to_ascii(a.kind)} at [{rel_x},{rel_y}] "
                    f"facing {a.facing} ({a.kind}, conf={a.confidence:.0%})"
                )

        return "\n".join(lines)

    # ── File I/O ────────────────────────────────────────────────────────

    def save(self, directory: Path) -> None:
        """Persist all layers to *directory*."""
        directory.mkdir(parents=True, exist_ok=True)

        # state.yaml
        state = {
            "tick": self.tick,
            "map_id": self.map_id,
            "player": {
                "pos": list(self.player.pos),
                "facing": self.player.facing,
                "screen_pos": list(self.player.screen_pos),
                "mode": self.player.mode,
            },
            "viewport": {
                "size": list(self.viewport.size),
                "origin": list(self.viewport.origin),
            },
            "lighting": self.lighting,
            "visibility_radius": self.visibility_radius,
            "last_button": self.last_button,
            "last_result": self.last_result,
        }
        (directory / "state.yaml").write_text(yaml.dump(state, default_flow_style=False))

        # terrain.map
        (directory / "terrain.map").write_text(
            "\n".join("".join(row) for row in self.terrain)
        )

        # objects.map
        (directory / "objects.map").write_text(
            "\n".join("".join(row) for row in self.objects)
        )

        # visited.map
        (directory / "visited.map").write_text(
            "\n".join("".join(row) for row in self.visited)
        )

        # actors.yaml
        actors_data = {
            aid: {
                "kind": a.kind,
                "pos": list(a.pos),
                "facing": a.facing,
                "blocks_movement": a.blocks_movement,
                "mobility": a.mobility,
                "confidence": a.confidence,
                "last_seen_tick": a.last_seen_tick,
                "symbol": a.symbol,
            }
            for aid, a in self.actors.items()
        }
        (directory / "actors.yaml").write_text(yaml.dump(actors_data, default_flow_style=False))

        # movement_edges.yaml
        edges_data = [
            {
                "from": list(e.from_pos),
                "dir": e.direction,
                "outcome": e.outcome,
                "reason": e.reason,
                "tick": e.tick,
            }
            for e in self.edges.values()
        ]
        (directory / "movement_edges.yaml").write_text(yaml.dump(edges_data, default_flow_style=False))

    @classmethod
    def load(cls, directory: Path) -> "WorldState":
        """Load all layers from *directory*."""
        ws = cls()

        # state.yaml
        state_path = directory / "state.yaml"
        if state_path.exists():
            state = yaml.safe_load(state_path.read_text()) or {}
            ws.tick = state.get("tick", 0)
            ws.map_id = state.get("map_id", "unknown")
            p = state.get("player", {})
            ws.player = PlayerState(
                pos=tuple(p.get("pos", [0, 0])),
                facing=p.get("facing", "S"),
                screen_pos=tuple(p.get("screen_pos", [0, 0])),
                mode=p.get("mode", "walk"),
            )
            v = state.get("viewport", {})
            ws.viewport = Viewport(
                size=tuple(v.get("size", [15, 11])),
                origin=tuple(v.get("origin", [0, 0])),
            )
            ws.lighting = state.get("lighting", "normal")
            ws.visibility_radius = state.get("visibility_radius", 0)
            ws.last_button = state.get("last_button", "")
            ws.last_result = state.get("last_result", "unknown")

        # terrain.map
        terrain_path = directory / "terrain.map"
        if terrain_path.exists():
            ws.terrain = [list(line.rstrip("\n")) for line in terrain_path.read_text().splitlines()]

        # objects.map
        objects_path = directory / "objects.map"
        if objects_path.exists():
            ws.objects = [list(line.rstrip("\n")) for line in objects_path.read_text().splitlines()]

        # visited.map
        visited_path = directory / "visited.map"
        if visited_path.exists():
            ws.visited = [list(line.rstrip("\n")) for line in visited_path.read_text().splitlines()]

        # actors.yaml
        actors_path = directory / "actors.yaml"
        if actors_path.exists():
            actors_data = yaml.safe_load(actors_path.read_text()) or {}
            for aid, adata in actors_data.items():
                ws.actors[aid] = Actor(
                    id=aid,
                    kind=adata.get("kind", "u"),
                    pos=tuple(adata.get("pos", [0, 0])),
                    facing=adata.get("facing", "S"),
                    blocks_movement=adata.get("blocks_movement", True),
                    mobility=adata.get("mobility", "static"),
                    confidence=adata.get("confidence", 0.5),
                    last_seen_tick=adata.get("last_seen_tick", 0),
                    symbol=adata.get("symbol", ""),
                )

        # movement_edges.yaml
        edges_path = directory / "movement_edges.yaml"
        if edges_path.exists():
            edges_data = yaml.safe_load(edges_path.read_text()) or []
            for edata in edges_data:
                from_pos = tuple(edata["from"])
                direction = edata["dir"]
                ws.edges[(from_pos, direction)] = MovementEdge(
                    from_pos=from_pos,
                    direction=direction,
                    outcome=edata.get("outcome", "unknown"),
                    reason=edata.get("reason", ""),
                    tick=edata.get("tick", 0),
                )

        return ws
