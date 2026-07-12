"""
Unit tests for src/core/symbols.py — terrain/object/actor symbol dicts + conversion functions.

349 lines at 0% coverage → target 90%+.
Pure data with zero dependencies — no ROM, no API, no emulator.
"""

from src.core.symbols import (
    TERRAIN_EMOJI,
    TERRAIN_ASCII,
    OBJECT_EMOJI,
    OBJECT_ASCII,
    ACTOR_EMOJI,
    ACTOR_ASCII,
    PLAYER_FACING_EMOJI,
    PLAYER_FACING_ASCII,
    MODE_EMOJI,
    LIGHTING_EMOJI,
    EDGE_OUTCOME_EMOJI,
    VISITED_EMOJI,
    VISITED_ASCII,
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
    TSV_STRIP_REFERENCE,
    SYMBOL_REFERENCE,
)


# ── Terrain dicts ───────────────────────────────────────────────────────────

class TestTerrainDicts:
    """TERRAIN_EMOJI and TERRAIN_ASCII — key coverage and lookup correctness."""

    TERRAIN_KEYS = [
        "?", ".", "g", "G", "T", "#", "~", "=", "^", "v",
        "<", ">", ":", "s", "i", "f", "d", "S", "p",
    ]

    def test_terrain_emoji_has_all_keys(self):
        """All 19 terrain keys present in TERRAIN_EMOJI."""
        for key in self.TERRAIN_KEYS:
            assert key in TERRAIN_EMOJI, f"Missing TERRAIN_EMOJI key: {key}"

    def test_terrain_emoji_no_extra_keys(self):
        """No unexpected keys in TERRAIN_EMOJI."""
        assert set(TERRAIN_EMOJI.keys()) == set(self.TERRAIN_KEYS)

    def test_terrain_ascii_has_all_keys(self):
        """All 19 terrain keys present in TERRAIN_ASCII."""
        for key in self.TERRAIN_KEYS:
            assert key in TERRAIN_ASCII, f"Missing TERRAIN_ASCII key: {key}"

    def test_terrain_ascii_no_extra_keys(self):
        """No unexpected keys in TERRAIN_ASCII."""
        assert set(TERRAIN_ASCII.keys()) == set(self.TERRAIN_KEYS)

    def test_terrain_emoji_values_are_strings(self):
        """Every value in TERRAIN_EMOJI is a non-empty string."""
        for key, val in TERRAIN_EMOJI.items():
            assert isinstance(val, str) and len(val) > 0, f"{key}: {val!r}"

    def test_terrain_ascii_values_are_single_char(self):
        """Every value in TERRAIN_ASCII is exactly 1 character."""
        for key, val in TERRAIN_ASCII.items():
            assert len(val) == 1, f"{key}: {val!r}"


# ── Object dicts ────────────────────────────────────────────────────────────

class TestObjectDicts:
    """OBJECT_EMOJI and OBJECT_ASCII — key coverage."""

    OBJECT_KEYS = [
        "D", "S", "C", "I", "B", "M", "H", "F", "N", "P",
        "K", "R", "T", "X", "Y",
    ]

    def test_object_emoji_has_all_keys(self):
        """All 15 object keys present in OBJECT_EMOJI."""
        for key in self.OBJECT_KEYS:
            assert key in OBJECT_EMOJI, f"Missing OBJECT_EMOJI key: {key}"

    def test_object_emoji_no_extra_keys(self):
        """No unexpected keys in OBJECT_EMOJI."""
        assert set(OBJECT_EMOJI.keys()) == set(self.OBJECT_KEYS)

    def test_object_ascii_has_all_keys(self):
        """All 15 object keys present in OBJECT_ASCII."""
        for key in self.OBJECT_KEYS:
            assert key in OBJECT_ASCII, f"Missing OBJECT_ASCII key: {key}"

    def test_object_emoji_values_are_strings(self):
        """Every value in OBJECT_EMOJI is a non-empty string."""
        for key, val in OBJECT_EMOJI.items():
            assert isinstance(val, str) and len(val) > 0, f"{key}: {val!r}"

    def test_object_ascii_values_are_single_char(self):
        """Every value in OBJECT_ASCII is exactly 1 character."""
        for key, val in OBJECT_ASCII.items():
            assert len(val) == 1, f"{key}: {val!r}"


