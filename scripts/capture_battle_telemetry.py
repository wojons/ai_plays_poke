#!/usr/bin/env python3
"""Capture contract-shaped battle telemetry from RAM (row BTL-RAM-1).

Contract: ``specs/contracts/battle-telemetry.md``. The sampler lives in
``src/core/battle_telemetry.py``; this script only DRIVES it from a fixture and
writes the JSONL the contract specifies.

Sources (combine freely; they are consumed in the order given):

  --ram-image PATH        a 32 KiB Game Boy RAM image (0x8000..0xFFFF). Repeat
                          it once per capture tick; each image is one sample.
  --state-sequence PATH   a JSON file holding a list of battle-state dicts in
                          the shape ``RAMReader.read_battle_state()`` returns,
                          each optionally carrying a top-level ``map_name``.
  --builtin-fixture       a deterministic two-encounter capture built in-process
                          from ``data/rom/pokemon_red.gb.ram`` when that dump is
                          present, else from a zeroed 32 KiB image (``data/rom``
                          ``*.ram`` is gitignored, so a fresh clone has none).

Output:

  --out PATH              one JSONL file with every record.
  --out-dir DIR           one file per encounter, named per contract §4.1
                          (``battle-<run_id>-ep<EEE>-enc<CCC>.jsonl``).
  --print-records         write the records to stdout as JSONL.

With no output option the records go to stdout. A one-line JSON summary always
goes to stderr. No emulator is attached and nothing is pressed: a capture run
reads memory and writes files.

Examples:

    ./venv/bin/python scripts/capture_battle_telemetry.py --builtin-fixture \\
        --out /tmp/battle.jsonl --run-id 20261117_090000 --episode 4
    ./venv/bin/python scripts/capture_battle_telemetry.py --verify-addresses
    ./venv/bin/python scripts/capture_battle_telemetry.py --ram-image a.ram \\
        --ram-image b.ram --out-dir /tmp/telemetry
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.battle_telemetry import (  # noqa: E402
    BattleAddressResolver,
    BattleTelemetrySampler,
    TelemetryIdentity,
    TelemetrySourceError,
)
from src.core.ram_reader import RAMReader  # noqa: E402

#: The 32 KiB RAM window a dump covers: 0x8000..0xFFFF.
RAM_WINDOW_START = 0x8000
RAM_WINDOW_SIZE = 32768

#: Where the shipped (gitignored) RAM dump lives, used as the fixture base.
BUILTIN_RAM_DUMP = REPO_ROOT / "data" / "rom" / "pokemon_red.gb.ram"


class ImageMemory:
    """Read-only emulator surface over one RAM image."""

    def __init__(self, image: bytes) -> None:
        if len(image) != RAM_WINDOW_SIZE:
            raise TelemetrySourceError(
                f"RAM image must be {RAM_WINDOW_SIZE} bytes, got {len(image)}"
            )
        self._image = image

    def read_u8(self, addr: int) -> int:
        offset = addr - RAM_WINDOW_START
        if not 0 <= offset < RAM_WINDOW_SIZE:
            raise TelemetrySourceError(
                f"address outside the dumped RAM window: 0x{addr:04X}"
            )
        return self._image[offset]

    def read_u16(self, addr: int) -> int:
        return self.read_u8(addr) | (self.read_u8(addr + 1) << 8)


class _WindowReader(RAMReader):
    """A ``RAMReader`` that needs no ROM file.

    ``read_battle_state()`` and ``current_map_name()`` read WRAM and the
    module-level ``MAP_NAMES`` table only — no ROM map data — so a capture over
    a raw RAM image works on a machine with no ROM dump at all.
    """

    def __init__(self, memory: ImageMemory) -> None:
        self._emu = memory
        self._mapdb = None  # type: ignore[assignment]  # unused by battle reads


class CaptureTick(Protocol):
    """One capture tick: the two read-only calls the sampler makes."""

    def read_battle_state(self) -> dict[str, Any]:  # pragma: no cover - protocol
        ...

    def current_map_name(self) -> str:  # pragma: no cover - protocol
        ...


class RamImageTick:
    """One tick decoded from a RAM image by the real ``RAMReader``."""

    def __init__(self, image: bytes) -> None:
        self._reader = _WindowReader(ImageMemory(image))

    def read_battle_state(self) -> dict[str, Any]:
        return self._reader.read_battle_state()

    def current_map_name(self) -> str:
        return str(self._reader.current_map_name())


class SequenceTick:
    """One tick replayed from a recorded battle-state dict."""

    def __init__(self, state: Mapping[str, Any]) -> None:
        self._state = dict(state)

    def read_battle_state(self) -> dict[str, Any]:
        return {key: value for key, value in self._state.items() if key != "map_name"}

    def current_map_name(self) -> str:
        return str(self._state.get("map_name", "Map_00"))


class FrameStream:
    """The ordered tick stream one capture run consumes, one tick per sample."""

    def __init__(self, ticks: Sequence[CaptureTick]) -> None:
        if not ticks:
            raise ValueError("a capture run needs at least one tick")
        self._ticks = list(ticks)
        self._index = 0
        self._last = 0

    def __len__(self) -> int:
        return len(self._ticks)

    def read_battle_state(self) -> dict[str, Any]:
        self._last = min(self._index, len(self._ticks) - 1)
        self._index += 1
        return self._ticks[self._last].read_battle_state()

    def current_map_name(self) -> str:
        return self._ticks[self._last].current_map_name()


# ── the builtin fixture ─────────────────────────────────────────────────────

#: Ids taken from the reader's own tables (RAMReader._pokemon_name/_move_name).
_CHARMANDER = 176
_WEEDLE = 106
_PIDGEY = 36
_TACKLE = 33
_GROWL = 45
_ROUTE_2 = 0x0D
_PEWTER_CITY = 0x02


def _fixture_image(
    resolver: BattleAddressResolver,
    base: bytes,
    *,
    battle_type: int,
    map_id: int,
    player_species: int,
    player_level: int,
    player_hp: int,
    player_max_hp: int,
    player_moves: Sequence[tuple[int, int]],
    enemy_species: int,
    enemy_level: int,
    enemy_hp: int,
    enemy_max_hp: int,
    enemy_moves: Sequence[tuple[int, int]],
) -> bytes:
    """Overlay one battle state onto *base* at the resolver's addresses."""
    image = bytearray(base)

    def write_u8(field_name: str, value: int) -> None:
        image[resolver.address(field_name) - RAM_WINDOW_START] = value & 0xFF

    def write_u16(field_name: str, value: int, *, byte_order: str) -> None:
        offset = resolver.address(field_name) - RAM_WINDOW_START
        high, low = (value >> 8) & 0xFF, value & 0xFF
        if byte_order == "be":
            image[offset], image[offset + 1] = high, low
        else:
            image[offset], image[offset + 1] = low, high

    def write_bytes(field_name: str, values: Iterable[int]) -> None:
        offset = resolver.address(field_name) - RAM_WINDOW_START
        for index, value in enumerate(values):
            image[offset + index] = value & 0xFF

    write_u8("in_battle", battle_type)
    write_u8("map_id", map_id)
    write_u8("player_species", player_species)
    write_u8("player_level", player_level)
    write_u16("player_hp", player_hp, byte_order="be")
    write_u16("player_max_hp", player_max_hp, byte_order="be")
    write_bytes("player_moves", [move for move, _pp in player_moves])
    write_bytes("player_pp", [pp for _move, pp in player_moves])
    write_u8("enemy_species", enemy_species)
    write_u8("enemy_level", enemy_level)
    write_u16("enemy_hp", enemy_hp, byte_order="le")
    write_u16("enemy_max_hp", enemy_max_hp, byte_order="be")
    write_bytes("enemy_moves", [move for move, _pp in enemy_moves])
    write_bytes("enemy_pp", [pp for _move, pp in enemy_moves])
    return bytes(image)


