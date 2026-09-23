"""Focused tests for MEM-2's boot memory injection (PRD_v2_lifecycle.md §R3).

The reader half of the memory architecture: at run boot, gather MECHANICS /
SAVE-STATE / RUNS-index / LEARNING from DuckBrain ns `pokemon-global` and
render the compact BOOT MEMORY block that rides in the controller system
prompt. All tests are hermetic — a temp namespace root, no network, no real
DuckBrain store.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import cron_runner
from src.core import duckbrain_client


@pytest.fixture()
def temp_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point duckbrain_client's namespace root at a throwaway temp dir."""

    def fake_ensure_namespace(ns: str) -> Path:
        data_dir = tmp_path / ns / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir

    monkeypatch.setattr(duckbrain_client, "_ensure_namespace", fake_ensure_namespace)
    monkeypatch.setattr(duckbrain_client, "DUCKBRAIN_ROOT", tmp_path)
    return tmp_path


def _remember(
    key: str, domain: str, attributes: dict[str, Any], text: str = ""
) -> None:
    """Seed the temp store through the real writer (same shapes MEM-1 writes)."""
    duckbrain_client.remember(
        key=key,
        domain=domain,
        attributes=attributes,
        embedding_text=text or key,
        namespace=cron_runner.BOOT_MEMORY_NAMESPACE,
    )


def _block(text: str, label: str, next_label: str | None = None) -> str:
    """Extract one rendered block body from the boot payload."""
    body = text.split(f"[{label}]\n", 1)[1]
    if next_label is None:
        return body
    return body.split(f"\n[{next_label}]", 1)[0]


def test_boot_blocks_render_populated_store(temp_store: Path) -> None:
    _remember(
        "/game/mechanics/controls",
        "game/mechanics",
        {"fact": "D-pad moves the player one tile; A interacts."},
    )
    _remember(
        "/game/mechanics/battle",
        "game/mechanics",
        {"text": "FIGHT picks a move, then the turn resolves."},
    )
    # No attributes: the embedding text is the only body available.
    _remember("/game/mechanics/text", "game/mechanics", {}, "Press A to advance text.")
    _remember(
        "/game/save/party",
        "game/save",
        {"party_count": 1, "species_hint": "Squirtle"},
    )
    _remember(
        "/game/save/items",
        "game/save",
        {"items": [{"name": "Potion", "count": 3}]},
    )
    _remember(
        "/game/save/location",
        "game/save",
        {"map_id": 40, "map_name": "Oak's Lab", "pos": {"x": 3, "y": 2}},
    )
    _remember(
        "/game/runs/index",
        "game/runs",
        {
            "runs": [
                {
                    "run_id": "mem2-run",
                    "ts": "2026-09-23T04:00:00+00:00",
                    "cycles": 90,
                    "ladder": {
                        "memory_events": 4,
                        "battle_events": 2,
                        "map_progress": "Viridian City",
                        "starter_picked": True,
                    },
                },
                # Legacy digest shape (older harness wrote events, no ladder).
                {
                    "run_id": "old-run",
                    "cycles": 20,
                    "events": {"memory_note": 1, "battle_start": 1},
                    "maps_sequence": ["Pallet Town", "Viridian City"],
                },
            ]
        },
    )
    _remember(
        "/game/learning/navigation",
        "game/learning",
        {"fact": "Oak's Lab exit door is bottom-center (tile ~5,6)."},
    )

    boot = cron_runner._build_boot_memory_blocks()

    assert boot.has_content is True
    assert boot.text.startswith("BOOT MEMORY (from previous runs):")
    assert len(boot.text) <= cron_runner.BOOT_TOTAL_CHAR_BUDGET

    mechanics = _block(boot.text, "MECHANICS", "SAVE")
    assert "/game/mechanics/controls: D-pad moves the player one tile" in mechanics
    assert "/game/mechanics/battle: FIGHT picks a move" in mechanics
    assert "Press A to advance text." in mechanics
    assert "(no mechanics recorded yet)" not in mechanics

    save = _block(boot.text, "SAVE", "RUN HISTORY")
    assert "- party: 1 party member(s); first species Squirtle" in save
    assert "- items: Potion x3" in save
    assert "- location: Oak's Lab (map 40) at 3,2" in save

    runs = _block(boot.text, "RUN HISTORY", "LEARNING")
    assert "mem2-run [2026-09-23]: 90 cycles, memory_events=4, battle_events=2" in runs
    assert "map=Viridian City, starter=yes" in runs
    # Legacy records still render a one-liner instead of being dropped.
    assert "old-run: 20 cycles, memory_events=1, battle_events=1" in runs
    assert "map=Viridian City" in runs

    learning = _block(boot.text, "LEARNING")
    assert "Oak's Lab exit door is bottom-center" in learning

    # The injected prompt section is exactly the rendered payload.
    assert cron_runner._boot_memory_prompt(boot) == boot.text


def test_boot_blocks_are_placeholders_on_empty_store(temp_store: Path) -> None:
    boot = cron_runner._build_boot_memory_blocks()

    assert boot.has_content is False
    assert "(no mechanics recorded yet)" in boot.text
    assert "(no save-state recorded yet)" in boot.text
    assert "(no runs recorded yet)" in boot.text
    assert "(no learning recorded yet)" in boot.text
    for label in ("MECHANICS", "SAVE", "RUN HISTORY", "LEARNING"):
        assert f"[{label}]" in boot.text

    # Placeholder-only payloads are never injected: a fresh clone keeps
    # today's prompt.
    assert cron_runner._boot_memory_prompt(boot) == ""