# ── Actor dicts ─────────────────────────────────────────────────────────────

class TestActorDicts:
    """ACTOR_EMOJI and ACTOR_ASCII — key coverage."""

    ACTOR_KEYS = [
        "u", "n", "o", "m", "p", "r", "t", "T", "b", "l",
        "h", "g", "s", "f", "c", "e", "k", "K", "P", "R", "x",
    ]

    def test_actor_emoji_has_all_keys(self):
        """All 21 actor keys present in ACTOR_EMOJI."""
        for key in self.ACTOR_KEYS:
            assert key in ACTOR_EMOJI, f"Missing ACTOR_EMOJI key: {key}"

    def test_actor_emoji_no_extra_keys(self):
        """No unexpected keys in ACTOR_EMOJI."""
        assert set(ACTOR_EMOJI.keys()) == set(self.ACTOR_KEYS)

    def test_actor_ascii_has_all_keys(self):
        """All 21 actor keys present in ACTOR_ASCII."""
        for key in self.ACTOR_KEYS:
            assert key in ACTOR_ASCII, f"Missing ACTOR_ASCII key: {key}"

    def test_actor_emoji_values_are_strings(self):
        """Every value in ACTOR_EMOJI is a non-empty string."""
        for key, val in ACTOR_EMOJI.items():
            assert isinstance(val, str) and len(val) > 0, f"{key}: {val!r}"

    def test_actor_ascii_values_are_single_char(self):
        """Every value in ACTOR_ASCII is exactly 1 character."""
        for key, val in ACTOR_ASCII.items():
            assert len(val) == 1, f"{key}: {val!r}"


# ── Player facing dicts ─────────────────────────────────────────────────────

class TestPlayerFacingDicts:
    """PLAYER_FACING_EMOJI and PLAYER_FACING_ASCII — N/S/E/W directions."""

    def test_facing_emoji_all_directions(self):
        """N/S/E/W have distinct emoji arrows."""
        assert PLAYER_FACING_EMOJI["N"] == "⬆️"
        assert PLAYER_FACING_EMOJI["S"] == "⬇️"
        assert PLAYER_FACING_EMOJI["E"] == "➡️"
        assert PLAYER_FACING_EMOJI["W"] == "⬅️"

    def test_facing_ascii_all_directions(self):
        """N/S/E/W have distinct ASCII arrows."""
        assert PLAYER_FACING_ASCII["N"] == "^"
        assert PLAYER_FACING_ASCII["S"] == "v"
        assert PLAYER_FACING_ASCII["E"] == ">"
        assert PLAYER_FACING_ASCII["W"] == "<"

    def test_facing_dicts_same_keys(self):
        """Both facing dicts have the same 4 keys."""
        assert set(PLAYER_FACING_EMOJI.keys()) == {"N", "S", "E", "W"}
        assert set(PLAYER_FACING_ASCII.keys()) == {"N", "S", "E", "W"}


# ── Mode emoji dict ─────────────────────────────────────────────────────────

class TestModeEmoji:
    """MODE_EMOJI — all game modes."""

    MODES = {"walk", "bike", "surf", "menu", "battle", "dialog", "cutscene", "unknown"}

    def test_all_modes_present(self):
        """All 8 mode keys in MODE_EMOJI."""
        assert set(MODE_EMOJI.keys()) == self.MODES

    def test_all_mode_values_are_strings(self):
        """Every mode value is a non-empty string."""
        for key, val in MODE_EMOJI.items():
            assert isinstance(val, str) and len(val) > 0, f"{key}: {val!r}"


