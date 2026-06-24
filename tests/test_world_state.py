"""
Unit tests for the world-state modules.

Tests cover:
- Symbols: terrain/object/actor/facing/mode/edge/visited translations (emoji and ASCII)
- WorldState: init_blank, set_terrain, composed_view rendering, composed_view_compact, save/load
- OBS_PATCH: parse (moved, blocked, resync, correction), validate_patch rejection rules
- MapIntegrator: apply success/rejection, compose_for_controller, stats, save
"""

import pytest
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from src.core.symbols import (
    terrain_to_emoji,
    terrain_to_ascii,
    object_to_emoji,
    object_to_ascii,
    actor_to_emoji,
    actor_to_ascii,
    facing_emoji,
    facing_ascii,
    mode_emoji,
    edge_emoji,
    visited_emoji,
    visited_ascii,
    describe_tile,
    SYMBOL_REFERENCE,
    TERRAIN_EMOJI,
    TERRAIN_ASCII,
    OBJECT_EMOJI,
    OBJECT_ASCII,
    ACTOR_EMOJI,
    ACTOR_ASCII,
    PLAYER_FACING_EMOJI,
    PLAYER_FACING_ASCII,
    MODE_EMOJI,
    EDGE_OUTCOME_EMOJI,
    VISITED_EMOJI,
    VISITED_ASCII,
)
from src.core.world_state import (
    WorldState,
    PlayerState,
    Viewport,
    Actor,
    MovementEdge,
)
from src.core.obs_patch import (
    ObsPatch,
    parse_obs_patch,
    validate_patch,
    Movement,
    ViewportDelta,
    StripUpdate,
    EdgeUpdate,
    ActorUpdate,
    Correction,
    Resync,
)
from src.core.map_integrator import MapIntegrator


# ═════════════════════════════════════════════════════════════════════════════
# Symbols tests
# ═════════════════════════════════════════════════════════════════════════════


class TestTerrainEmojiTranslation:
    """Tests for terrain_to_emoji and terrain_to_ascii."""

    def test_known_terrain_emoji(self) -> None:
        """Each known terrain char maps to its emoji."""
        assert terrain_to_emoji(".") == "⬜"    # walkable floor
        assert terrain_to_emoji("g") == "🌿"    # tall grass
        assert terrain_to_emoji("T") == "🌲"    # tree
        assert terrain_to_emoji("#") == "🧱"    # wall
        assert terrain_to_emoji("~") == "🌊"    # water
        assert terrain_to_emoji("d") == "🚪"    # door

    def test_unknown_terrain_emoji(self) -> None:
        """Unknown terrain chars fall back to ❓."""
        assert terrain_to_emoji("Z") == "❓"
        assert terrain_to_emoji("") == "❓"
        assert terrain_to_emoji("🐛") == "❓"

    def test_known_terrain_ascii(self) -> None:
        """Each known terrain char maps to its ASCII char."""
        assert terrain_to_ascii(".") == "."
        assert terrain_to_ascii("g") == "g"
        assert terrain_to_ascii("T") == "T"
        assert terrain_to_ascii("#") == "#"
        assert terrain_to_ascii("~") == "~"
        assert terrain_to_ascii("d") == "D"

    def test_unknown_terrain_ascii(self) -> None:
        """Unknown terrain chars are passed through as-is."""
        assert terrain_to_ascii("Z") == "Z"
        assert terrain_to_ascii("") == ""

    def test_all_terrain_keys_consistent(self) -> None:
        """TERRAIN_EMOJI and TERRAIN_ASCII share the same keys."""
        for k in TERRAIN_EMOJI:
            assert k in TERRAIN_ASCII, f"Key '{k}' missing from TERRAIN_ASCII"


class TestObjectEmojiTranslation:
    """Tests for object_to_emoji and object_to_ascii."""

    def test_known_object_emoji(self) -> None:
        """Known object chars map to emoji."""
        assert object_to_emoji("D") == "🚪"    # door
        assert object_to_emoji("S") == "🪧"    # sign
        assert object_to_emoji("I") == "💎"    # item

    def test_space_object_emoji(self) -> None:
        """Space returns double-width spacer for alignment."""
        assert object_to_emoji(" ") == "  "

    def test_unknown_object_emoji(self) -> None:
        """Unknown object chars fall back to ❓."""
        assert object_to_emoji("Z") == "❓"

    def test_known_object_ascii(self) -> None:
        """Known object chars map to ASCII."""
        assert object_to_ascii("D") == "D"
        assert object_to_ascii("I") == "I"
        assert object_to_ascii("X") == "X"     # cut tree

    def test_space_object_ascii(self) -> None:
        """Space returns regular space."""
        assert object_to_ascii(" ") == " "

    def test_unknown_object_ascii(self) -> None:
        """Unknown object chars are passed through."""
        assert object_to_ascii("Z") == "Z"


