"""Tests for the passive battle-telemetry reader (row BTL-RAM-1).

Contract: ``specs/contracts/battle-telemetry.md`` (row BTL-SCHEMA-1).

Covers:
- AC3 — the sampler is a pure observer: a fake bridge whose every write method
  raises AssertionError is never called by a full capture run.
- AC4 — a deterministic in-repo fixture (32 KiB RAM images) round-trips known
  species/levels/HP/damage/wild-vs-trainer/map/turn through the REAL
  ``RAMReader.read_battle_state()``.
- AC1 — a capture over several exchanges yields one stream per encounter.
- AC2 — every resolved address carries a named source and a verification note,
  and the module holds no address literal of its own.
- §3.3 R2/R4 — out-of-range records are dropped and counted, never nulled.

The fixture writes bytes at the addresses the resolver returns, which is what
makes it a test of the resolver too: ``read_battle_state()`` reads its own
constants, so a fixture frame only decodes correctly when the resolved address
is the address the reader actually uses.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.battle_telemetry import (  # noqa: E402
    ADDRESS_BINDINGS,
    BattleAddressResolver,
    BattleSnapshot,
    BattleTelemetrySampler,
    TelemetryIdentity,
    read_snapshot,
)

RAM_SIZE = 32768
RAM_BASE = 0x8000
REAL_DUMP = REPO_ROOT / "data" / "rom" / "pokemon_red.gb.ram"

# Move ids whose names resolve through ram_reader.MOVE_NAMES, and whose damage
# class the repo's keyword classifier calls the way the fixture needs it.
TACKLE = 33
GROWL = 45

# Species ids from the reader's own tables.
CHARMANDER = 176  # STARTER_SPECIES_NAMES[176]
SQUIRTLE = 177  # STARTER_SPECIES_NAMES[177]
WEEDLE = 106  # POKEMON_NAMES[106]
PIDGEY = 36  # POKEMON_NAMES[36]

ROUTE_2 = 0x0D
PEWTER_CITY = 0x02


def _resolver() -> BattleAddressResolver:
    return BattleAddressResolver()


# ── 32 KiB RAM image fixture ────────────────────────────────────────────────


class RamImage:
    """A 32 KiB Game Boy RAM image addressed exactly like the emulator does."""

    def __init__(self, base: bytes | None = None) -> None:
        self._bytes = bytearray(base or bytes(RAM_SIZE))
        if len(self._bytes) != RAM_SIZE:  # pragma: no cover - fixture guard
            raise AssertionError(f"fixture base must be {RAM_SIZE} bytes")
        self._resolver = _resolver()

    @classmethod
    def from_real_dump(cls) -> "RamImage":
        """Base image from the shipped dump, or zeros when it is not present.

        ``data/rom/*.ram`` is gitignored (``.gitignore`` line 126), so a fresh
        clone has no dump. The overlay writes every byte the reader reads, so
        both bases decode to the same battle — the fixture is self-contained.
        """
        if REAL_DUMP.is_file():
            return cls(REAL_DUMP.read_bytes())
        return cls()

    def _offset(self, field_name: str) -> int:
        return self._resolver.address(field_name) - RAM_BASE

    def set_u8(self, field_name: str, value: int) -> "RamImage":
        self._bytes[self._offset(field_name)] = value & 0xFF
        return self

    def set_u16(self, field_name: str, value: int, *, byte_order: str) -> "RamImage":
        offset = self._offset(field_name)
        high, low = (value >> 8) & 0xFF, value & 0xFF
        if byte_order == "be":
            self._bytes[offset], self._bytes[offset + 1] = high, low
        else:
            self._bytes[offset], self._bytes[offset + 1] = low, high
        return self

    def set_bytes(self, field_name: str, values: list[int]) -> "RamImage":
        offset = self._offset(field_name)
        for index, value in enumerate(values):
            self._bytes[offset + index] = value & 0xFF
        return self

    def to_bytes(self) -> bytes:
        return bytes(self._bytes)


class FakeEmulator:
    """Read-only emulator surface, plus write methods that must never run.

    Every mutating method mirrors the real bridge's naming (``press``,
    ``press_button``, ``step``, ``tick``, ``fast_forward``, ``write_u8``) and
    raises AssertionError, so any accidental write during a capture is a hard
    test failure rather than a silent state change.
    """

    def __init__(self, image: bytes) -> None:
        self.image = bytearray(image)
        self.press_calls = 0
        self.step_calls = 0
        self.write_calls = 0

    # reads
    def read_u8(self, addr: int) -> int:
        return self.image[addr - RAM_BASE]

    def read_u16(self, addr: int) -> int:
        return self.read_u8(addr) | (self.read_u8(addr + 1) << 8)

    # writes — never legal during a passive capture
    def press(self, *_args: Any, **_kwargs: Any) -> None:
        self.press_calls += 1
        raise AssertionError("passive sampler must never press a button")

    def press_button(self, *_args: Any, **_kwargs: Any) -> None:
        self.press_calls += 1
        raise AssertionError("passive sampler must never press a button")

    def step(self, *_args: Any, **_kwargs: Any) -> None:
        self.step_calls += 1
        raise AssertionError("passive sampler must never step the emulator")

    def tick(self, *_args: Any, **_kwargs: Any) -> None:
        self.step_calls += 1
        raise AssertionError("passive sampler must never tick the emulator")

    def fast_forward(self, *_args: Any, **_kwargs: Any) -> None:
        self.step_calls += 1
        raise AssertionError("passive sampler must never advance frames")

    def write_u8(self, *_args: Any, **_kwargs: Any) -> None:
        self.write_calls += 1
        raise AssertionError("passive sampler must never write RAM")

    @property
    def total_writes(self) -> int:
        return self.press_calls + self.step_calls + self.write_calls


class FakeBridge:
    """The object handed to the sampler in AC3: a reader that counts writes."""

    def __init__(self, emulator: FakeEmulator, reader: Any) -> None:
        self._emulator = emulator
        self._reader = reader

    def read_battle_state(self) -> dict[str, Any]:
        return dict(self._reader.read_battle_state())

    def current_map_name(self) -> str:
        return str(self._reader.current_map_name())

    # write surfaces the sampler must never touch
    def press(self, *_args: Any, **_kwargs: Any) -> None:
        self._emulator.press()

    def step(self, *_args: Any, **_kwargs: Any) -> None:
        self._emulator.step()

    def write_u8(self, *_args: Any, **_kwargs: Any) -> None:
        self._emulator.write_u8()

    @property
    def write_calls(self) -> int:
        return self._emulator.total_writes


def _reader_for(image: bytes) -> tuple[Any, FakeEmulator]:
    """Build a real RAMReader over *image* (map DB patched out: unused here)."""
    from src.core.ram_reader import RAMReader

    emulator = FakeEmulator(image)
    with patch("src.core.ram_reader._MapDB"):
        reader = RAMReader(emulator, "/fake/rom.gb")
    return reader, emulator


def _frame(
    *,
    battle_type: int,
    map_id: int,
    player_species: int,
    player_level: int,
    player_hp: int,
    player_max_hp: int,
    player_moves: list[tuple[int, int]],
    enemy_species: int,
    enemy_level: int,
    enemy_hp: int,
    enemy_max_hp: int,
    enemy_moves: list[tuple[int, int]],
    base: bytes | None = None,
) -> bytes:
    """One RAM image: the whole battle state the reader needs, nothing else."""
    image = RamImage.from_real_dump() if base is None else RamImage(base)
    image.set_u8("in_battle", battle_type)
    image.set_u8("map_id", map_id)
    image.set_u8("player_species", player_species)
    image.set_u8("player_level", player_level)
    # The reader validates byte order, so player HP/max HP are BIG-endian
    # (the SGB Enhanced ROM layout its comments document).
    image.set_u16("player_hp", player_hp, byte_order="be")
    image.set_u16("player_max_hp", player_max_hp, byte_order="be")
    image.set_bytes("player_moves", [move for move, _pp in player_moves])
    image.set_bytes("player_pp", [pp for _move, pp in player_moves])
    image.set_u8("player_type1", 0x14)  # FIRE
    image.set_u8("player_type2", 0x14)
    image.set_u8("enemy_species", enemy_species)
    image.set_u8("enemy_level", enemy_level)
    # Live enemy HP is little-endian, enemy max HP big-endian — the reader's
    # documented asymmetry (0xCEE9 damage-proven LE; party struct BE).
    image.set_u16("enemy_hp", enemy_hp, byte_order="le")
    image.set_u16("enemy_max_hp", enemy_max_hp, byte_order="be")
    image.set_bytes("enemy_moves", [move for move, _pp in enemy_moves])
    image.set_bytes("enemy_pp", [pp for _move, pp in enemy_moves])
    image.set_u8("enemy_type1", 0x15)  # WATER
    image.set_u8("enemy_type2", 0x15)
    return image.to_bytes()


# ── the AC4 encounter fixture ───────────────────────────────────────────────

#: Encounter A — wild Weedle L3 (max HP 15) on Route 2, player
#: Charmander L8 (max HP 25). One tuple per sample tick; the numbers are the
#: fixture's ground truth and are asserted side by side with the records.
ENCOUNTER_A_FRAMES: list[dict[str, Any]] = [
    # battle start: nothing has happened yet
    dict(
        player_hp=24,
        player_pp=[35, 30],
        enemy_hp=15,
        enemy_pp=[35],
    ),
    # turn 1 — player Tackle 15->11, enemy Tackle 24->22
    dict(player_hp=22, player_pp=[34, 30], enemy_hp=11, enemy_pp=[34]),
    # turn 2 — player Tackle whiffs: PP down, enemy HP unchanged, no enemy act
    dict(player_hp=22, player_pp=[33, 30], enemy_hp=11, enemy_pp=[34]),
    # turn 3 — player Tackle 11->6
    dict(player_hp=22, player_pp=[32, 30], enemy_hp=6, enemy_pp=[34]),
    # turn 4 — player Tackle 6->0: KO, damage == remaining HP
    dict(player_hp=22, player_pp=[31, 30], enemy_hp=0, enemy_pp=[34]),
]

ENCOUNTER_A_EXPECTED: list[dict[str, Any]] = [
    {
        "turn": 1,
        "attacker_side": "player",
        "move": "Tackle",
        "outcome": "damage",
        "damage": 4,
        "defender_hp_before": 15,
        "defender_hp_after": 11,
    },
    {
        "turn": 1,
        "attacker_side": "enemy",
        "move": "Tackle",
        "outcome": "damage",
        "damage": 2,
        "defender_hp_before": 24,
        "defender_hp_after": 22,
    },
    {
        "turn": 2,
        "attacker_side": "player",
        "move": "Tackle",
        "outcome": "miss",
        "damage": 0,
        "defender_hp_before": 11,
        "defender_hp_after": 11,
    },
    {
        "turn": 3,
        "attacker_side": "player",
        "move": "Tackle",
        "outcome": "damage",
        "damage": 5,
        "defender_hp_before": 11,
        "defender_hp_after": 6,
    },
    {
        "turn": 4,
        "attacker_side": "player",
        "move": "Tackle",
        "outcome": "damage",
        "damage": 6,
        "defender_hp_before": 6,
        "defender_hp_after": 0,
    },
]


def _encounter_a_images() -> list[bytes]:
    base: bytes | None = None
    images: list[bytes] = []
    for frame in ENCOUNTER_A_FRAMES:
        image = _frame(
            battle_type=1,
            map_id=ROUTE_2,
            player_species=CHARMANDER,
            player_level=8,
            player_hp=frame["player_hp"],
            player_max_hp=25,
            player_moves=[
                (TACKLE, frame["player_pp"][0]),
                (GROWL, frame["player_pp"][1]),
            ],
            enemy_species=WEEDLE,
            enemy_level=3,
            enemy_hp=frame["enemy_hp"],
            enemy_max_hp=15,
            enemy_moves=[(TACKLE, frame["enemy_pp"][0])],
            base=base,
        )
        base = image
        images.append(image)
    return images


def _encounter_b_images(base: bytes) -> list[bytes]:
    """Encounter B — trainer Pidgey L5 (max HP 20) in Pewter City."""
    frames = [
        dict(player_hp=22, player_pp=[30, 28], enemy_hp=20, enemy_pp=[35, 20]),
        dict(player_hp=22, player_pp=[30, 27], enemy_hp=20, enemy_pp=[35, 20]),
        dict(player_hp=19, player_pp=[29, 27], enemy_hp=16, enemy_pp=[34, 20]),
    ]
    images: list[bytes] = []
    for index, frame in enumerate(frames):
        image = _frame(
            battle_type=2,
            map_id=PEWTER_CITY,
            player_species=CHARMANDER,
            player_level=8,
            player_hp=frame["player_hp"],
            player_max_hp=25,
            player_moves=[
                (TACKLE, frame["player_pp"][0]),
                (GROWL, frame["player_pp"][1]),
            ],
            enemy_species=PIDGEY,
            enemy_level=5,
            enemy_hp=frame["enemy_hp"],
            enemy_max_hp=20,
            enemy_moves=[(TACKLE, frame["enemy_pp"][0]), (GROWL, frame["enemy_pp"][1])],
            base=base if index == 0 else None,
        )
        images.append(image)
    return images


def _sequence_source(images: list[bytes]) -> Any:
    """A source that advances one RAM image per read (the capture cadence)."""

    class _Sequence:
        def __init__(self) -> None:
            self._frames = [_reader_for(image)[0] for image in images]
            self._index = 0
            self._last = 0

        def read_battle_state(self) -> dict[str, Any]:
            if self._index >= len(self._frames):
                raise AssertionError("capture read past the end of the fixture")
            self._last = min(self._index, len(self._frames) - 1)
            self._index += 1
            return self._frames[self._last].read_battle_state()

        def current_map_name(self) -> str:
            return str(self._frames[self._last].current_map_name())

    return _Sequence()


def _identity(**overrides: Any) -> TelemetryIdentity:
    payload: dict[str, Any] = dict(
        run_id="20261117_090000",
        episode=4,
        decision_arm="DECISION_MODE=llm",
        model_decision="deepseek-v4-flash",
        model_vision=None,
        provider="deepseek",
    )
    payload.update(overrides)
    return TelemetryIdentity(**payload)


TICK = "2026-11-17T09:00:00Z"


# ── AC4: fixture round-trip through the real reader ─────────────────────────


def test_fixture_round_trips_known_battle_through_reader() -> None:
    """AC4 — the fixture's numbers reach the records unchanged."""
    images = _encounter_a_images()

    # Premise: the REAL reader decodes the fixture exactly as specified.
    reader, _emu = _reader_for(images[1])
    state = reader.read_battle_state()
    assert state["battle_type"] == "wild"
    assert state["player"]["name"] == "Charmander"
    assert state["player"]["level"] == 8
    assert state["player"]["hp"] == 22
    assert state["player"]["max_hp"] == 25
    assert state["enemy"]["name"] == "Weedle"
    assert state["enemy"]["level"] == 3
    assert state["enemy"]["hp"] == 11
    assert state["enemy"]["max_hp"] == 15
    assert [move["name"] for move in state["player"]["moves"]] == ["Tackle", "Growl"]
    assert reader.current_map_name() == "Route 2"

    sampler = BattleTelemetrySampler(_sequence_source(images), _identity())
    for _ in images:
        sampler.sample(ts=TICK)

    records = sampler.records
    assert len(records) == len(ENCOUNTER_A_EXPECTED)
    for record, expected in zip(records, ENCOUNTER_A_EXPECTED, strict=True):
        for key, value in expected.items():
            assert record[key] == value, f"{key}: {record[key]!r} != {value!r}"
        # Identity: species/levels on BOTH sides, wild flag, map, episode.
        assert record["battle_type"] == "wild"
        assert record["map"] == "Route 2"
        assert record["map_resolved"] is True
        assert record["episode"] == 4
        assert record["encounter_id"] == "ep004-enc001"
        assert record["run_id"] == "20261117_090000"
        if record["attacker_side"] == "player":
            assert record["attacker_species"] == "Charmander"
            assert record["attacker_level"] == 8
            assert record["defender_species"] == "Weedle"
            assert record["defender_level"] == 3
            assert record["defender_max_hp"] == 15
        else:
            assert record["attacker_species"] == "Weedle"
            assert record["attacker_level"] == 3
            assert record["defender_species"] == "Charmander"
            assert record["defender_level"] == 8
            assert record["defender_max_hp"] == 25

    # The KO record's damage IS the defender's remaining HP (§3.3 R5).
    ko = records[-1]
    assert ko["defender_hp_before"] == 6
    assert ko["defender_hp_after"] == 0
    assert ko["damage"] == 6
    assert ko["encounter_outcome"] == "won"
    # Percent of max, 1 dp, computed from the measured delta.
    assert ko["damage_pct_of_max"] == round(6 / 15 * 100, 1)


def test_fixture_works_on_the_shipped_dump_base() -> None:
    """The same numbers decode when the base image is the shipped RAM dump."""
    images = _encounter_a_images()
    sampler = BattleTelemetrySampler(_sequence_source(images), _identity())
    for _ in images:
        sampler.sample(ts=TICK)
    damages = [
        (rec["turn"], rec["attacker_side"], rec["damage"]) for rec in sampler.records
    ]
    assert damages == [
        (1, "player", 4),
        (1, "enemy", 2),
        (2, "player", 0),
        (3, "player", 5),
        (4, "player", 6),
    ]
    if REAL_DUMP.is_file():
        # The shipped dump itself carries no battle state — recorded honestly
        # so a later reader knows the fixture overlay is what supplies it.
        reader, _emu = _reader_for(REAL_DUMP.read_bytes())
        raw = reader.read_battle_state()
        assert raw["battle_type"] == "unknown"
        assert raw["enemy"]["hp"] == 0


def test_non_damaging_move_records_no_damage() -> None:
    """A status move that deals nothing is ``no_damage``, not a miss (§3)."""
    images = _encounter_b_images(_encounter_a_images()[-1])
    sampler = BattleTelemetrySampler(_sequence_source(images), _identity())
    for _ in images:
        sampler.sample(ts=TICK)
    growl = [rec for rec in sampler.records if rec["move"] == "Growl"]
    assert growl, "the Growl turn produced no record"
    assert growl[0]["outcome"] == "no_damage"
    assert growl[0]["damage"] == 0
    assert growl[0]["defender_hp_before"] == growl[0]["defender_hp_after"] == 20


# ── AC1: one stream per encounter over several exchanges ────────────────────


def test_capture_yields_one_stream_per_encounter() -> None:
    """AC1 — two encounters, N>1 exchanges, grouped by encounter_id."""
    first = _encounter_a_images()
    second = _encounter_b_images(first[-1])
    sampler = BattleTelemetrySampler(_sequence_source(first + second), _identity())
    for _ in first + second:
        sampler.sample(ts=TICK)

    records = sampler.records
    assert len(records) == 8
    streams: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        streams.setdefault(record["encounter_id"], []).append(record)
    assert sorted(streams) == ["ep004-enc001", "ep004-enc002"]

    wild = streams["ep004-enc001"]
    trainer = streams["ep004-enc002"]
    assert {rec["battle_type"] for rec in wild} == {"wild"}
    assert {rec["battle_type"] for rec in trainer} == {"trainer"}
    assert {rec["map"] for rec in wild} == {"Route 2"}
    assert {rec["map"] for rec in trainer} == {"Pewter City"}
    assert {rec["defender_species"] for rec in trainer} == {"Charmander", "Pidgey"}
    assert [rec["turn"] for rec in wild] == sorted(rec["turn"] for rec in wild)
    assert [rec["turn"] for rec in trainer] == sorted(rec["turn"] for rec in trainer)
    assert trainer[0]["turn"] == 1  # turn restarts per encounter
    assert {rec["attacker_level"] for rec in trainer} == {8, 5}

    encounters = sampler.encounters
    assert [enc.encounter_id for enc in encounters] == [
        "ep004-enc001",
        "ep004-enc002",
    ]
    assert encounters[0].partition_filename() == (
        "battle-20261117_090000-ep004-enc001.jsonl"
    )
    assert encounters[0].turns == 4
    assert encounters[0].outcome == "won"
    assert encounters[1].opponent_species == "Pidgey"
    assert encounters[1].records == 3


def test_records_carry_every_contract_field() -> None:
    """§3.1 (11 identity keys) + §3.2 (17 event fields) — spelled as tabled."""
    identity_keys = {
        "run_id",
        "episode",
        "encounter_id",
        "turn",
        "map",
        "map_resolved",
        "ts",
        "model_decision",
        "model_vision",
        "provider",
        "decision_arm",
    }
    event_fields = {
        "attacker_side",
        "attacker_species",
        "attacker_species_resolved",
        "attacker_level",
        "defender_species",
        "defender_species_resolved",
        "defender_level",
        "battle_type",
        "move",
        "move_resolved",
        "outcome",
        "damage",
        "damage_pct_of_max",
        "defender_hp_before",
        "defender_hp_after",
        "defender_max_hp",
        "encounter_outcome",
    }
    images = _encounter_a_images()
    sampler = BattleTelemetrySampler(_sequence_source(images), _identity())
    for _ in images:
        sampler.sample(ts=TICK)
    assert len(identity_keys) == 11
    assert len(event_fields) == 17
    for record in sampler.records:
        assert identity_keys <= set(record)
        assert event_fields <= set(record)
        assert record["ts"] == TICK
        assert record["decision_arm"] == "DECISION_MODE=llm"
        assert record["model_decision"] == "deepseek-v4-flash"
        assert record["provider"] == "deepseek"
        assert record["model_vision"] is None


# ── AC3: the sampler never writes ───────────────────────────────────────────


def test_sampler_never_calls_a_write_method_on_the_bridge() -> None:
    """AC3 — fake bridge whose press/step/write all raise; call count stays 0."""
    images = _encounter_a_images() + _encounter_b_images(_encounter_a_images()[-1])
    reader, emulator = _reader_for(images[0])

    class _Frames:
        def __init__(self) -> None:
            self.index = 0

        def _current(self) -> tuple[bytes, Any]:
            frame = images[min(self.index, len(images) - 1)]
            return frame, _reader_for(frame)[0]

        def read_battle_state(self) -> dict[str, Any]:
            _frame_bytes, frame_reader = self._current()
            state = frame_reader.read_battle_state()
            self.index += 1
            return state

        def current_map_name(self) -> str:
            _frame_bytes, frame_reader = self._current()
            return str(frame_reader.current_map_name())

    del reader
    bridge = FakeBridge(emulator, _Frames())
    sampler = BattleTelemetrySampler(bridge, _identity())
    emitted = 0
    for _ in images:
        emitted += len(sampler.sample(ts=TICK))

    assert emitted == 8, "the capture run must actually produce records"
    assert bridge.write_calls == 0
    assert emulator.press_calls == 0
    assert emulator.step_calls == 0
    assert emulator.write_calls == 0
    # And the sampler holds no writer surface at all.
    for attribute in ("press", "step", "advance", "wait"):
        assert not hasattr(sampler, attribute)


# ── AC2: address resolution evidence ───────────────────────────────────────


def test_every_resolved_address_has_a_source_and_a_note() -> None:
    """AC2 — symbol, named source and basis on every resolved address."""
    resolver = _resolver()
    resolved = resolver.resolve_all()
    assert set(resolved) == set(ADDRESS_BINDINGS)
    for field_name, entry in resolved.items():
        assert entry.field_name == field_name
        assert entry.symbol
        assert entry.source in ("sym-file", "reader-constant-block")
        assert entry.source_detail
        assert entry.basis
        assert entry.verified
        note = entry.verification_note
        assert entry.symbol in note
        assert entry.source in note
        assert entry.basis in note
        assert f"0x{entry.address:04X}" in note
    # No symbol map ships today, so the constant block is the attested source.
    assert resolver.sym_files == []
    assert {entry.source for entry in resolved.values()} == {"reader-constant-block"}


def test_resolved_addresses_equal_the_reader_constants() -> None:
    """Every resolved number is the reader's own constant — never a new literal."""
    from src.core import ram_reader

    resolver = _resolver()
    for field_name, binding in ADDRESS_BINDINGS.items():
        assert resolver.address(field_name) == getattr(ram_reader, binding.constant)


def test_enemy_struct_offsets_match_the_constant_block() -> None:
    """The binding offsets reproduce the reader's party-struct addresses."""
    resolver = _resolver()
    base = resolver.address("enemy_species")
    for field_name, binding in ADDRESS_BINDINGS.items():
        if field_name == "enemy_hp":
            continue  # live HP-bar mirror, not a party-struct field
        if not field_name.startswith("enemy_"):
            continue
        assert resolver.address(field_name) == base + binding.offset, field_name


def test_symbol_file_takes_precedence_and_records_conflicts(tmp_path: Path) -> None:
    """A ``*.sym`` map resolves by symbol; a disagreement is recorded, not hidden."""
    constants = _resolver()
    lines = []
    seen: set[str] = set()
    for field_name, binding in ADDRESS_BINDINGS.items():
        if field_name == "map_id":
            continue  # stays sym-less so the constant-block fallback is proven
        if binding.symbol in seen:
            continue  # one line per symbol, as an RGBDS map would have
        seen.add(binding.symbol)
        address = constants.address(field_name) - binding.offset
        lines.append(f"00:{address:04x} {binding.symbol}")
    # A deliberately wrong entry to prove conflicts surface.
    lines.append(f"00:{0xD014:04x} wIsInBattle")
    (tmp_path / "pokemon.sym").write_text("\n".join(lines) + "\n", encoding="utf-8")

    resolver = BattleAddressResolver(sym_dir=tmp_path)
    assert resolver.sym_files and resolver.sym_files[0].endswith("pokemon.sym")
    enemy = resolver.resolve("enemy_level")
    assert enemy.source == "sym-file"
    assert "offset +33" in enemy.source_detail
    assert enemy.address == constants.address("enemy_level")
    # wCurMap came only from the constant block (no sym line was written).
    assert resolver.resolve("map_id").source == "reader-constant-block"
    resolver.resolve_all()  # conflicts are recorded on resolution
    conflicts = resolver.conflicts
    assert len(conflicts) == 1
    assert "wIsInBattle" in conflicts[0]
    assert "symbol file wins" in conflicts[0]


def test_module_holds_no_address_literal_of_its_own() -> None:
    """AC2 — no hex address literal in the module's CODE, only attested lookups.

    Scanned with the tokenizer, not a regex: hex mentions inside string literals
    are evidence quotes from the reader's own annotations (``0xB1 Squirtle``,
    ``0xCFE7``), not addresses the module uses. ``0xFFFF`` is the 16-bit wrap
    mask for symbol arithmetic and is explicitly not an address.
    """
    import io
    import tokenize

    path = REPO_ROOT / "src" / "core" / "battle_telemetry.py"
    source = path.read_text(encoding="utf-8")
    hex_values: list[int] = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type != tokenize.NUMBER:
            continue
        text = token.string
        if text.lower().startswith("0x"):
            hex_values.append(int(text, 16))
    allowed_structural = {0xFFFF}
    resolved = {entry.address for entry in _resolver().resolve_all().values()}
    offenders = [
        value
        for value in hex_values
        if value not in allowed_structural or value in resolved
    ]
    assert offenders == [], f"hex address literals in module code: {offenders}"
    assert not (allowed_structural & resolved)

    # And the only source of truth is the reader's constant block.
    from src.core import ram_reader

    for binding in ADDRESS_BINDINGS.values():
        assert hasattr(ram_reader, binding.constant)


def test_resolver_rejects_unknown_field() -> None:
    with pytest.raises(Exception) as excinfo:
        _resolver().resolve("not_a_field")
    assert "unknown address field" in str(excinfo.value)


# ── §3.3 R2/R4: drop and count, never write a null ─────────────────────────


def test_out_of_range_level_drops_the_record_and_counts_it() -> None:
    """§3.3 R2 — level 1 is outside 2..100, so the record is dropped."""
    good = _encounter_a_images()
    # Rebuild the same encounter with an out-of-range defender level.
    bad_frames = [
        _frame(
            battle_type=1,
            map_id=ROUTE_2,
            player_species=CHARMANDER,
            player_level=8,
            player_hp=frame["player_hp"],
            player_max_hp=25,
            player_moves=[
                (TACKLE, frame["player_pp"][0]),
                (GROWL, frame["player_pp"][1]),
            ],
            enemy_species=WEEDLE,
            enemy_level=1,
            enemy_hp=frame["enemy_hp"],
            enemy_max_hp=15,
            enemy_moves=[(TACKLE, frame["enemy_pp"][0])],
        )
        for frame in ENCOUNTER_A_FRAMES
    ]
    del good
    sampler = BattleTelemetrySampler(_sequence_source(bad_frames), _identity())
    for _ in bad_frames:
        sampler.sample(ts=TICK)
    assert sampler.records == []
    assert sampler.dropped_records == 5
    assert all(
        "outside 2..100" in " ".join(d["violations"]) for d in sampler.dropped_details
    )


def test_unreadable_attacker_level_is_dropped_not_nulled() -> None:
    """A zeroed level (no battle state in RAM) is out of range → dropped."""
    blank = RamImage.from_real_dump()
    blank.set_u8("in_battle", 1)
    blank.set_u8("player_species", CHARMANDER)
    blank.set_u8("enemy_species", WEEDLE)
    blank.set_u8("enemy_level", 3)
    blank.set_u8("player_level", 8)
    blank.set_u16("player_max_hp", 25, byte_order="be")
    blank.set_u16("player_hp", 20, byte_order="be")
    blank.set_u16("enemy_max_hp", 15, byte_order="be")
    blank.set_u16("enemy_hp", 10, byte_order="le")
    before = blank.to_bytes()

    after = RamImage(before)
    after.set_u16("enemy_hp", 7, byte_order="le")

    class _Pair:
        def __init__(self) -> None:
            self._states = [_reader_for(before)[0], _reader_for(after.to_bytes())[0]]
            self._index = 0

        def read_battle_state(self) -> dict[str, Any]:
            reader = self._states[min(self._index, 1)]
            self._index += 1
            return reader.read_battle_state()

        def current_map_name(self) -> str:
            return "Route 2"

    sampler = BattleTelemetrySampler(_Pair(), _identity())
    sampler.sample(ts=TICK)  # baseline frame, no PP data
    emitted = sampler.sample(ts=TICK)
    # No PP channel exists in this source, so the HP-drop fallback fires and the
    # move label is honestly unresolved.
    assert len(emitted) == 1
    assert emitted[0]["move"] == "Move#0"
    assert emitted[0]["move_resolved"] is False
    assert emitted[0]["damage"] == 3
    assert emitted[0]["outcome"] == "damage"  # the measured delta decides


# ── encounter lifecycle ────────────────────────────────────────────────────


def test_battle_end_closes_the_encounter_and_next_battle_gets_a_new_id() -> None:
    images = _encounter_a_images()
    ended = _frame(
        battle_type=0,
        map_id=ROUTE_2,
        player_species=CHARMANDER,
        player_level=8,
        player_hp=22,
        player_max_hp=25,
        player_moves=[(TACKLE, 31), (GROWL, 30)],
        enemy_species=WEEDLE,
        enemy_level=3,
        enemy_hp=0,
        enemy_max_hp=15,
        enemy_moves=[(TACKLE, 34)],
    )
    restart = _frame(
        battle_type=1,
        map_id=ROUTE_2,
        player_species=CHARMANDER,
        player_level=8,
        player_hp=22,
        player_max_hp=25,
        player_moves=[(TACKLE, 31), (GROWL, 30)],
        enemy_species=WEEDLE,
        enemy_level=4,
        enemy_hp=9,
        enemy_max_hp=9,
        enemy_moves=[(TACKLE, 34)],
    )
    later = RamImage(restart)
    later.set_u16("enemy_hp", 5, byte_order="le")
    later.set_bytes("player_pp", [30, 30])  # one more Tackle: a real action
    frames = images + [ended, restart, later.to_bytes()]
    sampler = BattleTelemetrySampler(_sequence_source(frames), _identity())
    for _ in frames:
        sampler.sample(ts=TICK)
    assert [enc.encounter_id for enc in sampler.encounters] == [
        "ep004-enc001",
        "ep004-enc002",
    ]
    assert sampler.encounters[0].outcome == "won"
    assert sampler.encounters[1].outcome == "unknown"
    assert sampler.records[-1]["encounter_id"] == "ep004-enc002"
    assert sampler.records[-1]["damage"] == 4


def test_start_episode_resets_turn_and_ordinal() -> None:
    images = _encounter_a_images()
    sampler = BattleTelemetrySampler(_sequence_source(images), _identity())
    for _ in images:
        sampler.sample(ts=TICK)
    sampler.start_episode(5, ts=TICK)
    assert sampler.turn == 0
    assert sampler.encounters[0].episode == 4


# ── the script: --help and an end-to-end capture ───────────────────────────


def _load_capture_script() -> Any:
    path = REPO_ROOT / "scripts" / "capture_battle_telemetry.py"
    spec = importlib.util.spec_from_file_location("capture_battle_telemetry", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_capture_script_writes_contract_shaped_jsonl(tmp_path: Path) -> None:
    module = _load_capture_script()
    out = tmp_path / "capture.jsonl"
    rc = module.main(
        [
            "--builtin-fixture",
            "--out",
            str(out),
            "--run-id",
            "20261117_090000",
            "--episode",
            "4",
            "--decision-arm",
            "DECISION_MODE=llm",
        ]
    )
    assert rc == 0
    lines = [json.loads(line) for line in out.read_text().splitlines() if line.strip()]
    assert lines, "the capture wrote no records"
    for record in lines:
        assert record["run_id"] == "20261117_090000"
        assert record["episode"] == 4
        assert record["encounter_id"].startswith("ep004-enc")
        assert isinstance(record["damage"], int)
    encounter_ids = {record["encounter_id"] for record in lines}
    assert encounter_ids == {"ep004-enc001", "ep004-enc002"}


def test_capture_script_help_and_partitioned_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load_capture_script()
    with pytest.raises(SystemExit) as exitinfo:
        module.main(["--help"])
    assert exitinfo.value.code == 0
    assert "--builtin-fixture" in capsys.readouterr().out

    out_dir = tmp_path / "data"
    rc = module.main(
        [
            "--builtin-fixture",
            "--out-dir",
            str(out_dir),
            "--run-id",
            "20261117_090000",
            "--episode",
            "4",
        ]
    )
    assert rc == 0
    files = sorted(path.name for path in out_dir.iterdir())
    assert files == [
        "battle-20261117_090000-ep004-enc001.jsonl",
        "battle-20261117_090000-ep004-enc002.jsonl",
    ]
    for path in out_dir.iterdir():
        first = json.loads(path.read_text().splitlines()[0])
        assert first["encounter_id"] in path.name


def test_capture_script_verify_addresses_prints_notes(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_capture_script()
    rc = module.main(["--verify-addresses"])
    assert rc == 0
    out = capsys.readouterr().out
    for field_name in ("in_battle", "player_hp", "enemy_hp", "enemy_level"):
        assert field_name in out
    assert "source=reader-constant-block" in out
    assert "basis=" in out


def test_snapshot_reports_unresolved_placeholders() -> None:
    """Unresolved species/move/map labels are flagged, never silently joined."""
    image = RamImage.from_real_dump()
    image.set_u8("in_battle", 1)
    image.set_u8("map_id", 0xEE)  # no MAP_NAMES entry → Map_EE
    image.set_u8("player_species", 200)
    image.set_u8("player_level", 9)
    image.set_u8("player_max_hp", 20)
    image.set_u8("player_moves", 250)  # not in MOVE_NAMES → Move#250
    image.set_u8("player_pp", 10)
    image.set_u8("enemy_species", 201)
    image.set_u8("enemy_level", 4)
    image.set_u8("enemy_max_hp", 12)
    reader, _emu = _reader_for(image.to_bytes())
    snapshot: BattleSnapshot = read_snapshot(reader)
    assert snapshot.map_name == "Map_EE"
    assert snapshot.map_resolved is False
    assert snapshot.player.species == "#200"
    assert snapshot.player.first_move_label == "Move#250"