# ── Lighting emoji dict ─────────────────────────────────────────────────────

class TestLightingEmoji:
    """LIGHTING_EMOJI — lighting/visibility states."""

    LIGHTING = {"normal", "dark", "flash", "indoor", "cave", "unknown"}

    def test_all_lighting_present(self):
        """All 6 lighting keys present."""
        assert set(LIGHTING_EMOJI.keys()) == self.LIGHTING

    def test_all_lighting_values_are_strings(self):
        """Every lighting value is a non-empty string."""
        for key, val in LIGHTING_EMOJI.items():
            assert isinstance(val, str) and len(val) > 0, f"{key}: {val!r}"


# ── Edge outcome emoji dict ─────────────────────────────────────────────────

class TestEdgeOutcomeEmoji:
    """EDGE_OUTCOME_EMOJI — movement edge outcomes."""

    EDGES = {"open", "blocked", "one_way_ledge", "warp", "npc_block", "water_edge", "unknown"}

    def test_all_edges_present(self):
        """All 7 edge outcome keys present."""
        assert set(EDGE_OUTCOME_EMOJI.keys()) == self.EDGES

    def test_all_edge_values_are_strings(self):
        """Every edge value is a non-empty string."""
        for key, val in EDGE_OUTCOME_EMOJI.items():
            assert isinstance(val, str) and len(val) > 0, f"{key}: {val!r}"


# ── Visited dicts ───────────────────────────────────────────────────────────

class TestVisitedDicts:
    """VISITED_EMOJI and VISITED_ASCII — tile visited states."""

    VISITED = {"?", ".", "+", "@"}

    def test_visited_emoji_all_keys(self):
        """All 4 visited keys present."""
        assert set(VISITED_EMOJI.keys()) == self.VISITED

    def test_visited_ascii_all_keys(self):
        """All 4 visited keys present."""
        assert set(VISITED_ASCII.keys()) == self.VISITED

    def test_visited_values_are_strings(self):
        """Every visited value is a non-empty string."""
        for key, val in VISITED_EMOJI.items():
            assert isinstance(val, str) and len(val) > 0, f"{key}: {val!r}"
        for key, val in VISITED_ASCII.items():
            assert isinstance(val, str) and len(val) == 1, f"{key}: {val!r}"


# ── terrain_to_emoji / terrain_to_ascii ─────────────────────────────────────

class TestTerrainToEmoji:
    """terrain_to_emoji() — known keys and unknown fallback."""

    def test_known_terrain_walkable(self):
        assert terrain_to_emoji(".") == "⬜"

    def test_known_terrain_grass(self):
        assert terrain_to_emoji("g") == "🌿"

    def test_known_terrain_tree(self):
        assert terrain_to_emoji("T") == "🌲"

    def test_known_terrain_wall(self):
        assert terrain_to_emoji("#") == "🧱"

    def test_known_terrain_water(self):
        assert terrain_to_emoji("~") == "🌊"

    def test_known_terrain_door(self):
        assert terrain_to_emoji("d") == "🚪"

    def test_unknown_terrain_fallback(self):
        """Unknown char returns ❓."""
        assert terrain_to_emoji("Z") == "❓"
        assert terrain_to_emoji("💥") == "❓"

    def test_empty_string_terrain(self):
        """Empty string returns ❓ (not in dict)."""
        assert terrain_to_emoji("") == "❓"


class TestTerrainToAscii:
    """terrain_to_ascii() — known keys return ASCII char; unknown returns identity."""

    def test_known_terrain_walkable(self):
        assert terrain_to_ascii(".") == "."

    def test_known_terrain_door(self):
        """ASCII uses 'D' for door (not 'd')."""
        assert terrain_to_ascii("d") == "D"

    def test_known_terrain_path(self):
        """Path 'p' renders as '.' in ASCII."""
        assert terrain_to_ascii("p") == "."

    def test_unknown_terrain_identity(self):
        """Unknown char returns itself as identity fallback."""
        assert terrain_to_ascii("Z") == "Z"
        assert terrain_to_ascii("💥") == "💥"

    def test_empty_string_terrain(self):
        """Empty string returns empty string (identity fallback)."""
        assert terrain_to_ascii("") == ""


