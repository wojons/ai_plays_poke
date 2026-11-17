"""Append-only partitioned store for battle telemetry (row BTL-STORE-1).

Contract: ``specs/contracts/battle-telemetry.md`` (row BTL-SCHEMA-1).
Row: BTL-STORE-1 — the writer half of the contract.

What this module is
-------------------
The writer the record shapes in ``src/core/battle_telemetry.py`` (BTL-RAM-1)
feed. It appends one record per line to the partition named by §4.1
(``battle-<run_id>-ep<EEE>-enc<CCC>.jsonl``), enforces the §3.3 rules in the
same call, honours the §4.2 caps by closing the encounter and continuing in the
next ``enc<CCC>`` partition (``continued_from`` recorded in the manifest), and
writes the single §4.3 manifest record through the EXISTING DuckBrain client
(``remember()`` / ``get()`` / ``recall()``) — this module never forks that
client's write path.

Rules enforced here rather than documented here
-----------------------------------------------
R1  every record carries the 11 identity keys (§3.1) and the 17 event fields
    (§3.2), spelled exactly. Missing keys raise ``RecordValidationError``.
R2  a record whose ``attacker_level``/``defender_level``/
    ``defender_max_hp``/``defender_hp_before``/``defender_hp_after`` is outside
    its declared range is DROPPED (never written with a null) and counted in
    ``dropped_records``.
R3  ``turn`` is non-decreasing; a regression raises ``TurnOrderError``.
R4  ``damage == defender_hp_before - defender_hp_after`` for
    ``outcome == "damage"`` and ``damage == 0`` for
    ``no_damage``/``miss``/``immune``; a mismatch raises
    ``RecordValidationError`` and is counted in ``dropped_records``.
R5  on a KO record the damage IS the defender's remaining HP — the arithmetic
    check names R5 so a formula-derived (overkill) number cannot land.
R6  every ``*_resolved`` flag is recomputed from its label form; a flag that
    disagrees with the label raises rather than being trusted.
N1  no telemetry path outside ``<root>/<namespace>/data`` may be written.
N8  no aggregate/rollup filename is ever created by this module.
N9  this module never writes a ``memories-*.jsonl`` file directly; the manifest
    reaches that file only through the client's ``remember()``.

Decisions this module had to settle (contract §10)
-------------------------------------------------
O-4 (transport) — filesystem only, exactly as the client already writes
(§9). Event files are never POSTed as memory records (N9). Moving bytes beyond
this host is a separate row's decision.
O-5 (manifest timing) — the manifest is written ONCE, by an explicit
``write_manifest(run_id)`` call (the CLI calls it at the end of a store run).
The contract offers "once at run end" or "incrementally per encounter close";
this module takes the first, because the client is APPEND-ONLY and
``duckbrain_client.get(key=...)`` returns the FIRST record carrying a key
(``recall`` walks a file top-down, ``get`` takes ``results[0]``). An incremental
re-write would therefore append a second record under the same key and every
reader would see the STALER one — a silent wrong answer. Writing once keeps
``get()`` exact, and a crashed run is still recoverable: its partitions are on
disk and no manifest exists yet, so a later ``write_manifest`` call writes it.
A second call for a run that already has a DIFFERENT manifest raises
``ManifestConflictError`` rather than forking the truth.

Two smaller choices, stated because they are visible in the API:

* the contract's ``map`` field arrives as the keyword ``map_name`` — ``map`` is
  a Python builtin and shadowing it in a keyword-only argument buys nothing.
* a contract row is ``(run_id, episode, encounter_id)``; this store's
  ``append_encounter`` therefore takes ``episode`` + ``encounter_ordinal`` and
  derives the ``encounter_id`` string, so a caller cannot pass a pair that
  disagrees with the filename it produces.
"""

from __future__ import annotations

import hashlib
import json
import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence, TypeGuard

from src.core import duckbrain_client as _client
from src.core.battle_telemetry import (
    BATTLE_TYPES,
    ENCOUNTER_OUTCOMES,
    LEVEL_MAX,
    LEVEL_MIN,
    OUTCOMES,
)

__all__ = [
    "EVENT_KEYS",
    "IDENTITY_KEYS",
    "MAX_BYTES_PER_FILE",
    "MAX_MANIFEST_ENCOUNTERS",
    "MAX_RECORDS_PER_FILE",
    "MANIFEST_DOMAIN",
    "MANIFEST_KEY_PREFIX",
    "REQUIRED_KEYS",
    "SCHEMA_VERSION",
    "AggregateFileError",
    "BattleTelemetryStore",
    "EncounterWrite",
    "ManifestWrite",
    "MemoryFileWriteError",
    "ManifestConflictError",
    "PartitionRef",
    "RecordTooLargeError",
    "RecordValidationError",
    "StorePathError",
    "TelemetryStoreError",
    "TurnOrderError",
    "assert_telemetry_filename",
    "client_root",
    "manifest_key",
    "parse_partition_filename",
    "partition_filename",
    "range_violations",
    "record_identity",
    "required_key_violations",
    "semantic_violations",
    "validate_record",
]