def builtin_fixture_images(resolver: BattleAddressResolver) -> list[bytes]:
    """A deterministic two-encounter capture (wild Weedle, then trainer Pidgey).

    Encounter one mirrors the contract's worked-example shape: four player turns
    including a whiff, a normal hit and a KO whose damage is the remaining HP.
    Encounter two is a trainer battle with a status move (``Growl`` →
    ``no_damage``) and an enemy counter-attack.
    """
    base = (
        BUILTIN_RAM_DUMP.read_bytes()
        if BUILTIN_RAM_DUMP.is_file()
        else bytes(RAM_WINDOW_SIZE)
    )
    images: list[bytes] = []
    frame_base = base

    encounter_one: list[dict[str, Any]] = [
        dict(player_hp=24, player_pp=(35, 30), enemy_hp=15, enemy_pp=(35,)),
        dict(player_hp=22, player_pp=(34, 30), enemy_hp=11, enemy_pp=(34,)),
        dict(player_hp=22, player_pp=(33, 30), enemy_hp=11, enemy_pp=(34,)),
        dict(player_hp=22, player_pp=(32, 30), enemy_hp=6, enemy_pp=(34,)),
        dict(player_hp=22, player_pp=(31, 30), enemy_hp=0, enemy_pp=(34,)),
    ]
    for frame in encounter_one:
        frame_base = _fixture_image(
            resolver,
            frame_base,
            battle_type=1,
            map_id=_ROUTE_2,
            player_species=_CHARMANDER,
            player_level=8,
            player_hp=frame["player_hp"],
            player_max_hp=25,
            player_moves=[
                (_TACKLE, frame["player_pp"][0]),
                (_GROWL, frame["player_pp"][1]),
            ],
            enemy_species=_WEEDLE,
            enemy_level=3,
            enemy_hp=frame["enemy_hp"],
            enemy_max_hp=15,
            enemy_moves=[(_TACKLE, frame["enemy_pp"][0])],
        )
        images.append(frame_base)

    encounter_two: list[dict[str, Any]] = [
        dict(player_hp=22, player_pp=(30, 28), enemy_hp=20, enemy_pp=(35, 20)),
        dict(player_hp=22, player_pp=(30, 27), enemy_hp=20, enemy_pp=(35, 20)),
        dict(player_hp=19, player_pp=(29, 27), enemy_hp=16, enemy_pp=(34, 20)),
    ]
    for frame in encounter_two:
        frame_base = _fixture_image(
            resolver,
            frame_base,
            battle_type=2,
            map_id=_PEWTER_CITY,
            player_species=_CHARMANDER,
            player_level=8,
            player_hp=frame["player_hp"],
            player_max_hp=25,
            player_moves=[
                (_TACKLE, frame["player_pp"][0]),
                (_GROWL, frame["player_pp"][1]),
            ],
            enemy_species=_PIDGEY,
            enemy_level=5,
            enemy_hp=frame["enemy_hp"],
            enemy_max_hp=20,
            enemy_moves=[
                (_TACKLE, frame["enemy_pp"][0]),
                (_GROWL, frame["enemy_pp"][1]),
            ],
        )
        images.append(frame_base)
    return images