class TestActorEmojiTranslation:
    """Tests for actor_to_emoji and actor_to_ascii."""

    def test_known_actor_emoji(self) -> None:
        """Known actor kinds map to emoji."""
        assert actor_to_emoji("n") == "👩‍⚕️"     # nurse Joy
        assert actor_to_emoji("o") == "👮"       # officer Jenny
        assert actor_to_emoji("P") == "🧬"       # wild Pokémon

    def test_unknown_actor_emoji(self) -> None:
        """Unknown actor kinds fall back to 👤."""
        assert actor_to_emoji("zzz") == "👤"
        assert actor_to_emoji("") == "👤"

    def test_known_actor_ascii(self) -> None:
        """Known actor kinds map to compact ASCII."""
        assert actor_to_ascii("u") == "u"
        assert actor_to_ascii("n") == "N"
        assert actor_to_ascii("o") == "O"
        assert actor_to_ascii("m") == "M"
        assert actor_to_ascii("p") == "P"

    def test_unknown_actor_ascii_fallback(self) -> None:
        """Unknown actor kinds use first character as fallback."""
        assert actor_to_ascii("xyz") == "x"
        assert actor_to_ascii("") == "?"

    def test_all_actor_keys_consistent(self) -> None:
        """ACTOR_EMOJI and ACTOR_ASCII share the same keys."""
        for k in ACTOR_EMOJI:
            assert k in ACTOR_ASCII, f"Key '{k}' missing from ACTOR_ASCII"


class TestFacingTranslation:
    """Tests for facing_emoji and facing_ascii."""

    def test_facing_emoji_north(self) -> None:
        assert facing_emoji("N") == "⬆️"

    def test_facing_emoji_south(self) -> None:
        assert facing_emoji("S") == "⬇️"

    def test_facing_emoji_east(self) -> None:
        assert facing_emoji("E") == "➡️"

    def test_facing_emoji_west(self) -> None:
        assert facing_emoji("W") == "⬅️"

    def test_facing_emoji_unknown(self) -> None:
        assert facing_emoji("X") == "❓"

    def test_facing_ascii_all(self) -> None:
        """All facing directions have ASCII mappings."""
        assert facing_ascii("N") == "^"
        assert facing_ascii("S") == "v"
        assert facing_ascii("E") == ">"
        assert facing_ascii("W") == "<"

    def test_facing_ascii_unknown(self) -> None:
        assert facing_ascii("X") == "?"


class TestModeTranslation:
    """Tests for mode_emoji."""

    def test_known_modes(self) -> None:
        assert mode_emoji("walk") == "🚶"
        assert mode_emoji("bike") == "🚲"
        assert mode_emoji("surf") == "🏄"
        assert mode_emoji("menu") == "📋"
        assert mode_emoji("battle") == "⚔️"
        assert mode_emoji("dialog") == "💬"
        assert mode_emoji("cutscene") == "🎬"

    def test_unknown_mode(self) -> None:
        assert mode_emoji("flying") == "❓"
        assert mode_emoji("") == "❓"


class TestEdgeEmoji:
    """Tests for edge_emoji."""

    def test_known_outcomes(self) -> None:
        assert edge_emoji("open") == "✅"
        assert edge_emoji("blocked") == "🚫"
        assert edge_emoji("one_way_ledge") == "⏬"
        assert edge_emoji("warp") == "🚪"
        assert edge_emoji("npc_block") == "👤"
        assert edge_emoji("water_edge") == "🌊"

    def test_unknown_outcome(self) -> None:
        assert edge_emoji("magic") == "❓"


class TestVisitedTranslation:
    """Tests for visited_emoji and visited_ascii."""

    def test_visited_emoji_known(self) -> None:
        assert visited_emoji("?") == "⬛"
        assert visited_emoji(".") == "⬜"
        assert visited_emoji("+") == "👣"
        assert visited_emoji("@") == "🎯"

    def test_visited_emoji_unknown(self) -> None:
        assert visited_emoji("X") == "⬛"  # fallback to never seen

    def test_visited_ascii_known(self) -> None:
        assert visited_ascii("?") == "?"
        assert visited_ascii(".") == "."
        assert visited_ascii("+") == "+"
        assert visited_ascii("@") == "@"

    def test_visited_ascii_unknown(self) -> None:
        assert visited_ascii("X") == "?"


class TestDescribeTile:
    """Tests for describe_tile composite description."""

    def test_bare_terrain(self) -> None:
        result = describe_tile(".")
        assert "⬜" in result

    def test_terrain_with_object(self) -> None:
        result = describe_tile(".", obj="D")
        assert "⬜" in result
        assert "🚪" in result

    def test_terrain_with_actor(self) -> None:
        result = describe_tile(".", actor_kind="n")
        assert "⬜" in result
        assert "👩‍⚕️" in result

    def test_terrain_object_and_actor(self) -> None:
        result = describe_tile("~", obj="I", actor_kind="s")
        assert "🌊" in result   # water
        assert "💎" in result   # item
        assert "🏊" in result   # swimmer

    def test_space_object_skipped(self) -> None:
        result = describe_tile(".", obj=" ")
        assert "  " not in result  # no double-space injection
        assert "⬜" in result


class TestSymbolReference:
    """Tests for the SYMBOL_REFERENCE prompt string."""

    def test_contains_terrain_symbols(self) -> None:
        assert "g = 🌿 tall grass" in SYMBOL_REFERENCE
        assert "# = 🧱 wall" in SYMBOL_REFERENCE

    def test_contains_object_symbols(self) -> None:
        assert "D = 🚪 door" in SYMBOL_REFERENCE
        assert "I = 💎 item" in SYMBOL_REFERENCE

    def test_contains_actor_kinds(self) -> None:
        assert "n = 👩‍⚕️ nurse" in SYMBOL_REFERENCE
        assert "P = 🧬 wild" in SYMBOL_REFERENCE


# ═════════════════════════════════════════════════════════════════════════════
# WorldState tests
# ═════════════════════════════════════════════════════════════════════════════