#: Contract version stamped on the manifest (§4.3).
SCHEMA_VERSION = 1

#: Dedicated namespace so telemetry is excluded from memory reads (N9, §4.1).
DEFAULT_NAMESPACE = "pokemon-battle"

#: §4.2 caps. A file never exceeds either one.
MAX_RECORDS_PER_FILE = 512
MAX_BYTES_PER_FILE = 262144

#: §4.3 index cap.
MAX_MANIFEST_ENCOUNTERS = 1000

#: Highest episode / encounter ordinal expressible as three digits (§4.1).
MAX_ORDINAL = 999

#: Manifest identity (§4.3).
MANIFEST_DOMAIN = "game/battle"
MANIFEST_KEY_PREFIX = "/game/battle/"

#: §3.1 identity keys — required on every record, spelled exactly.
IDENTITY_KEYS: tuple[str, ...] = (
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
)

#: §3.2 event fields — required on every record, spelled exactly.
EVENT_KEYS: tuple[str, ...] = (
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
)

REQUIRED_KEYS: tuple[str, ...] = IDENTITY_KEYS + EVENT_KEYS

#: §3.2 enumerated fields.
ATTACKER_SIDES = ("player", "enemy")

#: N8 — tokens that mark an aggregate/rollup filename. Checked only for names
#: that do not parse as a partition (a run_id may legitimately contain them).
_AGGREGATE_TOKENS = ("all", "rollup", "aggregate", "summary", "combined", "merged")

_RUN_ID = re.compile(r"^[A-Za-z0-9_]+$")
_PARTITION_NAME = re.compile(r"^battle-([A-Za-z0-9_]+)-ep(\d{3})-enc(\d{3})\.jsonl$")
_ENCOUNTER_ID = re.compile(r"^ep(\d{3})-enc(\d{3})$")
_UNRESOLVED_SPECIES = re.compile(r"^#\d+$")
_UNRESOLVED_MOVE = re.compile(r"^Move#\d+$")
_UNRESOLVED_MAP = re.compile(r"^Map_[0-9A-F]{2}$")


class TelemetryStoreError(Exception):
    """Base error for the battle-telemetry store."""


class StorePathError(TelemetryStoreError, ValueError):
    """N1 — a write would leave the namespace data directory."""


class AggregateFileError(TelemetryStoreError, ValueError):
    """N8 — a write would create an aggregate/rollup file."""


class MemoryFileWriteError(TelemetryStoreError, ValueError):
    """N9 — this module may never write a ``memories-*.jsonl`` file."""


class RecordValidationError(TelemetryStoreError, ValueError):
    """R1/R4/R5/R6 — the record cannot be written as it stands."""


class TurnOrderError(TelemetryStoreError, ValueError):
    """R3 — ``turn`` went backwards inside one encounter."""


class ManifestConflictError(TelemetryStoreError, RuntimeError):
    """A run already has a manifest and the new one would differ (§4.3, O-5)."""


class RecordTooLargeError(TelemetryStoreError, ValueError):
    """A single record exceeds ``MAX_BYTES_PER_FILE`` and can never fit."""


# ── partition naming (§4.1) ─────────────────────────────────────────────────


@dataclass(frozen=True, order=True)
class PartitionRef:
    """One partition: the triple the §4.1 filename encodes."""

    run_id: str
    episode: int
    ordinal: int

    def __post_init__(self) -> None:
        if not _RUN_ID.match(self.run_id):
            raise ValueError(
                f"run_id {self.run_id!r} must match [A-Za-z0-9_]+ (contract §4.1)"
            )
        for label, value in (("episode", self.episode), ("ordinal", self.ordinal)):
            if not 1 <= value <= MAX_ORDINAL:
                raise ValueError(
                    f"{label} must be 1..{MAX_ORDINAL}, got {value} "
                    "(contract §4.1 uses three digits)"
                )

    @property
    def encounter_id(self) -> str:
        """``ep<EEE>-enc<CCC>`` (contract §3.1)."""
        return f"ep{self.episode:03d}-enc{self.ordinal:03d}"

    @property
    def filename(self) -> str:
        """``battle-<run_id>-ep<EEE>-enc<CCC>.jsonl`` (contract §4.1)."""
        return partition_filename(self)

    def next(self) -> "PartitionRef":
        """The partition a cap overflow continues in (contract §4.2)."""
        return PartitionRef(self.run_id, self.episode, self.ordinal + 1)

    @classmethod
    def parse(cls, name: str) -> "PartitionRef":
        match = _PARTITION_NAME.match(name)
        if match is None:
            raise ValueError(
                f"{name!r} does not parse to battle-<run_id>-ep<EEE>-enc<CCC>.jsonl"
            )
        return cls(match.group(1), int(match.group(2)), int(match.group(3)))