# ── capture driver ──────────────────────────────────────────────────────────


def run_capture(
    source: Any,
    identity: TelemetryIdentity,
    ticks: int,
    *,
    interval: float = 0.0,
    resolver: BattleAddressResolver | None = None,
) -> BattleTelemetrySampler:
    """Sample *source* *ticks* times and return the sampler that saw it."""
    sampler = BattleTelemetrySampler(source, identity, resolver=resolver)
    for index in range(ticks):
        sampler.sample()
        if interval > 0 and index + 1 < ticks:
            time.sleep(interval)
    return sampler


def write_records(
    sampler: BattleTelemetrySampler,
    *,
    out: Path | None = None,
    out_dir: Path | None = None,
) -> list[str]:
    """Write the records as JSONL; returns the files written."""
    written: list[str] = []
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as handle:
            for record in sampler.records:
                handle.write(json.dumps(record, default=str) + "\n")
        written.append(str(out))
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        for encounter in sampler.encounters:
            records = [
                record
                for record in sampler.records
                if record["encounter_id"] == encounter.encounter_id
            ]
            if not records:
                continue
            path = out_dir / encounter.partition_filename()
            with path.open("w", encoding="utf-8") as handle:
                for record in records:
                    handle.write(json.dumps(record, default=str) + "\n")
            written.append(str(path))
    return written


def _summary(sampler: BattleTelemetrySampler, files: Sequence[str]) -> dict[str, Any]:
    return {
        "records": len(sampler.records),
        "dropped_records": sampler.dropped_records,
        "dropped_details": sampler.dropped_details,
        "unattributed_hp_deltas": sampler.unattributed_hp_deltas,
        "skipped_actions": sampler.skipped_actions,
        "encounters": [
            {
                "encounter_id": encounter.encounter_id,
                "file": encounter.partition_filename(),
                "map": encounter.map_name,
                "map_resolved": encounter.map_resolved,
                "opponent_species": encounter.opponent_species,
                "opponent_level": encounter.opponent_level,
                "battle_type": encounter.battle_type,
                "turns": encounter.turns,
                "records": encounter.records,
                "outcome": encounter.outcome,
            }
            for encounter in sampler.encounters
        ],
        "files": list(files),
    }