# ── object_to_emoji / object_to_ascii ──────────────────────────────────────

class TestObjectToEmoji:
    """object_to_emoji() — space handling and known keys."""

    def test_space_returns_double_width(self):
        """Space char returns double-width spacer for grid alignment."""
        assert object_to_emoji(" ") == "  "

    def test_known_object_door(self):
        assert object_to_emoji("D") == "🚪"

    def test_known_object_sign(self):
        assert object_to_emoji("S") == "🪧"

    def test_known_object_item_ball(self):
        assert object_to_emoji("I") == "💎"

    def test_known_object_heal_machine(self):
        assert object_to_emoji("H") == "🏥"

    def test_unknown_object_fallback(self):
        """Unknown char returns ❓."""
        assert object_to_emoji("Z") == "❓"

    def test_empty_string_object(self):
        """Empty string returns ❓."""
        assert object_to_emoji("") == "❓"


class TestObjectToAscii:
    """object_to_ascii() — space handling and known keys."""

    def test_space_returns_space(self):
        assert object_to_ascii(" ") == " "

    def test_known_object_door(self):
        assert object_to_ascii("D") == "D"

    def test_known_object_bookshelf(self):
        """Bookshelf 'K' maps to 'B' in ASCII."""
        assert object_to_ascii("K") == "B"

    def test_unknown_object_identity(self):
        """Unknown char returns itself."""
        assert object_to_ascii("Z") == "Z"

    def test_empty_string_object(self):
        assert object_to_ascii("") == ""


# ── actor_to_emoji / actor_to_ascii ────────────────────────────────────────

class TestActorToEmoji:
    """actor_to_emoji() — known kinds and empty string fallback."""

    def test_known_actor_unknown_person(self):
        assert actor_to_emoji("u") == "👤"

    def test_known_actor_nurse(self):
        assert actor_to_emoji("n") == "👩‍⚕️"

    def test_known_actor_rival(self):
        assert actor_to_emoji("r") == "🧑‍🔬"

    def test_known_actor_trainer(self):
        assert actor_to_emoji("t") == "🧒"

    def test_known_actor_wild_pokemon(self):
        assert actor_to_emoji("P") == "🧬"

    def test_unknown_actor_fallback(self):
        """Unknown kind returns 👤."""
        assert actor_to_emoji("zzz") == "👤"

    def test_empty_string_actor(self):
        """Empty string returns 👤."""
        assert actor_to_emoji("") == "👤"


class TestActorToAscii:
    """actor_to_ascii() — known kinds, empty string fallback."""

    def test_known_actor_unknown(self):
        assert actor_to_ascii("u") == "u"

    def test_known_actor_rocket_grunt(self):
        assert actor_to_ascii("k") == "k"

    def test_known_actor_professor(self):
        assert actor_to_ascii("p") == "P"

    def test_unknown_actor_fallback_first_char(self):
        """Unknown kind returns first character."""
        assert actor_to_ascii("xyz") == "x"
        assert actor_to_ascii("hello") == "h"

    def test_empty_string_actor_fallback(self):
        """Empty string returns '?'."""
        assert actor_to_ascii("") == "?"


# ── facing_emoji / facing_ascii ────────────────────────────────────────────