class TestWorldStateInitBlank:
    """Tests for WorldState.init_blank."""

    def test_creates_terrain_grid(self) -> None:
        ws = WorldState()
        ws.init_blank(5, 3)
        assert len(ws.terrain) == 3          # height (rows)
        assert len(ws.terrain[0]) == 5       # width (cols)
        assert all(ch == "?" for row in ws.terrain for ch in row)

    def test_creates_objects_grid(self) -> None:
        ws = WorldState()
        ws.init_blank(4, 4)
        assert len(ws.objects) == 4
        assert all(ch == " " for row in ws.objects for ch in row)

    def test_creates_visited_grid(self) -> None:
        ws = WorldState()
        ws.init_blank(3, 7)
        assert len(ws.visited) == 7
        assert all(ch == "?" for row in ws.visited for ch in row)


class TestWorldStateGridAccess:
    """Tests for terrain_at, set_terrain, object_at, actor_at, edge_at."""

    def test_set_and_get_terrain(self) -> None:
        ws = WorldState()
        ws.init_blank(10, 10)
        ws.set_terrain(3, 5, "g")
        assert ws.terrain_at(3, 5) == "g"

    def test_terrain_at_oob(self) -> None:
        ws = WorldState()
        ws.init_blank(5, 5)
        assert ws.terrain_at(999, 0) == "?"
        assert ws.terrain_at(-1, 2) == "?"

    def test_set_terrain_oob_silent(self) -> None:
        ws = WorldState()
        ws.init_blank(2, 2)
        ws.set_terrain(100, 100, "T")
        # Should not raise, just silently ignore
        assert ws.terrain_at(0, 0) == "?"

    def test_object_at_empty(self) -> None:
        ws = WorldState()
        ws.init_blank(5, 5)
        assert ws.object_at(2, 2) == " "

    def test_actor_at_found(self) -> None:
        ws = WorldState()
        ws.init_blank(10, 10)
        ws.actors["npc1"] = Actor(id="npc1", kind="t", pos=(2, 3))
        actor = ws.actor_at(2, 3)
        assert actor is not None
        assert actor.kind == "t"

    def test_actor_at_not_found(self) -> None:
        ws = WorldState()
        ws.init_blank(10, 10)
        assert ws.actor_at(5, 5) is None

    def test_edge_at_missing(self) -> None:
        ws = WorldState()
        assert ws.edge_at(0, 0, "N") is None

    def test_set_and_get_edge(self) -> None:
        ws = WorldState()
        ws.tick = 42
        ws.set_edge(1, 2, "N", "blocked", "tree")
        e = ws.edge_at(1, 2, "N")
        assert e is not None
        assert e.outcome == "blocked"
        assert e.reason == "tree"
        assert e.tick == 42


class TestPlayerStateDefaults:
    """Default values for PlayerState."""

    def test_defaults(self) -> None:
        p = PlayerState()
        assert p.pos == (0, 0)
        assert p.facing == "S"
        assert p.screen_pos == (0, 0)
        assert p.mode == "walk"


class TestViewportDefaults:
    """Default values for Viewport."""

    def test_defaults(self) -> None:
        vp = Viewport()
        assert vp.size == (15, 11)
        assert vp.origin == (0, 0)


class TestActorDefaults:
    """Default values for Actor."""

    def test_defaults(self) -> None:
        a = Actor(id="test")
        assert a.kind == "u"
        assert a.confidence == 0.5
        assert a.blocks_movement is True
        assert a.mobility == "static"


class TestMovementEdgeDefaults:
    """Default values for MovementEdge."""

    def test_defaults(self) -> None:
        e = MovementEdge(from_pos=(0, 0), direction="N", outcome="open")
        assert e.from_pos == (0, 0)
        assert e.direction == "N"
        assert e.outcome == "open"
        assert e.reason == ""
        assert e.tick == 0


class TestComposedView:
    """Tests for WorldState.composed_view rendering."""

    def test_basic_ascii_view(self) -> None:
        ws = WorldState()
        ws.init_blank(15, 11)
        ws.viewport = Viewport(size=(5, 3), origin=(0, 0))
        # Set some terrain
        ws.set_terrain(0, 0, ".")
        ws.set_terrain(1, 0, "g")
        ws.set_terrain(2, 0, "#")
        ws.player.pos = (0, 1)
        ws.player.facing = "E"

        view = ws.composed_view(use_ascii=True)
        lines = view.split("\n")
        assert len(lines) == 3  # height=3
        assert len(lines[0]) == 5  # width=5
        # Row 0: terrain chars
        assert lines[0][0] == "."     # floor
        assert lines[0][1] == "g"    # grass
        assert lines[0][2] == "#"    # wall
        # Row 1: player at (0,1)
        assert lines[1][0] == ">"     # facing East → ASCII >
        # Row 2: unknown
        assert lines[2][0] == "?"

    def test_emoji_view(self) -> None:
        ws = WorldState()
        ws.init_blank(3, 3)
        ws.viewport = Viewport(size=(3, 3), origin=(0, 0))
        ws.set_terrain(0, 0, ".")
        ws.set_terrain(1, 0, "T")
        ws.player.pos = (2, 0)
        ws.player.facing = "S"

        view = ws.composed_view(use_ascii=False)
        lines = view.split("\n")
        # Row 0: floor emoji, tree emoji, player facing south emoji
        assert "⬜" in lines[0]
        assert "🌲" in lines[0]
        assert "⬇️" in lines[0]

    def test_actor_rendered_in_ascii_view(self) -> None:
        ws = WorldState()
        ws.init_blank(5, 3)
        ws.viewport = Viewport(size=(5, 3), origin=(0, 0))
        ws.actors["npc"] = Actor(id="npc", kind="n", pos=(2, 1))
        ws.player.pos = (0, 0)
        ws.player.facing = "S"

        view = ws.composed_view(use_ascii=True)
        lines = view.split("\n")
        assert lines[1][2] == "N"  # nurse → N in ASCII

    def test_object_rendered_in_ascii_view(self) -> None:
        ws = WorldState()
        ws.init_blank(5, 3)
        ws.viewport = Viewport(size=(5, 3), origin=(0, 0))
        ws.objects[1][3] = "D"  # door at (3,1)
        ws.player.pos = (0, 0)
        ws.player.facing = "S"

        view = ws.composed_view(use_ascii=True)
        lines = view.split("\n")
        assert lines[1][3] == "D"

    def test_player_has_priority_over_all(self) -> None:
        """Player renders even if on same tile as actor or object."""
        ws = WorldState()
        ws.init_blank(3, 3)
        ws.viewport = Viewport(size=(3, 3), origin=(0, 0))
        ws.objects[1][1] = "I"
        ws.actors["npc"] = Actor(id="npc", kind="t", pos=(1, 1))
        ws.player.pos = (1, 1)
        ws.player.facing = "N"

        view = ws.composed_view(use_ascii=True)
        lines = view.split("\n")
        # Player should render as "^" (facing North), not "I" or "t"
        assert lines[1][1] == "^"


