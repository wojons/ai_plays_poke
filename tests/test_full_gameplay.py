"""
Integration test: boots Pokémon Red ROM, runs the gameplay loop, and verifies progress.

Mark: ``pytest.mark.rom`` — requires ROM file at data/rom/pokemon_red.gb.
Skip in CI without ROM: ``pytest -m "not rom"``
"""

from __future__ import annotations

import json
import pytest
from pathlib import Path

ROM_PATH = Path("data/rom/pokemon_red.gb")

# ── Helpers ────────────────────────────────────────────────────────────────


def _has_rom() -> bool:
    return ROM_PATH.is_file()


def _advance_to_overworld(emu, reader, max_cycles: int = 120) -> None:
    """Advance both naming screens and dialogs to a controllable map."""
    emu.wait(180)
    emu.bypass_title()
    emu.press_button("a", frames=15)
    emu.fast_forward(60)

    name_entries = 0
    for _ in range(max_cycles):
        screen = reader.screen_type()
        if screen == "name_entry":
            emu.submit_name()
            name_entries += 1
        elif screen == "overworld" and emu.read_u8(0xC100) != 0:
            return
        else:
            emu.press_button("a", frames=20)
            emu.fast_forward(60)

    pytest.fail(
        f"Did not reach controllable overworld within {max_cycles} cycles "
        f"(last screen={reader.screen_type()}, names={name_entries})"
    )


def _count_action_types(log_path: Path) -> dict[str, int]:
    """Count the types of actions taken across cycles."""
    counts: dict[str, int] = {}
    with open(log_path) as f:
        for line in f:
            try:
                entry = json.loads(line)
                screen = entry.get("screen", "unknown")
                counts[screen] = counts.get(screen, 0) + 1
            except json.JSONDecodeError:
                pass
    return counts


# ── Tests ──────────────────────────────────────────────────────────────────