def test_over_long_entry_is_truncated_to_value_cap(temp_store: Path) -> None:
    _remember(
        "/game/mechanics/battle",
        "game/mechanics",
        {"fact": "battle rule " * 800},
    )

    boot = cron_runner._build_boot_memory_blocks()
    mechanics = _block(boot.text, "MECHANICS", "SAVE")
    line = next(
        ln for ln in mechanics.splitlines() if ln.startswith("- /game/mechanics/battle")
    )

    # One attribute value can never dominate a line.
    body = line.split(": ", 1)[1]
    assert len(body) <= cron_runner.BOOT_VALUE_CHAR_CAP
    assert body.endswith("...")
    assert "battle rule " * 800 not in mechanics


def test_over_long_block_is_truncated_to_block_cap(temp_store: Path) -> None:
    # Many small item values: each stays under the value cap while the
    # assembled SAVE block still blows past the block cap.
    _remember(
        "/game/save/items",
        "game/save",
        {"items": [{"name": f"Item{index:03d}", "count": 1} for index in range(130)]},
    )

    boot = cron_runner._build_boot_memory_blocks()
    save = _block(boot.text, "SAVE", "RUN HISTORY")

    assert boot.has_content is True
    assert len(save) <= cron_runner.BOOT_BLOCK_CHAR_CAP
    assert save.endswith("...")
    assert "Item129" not in save  # the tail was cut by the cap, not by the store
    assert len(boot.text) <= cron_runner.BOOT_TOTAL_CHAR_BUDGET


def test_payload_budget_is_enforced() -> None:
    oversized = "BOOT MEMORY (from previous runs):\n" + "x" * 6000

    capped = cron_runner._cap_boot_payload(oversized)

    assert len(capped) <= cron_runner.BOOT_TOTAL_CHAR_BUDGET
    assert capped.endswith("...")
    assert cron_runner._cap_boot_payload("short") == "short"


def test_runs_index_digest_is_capped_at_last_ten(temp_store: Path) -> None:
    _remember(
        "/game/runs/index",
        "game/runs",
        {
            "runs": [
                {"run_id": f"run-{index}", "cycles": index, "ladder": {}}
                for index in range(15)
            ]
        },
    )

    boot = cron_runner._build_boot_memory_blocks()
    runs = _block(boot.text, "RUN HISTORY", "LEARNING")
    lines = [line for line in runs.splitlines() if line.startswith("- ")]

    assert len(lines) == cron_runner.BOOT_RUNS_DIGEST_LIMIT == 10
    assert "run-0" in lines[0]
    assert "run-14" not in runs


def test_save_state_renders_plain_item_name_lists(temp_store: Path) -> None:
    _remember(
        "/game/save/items",
        "game/save",
        {"items": ["Potion", "Potion", "Antidote"]},
    )

    boot = cron_runner._build_boot_memory_blocks()
    save = _block(boot.text, "SAVE", "RUN HISTORY")

    assert "- items: Antidote x1; Potion x2" in save


def test_boot_injection_failure_is_swallowed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail_get(**kwargs: Any) -> None:
        raise OSError("duckbrain offline")

    monkeypatch.setattr(duckbrain_client, "get", fail_get)

    boot = cron_runner._build_boot_memory_blocks()

    assert boot.text == ""
    assert boot.has_content is False
    assert cron_runner._boot_memory_prompt(boot) == ""
    assert "[MEM] boot injection skipped: duckbrain offline" in capsys.readouterr().out


class _CapturingClient:
    """Minimal OpenRouterClient stand-in that records the prompt it sent."""

    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def chat_completion(self, **kwargs: Any) -> dict[str, Any]:
        self.messages = kwargs["messages"]
        return {"content": '{"plan": ["UP"], "intent": "test"}'}


def _controller_system(boot_memory: str) -> str:
    client = _CapturingClient()
    cron_runner.controller_plan(
        client,
        {"map_name": "Pallet Town"},
        "",
        "",
        boot_memory=boot_memory,
    )
    assert client.messages, "controller_plan sent no messages"
    assert client.messages[0]["role"] == "system"
    return str(client.messages[0]["content"])


def test_prompt_includes_blocks_only_when_nontrivial() -> None:
    plain = _controller_system("")

    # The tool-filing lines are the one unconditional prompt addition.
    assert "TOOL FILING" in plain
    assert "/game/mechanics/*" in plain
    assert "BOOT MEMORY" not in plain

    boot = cron_runner.BootMemory(
        text="BOOT MEMORY (from previous runs):\n[MECHANICS]\n- controls: D-pad.",
        has_content=True,
    )
    injected = _controller_system(cron_runner._boot_memory_prompt(boot))

    # Appended after the existing prompt, byte-for-byte identical otherwise.
    assert injected == f"{plain}\n\n{boot.text}"


def test_prompt_assembly_matches_populated_store(temp_store: Path) -> None:
    _remember(
        "/game/learning/battle",
        "game/learning",
        {"fact": "Type advantage doubles damage; switch before fainting."},
    )

    boot = cron_runner._build_boot_memory_blocks()
    system = _controller_system(cron_runner._boot_memory_prompt(boot))

    assert "BOOT MEMORY (from previous runs):" in system
    assert "Type advantage doubles damage" in system
    # Boot memory must not leak into the per-cycle user message.
    client = _CapturingClient()
    cron_runner.controller_plan(
        client, {"map_name": "Pallet Town"}, "", "", boot_memory=boot.text
    )
    assert "BOOT MEMORY" not in str(client.messages[1]["content"])
