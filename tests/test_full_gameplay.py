"""
Integration test: boots Pokémon Red ROM, runs the gameplay loop, and verifies progress.

Mark: ``pytest.mark.rom`` — requires ROM file at data/rom/pokemon_red.gb.
Skip in CI without ROM: ``pytest -m "not rom"``
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from cron_runner import (
    _approach_first_starter,
    _select_starter_from_menu,
    _should_select_starter,
    _starter_milestone_for_cycle,
    _starter_picked_event,
)

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


class TestStarterSelection:
    def test_branch_requires_oaks_lab_empty_party_and_menu(self) -> None:
        assert _should_select_starter(
            map_id=40,
            party_count=0,
            screen_type="menu",
            menu_state={"menu_id": 0, "active": True},
        )
        assert _should_select_starter(
            map_id=40,
            party_count=0,
            screen_type="dialog",
            menu_state={"menu_id": 1, "active": True},
        )

    @pytest.mark.parametrize(
        ("map_id", "party_count", "screen_type", "menu_state"),
        [
            (0, 0, "menu", {"menu_id": 1, "active": True}),
            (40, 1, "menu", {"menu_id": 1, "active": True}),
            (40, 0, "dialog", {"menu_id": 0}),
        ],
    )
    def test_branch_does_not_fire_outside_starter_menu(
        self,
        map_id: int,
        party_count: int,
        screen_type: str,
        menu_state: dict[str, object],
    ) -> None:
        assert not _should_select_starter(
            map_id=map_id,
            party_count=party_count,
            screen_type=screen_type,
            menu_state=menu_state,
        )

    def test_tile_lock_approaches_first_starter_with_one_tile_taps(self) -> None:
        emu = MagicMock()
        reader = MagicMock()
        reader.screen_type.side_effect = ["overworld", "menu"]
        reader.player_tile_x.return_value = 5
        reader.player_tile_y.return_value = 3

        assert _approach_first_starter(emu, reader)
        assert reader.screen_type.call_count == 2
        assert emu.press_button.call_args_list == [
            call("down", frames=5),
            call("right", frames=5),
            call("up", frames=5),
            call("a", frames=20),
        ]

    def test_deterministic_branch_confirms_then_declines_nickname(self) -> None:
        emu = MagicMock()
        reader = MagicMock()
        reader.party_count.side_effect = [0, 0, 1]

        party_count = _select_starter_from_menu(
            emu,
            reader,
            max_advances=4,
            decline_presses=2,
        )

        assert party_count == 1
        assert emu.press_button.call_args_list == [
            call("a", frames=20),
            call("a", frames=20),
            call("b", frames=20),
            call("b", frames=20),
        ]

    def test_party_count_transition_builds_starter_milestone(self) -> None:
        assert _starter_picked_event(0, 1, "Charmander") == {
            "event": "starter_picked",
            "party_count": 1,
            "species_hint": "Charmander",
        }

    @pytest.mark.parametrize("before,after", [(0, 0), (1, 1), (1, 2)])
    def test_non_starter_transitions_do_not_build_milestone(
        self, before: int, after: int
    ) -> None:
        assert _starter_picked_event(before, after, None) is None

    # ── GAMEPLAY-STARTER-002 regression: the milestone must fire on real
    # ── picks — both the in-run 0→1 transition and the post-pick boot
    # ── baseline (data/boot.state already holds a starter, so no in-run
    # ── 0→1 transition is ever observable).

    def test_cycle_milestone_fires_on_mid_dialog_party_transition(self) -> None:
        """Mocked RAM shows party-count 0→1 while advancing Oak's dialog:
        the milestone must be emitted."""
        event, emitted = _starter_milestone_for_cycle(
            previous_party_count=0,
            current_party_count=1,
            species_hint="Squirtle",
            baseline_starter_name=None,
            milestone_emitted=False,
        )
        assert emitted is True
        assert event == {
            "event": "starter_picked",
            "party_count": 1,
            "species_hint": "Squirtle",
        }

    def test_cycle_milestone_fires_on_post_pick_boot_baseline(self) -> None:
        """Run boots from a checkpoint whose party already holds a starter
        (T192/T187 signature: rival battle reached, no 0→1 transition):
        the milestone must fire from the baseline party."""
        event, emitted = _starter_milestone_for_cycle(
            previous_party_count=1,
            current_party_count=1,
            species_hint="Charmander",
            baseline_starter_name="Charmander",
            milestone_emitted=False,
        )
        assert emitted is True
        assert event is not None
        assert event["event"] == "starter_picked"
        assert event["party_count"] == 1
        assert event["species_hint"] == "Charmander"
        assert event.get("source") == "boot_baseline"

    def test_cycle_milestone_ignores_non_starter_baseline(self) -> None:
        """A mid-game save with a non-starter species must not masquerade as
        a starter pick."""
        event, emitted = _starter_milestone_for_cycle(
            previous_party_count=1,
            current_party_count=1,
            species_hint="Pikachu",
            baseline_starter_name=None,
            milestone_emitted=False,
        )
        assert emitted is False
        assert event is None

    def test_cycle_milestone_is_one_shot(self) -> None:
        """Once emitted, the milestone never fires again on later cycles."""
        event, emitted = _starter_milestone_for_cycle(
            previous_party_count=0,
            current_party_count=1,
            species_hint="Charmander",
            baseline_starter_name=None,
            milestone_emitted=True,
        )
        assert emitted is True
        assert event is None


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