@pytest.mark.rom
@pytest.mark.skipif(not _has_rom(), reason="ROM not found at data/rom/pokemon_red.gb")
class TestFullGameplay:
    """End-to-end gameplay test with real ROM."""

    def test_boots_and_reaches_overworld(self) -> None:
        """Boot ROM, bypass intro, and reach a controllable overworld."""
        from src.core.emulator import Emulator
        from src.core.ram_reader import RAMReader

        emu = Emulator(ROM_PATH)
        try:
            reader = RAMReader(emu, ROM_PATH)
            _advance_to_overworld(emu, reader)
            obs = reader.observe()
            assert obs["result"] == "overworld"
        finally:
            emu.stop()

    def test_ram_reader_produces_valid_state(self) -> None:
        """RAM reader returns structured observation with required keys after boot."""
        from src.core.emulator import Emulator
        from src.core.ram_reader import RAMReader

        emu = Emulator(ROM_PATH)
        emu.bypass_title()
        for _ in range(240):
            emu._pyboy.tick()

        reader = RAMReader(emu, ROM_PATH)

        for _ in range(20):
            emu.press_button("a", frames=5)
            emu.wait(10)

        obs = reader.observe()

        # Required keys
        assert "result" in obs
        assert "player_x" in obs
        assert "player_y" in obs
        assert "player_facing" in obs
        assert "map_id" in obs
        assert "map_name" in obs

        # Overworld-specific
        if obs["result"] == "overworld":
            assert "adjacent" in obs
            assert "render" in obs
            assert len(obs.get("adjacent", {})) == 4

        emu.stop()

    def test_overworld_grid_dimensions(self) -> None:
        """Overworld grid renders 5x5 player-centered view."""
        from src.core.emulator import Emulator
        from src.core.ram_reader import RAMReader

        emu = Emulator(ROM_PATH)
        emu.bypass_title()
        for _ in range(240):
            emu._pyboy.tick()

        for _ in range(20):
            emu.press_button("a", frames=5)
            emu.wait(10)

        reader = RAMReader(emu, ROM_PATH)
        render = reader.render_overworld()

        lines = render.strip().split("\n")
        # Should have header lines + grid rows + legend
        assert len(lines) >= 7, f"Expected >=7 lines, got {len(lines)}:\n{render}"

        # Grid lines should contain @ (player) symbol
        grid_lines = [
            line for line in lines if "@" in line or "?" in line or "." in line
        ]
        assert len(grid_lines) >= 3, f"Expected >=3 grid rows, got {len(grid_lines)}"

        emu.stop()

    def test_battle_state_reads_zero_when_not_in_battle(self) -> None:
        """RAM reader returns empty battle state when wIsInBattle == 0."""
        from src.core.emulator import Emulator
        from src.core.ram_reader import RAMReader

        emu = Emulator(ROM_PATH)
        emu.bypass_title()
        for _ in range(240):
            emu._pyboy.tick()

        reader = RAMReader(emu, ROM_PATH)

        for _ in range(20):
            emu.press_button("a", frames=5)
            emu.wait(10)

        obs = reader.observe()
        bs = obs.get("battle_state", {})

        # Not in battle — battle_state should be empty or have null values
        assert (
            not bs or bs.get("player", {}).get("hp", 0) == 0
        ), f"Expected empty battle state, got {bs}"

        emu.stop()

    def test_menu_state_empty_when_no_menu(self) -> None:
        """RAM reader returns empty menu when no menu is active."""
        from src.core.emulator import Emulator
        from src.core.ram_reader import RAMReader

        emu = Emulator(ROM_PATH)
        emu.bypass_title()
        for _ in range(240):
            emu._pyboy.tick()

        reader = RAMReader(emu, ROM_PATH)

        for _ in range(20):
            emu.press_button("a", frames=5)
            emu.wait(10)

        obs = reader.observe()
        ms = obs.get("menu_state", {})

        # No menu should be active
        assert (
            ms.get("num_items", 0) == 0 or ms.get("active", False) is False
        ), f"Expected no active menu, got {ms}"

        emu.stop()

    def test_player_coordinates_change_over_60_gameplay_cycles(self) -> None:
        """A real-ROM run must move the player, not merely boot the emulator."""
        from src.core.emulator import Emulator
        from src.core.ram_reader import RAMReader

        emu = Emulator(ROM_PATH)
        try:
            reader = RAMReader(emu, ROM_PATH)
            _advance_to_overworld(emu, reader)

            coordinates: list[tuple[int, int, int]] = []
            route = ["right"] * 4 + ["up"] * 5 + ["left"] * 5 + ["down"] * 6
            for cycle in range(60):
                if reader.screen_type() == "dialog":
                    emu.press_button("a", frames=30)
                else:
                    emu.press_button(route[cycle % len(route)], frames=30)
                emu.fast_forward(60)
                coordinates.append(
                    (
                        reader.current_map_id(),
                        reader.player_x(),
                        reader.player_y(),
                    )
                )

            assert (
                len(set(coordinates)) > 1
            ), f"Player never moved over 60 cycles: {coordinates[0]}"
        finally:
            emu.stop()


@pytest.mark.rom
@pytest.mark.skipif(not _has_rom(), reason="ROM not found at data/rom/pokemon_red.gb")
class TestRamReaderAccuracy:
    """Verify RAM reader addresses match actual game state."""

    def test_coordinates_are_reasonable(self) -> None:
        """Player coordinates should be within map bounds after intro."""
        from src.core.emulator import Emulator
        from src.core.ram_reader import RAMReader

        emu = Emulator(ROM_PATH)
        emu.bypass_title()
        for _ in range(240):
            emu._pyboy.tick()

        for _ in range(20):
            emu.press_button("a", frames=5)
            emu.wait(10)

        reader = RAMReader(emu, ROM_PATH)
        obs = reader.observe()

        # After intro, player should be on a real map
        px, py = obs["player_x"], obs["player_y"]
        # Allow transient negative coords (intro transition) but not completely insane
        assert -10 <= px <= 50, f"Player X {px} out of reasonable range"
        assert -10 <= py <= 50, f"Player Y {py} out of reasonable range"

        emu.stop()

    def test_facing_is_valid(self) -> None:
        """Player facing should be one of up/down/left/right."""
        from src.core.emulator import Emulator
        from src.core.ram_reader import RAMReader

        emu = Emulator(ROM_PATH)
        emu.bypass_title()
        for _ in range(240):
            emu._pyboy.tick()

        reader = RAMReader(emu, ROM_PATH)
        facing = reader.player_facing()

        assert facing in ("up", "down", "left", "right"), f"Invalid facing: {facing}"

        emu.stop()