class TestComposedViewCompact:
    """Tests for WorldState.composed_view_compact."""

    def test_output_contains_header(self) -> None:
        ws = WorldState()
        ws.init_blank(5, 5)
        ws.viewport = Viewport(size=(5, 5), origin=(0, 0))
        ws.map_id = "pallet_town"
        ws.player.pos = (2, 2)
        ws.player.facing = "S"

        text = ws.composed_view_compact()
        assert "MAP: pallet_town" in text
        assert "POS:" in text
        assert "FACING: S" in text
        assert "MODE: walk" in text
        assert "LOCAL MAP:" in text

    def test_output_contains_nsew_edges(self) -> None:
        ws = WorldState()
        ws.init_blank(5, 5)
        ws.viewport = Viewport(size=(5, 5), origin=(0, 0))
        ws.player.pos = (2, 2)
        ws.set_edge(2, 2, "N", "blocked", "wall")
        ws.set_edge(2, 2, "S", "open")

        text = ws.composed_view_compact()
        assert "N: blocked (wall)" in text
        assert "S: open" in text
        assert "E: unknown" in text
        assert "W: unknown" in text

    def test_visible_actors_in_viewport(self) -> None:
        ws = WorldState()
        ws.init_blank(10, 10)
        ws.viewport = Viewport(size=(5, 5), origin=(0, 0))
        ws.player.pos = (0, 0)
        ws.actors["npc1"] = Actor(id="npc1", kind="t", pos=(2, 1), confidence=0.9)

        text = ws.composed_view_compact()
        assert "VISIBLE ACTORS:" in text
        assert "t at [2,1]" in text
        assert "conf=90%" in text

    def test_actors_outside_viewport_not_shown(self) -> None:
        ws = WorldState()
        ws.init_blank(10, 10)
        ws.viewport = Viewport(size=(5, 5), origin=(0, 0))
        ws.player.pos = (0, 0)
        ws.actors["far_away"] = Actor(id="far", kind="c", pos=(99, 99))

        text = ws.composed_view_compact()
        assert "far_away" not in text
        assert "VISIBLE ACTORS:" not in text