def _print_addresses(resolver: BattleAddressResolver) -> None:
    print(f"symbol files: {resolver.sym_files or 'none — constant block only'}")
    for note in resolver.verification_notes():
        print(note)
    for conflict in resolver.conflicts:
        print(f"CONFLICT: {conflict}", file=sys.stderr)


def _load_sequence(path: Path) -> list[Mapping[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("states", [])
    if not isinstance(payload, list):
        raise TelemetrySourceError(
            f"{path} must hold a JSON list of battle-state dicts"
        )
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="capture_battle_telemetry.py",
        description=(
            "Passive RAM battle-telemetry capture. Samples the RAM reader and "
            "writes contract-shaped JSONL; never presses a button or advances "
            "the emulator."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Field names, sources and the fail-closed rules come from "
            "specs/contracts/battle-telemetry.md."
        ),
    )
    parser.add_argument(
        "--ram-image",
        action="append",
        default=[],
        metavar="PATH",
        help="a 32 KiB RAM image (0x8000..0xFFFF); repeat once per capture tick",
    )
    parser.add_argument(
        "--state-sequence",
        action="append",
        default=[],
        metavar="PATH",
        help="JSON file with a list of battle-state dicts (one per tick)",
    )
    parser.add_argument(
        "--builtin-fixture",
        action="store_true",
        help="use the deterministic two-encounter fixture built in-process",
    )
    parser.add_argument("--out", metavar="PATH", help="write every record here")
    parser.add_argument(
        "--out-dir",
        metavar="DIR",
        help="write one file per encounter named per contract §4.1",
    )
    parser.add_argument(
        "--print-records",
        action="store_true",
        help="write the records to stdout as JSONL",
    )
    parser.add_argument("--run-id", default="capture_000000_000000", metavar="ID")
    parser.add_argument("--episode", type=int, default=1, metavar="N")
    parser.add_argument(
        "--decision-arm",
        default="DECISION_MODE=unrecorded",
        metavar="LABEL",
        help="the run's decision-architecture label (required on every record)",
    )
    parser.add_argument("--model-decision", default=None, metavar="MODEL")
    parser.add_argument("--model-vision", default=None, metavar="MODEL")
    parser.add_argument("--provider", default=None, metavar="PROVIDER")
    parser.add_argument(
        "--interval",
        type=float,
        default=0.0,
        metavar="SECONDS",
        help="sleep between samples (keep it well under one battle turn)",
    )
    parser.add_argument(
        "--sym-dir",
        default=None,
        metavar="DIR",
        help="directory holding *.sym symbol maps (default: data/rom)",
    )
    parser.add_argument(
        "--verify-addresses",
        action="store_true",
        help="print every resolved address with its verification note and exit",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.verify_addresses:
        _print_addresses(BattleAddressResolver(sym_dir=args.sym_dir))
        return 0

    resolver = BattleAddressResolver(sym_dir=args.sym_dir)
    ticks: list[CaptureTick] = []
    try:
        for path in args.ram_image:
            ticks.append(RamImageTick(Path(path).read_bytes()))
        for path in args.state_sequence:
            ticks.extend(SequenceTick(state) for state in _load_sequence(Path(path)))
        if args.builtin_fixture:
            ticks.extend(
                RamImageTick(image) for image in builtin_fixture_images(resolver)
            )
    except (OSError, ValueError, TelemetrySourceError, json.JSONDecodeError) as exc:
        print(f"capture_battle_telemetry: {exc}", file=sys.stderr)
        return 2

    if not ticks:
        parser.error(
            "no source given: pass --ram-image, --state-sequence or "
            "--builtin-fixture (or --verify-addresses)"
        )

    try:
        identity = TelemetryIdentity(
            run_id=args.run_id,
            episode=args.episode,
            decision_arm=args.decision_arm,
            model_decision=args.model_decision,
            model_vision=args.model_vision,
            provider=args.provider,
        )
    except ValueError as exc:
        print(f"capture_battle_telemetry: {exc}", file=sys.stderr)
        return 2

    stream = FrameStream(ticks)
    sampler = run_capture(
        stream, identity, len(stream), interval=args.interval, resolver=resolver
    )
    files = write_records(
        sampler,
        out=Path(args.out) if args.out else None,
        out_dir=Path(args.out_dir) if args.out_dir else None,
    )
    if args.print_records or (args.out is None and args.out_dir is None):
        for record in sampler.records:
            print(json.dumps(record, default=str, sort_keys=True))
    print(json.dumps(_summary(sampler, files), default=str), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