def partition_filename(ref: PartitionRef) -> str:
    """§4.1 filename for *ref*."""
    return f"battle-{ref.run_id}-{ref.encounter_id}.jsonl"


def parse_partition_filename(name: str) -> PartitionRef:
    """Parse a §4.1 filename back to its :class:`PartitionRef`."""
    return PartitionRef.parse(name)


def assert_telemetry_filename(name: str) -> PartitionRef:
    """N2/N8/N9 gate for any filename this module is about to create."""
    if name.startswith("memories-"):
        raise MemoryFileWriteError(
            f"N9: {name!r} is a memory file — the manifest reaches it through "
            "duckbrain_client.remember(), never through this module"
        )
    match = _PARTITION_NAME.match(name)
    if match is not None:
        return PartitionRef.parse(name)
    lowered = name.lower()
    for token in _AGGREGATE_TOKENS:
        if token in lowered:
            raise AggregateFileError(
                f"N8: {name!r} looks like an aggregate/rollup ({token!r}); "
                "aggregates are computed at read time (contract §7 N8)"
            )
    raise StorePathError(
        f"N2: {name!r} does not match battle-<run_id>-ep<EEE>-enc<CCC>.jsonl"
    )


def manifest_key(run_id: str) -> str:
    """§4.3 exact key for one run's manifest."""
    return f"{MANIFEST_KEY_PREFIX}{run_id}/manifest"


# ── record identity and validation (§3.3) ───────────────────────────────────