class TestWorldStateSaveLoad:
    """Tests for WorldState.save and WorldState.load roundtrip."""

    def test_save_and_load_roundtrip(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        ws = WorldState()
        ws.tick = 42
        ws.map_id = "route1"
        ws.init_blank(4, 3)
        ws.set_terrain(1, 1, "g")
        ws.player = PlayerState(pos=(1, 1), facing="N", screen_pos=(4, 4), mode="walk")
        ws.viewport = Viewport(size=(15, 11), origin=(0, 0))
        ws.lighting = "indoor"
        ws.visibility_radius = 3
        ws.actors["guy"] = Actor(id="guy", kind="t", pos=(2, 1), confidence=0.8,
                                  last_seen_tick=30)
        ws.set_edge(1, 1, "N", "blocked", "tree")
        ws.last_button = "UP"
        ws.last_result = "blocked"

        d = tmp_path / "world"
        ws.save(d)

        assert (d / "state.yaml").exists()
        assert (d / "terrain.map").exists()
        assert (d / "objects.map").exists()
        assert (d / "visited.map").exists()
        assert (d / "actors.yaml").exists()
        assert (d / "movement_edges.yaml").exists()

        loaded = WorldState.load(d)
        assert loaded.tick == 42
        assert loaded.map_id == "route1"
        assert loaded.player.pos == (1, 1)
        assert loaded.player.facing == "N"
        assert loaded.lighting == "indoor"
        assert loaded.visibility_radius == 3
        assert loaded.last_button == "UP"
        assert loaded.last_result == "blocked"
        assert loaded.terrain_at(1, 1) == "g"
        assert "guy" in loaded.actors
        assert loaded.actors["guy"].kind == "t"
        assert loaded.actors["guy"].confidence == 0.8
        e = loaded.edge_at(1, 1, "N")
        assert e is not None
        assert e.outcome == "blocked"

    def test_load_empty_directory(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        d = tmp_path / "empty"
        d.mkdir()
        ws = WorldState.load(d)
        assert ws.tick == 0
        assert ws.map_id == "unknown"
        assert ws.terrain == []


# ═════════════════════════════════════════════════════════════════════════════
# OBS_PATCH parse tests
# ═════════════════════════════════════════════════════════════════════════════


class TestParseObsPatchMovement:
    """parse_obs_patch with movement result: moved."""

    def test_moved_patch(self) -> None:
        data = {
            "tick": 10,
            "prev_tick": 9,
            "movement": {
                "input": "UP",
                "result": "moved",
                "player_delta": [0, -1],
                "facing": "N",
                "mode": "walk",
            },
            "viewport": {"origin_delta": [0, -1], "new_edge": "N"},
            "strip": {
                "edge": "N",
                "global_y": 0,
                "x_start": 0,
                "terrain": ".....",
                "objects": "     ",
            },
            "visited": [{"add": [[0, 0], [1, 0]]}],
        }
        patch = parse_obs_patch(data)
        assert patch.tick == 10
        assert patch.prev_tick == 9
        assert patch.movement is not None
        assert patch.movement.result == "moved"
        assert patch.movement.player_delta == [0, -1]
        assert patch.viewport is not None
        assert patch.viewport.origin_delta == [0, -1]
        assert patch.strip is not None
        assert patch.strip.terrain == "....."

    def test_moved_patch_from_yaml_string(self) -> None:
        yaml_str = """\
tick: 5
prev_tick: 4
movement:
  input: RIGHT
  result: moved
  player_delta: [1, 0]
  facing: E
  mode: walk
"""
        patch = parse_obs_patch(yaml_str)
        assert patch.tick == 5
        assert patch.movement.result == "moved"  # type: ignore[union-attr]
        assert patch.movement.player_delta == [1, 0]  # type: ignore[union-attr]
class TestParseObsPatchBlocked:
    """parse_obs_patch with movement result: blocked."""

    def test_blocked_patch(self) -> None:
        data = {
            "tick": 20,
            "movement": {
                "input": "UP",
                "result": "blocked",
                "player_delta": [0, 0],
                "facing": "N",
            },
            "edges": [
                {"from": [5, 10], "dir": "N", "outcome": "blocked", "reason": "tree"},
            ],
        }
        patch = parse_obs_patch(data)
        assert patch.movement.result == "blocked"  # type: ignore[union-attr]
        assert len(patch.edges) == 1
        assert patch.edges[0].outcome == "blocked"
        assert patch.edges[0].reason == "tree"

    def test_blocked_patch_with_various_edge_keys(self) -> None:
        data = {
            "tick": 30,
            "movement": {"input": "LEFT", "result": "blocked"},
            "edges": [
                {"from_pos": [3, 4], "direction": "W", "outcome": "npc_block"},
            ],
        }
        patch = parse_obs_patch(data)
        assert len(patch.edges) == 1
        assert patch.edges[0].dir == "W"
        assert patch.edges[0].outcome == "npc_block"


class TestParseObsPatchResync:
    """parse_obs_patch with resync section."""

    def test_resync_patch(self) -> None:
        data = {
            "tick": 100,
            "resync": {
                "reason": "warp",
                "new_map_id": "pokecenter_1f",
                "viewport_origin": [0, 0],
                "player_pos": [7, 4],
                "player_facing": "S",
                "full_viewport": {
                    "terrain": ["......", "......"],
                    "objects": ["      ", "      "],
                },
            },
        }
        patch = parse_obs_patch(data)
        assert patch.resync is not None
        assert patch.resync.reason == "warp"
        assert patch.resync.new_map_id == "pokecenter_1f"
        assert patch.resync.player_pos == [7, 4]
        assert "terrain" in patch.resync.full_viewport


class TestParseObsPatchCorrection:
    """parse_obs_patch with corrections."""

    def test_correction_patch(self) -> None:
        data = {
            "tick": 50,
            "movement": {"input": "DOWN", "result": "moved", "player_delta": [0, 1]},
            "corrections": [
                {
                    "layer": "terrain",
                    "at": [3, 2],
                    "from": "?",
                    "to": ".",
                    "confidence": 0.9,
                    "reason": "re-evaluated tile",
                },
            ],
        }
        patch = parse_obs_patch(data)
        assert len(patch.corrections) == 1
        c = patch.corrections[0]
        assert c.layer == "terrain"
        assert c.at == [3, 2]
        assert c.to_char == "."


class TestParseObsPatchActorUpdates:
    """parse_obs_patch with actor_updates."""

    def test_actor_updates(self) -> None:
        data = {
            "tick": 5,
            "movement": {"input": "A", "result": "moved"},
            "actor_updates": [
                {"id": "npc_1", "kind": "n", "pos": [3, 4], "facing": "W", "confidence": 0.8},
            ],
        }
        patch = parse_obs_patch(data)
        assert len(patch.actor_updates) == 1
        a = patch.actor_updates[0]
        assert a.id == "npc_1"
        assert a.kind == "n"
        assert a.pos == [3, 4]

    def test_actor_updates_via_actors_key(self) -> None:
        data = {
            "tick": 6,
            "movement": {"input": "B", "result": "moved"},
            "actors": [
                {"id": "npc_2", "kind": "t", "pos": [1, 1]},
            ],
        }
        patch = parse_obs_patch(data)
        assert len(patch.actor_updates) == 1
        assert patch.actor_updates[0].kind == "t"


class TestParseObsPatchErrors:
    """parse_obs_patch error/edge cases."""

    def test_bad_string_returns_error(self) -> None:
        patch = parse_obs_patch("not valid yaml::: {{{")
        assert "_errors" in patch.raw
        assert len(patch.raw["_errors"]) > 0

    def test_non_dict_after_parse(self) -> None:
        patch = parse_obs_patch("[1, 2, 3]")
        assert "_errors" in patch.raw
        assert "not a dict" in patch.raw["_errors"][0]

    def test_empty_dict(self) -> None:
        patch = parse_obs_patch({})
        assert patch.tick == 0
        assert patch.movement is None
        assert patch.strip is None

    def test_visited_as_list(self) -> None:
        data = {
            "tick": 1,
            "movement": {"input": "UP", "result": "moved"},
            "visited": [[0, 0], [1, 0]],
        }
        patch = parse_obs_patch(data)
        assert patch.visited_add == [[0, 0], [1, 0]]

    def test_visited_as_dict(self) -> None:
        data = {
            "tick": 1,
            "movement": {"input": "UP", "result": "moved"},
            "visited": {"add": [[2, 2]]},
        }
        patch = parse_obs_patch(data)
        assert patch.visited_add == [[2, 2]]

    def test_visited_via_visited_add_key(self) -> None:
        data = {
            "tick": 2,
            "movement": {"input": "RIGHT", "result": "moved"},
            "visited_add": [[3, 3]],
        }
        patch = parse_obs_patch(data)
        assert patch.visited_add == [[3, 3]]


class TestObsPatchDataclassDefaults:
    """ObsPatch and sub-dataclasses default values."""

    def test_obs_patch_defaults(self) -> None:
        p = ObsPatch()
        assert p.tick == 0
        assert p.movement is None
        assert p.viewport is None
        assert p.strip is None
        assert p.visited_add == []
        assert p.edges == []
        assert p.actor_updates == []
        assert p.corrections == []

    def test_movement_defaults(self) -> None:
        m = Movement()
        assert m.result == "unknown"
        assert m.player_delta == [0, 0]

    def test_strip_update_defaults(self) -> None:
        s = StripUpdate(edge="N")
        assert s.edge == "N"
        assert s.terrain == ""

    def test_resync_defaults(self) -> None:
        r = Resync()
        assert r.reason == ""
        assert r.full_viewport == {}


# ═════════════════════════════════════════════════════════════════════════════
# validate_patch tests
# ═════════════════════════════════════════════════════════════════════════════


class TestValidatePatch:
    """Tests for validate_patch rejection rules."""

    def test_valid_moved_patch(self) -> None:
        patch = ObsPatch(
            tick=10,
            movement=Movement(input="UP", result="moved", player_delta=[0, -1]),
        )
        errors = validate_patch(patch)
        assert errors == []

    def test_resync_skips_validation(self) -> None:
        """Resync patches skip all normal validation."""
        patch = ObsPatch(
            tick=100,
            resync=Resync(reason="warp"),
            # Missing movement, but resync bypasses
        )
        errors = validate_patch(patch)
        assert errors == []

    def test_missing_movement(self) -> None:
        """Non-resync patches must have a movement section."""
        patch = ObsPatch(tick=1)
        errors = validate_patch(patch)
        assert any("Missing 'movement'" in e for e in errors)

    def test_moved_more_than_one_tile(self) -> None:
        patch = ObsPatch(
            tick=5,
            movement=Movement(input="UP", result="moved", player_delta=[0, -3]),
        )
        errors = validate_patch(patch)
        assert any("more than 1 tile" in e for e in errors)

    def test_moved_viewport_scroll_no_strip(self) -> None:
        patch = ObsPatch(
            tick=5,
            movement=Movement(input="UP", result="moved", player_delta=[0, -1]),
            viewport=ViewportDelta(new_edge="N"),
            strip=None,
        )
        errors = validate_patch(patch)
        assert any("no 'strip'" in e for e in errors)

    def test_moved_viewport_scroll_strip_no_terrain(self) -> None:
        patch = ObsPatch(
            tick=5,
            movement=Movement(input="UP", result="moved", player_delta=[0, -1]),
            viewport=ViewportDelta(new_edge="N"),
            strip=StripUpdate(edge="N", terrain=""),
        )
        errors = validate_patch(patch)
        assert any("no terrain data" in e for e in errors)

    def test_strip_terrain_too_long(self) -> None:
        patch = ObsPatch(
            tick=5,
            movement=Movement(input="UP", result="moved", player_delta=[0, -1]),
            strip=StripUpdate(edge="N", terrain="x" * 31),
        )
        errors = validate_patch(patch)
        assert any("too long" in e for e in errors)

    def test_blocked_should_not_shift_viewport(self) -> None:
        patch = ObsPatch(
            tick=10,
            movement=Movement(input="UP", result="blocked"),
            viewport=ViewportDelta(origin_delta=[1, 0]),
        )
        errors = validate_patch(patch)
        assert any("should not shift viewport" in e for e in errors)

    def test_blocked_should_record_edges(self) -> None:
        patch = ObsPatch(
            tick=10,
            movement=Movement(input="UP", result="blocked"),
            edges=[],
        )
        errors = validate_patch(patch)
        assert any("should record at least one blocked edge" in e for e in errors)

    def test_turned_only_delta_must_be_zero(self) -> None:
        patch = ObsPatch(
            tick=10,
            movement=Movement(input="LEFT", result="turned_only", player_delta=[1, 0]),
        )
        errors = validate_patch(patch)
        assert any("turned_only" in e for e in errors)

    def test_warp_without_resync(self) -> None:
        patch = ObsPatch(
            tick=10,
            movement=Movement(input="A", result="warp"),
        )
        errors = validate_patch(patch)
        assert any("should include 'resync'" in e for e in errors)

    def test_battle_without_resync(self) -> None:
        patch = ObsPatch(
            tick=10,
            movement=Movement(result="battle"),
        )
        errors = validate_patch(patch)
        assert any("should include 'resync'" in e for e in errors)

    def test_dialog_without_resync(self) -> None:
        patch = ObsPatch(
            tick=10,
            movement=Movement(result="dialog"),
        )
        errors = validate_patch(patch)
        assert any("should include 'resync'" in e for e in errors)


# ═════════════════════════════════════════════════════════════════════════════
# MapIntegrator tests
# ═════════════════════════════════════════════════════════════════════════════


class TestMapIntegratorInit:
    """Tests for MapIntegrator initialization."""

    def test_init_with_world_state(self) -> None:
        ws = WorldState()
        ws.init_blank(20, 20)
        mi = MapIntegrator(world=ws)
        assert mi.world is ws

    def test_init_blank_default(self) -> None:
        mi = MapIntegrator()
        assert mi.world is not None
        assert len(mi.world.terrain) == 200
        assert len(mi.world.terrain[0]) == 200

    def test_init_from_directory(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        ws = WorldState()
        ws.init_blank(10, 10)
        ws.set_terrain(5, 5, "g")
        ws.map_id = "test_map"
        ws.save(tmp_path)

        mi = MapIntegrator(world_dir=tmp_path)
        assert mi.world.map_id == "test_map"
        assert mi.world.terrain_at(5, 5) == "g"


class TestMapIntegratorApplySuccess:
    """Tests for MapIntegrator.apply success paths."""

    def test_apply_moved_patch(self) -> None:
        ws = WorldState()
        ws.init_blank(20, 20)
        ws.viewport = Viewport(size=(10, 10), origin=(0, 0))
        ws.player.pos = (5, 5)
        mi = MapIntegrator(world=ws)

        data = {
            "tick": 1,
            "movement": {"input": "RIGHT", "result": "moved", "player_delta": [1, 0], "facing": "E"},
        }
        result = mi.apply(data)
        assert result is True
        assert mi.world.player.pos == (6, 5)
        assert mi.world.player.facing == "E"
        assert mi.world.last_button == "RIGHT"
        assert mi.world.last_result == "moved"

    def test_apply_blocked_patch(self) -> None:
        ws = WorldState()
        ws.init_blank(20, 20)
        ws.player.pos = (5, 5)
        mi = MapIntegrator(world=ws)

        data = {
            "tick": 2,
            "movement": {"input": "UP", "result": "blocked", "facing": "N"},
            "edges": [
                {"from": [5, 5], "dir": "N", "outcome": "blocked", "reason": "wall"},
            ],
        }
        result = mi.apply(data)
        assert result is True
        assert mi.world.last_result == "blocked"
        e = mi.world.edge_at(5, 5, "N")
        assert e is not None
        assert e.outcome == "blocked"

    def test_apply_correction(self) -> None:
        ws = WorldState()
        ws.init_blank(10, 10)
        ws.set_terrain(3, 3, "?")  # was unknown
        mi = MapIntegrator(world=ws)

        data = {
            "tick": 3,
            "movement": {"input": "DOWN", "result": "moved", "player_delta": [0, 1], "facing": "S"},
            "corrections": [
                {"layer": "terrain", "at": [3, 3], "from": "?", "to": ".", "confidence": 0.9},
            ],
        }
        result = mi.apply(data)
        assert result is True
        assert mi.world.terrain_at(3, 3) == "."

    def test_apply_with_strip(self) -> None:
        ws = WorldState()
        ws.init_blank(10, 10)
        ws.viewport = Viewport(size=(10, 10), origin=(0, 0))
        ws.player.pos = (5, 1)
        mi = MapIntegrator(world=ws)

        data = {
            "tick": 4,
            "movement": {"input": "UP", "result": "moved", "player_delta": [0, -1], "facing": "N"},
            "viewport": {"origin_delta": [0, -1], "new_edge": "N"},
            "strip": {
                "edge": "N",
                "global_y": 0,
                "x_start": 0,
                "terrain": "TTTTTTTTTT",
            },
        }
        result = mi.apply(data)
        assert result is True
        assert mi.world.terrain_at(0, 0) == "T"
        assert mi.world.terrain_at(5, 0) == "T"

    def test_apply_resync(self) -> None:
        ws = WorldState()
        ws.init_blank(20, 20)
        ws.player.pos = (5, 5)
        ws.set_edge(5, 5, "N", "blocked", "old edge")
        mi = MapIntegrator(world=ws)

        data = {
            "tick": 50,
            "resync": {
                "reason": "warp",
                "new_map_id": "oak_lab",
                "viewport_origin": [0, 0],
                "player_pos": [4, 6],
                "player_facing": "S",
                "full_viewport": {
                    "terrain": ["....", "....", "....", "...."],
                    "objects": ["    ", "    ", "    ", "    "],
                },
            },
        }
        result = mi.apply(data)
        assert result is True
        assert mi.world.map_id == "oak_lab"
        assert mi.world.player.pos == (4, 6)
        assert mi.world.player.facing == "S"
        assert len(mi.world.terrain) == 4  # height from full_viewport
        # Old edges should be cleared
        assert mi.world.edge_at(5, 5, "N") is None

    def test_apply_visited_marking(self) -> None:
        ws = WorldState()
        ws.init_blank(10, 10)
        ws.player.pos = (0, 0)
        mi = MapIntegrator(world=ws)

        data = {
            "tick": 5,
            "movement": {"input": "RIGHT", "result": "moved", "player_delta": [1, 0], "facing": "E"},
            "visited_add": [[0, 0]],
        }
        result = mi.apply(data)
        assert result is True
        assert mi.world.visited[0][1] == "@"  # new player pos marked
        assert mi.world.visited[0][0] == "+"  # old pos from visited_add

    def test_apply_actor_update(self) -> None:
        ws = WorldState()
        ws.init_blank(20, 20)
        mi = MapIntegrator(world=ws)

        data = {
            "tick": 6,
            "movement": {"input": "DOWN", "result": "moved", "player_delta": [0, 1], "facing": "S"},
            "actor_updates": [
                {"id": "joy", "kind": "n", "pos": [7, 4], "confidence": 0.9},
            ],
        }
        result = mi.apply(data)
        assert result is True
        assert "joy" in mi.world.actors
        assert mi.world.actors["joy"].kind == "n"
        assert mi.world.actors["joy"].pos == (7, 4)

    def test_apply_movement_mode_update(self) -> None:
        ws = WorldState()
        ws.init_blank(20, 20)
        ws.player.mode = "walk"
        mi = MapIntegrator(world=ws)

        data = {
            "tick": 7,
            "movement": {"input": "A", "result": "moved", "player_delta": [0, 0], "facing": "N", "mode": "bike"},
        }
        result = mi.apply(data)
        assert result is True
        assert mi.world.player.mode == "bike"


class TestMapIntegratorApplyRejection:
    """Tests for MapIntegrator.apply rejection paths."""

    def test_apply_rejects_invalid_patch(self) -> None:
        mi = MapIntegrator()
        # A blocked patch without edges (fails validate_patch)
        data = {
            "tick": 1,
            "movement": {"input": "UP", "result": "blocked"},
        }
        result = mi.apply(data)
        assert result is False
        assert mi.stats["patches_rejected"] == 1
        assert mi.stats["patches_applied"] == 0

    def test_apply_rejects_bad_parse(self) -> None:
        mi = MapIntegrator()
        result = mi.apply("not valid at all: {{{")
        assert result is False
        assert mi.stats["patches_rejected"] == 1

    def test_apply_rejects_turned_only_with_delta(self) -> None:
        mi = MapIntegrator()
        ws = mi.world
        data = {
            "tick": 1,
            "movement": {"input": "LEFT", "result": "turned_only", "player_delta": [1, 0]},
        }
        result = mi.apply(data)
        assert result is False


class TestMapIntegratorComposeForController:
    """Tests for MapIntegrator.compose_for_controller output format."""

    def test_output_is_string(self) -> None:
        mi = MapIntegrator()
        output = mi.compose_for_controller()
        assert isinstance(output, str)

    def test_output_contains_map_and_mode(self) -> None:
        ws = WorldState()
        ws.init_blank(5, 5)
        ws.map_id = "viridian_city"
        ws.viewport = Viewport(size=(5, 5), origin=(0, 0))
        mi = MapIntegrator(world=ws)

        output = mi.compose_for_controller()
        assert "MAP: viridian_city" in output
        assert "MODE:" in output
        assert "LOCAL MAP:" in output

    def test_output_contains_player_pos(self) -> None:
        ws = WorldState()
        ws.init_blank(5, 5)
        ws.viewport = Viewport(size=(5, 5), origin=(0, 0))
        ws.player.pos = (3, 2)
        mi = MapIntegrator(world=ws)

        output = mi.compose_for_controller()
        assert "POS: (3, 2)" in output


class TestMapIntegratorStats:
    """Tests for MapIntegrator.stats property."""

    def test_initial_stats(self) -> None:
        mi = MapIntegrator()
        s = mi.stats
        assert s["patches_applied"] == 0
        assert s["patches_rejected"] == 0
        assert s["total_patches"] == 0
        assert s["rejection_rate"] == 0.0

    def test_stats_after_successful_apply(self) -> None:
        mi = MapIntegrator()
        mi.apply({
            "tick": 1,
            "movement": {"input": "UP", "result": "moved", "player_delta": [0, -1]},
        })
        s = mi.stats
        assert s["patches_applied"] == 1
        assert s["patches_rejected"] == 0

    def test_stats_rejection_rate(self) -> None:
        mi = MapIntegrator()
        mi.apply({"tick": 1, "movement": {"input": "UP", "result": "moved"}})
        mi.apply({"tick": 2, "movement": {"input": "UP", "result": "blocked"}})  # rejected: no edges
        s = mi.stats
        assert s["total_patches"] == 2
        assert s["rejection_rate"] == 0.5

    def test_recent_rejections_capped(self) -> None:
        mi = MapIntegrator()
        for i in range(10):
            mi.apply({"tick": i, "movement": {"input": "UP", "result": "blocked"}})
        s = mi.stats
        assert len(s["recent_rejections"]) == 5  # capped at 5


class TestMapIntegratorSave:
    """Tests for MapIntegrator.save."""

    def test_save_persists(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        ws = WorldState()
        ws.init_blank(10, 10)
        ws.set_terrain(5, 5, "#")
        ws.map_id = "test"
        mi = MapIntegrator(world=ws)
        mi.save(tmp_path)

        assert (tmp_path / "state.yaml").exists()
        assert (tmp_path / "terrain.map").exists()

        # Load back and verify
        loaded = WorldState.load(tmp_path)
        assert loaded.map_id == "test"
        assert loaded.terrain_at(5, 5) == "#"