class TestFacingEmoji:
    """facing_emoji() — N/S/E/W directions."""

    def test_north(self):
        assert facing_emoji("N") == "⬆️"

    def test_south(self):
        assert facing_emoji("S") == "⬇️"

    def test_east(self):
        assert facing_emoji("E") == "➡️"

    def test_west(self):
        assert facing_emoji("W") == "⬅️"

    def test_unknown_direction(self):
        """Unknown direction returns ❓."""
        assert facing_emoji("X") == "❓"
        assert facing_emoji("north") == "❓"


class TestFacingAscii:
    """facing_ascii() — N/S/E/W directions."""

    def test_north(self):
        assert facing_ascii("N") == "^"

    def test_south(self):
        assert facing_ascii("S") == "v"

    def test_east(self):
        assert facing_ascii("E") == ">"

    def test_west(self):
        assert facing_ascii("W") == "<"

    def test_unknown_direction(self):
        """Unknown direction returns '?'."""
        assert facing_ascii("X") == "?"
        assert facing_ascii("") == "?"


# ── mode_emoji ─────────────────────────────────────────────────────────────

class TestModeEmojiFunction:
    """mode_emoji() — known modes and unknown fallback."""

    def test_walk(self):
        assert mode_emoji("walk") == "🚶"

    def test_bike(self):
        assert mode_emoji("bike") == "🚲"

    def test_surf(self):
        assert mode_emoji("surf") == "🏄"

    def test_menu(self):
        assert mode_emoji("menu") == "📋"

    def test_battle(self):
        assert mode_emoji("battle") == "⚔️"

    def test_dialog(self):
        assert mode_emoji("dialog") == "💬"

    def test_cutscene(self):
        assert mode_emoji("cutscene") == "🎬"

    def test_unknown_mode(self):
        """Unknown mode returns ❓."""
        assert mode_emoji("unknown") == "❓"
        assert mode_emoji("flying") == "❓"


# ── edge_emoji ─────────────────────────────────────────────────────────────

class TestEdgeEmoji:
    """edge_emoji() — all edge outcomes."""

    def test_open(self):
        assert edge_emoji("open") == "✅"

    def test_blocked(self):
        assert edge_emoji("blocked") == "🚫"

    def test_one_way_ledge(self):
        assert edge_emoji("one_way_ledge") == "⏬"

    def test_warp(self):
        assert edge_emoji("warp") == "🚪"

    def test_npc_block(self):
        assert edge_emoji("npc_block") == "👤"

    def test_water_edge(self):
        assert edge_emoji("water_edge") == "🌊"

    def test_unknown_edge(self):
        """Unknown or unknown outcome returns ❓."""
        assert edge_emoji("unknown") == "❓"
        assert edge_emoji("cliff") == "❓"


# ── visited_emoji / visited_ascii ──────────────────────────────────────────

class TestVisitedEmoji:
    """visited_emoji() — all visited states."""

    def test_never_seen(self):
        assert visited_emoji("?") == "⬛"

    def test_seen_not_stood(self):
        assert visited_emoji(".") == "⬜"

    def test_player_stood_here(self):
        assert visited_emoji("+") == "👣"

    def test_current_position(self):
        assert visited_emoji("@") == "🎯"

    def test_unknown_state_fallback(self):
        """Unknown state returns ⬛."""
        assert visited_emoji("X") == "⬛"
        assert visited_emoji("") == "⬛"


class TestVisitedAscii:
    """visited_ascii() — all visited states."""

    def test_never_seen(self):
        assert visited_ascii("?") == "?"

    def test_seen_not_stood(self):
        assert visited_ascii(".") == "."

    def test_player_stood_here(self):
        assert visited_ascii("+") == "+"

    def test_current_position(self):
        assert visited_ascii("@") == "@"

    def test_unknown_state_fallback(self):
        """Unknown state returns '?'."""
        assert visited_ascii("X") == "?"
        assert visited_ascii("") == "?"


# ── describe_tile ──────────────────────────────────────────────────────────