def record_identity(record: Mapping[str, Any]) -> str:
    """Stable hash of the record's own fields (no write timestamp).

    Used for idempotence: a record already present in the partition is skipped
    instead of appended twice. ``ts`` is the OBSERVATION stamp the record
    carries (§3.1) — it is part of the record, not part of the write — so two
    appends of the same observation are the same identity.
    """
    blob = json.dumps(dict(record), sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def required_key_violations(record: Mapping[str, Any]) -> list[str]:
    """R1 — missing required keys, in table order."""
    return [key for key in REQUIRED_KEYS if key not in record]


def _is_int(value: Any) -> TypeGuard[int]:
    """True for a real int (``bool`` subclasses ``int`` and is excluded)."""
    return isinstance(value, int) and not isinstance(value, bool)


def range_violations(record: Mapping[str, Any]) -> list[str]:
    """R2 — the five fields whose out-of-range value drops the record."""
    reasons: list[str] = []
    for side in ("attacker", "defender"):
        level = record.get(f"{side}_level")
        if not _is_int(level) or not LEVEL_MIN <= int(level) <= LEVEL_MAX:
            reasons.append(
                f"R2: {side}_level {level!r} outside {LEVEL_MIN}..{LEVEL_MAX}"
            )
    for name in ("defender_max_hp", "defender_hp_before", "defender_hp_after"):
        value = record.get(name)
        if not _is_int(value) or int(value) < 0:
            reasons.append(f"R2: {name} {value!r} is not a non-negative int")
    return reasons


def _flag_mismatch(
    record: Mapping[str, Any],
    field_name: str,
    label: str,
    unresolved: re.Pattern[str],
) -> str | None:
    """R6 — a ``*_resolved`` flag that disagrees with its own label."""
    supplied = record.get(field_name)
    expected = unresolved.match(str(label)) is None
    if not isinstance(supplied, bool):
        return f"R6: {field_name} {supplied!r} is not a bool"
    if supplied != expected:
        return (
            f"R6: {field_name} is {supplied} but its label {label!r} "
            f"is {'resolved' if expected else 'unresolved'}"
        )
    return None


def semantic_violations(record: Mapping[str, Any], ref: PartitionRef) -> list[str]:
    """R1/R4/R5/R6 plus the N6 identity agreement with the partition."""
    problems: list[str] = []

    if record.get("run_id") != ref.run_id:
        problems.append(
            f"N6: run_id {record.get('run_id')!r} != partition {ref.run_id!r}"
        )
    if record.get("episode") != ref.episode:
        problems.append(
            f"N6: episode {record.get('episode')!r} != partition {ref.episode}"
        )
    if record.get("encounter_id") != ref.encounter_id:
        problems.append(
            f"N6: encounter_id {record.get('encounter_id')!r} != source "
            f"partition {ref.encounter_id!r}"
        )

    if not isinstance(record.get("map"), str) or not str(record.get("map")):
        problems.append("R1: map must be a non-empty string")
    elif flag := _flag_mismatch(record, "map_resolved", record["map"], _UNRESOLVED_MAP):
        problems.append(flag)
    if not isinstance(record.get("ts"), str) or not str(record.get("ts")):
        problems.append("R1: ts must be a non-empty ISO-8601 string")
    if not isinstance(record.get("decision_arm"), str) or not str(
        record.get("decision_arm")
    ):
        problems.append("R1: decision_arm must be a non-empty string")
    for nullable in ("model_decision", "model_vision", "provider"):
        if record.get(nullable) is not None and not isinstance(
            record.get(nullable), str
        ):
            problems.append(f"R1: {nullable} must be a string or null")

    turn = record.get("turn")
    if not _is_int(turn) or int(turn) < 1:
        problems.append(f"R3: turn {turn!r} is not an int >= 1")

    side = record.get("attacker_side")
    if side not in ATTACKER_SIDES:
        problems.append(f"R1: attacker_side {side!r} not in {ATTACKER_SIDES}")
    battle_type = record.get("battle_type")
    if battle_type not in BATTLE_TYPES:
        problems.append(f"R1: battle_type {battle_type!r} not in {BATTLE_TYPES}")
    outcome = record.get("outcome")
    if outcome not in OUTCOMES:
        problems.append(f"R1: outcome {outcome!r} not in {OUTCOMES}")
    encounter_outcome = record.get("encounter_outcome")
    if encounter_outcome not in ENCOUNTER_OUTCOMES:
        problems.append(
            f"R1: encounter_outcome {encounter_outcome!r} not in {ENCOUNTER_OUTCOMES}"
        )

    for name, pattern in (
        ("attacker_species", _UNRESOLVED_SPECIES),
        ("defender_species", _UNRESOLVED_SPECIES),
        ("move", _UNRESOLVED_MOVE),
    ):
        label = record.get(name)
        if not isinstance(label, str) or not label:
            problems.append(f"R1: {name} must be a non-empty string")
            continue
        flag = _flag_mismatch(record, f"{name}_resolved", label, pattern)
        if flag:
            problems.append(flag)

    damage = record.get("damage")
    before = record.get("defender_hp_before")
    after = record.get("defender_hp_after")
    max_hp = record.get("defender_max_hp")
    if not _is_int(damage) or damage < 0:
        problems.append(f"R4: damage {damage!r} is not a non-negative int")
    elif _is_int(before) and _is_int(after):
        ko = after == 0 and before > 0
        expected = max(0, before - after)
        if damage != expected:
            # R5: HP clamps at 0 (src/core/combat.py), so on a KO the delta IS
            # the defender's remaining HP. A formula-derived number cannot pass,
            # and the message names the rule the record broke.
            rule = "R5" if ko else "R4"
            problems.append(
                f"{rule}: damage {damage} != defender_hp_before-defender_hp_after "
                f"({before}-{after}={expected})"
                + (" — on a KO the delta is the remaining HP" if ko else "")
            )
        elif outcome in ("no_damage", "miss", "immune") and damage:
            problems.append(f"R4: outcome {outcome} with damage {damage}")
        elif _is_int(max_hp) and max_hp > 0 and damage > max_hp:
            problems.append(
                f"R5: damage {damage} > defender_max_hp {max_hp} — HP clamps at 0, "
                "so no record may report overkill"
            )

    pct = record.get("damage_pct_of_max")
    if pct is not None:
        if not isinstance(pct, (int, float)) or isinstance(pct, bool):
            problems.append(f"R1: damage_pct_of_max {pct!r} is not a number or null")
        elif not 0.0 <= float(pct) <= 100.0:
            problems.append(f"R1: damage_pct_of_max {pct!r} outside 0.0..100.0")

    return problems


def validate_record(record: Mapping[str, Any], ref: PartitionRef) -> None:
    """Fail closed on R1/R4/R5/R6 and N6. R2 is a drop, not a raise."""
    missing = required_key_violations(record)
    if missing:
        raise RecordValidationError(
            f"R1: {ref.filename} record is missing required keys {missing}"
        )
    problems = semantic_violations(record, ref)
    if problems:
        raise RecordValidationError(f"{ref.filename}: " + "; ".join(problems))


# ── client root injection ───────────────────────────────────────────────────


@contextmanager
def client_root(root: Path) -> Iterator[None]:
    """Point the DuckBrain client at *root* for the duration of the block.

    The client's write path is used UNCHANGED (§4.3) — only the module-level
    root it resolves against is redirected, so a test (or a CLI ``--store-root``
    run) never touches a real ``~/duckbrain``. The previous value is restored
    even on an exception.
    """
    previous = _client.DUCKBRAIN_ROOT
    _client.DUCKBRAIN_ROOT = Path(root)
    try:
        yield
    finally:
        _client.DUCKBRAIN_ROOT = previous


# ── write results ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EncounterWrite:
    """What one ``append_encounter`` call did."""

    run_id: str
    episode: int
    encounter_ids: tuple[str, ...]
    files: tuple[str, ...]
    written: int
    skipped: int
    dropped: int


@dataclass(frozen=True)
class ManifestWrite:
    """What one ``write_manifest`` call did."""

    run_id: str
    key: str
    written: bool
    memory_id: str | None
    attributes: dict[str, Any]


@dataclass
class _PartitionState:
    """On-disk (plus this-call buffered) state of one partition."""

    path: Path
    count: int = 0
    size: int = 0
    identities: set[str] = field(default_factory=set)
    last_turn: int = 0
    records: list[dict[str, Any]] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)


# ── the store ───────────────────────────────────────────────────────────────


class BattleTelemetryStore:
    """Append-only writer for one namespace's battle-telemetry partitions."""

    def __init__(
        self,
        namespace: str = DEFAULT_NAMESPACE,
        root: Path | str | None = None,
        *,
        decision_arm: str | None = None,
        model_decision: str | None = None,
        model_vision: str | None = None,
        provider: str | None = None,
    ) -> None:
        self.namespace = namespace
        self.root = Path(root) if root is not None else Path(_client.DUCKBRAIN_ROOT)
        self.data_dir = self.root / namespace / "data"
        self._overrides: dict[str, str | None] = {
            "decision_arm": decision_arm,
            "model_decision": model_decision,
            "model_vision": model_vision,
            "provider": provider,
        }
        self._index: dict[str, dict[str, Any]] = {}
        self._encounters_total = 0
        self._episodes: set[int] = set()
        self._dropped = 0
        self._dropped_identities: set[str] = set()
        self._identity: dict[str, dict[str, Any]] = {}
        self._started: dict[str, str] = {}
        self._ended: dict[str, str] = {}
        self._continued_from: dict[str, str] = {}

    # ── introspection ──

    @property
    def index(self) -> list[dict[str, Any]]:
        """Manifest index entries, ordered by ``encounter_id``."""
        return [self._index[key] for key in sorted(self._index)]

    @property
    def encounters_total(self) -> int:
        """True partition count, even when ``index`` was truncated (§4.3)."""
        return self._encounters_total

    @property
    def episodes(self) -> int:
        return len(self._episodes)

    @property
    def dropped_records(self) -> int:
        """Records refused under R2/R4/R5/R6 — visible loss, never silent."""
        return self._dropped

    # ── paths and guards (N1, N8, N9) ──

    def partition_path(self, run_id: str, episode: int, ordinal: int) -> Path:
        """Absolute path of one partition, inside the namespace data dir."""
        return self._partition_path(PartitionRef(run_id, episode, ordinal))

    def _partition_path(self, ref: PartitionRef) -> Path:
        assert_telemetry_filename(ref.filename)  # N2/N8/N9
        path = self.data_dir / ref.filename
        self._assert_inside(path)
        return path

    def _assert_inside(self, path: Path) -> None:
        """N1 — a telemetry path must be DIRECTLY inside the namespace data dir."""
        data_dir = self.data_dir.resolve()
        resolved = path.resolve()
        if resolved.parent != data_dir:
            raise StorePathError(
                f"N1: refusing to write {path} — telemetry lives directly under "
                f"{data_dir} (contract §7 N1)"
            )

    def _append_lines(self, path: Path, lines: Sequence[str]) -> int:
        """The only write primitive: append with ``open(path, "a")`` (§9)."""
        assert_telemetry_filename(path.name)  # N9, then N8/N2
        self._assert_inside(path)  # N1
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            for line in lines:
                handle.write(line)
        return len(lines)

    # ── partition reading ──

    def _read_partition(self, path: Path) -> _PartitionState:
        state = _PartitionState(path=path)
        if not path.is_file():
            return state
        state.size = path.stat().st_size
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            state.count += 1
            try:
                parsed: Any = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(parsed, dict):
                continue
            record = dict(parsed)
            state.records.append(record)
            state.identities.add(record_identity(record))
            turn = record.get("turn")
            if _is_int(turn):
                state.last_turn = max(state.last_turn, int(turn))
        return state

    def _chain(self, ref: PartitionRef) -> list[PartitionRef]:
        """*ref* plus every consecutive higher-ordinal partition it CONTINUED in.

        A higher ordinal that is a different encounter (not a cap split) is not
        part of this chain — otherwise a re-write of encounter *n* would be
        de-duplicated against, and turn-checked against, encounter *n+1*.
        """
        chain = [ref]
        ordinal = ref.ordinal
        while ordinal < MAX_ORDINAL:
            candidate = PartitionRef(ref.run_id, ref.episode, ordinal + 1)
            if not self._partition_path(candidate).is_file():
                break
            if not self._predecessor_split(candidate):
                break
            ordinal += 1
            chain.append(candidate)
        return chain

    # ── appending (§4.1, §4.2, §3.3) ──

    def append_encounter(
        self,
        records: Iterable[Mapping[str, Any]],
        *,
        run_id: str,
        episode: int,
        encounter_ordinal: int,
        map_name: str | None = None,
        battle_type: str | None = None,
        outcome: str | None = None,
        continued_from: str | None = None,
    ) -> EncounterWrite:
        """Append one encounter's records, splitting at the §4.2 caps.

        Idempotent per encounter: a record whose own fields are already present
        in the encounter's partitions is skipped, never appended twice, and the
        partition is never rewritten or truncated. The manifest index entry for
        each touched partition is REPLACED in place (one entry per partition).
        """
        ref0 = PartitionRef(run_id, episode, encounter_ordinal)
        if outcome is not None and outcome not in ENCOUNTER_OUTCOMES:
            raise ValueError(
                f"encounter outcome {outcome!r} not in {ENCOUNTER_OUTCOMES}"
            )

        prepared, dropped = self._prepare(records, ref0)
        self._check_partition_labels(prepared, ref0, map_name, battle_type)
        if continued_from is not None:
            self._continued_from[ref0.encounter_id] = continued_from
        chain = self._chain(ref0)
        states: dict[PartitionRef, _PartitionState] = {}

        def state_for(ref: PartitionRef) -> _PartitionState:
            if ref not in states:
                states[ref] = self._read_partition(self._partition_path(ref))
            return states[ref]

        current = chain[-1]
        skipped = 0
        written = 0

        def already_stored(record: Mapping[str, Any]) -> bool:
            """Is this record already on disk in ANY partition of the chain?"""
            for ref in chain:
                candidate = dict(record)
                candidate["encounter_id"] = ref.encounter_id
                if record_identity(candidate) in state_for(ref).identities:
                    return True
            return False

        for record in prepared:
            if already_stored(record):
                skipped += 1
                continue
            while True:
                state = state_for(current)
                stamped = dict(record)
                stamped["encounter_id"] = current.encounter_id
                line = json.dumps(stamped, sort_keys=True, default=str) + "\n"
                blob = line.encode("utf-8")

                if len(blob) > MAX_BYTES_PER_FILE:
                    raise RecordTooLargeError(
                        f"a single record is {len(blob)} B > MAX_BYTES_PER_FILE "
                        f"{MAX_BYTES_PER_FILE} and can never be written (§4.2)"
                    )
                at_cap = (
                    state.count >= MAX_RECORDS_PER_FILE
                    or state.size + len(blob) > MAX_BYTES_PER_FILE
                )
                if at_cap:
                    if current.ordinal >= MAX_ORDINAL:
                        raise StorePathError(
                            f"encounter chain for {ref0.encounter_id} reached "
                            f"enc{MAX_ORDINAL}: the three-digit ordinal is spent (§4.1)"
                        )
                    current = current.next()
                    if current not in chain:
                        chain.append(current)
                    continue

                # R3 is a per-file rule (§3.3), so the floor is the file's own
                # last turn — not the tail's, which a replay may exceed.
                turn = int(record["turn"])
                if turn < state.last_turn:
                    raise TurnOrderError(
                        f"R3: turn {turn} after {state.last_turn} in "
                        f"{current.filename} (turns must be non-decreasing)"
                    )
                state.last_turn = turn

                state.pending.append(line)
                state.count += 1
                state.size += len(blob)
                state.identities.add(record_identity(stamped))
                written += 1
                break

        touched = sorted(states.keys(), key=lambda ref: (ref.episode, ref.ordinal))
        for ref in touched:
            pending = states[ref].pending
            if pending:
                self._append_lines(self._partition_path(ref), pending)
                states[ref].pending = []

        files: list[str] = []
        for ref in touched:
            entry, started, ended = self._entry_for(ref, outcome=outcome)
            if entry is None:
                continue
            self._note_ts(run_id, started, ended)
            if self._index.get(ref.encounter_id) is None:
                self._encounters_total += 1
            self._index[ref.encounter_id] = entry
            files.append(ref.filename)

        self._episodes.add(episode)
        for record in prepared:
            self._stamp_run_identity(run_id, record)

        return EncounterWrite(
            run_id=run_id,
            episode=episode,
            encounter_ids=tuple(ref.encounter_id for ref in touched),
            files=tuple(files),
            written=written,
            skipped=skipped,
            dropped=dropped,
        )

    def _prepare(
        self, records: Iterable[Mapping[str, Any]], ref0: PartitionRef
    ) -> tuple[list[dict[str, Any]], int]:
        """Validate everything before a single byte is appended (fail closed)."""
        prepared: list[dict[str, Any]] = []
        dropped = 0
        for raw in records:
            if not isinstance(raw, Mapping):
                raise RecordValidationError(
                    f"R1: a record is {type(raw).__name__}, not a mapping"
                )
            record = dict(raw)
            missing = required_key_violations(record)
            if missing:
                self._count_dropped(record)
                raise RecordValidationError(
                    f"R1: {ref0.filename} record is missing required keys {missing}"
                )
            reasons = range_violations(record)
            if reasons:
                self._count_dropped(record)
                dropped += 1
                continue
            problems = semantic_violations(record, ref0)
            if problems:
                self._count_dropped(record)
                raise RecordValidationError(f"{ref0.filename}: " + "; ".join(problems))
            prepared.append(record)
        return prepared, dropped

    def _check_partition_labels(
        self,
        records: Sequence[Mapping[str, Any]],
        ref0: PartitionRef,
        map_name: str | None,
        battle_type: str | None,
    ) -> None:
        """A caller-supplied map/battle_type must agree with the records (N6)."""
        checks = (("map", map_name), ("battle_type", battle_type))
        for field_name, declared in checks:
            if declared is None:
                continue
            for record in records:
                if record.get(field_name) != declared:
                    raise RecordValidationError(
                        f"N6: {ref0.filename} declares {field_name}={declared!r} but "
                        f"a record carries {record.get(field_name)!r}"
                    )

    def _count_dropped(self, record: Mapping[str, Any]) -> None:
        identity = record_identity(record)
        if identity in self._dropped_identities:
            return
        self._dropped_identities.add(identity)
        self._dropped += 1

    # ── manifest (§4.3) ──

    def write_manifest(
        self,
        *,
        run_id: str,
        started: str | None = None,
        ended: str | None = None,
        dropped_records: int | None = None,
    ) -> ManifestWrite:
        """Write the run's single manifest record through the client (§4.3).

        Idempotent for identical content and fail-closed otherwise: the client
        is append-only and ``get()`` returns the FIRST record carrying a key, so
        a second, different manifest would silently shadow the real one.

        The index is rebuilt from the partitions ON DISK, so a process that
        resumed an existing run still describes the whole run.
        ``dropped_records`` is the loss count observed by THIS process (the
        partitions do not record which input records were refused), so the
        writer of the manifest must be the process that ingested the records.
        """
        scanned = self._scan_run(run_id)
        self._index = {entry["encounter_id"]: entry for entry in scanned}
        self._encounters_total = len(scanned)
        entries = scanned[:MAX_MANIFEST_ENCOUNTERS]
        identity = self._identity.get(run_id, {})
        arm = self._overrides["decision_arm"] or identity.get("decision_arm")
        attributes: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "decision_arm": arm or "unrecorded",
            "model_decision": self._overrides["model_decision"]
            or identity.get("model_decision"),
            "model_vision": self._overrides["model_vision"]
            or identity.get("model_vision"),
            "provider": self._overrides["provider"] or identity.get("provider"),
            "started": started or self._started.get(run_id) or _utc_now(),
            "ended": ended if ended is not None else self._ended.get(run_id),
            "episodes": len({entry["encounter_id"][2:5] for entry in scanned}),
            "encounters_total": self._encounters_total,
            "truncated": len(entries) < self._encounters_total
            or any(bool(entry.get("truncated")) for entry in entries),
            "dropped_records": (
                self._dropped if dropped_records is None else dropped_records
            ),
            "index": entries,
        }
        key = manifest_key(run_id)
        existing = self.read_manifest(run_id)
        if existing is not None:
            current: Any = existing.get("attributes")
            if current == json.loads(json.dumps(attributes, default=str)):
                return ManifestWrite(run_id, key, False, None, attributes)
            raise ManifestConflictError(
                f"a manifest for run {run_id!r} already exists at {key} and differs: "
                "the DuckBrain client is append-only and get() returns the FIRST "
                "record for a key, so a second manifest would make the run read as "
                "the stale one — write the manifest once, at run end (§4.3 / O-5)"
            )

        text = (
            f"battle telemetry manifest run {run_id}: "
            f"{attributes['encounters_total']} encounter partitions, "
            f"arm {attributes['decision_arm']}, "
            f"model {attributes['model_decision']}, "
            f"{attributes['dropped_records']} dropped records"
        )
        with client_root(self.root):
            memory_id = _client.remember(
                key=key,
                domain=MANIFEST_DOMAIN,
                attributes=attributes,
                embedding_text=text,
                namespace=self.namespace,
            )
        return ManifestWrite(run_id, key, True, memory_id, attributes)

    def read_manifest(self, run_id: str) -> dict[str, Any] | None:
        """Read the manifest back through the client's exact-key lookup."""
        with client_root(self.root):
            return _client.get(key=manifest_key(run_id), namespace=self.namespace)

    # ── index entry construction ──

    def _entry_for(
        self, ref: PartitionRef, *, outcome: str | None = None
    ) -> tuple[dict[str, Any] | None, str | None, str | None]:
        """Build the manifest entry for one partition, plus its ts bounds.

        Read from disk (never from a buffer), so the entry describes what a
        reader will find rather than what this process intended to write.
        """
        path = self._partition_path(ref)
        fresh = self._read_partition(path)
        if fresh.count == 0:
            return None, None, None
        first = fresh.records[0] if fresh.records else {}
        species, level = _opponent_of(fresh.records)
        encounter_outcome = outcome or _encounter_outcome_of(fresh.records)
        hit_cap = (
            fresh.count >= MAX_RECORDS_PER_FILE
            or fresh.size >= MAX_BYTES_PER_FILE
            or self._successor_continues(ref)
        )
        stamps = [str(record["ts"]) for record in fresh.records if record.get("ts")]
        entry = {
            "encounter_id": ref.encounter_id,
            "file": ref.filename,
            "map": str(first.get("map", "Map_00")),
            "map_resolved": bool(first.get("map_resolved", False)),
            "opponent_species": species,
            "opponent_species_resolved": _UNRESOLVED_SPECIES.match(species) is None,
            "opponent_level": level,
            "battle_type": str(first.get("battle_type", "unknown")),
            "turns": fresh.last_turn,
            "records": fresh.count,
            "outcome": encounter_outcome,
            "continued_from": self._continued_from_for(ref),
            "truncated": hit_cap,
        }
        return (
            entry,
            (min(stamps) if stamps else None),
            (max(stamps) if stamps else None),
        )

    def _scan_run(self, run_id: str) -> list[dict[str, Any]]:
        """Index every partition of *run_id* that is on disk (§4.3 index)."""
        if not self.data_dir.is_dir():
            return []
        entries: list[dict[str, Any]] = []
        for path in sorted(self.data_dir.glob(f"battle-{run_id}-*.jsonl")):
            try:
                ref = parse_partition_filename(path.name)
            except ValueError:
                continue  # an unparseable name is the §7.1 checker's finding
            if ref.run_id != run_id:
                continue
            entry, started, ended = self._entry_for(ref)
            if entry is None:
                continue
            entries.append(entry)
            self._note_ts(run_id, started, ended)
            self._episodes.add(ref.episode)
        return sorted(entries, key=lambda item: item["encounter_id"])

    def _continued_from_for(self, ref: PartitionRef) -> str | None:
        """§4.2 continuation link: the predecessor this partition split from.

        Structural, so a later process can re-derive it exactly: the store only
        ever opens ordinal *n+1* when ordinal *n* could not take the next
        record, and that condition is re-testable from the successor's first
        record (``_predecessor_split``). A distinct encounter written at
        ordinal *n+1* — not a split — therefore carries no link.
        """
        declared = self._continued_from.get(ref.encounter_id)
        if declared is not None:
            return declared
        if not self._predecessor_split(ref):
            return None
        return PartitionRef(ref.run_id, ref.episode, ref.ordinal - 1).encounter_id

    def _predecessor_split(self, ref: PartitionRef) -> bool:
        """True when *ref* exists only because its predecessor was at a cap."""
        if ref.ordinal <= 1:
            return False
        predecessor = PartitionRef(ref.run_id, ref.episode, ref.ordinal - 1)
        if not self._partition_path(predecessor).is_file():
            return False
        successor = self._read_partition(self._partition_path(ref))
        if not successor.records:
            return False
        before = self._read_partition(self._partition_path(predecessor))
        first = json.dumps(successor.records[0], sort_keys=True, default=str) + "\n"
        return (
            before.count >= MAX_RECORDS_PER_FILE
            or before.size + len(first.encode("utf-8")) > MAX_BYTES_PER_FILE
        )

    def _successor_continues(self, ref: PartitionRef) -> bool:
        """True when *ref* was closed at a cap and continued in the next ordinal."""
        if ref.ordinal >= MAX_ORDINAL:
            return False
        successor = PartitionRef(ref.run_id, ref.episode, ref.ordinal + 1)
        if not self._partition_path(successor).is_file():
            return False
        return self._predecessor_split(successor)

    def _note_ts(self, run_id: str, started: str | None, ended: str | None) -> None:
        """Track the run's observed window from the records themselves."""
        if started is not None:
            current_start = self._started.get(run_id)
            if current_start is None or started < current_start:
                self._started[run_id] = started
        if ended is not None:
            current_end = self._ended.get(run_id)
            if current_end is None or ended > current_end:
                self._ended[run_id] = ended

    def _stamp_run_identity(self, run_id: str, record: Mapping[str, Any]) -> None:
        self._identity.setdefault(
            run_id,
            {
                "decision_arm": record.get("decision_arm"),
                "model_decision": record.get("model_decision"),
                "model_vision": record.get("model_vision"),
                "provider": record.get("provider"),
            },
        )
        ts = record.get("ts")
        if isinstance(ts, str):
            self._note_ts(run_id, ts, ts)


# ── helpers ─────────────────────────────────────────────────────────────────


def _opponent_of(records: Sequence[Mapping[str, Any]]) -> tuple[str, int]:
    """The defending side's species/level, from the records themselves."""
    for record in records:
        if record.get("attacker_side") == "player":
            species = record.get("defender_species")
            level = record.get("defender_level")
            if isinstance(species, str):
                return species, int(level) if _is_int(level) else 0
    for record in records:
        if record.get("attacker_side") == "enemy":
            species = record.get("attacker_species")
            level = record.get("attacker_level")
            if isinstance(species, str):
                return species, int(level) if _is_int(level) else 0
    return "unknown", 0


def _encounter_outcome_of(records: Sequence[Mapping[str, Any]]) -> str:
    """Last non-``unknown`` encounter outcome stamped on the partition."""
    for record in reversed(records):
        value = record.get("encounter_outcome")
        if value in ENCOUNTER_OUTCOMES and value != "unknown":
            return str(value)
    return "unknown"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