class TestDescribeTile:
    """describe_tile() — terrain-only, terrain+object, terrain+object+actor."""

    def test_terrain_only(self):
        """Only terrain → single emoji."""
        result = describe_tile("g")
        assert result == "🌿"

    def test_terrain_with_space_object(self):
        """Space object is ignored (treated as 'no object')."""
        result = describe_tile(".", obj=" ")
        assert result == "⬜"

    def test_terrain_with_real_object(self):
        """Terrain + real object → two emojis separated by space."""
        result = describe_tile(".", obj="I")
        assert result == "⬜ 💎"

    def test_terrain_with_object_and_actor(self):
        """Terrain + object + actor → three emojis."""
        result = describe_tile(".", obj="I", actor_kind="t")
        assert result == "⬜ 💎 🧒"

    def test_terrain_with_actor_no_object(self):
        """Terrain + actor (no object) → two emojis."""
        result = describe_tile("T", actor_kind="P")
        assert "🌲" in result
        assert "🧬" in result

    def test_unknown_terrain_emoji(self):
        """Unknown terrain char still produces a description."""
        result = describe_tile("Z")
        assert result == "❓"

    def test_all_args_empty_strings(self):
        """Empty terrain, empty obj, empty actor — no crash."""
        result = describe_tile("", obj="", actor_kind="")
        assert result == "❓"  # unknown terrain fallback, no object/actor


# ── TSV_STRIP_REFERENCE ─────────────────────────────────────────────────────

class TestTSVStripReference:
    """TSV_STRIP_REFERENCE — format reference string."""

    def test_is_string(self):
        assert isinstance(TSV_STRIP_REFERENCE, str)

    def test_contains_packed_example(self):
        """Reference mentions packed format."""
        assert "TTT....ggg....T" in TSV_STRIP_REFERENCE

    def test_contains_tsv_example(self):
        """Reference mentions TSV format with <TAB> markup."""
        assert "<TAB>" in TSV_STRIP_REFERENCE


# ── SYMBOL_REFERENCE ────────────────────────────────────────────────────────

class TestSymbolReference:
    """SYMBOL_REFERENCE — contains key terrain symbols for prompts."""

    def test_is_string(self):
        assert isinstance(SYMBOL_REFERENCE, str)

    def test_contains_terrain_section(self):
        """Reference has TERRAIN SYMBOLS section."""
        assert "TERRAIN SYMBOLS" in SYMBOL_REFERENCE

    def test_contains_object_section(self):
        """Reference has OBJECT SYMBOLS section."""
        assert "OBJECT SYMBOLS" in SYMBOL_REFERENCE

    def test_contains_actor_section(self):
        """Reference has ACTOR KINDS section."""
        assert "ACTOR KINDS" in SYMBOL_REFERENCE

    def test_contains_walkable(self):
        """Reference documents the '.' terrain symbol."""
        assert ". = ⬜ walkable" in SYMBOL_REFERENCE

    def test_contains_grass(self):
        """Reference documents the 'g' terrain symbol."""
        assert "g = 🌿 tall grass" in SYMBOL_REFERENCE

    def test_contains_tree(self):
        """Reference documents the 'T' symbol."""
        assert "T = 🌲 tree" in SYMBOL_REFERENCE

    def test_contains_wall(self):
        """Reference documents the '#' symbol."""
        assert "# = 🧱 wall" in SYMBOL_REFERENCE

    def test_contains_water(self):
        """Reference documents the '~' symbol."""
        assert "~ = 🌊 water" in SYMBOL_REFERENCE

    def test_contains_door(self):
        """Reference documents the 'd' symbol."""
        assert "d = 🚪 door" in SYMBOL_REFERENCE

    def test_contains_rival(self):
        """Reference documents the 'r' actor."""
        assert "r = 🧑‍🔬 rival" in SYMBOL_REFERENCE

    def test_contains_wild_pokemon(self):
        """Reference documents the 'P' actor."""
        assert "P = 🧬 wild Pokémon" in SYMBOL_REFERENCE
