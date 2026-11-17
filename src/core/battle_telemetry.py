"""Passive battle telemetry capture for the battle-telemetry data contract.

Contract: ``specs/contracts/battle-telemetry.md`` (row BTL-SCHEMA-1).
Row: BTL-RAM-1 — RAM battle reader.

What this module is
-------------------
A pure OBSERVER over the RAM reader. It samples ``read_battle_state()`` on a
caller-driven cadence and emits one contract-shaped record per observed attack
event. Damage is MEASURED as the defender's HP delta between two consecutive
samples — never inferred from a damage formula — so a knockout record's damage
is the defender's remaining HP, because HP clamps at 0 (contract §3.3 R5).

It never presses a button, never steps the emulator, never advances a frame and
never mutates emulator state: the only methods it calls on its source are
``read_battle_state()`` and ``current_map_name()``.

Address resolution (§8)
-----------------------
``BattleAddressResolver`` resolves each address the reader uses by SYMBOL NAME
from a ``data/rom/*.sym`` map when one exists, and otherwise falls back to the
constant block ``src/core/ram_reader.py`` already carries. This module holds no
address literal of its own: every number comes from the symbol file or from
``getattr(ram_reader, <constant named in ADDRESS_BINDINGS>)``. Each resolved
address carries a verification note naming the symbol, the source
(``sym-file`` / ``reader-constant-block``) and the basis for trusting it.

Decisions this module had to settle
-----------------------------------
O-1 (symbol map) — see the resolver docstring: symbol file first, reader
constant block second, conflicts recorded rather than hidden.
O-2 (how ``turn`` is detected) — a player action is observed through the
player's OWN move-PP decrement (contract §10 O-2 names PP decrement); the enemy
response belongs to that same ``turn`` (§10 O-3). When a source exposes no PP
data at all, the sampler falls back to an enemy-HP drop as the player-action
signal and labels the move ``Move#0`` so the label is honestly unresolved.
A whiff is distinguished from a non-damaging move by the move's damage class,
reused from the repo's existing keyword classifier (``EnemyPredictor``); when
that classifier cannot decide, the outcome is ``unknown`` instead of a guess.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from src.core import ram_reader as _ram_reader

__all__ = [
    "ADDRESS_BINDINGS",
    "AddressResolutionError",
    "BattleAddressResolver",
    "BattleEncounter",
    "BattleSnapshot",
    "BattleStateSource",
    "BattleTelemetryError",
    "BattleTelemetrySampler",
    "MonSnapshot",
    "MovePP",
    "ResolvedAddress",
    "SymbolBinding",
    "TelemetryIdentity",
    "TelemetrySourceError",
    "default_move_kind_classifier",
    "read_snapshot",
]

#: Contract enums (§3.2).
BATTLE_TYPES = ("wild", "trainer", "unknown")
OUTCOMES = ("damage", "no_damage", "miss", "immune", "unknown")
ENCOUNTER_OUTCOMES = ("won", "lost", "fled", "caught", "unknown")

#: Contract ranges (§3.2 / §3.3 R2).
LEVEL_MIN = 2
LEVEL_MAX = 100

#: Symbol-file suffix searched for in ``data/rom/`` (§8.2).
SYM_SUFFIX = ".sym"

#: Repo-relative directory the contract names as the symbol source (§8.2).
DEFAULT_SYM_DIR = Path("data/rom")

_UNRESOLVED_SPECIES = re.compile(r"^#\d+$")
_UNRESOLVED_MOVE = re.compile(r"^Move#\d+$")
_UNRESOLVED_MAP = re.compile(r"^Map_[0-9A-F]{2}$")


class BattleTelemetryError(Exception):
    """Base error for battle-telemetry capture."""


class AddressResolutionError(BattleTelemetryError):
    """An address could not be resolved from any attested source."""


class TelemetrySourceError(BattleTelemetryError):
    """The battle-state source returned a shape this sampler cannot read."""


# ── Address resolution layer ────────────────────────────────────────────────


@dataclass(frozen=True)
class SymbolBinding:
    """One address the reader uses, expressed as symbol + struct offset.

    ``symbol`` is looked up in a ``*.sym`` file when one ships. ``offset`` is
    the offset of the field INSIDE that symbol, exactly as the reader's
    constant-block comments document it (enemy party struct: level ``+33``,
    max HP ``+34``, PP ``+29``, type1 ``+5``, moves ``+8``). ``constant`` names
    the ``src/core/ram_reader.py`` attribute that already holds the resolved
    address, which is the fallback source and the cross-check.
    """

    symbol: str
    constant: str
    offset: int
    basis: str


#: Every address this module can resolve, keyed by the field it serves.
#: The numbers live in ``src/core/ram_reader.py`` or in a symbol file — never
#: here (contract §8.1/R-014).
ADDRESS_BINDINGS: dict[str, SymbolBinding] = {
    "in_battle": SymbolBinding(
        "wIsInBattle",
        "ADDR_IS_IN_BATTLE",
        0,
        "reader constant is annotated 'wIsInBattle — 0=none, 1=wild, 2=trainer' "
        "and read_battle_state() derives battle_type from it (pret/pokered name)",
    ),
    "map_id": SymbolBinding(
        "wCurMap",
        "ADDR_CUR_MAP",
        0,
        "reader constant is annotated 'wCurMap — current map ID' and "
        "current_map_name() maps it through MAP_NAMES (pret/pokered name)",
    ),
    "player_species": SymbolBinding(
        "wBattleMonSpecies",
        "ADDR_BATTLE_MON_SPECIES",
        0,
        "reader constant heads the wBattleMon block at the pret/pokered "
        "wBattleMon base; read_battle_state() resolves the name through "
        "STARTER_SPECIES_NAMES/POKEMON_NAMES",
    ),
    "player_hp": SymbolBinding(
        "wBattleMonHP",
        "ADDR_BATTLE_MON_HP",
        0,
        "reader constant annotated 'u16 (BE in struct copies)'; "
        "read_battle_state() validates byte order against max HP before use",
    ),
    "player_level": SymbolBinding(
        "wBattleMonLevel",
        "ADDR_BATTLE_MON_LEVEL",
        0,
        "reader constant annotated as the level byte of the battle_struct "
        "layout (battle_struct +14)",
    ),
    "player_max_hp": SymbolBinding(
        "wBattleMonMaxHP",
        "ADDR_BATTLE_MON_MAX_HP",
        0,
        "reader constant annotated 'u16 (BE)', battle_struct +15",
    ),
    "player_moves": SymbolBinding(
        "wBattleMonMoves",
        "ADDR_BATTLE_MON_MOVES",
        0,
        "reader constant annotated '4 bytes' of move ids, battle_struct +8",
    ),
    "player_pp": SymbolBinding(
        "wBattleMonPP",
        "ADDR_BATTLE_MON_PP",
        0,
        "reader constant annotated '4 bytes' of per-slot PP, battle_struct +25",
    ),
    "player_status": SymbolBinding(
        "wBattleMonStatus",
        "ADDR_BATTLE_MON_STATUS",
        0,
        "reader constant annotated as the status byte, battle_struct +4",
    ),
    "player_type1": SymbolBinding(
        "wBattleMonType1",
        "ADDR_BATTLE_MON_TYPE1",
        0,
        "reader constant annotated as type1, battle_struct +5",
    ),
    "player_type2": SymbolBinding(
        "wBattleMonType2",
        "ADDR_BATTLE_MON_TYPE2",
        0,
        "reader constant annotated as type2, battle_struct +6",
    ),
    "enemy_species": SymbolBinding(
        "wEnemyPartyMon1",
        "ADDR_ENEMY_MON_SPECIES",
        0,
        "reader constant annotated 'enemy party struct species (0xB1 Squirtle)' "
        "at the party_struct base; the old 0xCFE7 battle-copy constants read "
        "garbage on the SGB Enhanced ROM (2026-08-18 note)",
    ),
    "enemy_level": SymbolBinding(
        "wEnemyPartyMon1",
        "ADDR_ENEMY_MON_LEVEL",
        33,
        "reader constant annotated 'enemy party struct level (party_struct +33)'",
    ),
    "enemy_max_hp": SymbolBinding(
        "wEnemyPartyMon1",
        "ADDR_ENEMY_MON_MAX_HP",
        34,
        "reader constant annotated 'enemy party struct max HP u16 (BE)' "
        "(party_struct +34)",
    ),
    "enemy_moves": SymbolBinding(
        "wEnemyPartyMon1",
        "ADDR_ENEMY_MON_MOVES",
        8,
        "reader constant annotated 'enemy party struct moves (0x21 TACKLE...)' "
        "(box_struct +8)",
    ),
    "enemy_pp": SymbolBinding(
        "wEnemyPartyMon1",
        "ADDR_ENEMY_MON_PP",
        29,
        "reader constant annotated 'enemy party struct PP (box_struct +29)'",
    ),
    "enemy_type1": SymbolBinding(
        "wEnemyPartyMon1",
        "ADDR_ENEMY_MON_TYPE1",
        5,
        "reader constant annotated 'enemy party struct type1 (0x15 = WATER)' "
        "(box_struct +5)",
    ),
    "enemy_type2": SymbolBinding(
        "wEnemyPartyMon1",
        "ADDR_ENEMY_MON_TYPE2",
        6,
        "reader constant annotated 'enemy party struct type2' (box_struct +6)",
    ),
    "enemy_hp": SymbolBinding(
        "wEnemyLiveHP",
        "ADDR_ENEMY_MON_HP",
        0,
        "reader constant annotated 'live enemy HP u16 (LE) — damage-proven' "
        "(2026-08-18 WRAM sweep + damage-diff experiment); the reader cites no "
        "pret symbol for this HP-bar mirror, so the symbol name is the reader's own",
    ),
}

#: The two values ``ResolvedAddress.source`` may take (§8.2).
SOURCE_SYM_FILE = "sym-file"
SOURCE_CONSTANT = "reader-constant-block"

_SYM_LINE = re.compile(r"^(?P<bank>[0-9A-Fa-f]{2,4}):(?P<addr>[0-9A-Fa-f]{4,8})$")


@dataclass(frozen=True)
class ResolvedAddress:
    """One address plus the evidence for trusting it (§8.2, §3.3).

    ``note`` is the verification note the contract's acceptance asks for:
    symbol name, source, and basis.
    """

    field_name: str
    symbol: str
    address: int
    source: str
    source_detail: str
    basis: str

    @property
    def verification_note(self) -> str:
        """Human-readable note: symbol, source and basis on one line."""
        return (
            f"{self.field_name}: {self.symbol} -> 0x{self.address:04X} "
            f"[source={self.source} ({self.source_detail})] "
            f"basis={self.basis}"
        )

    @property
    def verified(self) -> bool:
        """True when the resolution carries every attestation field."""
        return bool(self.symbol and self.source and self.basis and self.source_detail)


def _default_sym_dir() -> Path:
    """Resolve the repo's ``data/rom`` regardless of the caller's cwd."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / DEFAULT_SYM_DIR
        if candidate.is_dir():
            return candidate
    return Path.cwd() / DEFAULT_SYM_DIR


class BattleAddressResolver:
    """Resolve the reader's battle addresses by symbol, with a constant fallback.

    Lookup order (contract §8.2, ``OPEN`` O-1):

    1. ``<sym_dir>/*.sym`` — RGBDS-style ``BANK:ADDR Label`` lines. A symbol
       found here gives ``address = (sym_addr + offset) & 0xFFFF``.
    2. ``src/core/ram_reader.py``'s constant block — the only grounded address
       source that ships in the repo today (no ``.sym`` exists).

    A symbol file that disagrees with the constant block does not abort the
    capture: the symbol file WINS (it is the ROM's own symbol map) and the
    disagreement is recorded in :meth:`conflicts` and in the note, so a stale
    constant block is visible instead of silent.
    """

    def __init__(
        self,
        sym_dir: str | Path | None = None,
        reader_module: Any | None = None,
    ) -> None:
        self._reader = reader_module if reader_module is not None else _ram_reader
        self._sym_dir = Path(sym_dir) if sym_dir is not None else _default_sym_dir()
        self._sym_map: dict[str, tuple[int, str]] | None = None
        self._cache: dict[str, ResolvedAddress] = {}
        self._conflicts: list[str] = []
        self._sym_files: list[str] = []

    # ── symbol files ──

    @property
    def sym_files(self) -> list[str]:
        """Symbol files that were read (empty when none ships)."""
        self._load_sym_map()
        return list(self._sym_files)

    @staticmethod
    def parse_sym_text(text: str, origin: str = "<sym>") -> dict[str, tuple[int, str]]:
        """Parse RGBDS ``BANK:ADDR Label`` lines into ``label -> (addr, origin)``."""
        symbols: dict[str, tuple[int, str]] = {}
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith(";"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            match = _SYM_LINE.match(parts[0])
            if not match:
                continue
            address = int(match.group("addr"), 16) & 0xFFFF
            symbols[parts[1]] = (address, origin)
        return symbols

    def _load_sym_map(self) -> dict[str, tuple[int, str]]:
        if self._sym_map is not None:
            return self._sym_map
        merged: dict[str, tuple[int, str]] = {}
        files: list[str] = []
        if self._sym_dir.is_dir():
            for path in sorted(self._sym_dir.glob(f"*{SYM_SUFFIX}")):
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                files.append(str(path))
                for label, entry in self.parse_sym_text(text, str(path)).items():
                    merged.setdefault(label, entry)
        self._sym_map = merged
        self._sym_files = files
        return merged

    # ── resolution ──

    @property
    def conflicts(self) -> list[str]:
        """Symbol-vs-constant disagreements seen so far (empty on agreement)."""
        return list(self._conflicts)

    def resolve(self, field_name: str) -> ResolvedAddress:
        """Resolve one field from :data:`ADDRESS_BINDINGS`."""
        cached = self._cache.get(field_name)
        if cached is not None:
            return cached
        binding = ADDRESS_BINDINGS.get(field_name)
        if binding is None:
            raise AddressResolutionError(
                f"unknown address field {field_name!r}; "
                f"known fields: {sorted(ADDRESS_BINDINGS)}"
            )
        constant = self._constant(binding)
        sym_entry = self._load_sym_map().get(binding.symbol)
        if sym_entry is not None:
            sym_address, origin = sym_entry
            address = (sym_address + binding.offset) & 0xFFFF
            if constant != address:
                self._conflicts.append(
                    f"{binding.symbol} (+{binding.offset}) resolves to "
                    f"0x{address:04X} from {origin} but "
                    f"ram_reader.{binding.constant} is 0x{constant:04X}; "
                    "symbol file wins"
                )
            resolved = ResolvedAddress(
                field_name=field_name,
                symbol=binding.symbol,
                address=address,
                source=SOURCE_SYM_FILE,
                source_detail=f"{origin} (offset +{binding.offset})",
                basis=binding.basis,
            )
        else:
            resolved = ResolvedAddress(
                field_name=field_name,
                symbol=binding.symbol,
                address=constant,
                source=SOURCE_CONSTANT,
                source_detail=f"ram_reader.{binding.constant}",
                basis=binding.basis,
            )
        self._cache[field_name] = resolved
        return resolved

    def _constant(self, binding: SymbolBinding) -> int:
        try:
            value = getattr(self._reader, binding.constant)
        except AttributeError as exc:
            raise AddressResolutionError(
                f"neither a symbol-file entry for {binding.symbol!r} nor the "
                f"reader constant ram_reader.{binding.constant} exists"
            ) from exc
        return int(value)

    def address(self, field_name: str) -> int:
        """Resolved integer address for *field_name*."""
        return self.resolve(field_name).address

    def resolve_all(self) -> dict[str, ResolvedAddress]:
        """Every binding, resolved (order follows :data:`ADDRESS_BINDINGS`)."""
        return {name: self.resolve(name) for name in ADDRESS_BINDINGS}

    def verification_notes(self) -> list[str]:
        """One verification note per binding — the AC2 evidence table."""
        return [res.verification_note for res in self.resolve_all().values()]


# ── battle-state snapshots ──────────────────────────────────────────────────


class BattleStateSource(Protocol):
    """The two read-only calls the sampler makes (never a write)."""

    def read_battle_state(self) -> Mapping[str, Any]:  # pragma: no cover - protocol
        ...

    def current_map_name(self) -> str:  # pragma: no cover - protocol
        ...


@dataclass(frozen=True)
class MovePP:
    """One move slot of an observed monster: its label and remaining PP."""

    slot: int
    label: str
    pp: int


@dataclass(frozen=True)
class MonSnapshot:
    """One side of a battle, as the reader reports it."""

    species: str
    level: int
    hp: int
    max_hp: int
    moves: tuple[MovePP, ...] = ()

    @property
    def pp_total(self) -> int:
        """Sum of remaining PP across slots — the player-action counter."""
        return sum(move.pp for move in self.moves)

    @property
    def pp_by_slot(self) -> dict[int, int]:
        """Slot -> remaining PP, for per-slot decrement detection."""
        return {move.slot: move.pp for move in self.moves}

    def move_label(self, slot: int) -> str | None:
        """Label of *slot*, or ``None`` when the slot holds no move."""
        for move in self.moves:
            if move.slot == slot:
                return move.label
        return None

    @property
    def first_move_label(self) -> str:
        """First known move label, or ``Move#0`` when nothing is known."""
        return self.moves[0].label if self.moves else "Move#0"


@dataclass(frozen=True)
class BattleSnapshot:
    """A full battle observation: both sides, the map and the battle class."""

    in_battle: bool
    battle_type: str
    map_name: str
    player: MonSnapshot
    enemy: MonSnapshot

    @property
    def map_resolved(self) -> bool:
        """False when the map name is the reader's ``Map_XX`` placeholder."""
        return _UNRESOLVED_MAP.match(self.map_name) is None


def _iso(moment: datetime) -> str:
    """ISO-8601 UTC second-resolution stamp, as §3.1 requires."""
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _mon_from_state(block: Any, side: str) -> MonSnapshot:
    if not isinstance(block, Mapping):
        raise TelemetrySourceError(
            f"read_battle_state()[{side!r}] is {type(block).__name__}, not a mapping"
        )
    try:
        species = str(block.get("name", "#0"))
        level = int(block.get("level", 0) or 0)
        hp = int(block.get("hp", 0) or 0)
        max_hp = int(block.get("max_hp", 0) or 0)
    except (TypeError, ValueError) as exc:
        raise TelemetrySourceError(
            f"read_battle_state()[{side!r}] carries non-numeric HP/level fields"
        ) from exc
    moves: list[MovePP] = []
    for index, raw in enumerate(block.get("moves") or []):
        if not isinstance(raw, Mapping):
            continue
        try:
            slot = int(raw.get("slot", index + 1))
            pp = int(raw.get("pp", 0) or 0)
        except (TypeError, ValueError):
            continue
        moves.append(MovePP(slot=slot, label=str(raw.get("name", "Move#0")), pp=pp))
    return MonSnapshot(
        species=species,
        level=level,
        hp=hp,
        max_hp=max_hp,
        moves=tuple(sorted(moves, key=lambda move: move.slot)),
    )


def read_snapshot(source: BattleStateSource) -> BattleSnapshot:
    """Sample *source* into a :class:`BattleSnapshot` (read-only)."""
    state = source.read_battle_state()
    if not isinstance(state, Mapping):
        raise TelemetrySourceError(
            f"read_battle_state() returned {type(state).__name__}, not a mapping"
        )
    battle_type = str(state.get("battle_type", "unknown")).lower()
    if battle_type not in BATTLE_TYPES:
        battle_type = "unknown"
    map_name = str(source.current_map_name() or "Map_00")
    return BattleSnapshot(
        in_battle=battle_type != "unknown",
        battle_type=battle_type,
        map_name=map_name,
        player=_mon_from_state(state.get("player"), "player"),
        enemy=_mon_from_state(state.get("enemy"), "enemy"),
    )


# ── move damage class (whiff vs non-damaging move) ──────────────────────────

_MOVE_KIND_CACHE: dict[str, str] = {}
_CLASSIFIER: Any | None = None


def default_move_kind_classifier(move_label: str) -> str:
    """Classify a move label as ``damaging``, ``status`` or ``unknown``.

    A Gen-1 move's damage class is not in RAM, so this reuses the repo's
    existing keyword classifier (``EnemyPredictor._get_move_category`` in
    ``src/core/combat.py``) instead of authoring a second move table. It is a
    heuristic: ``unknown`` is returned when the classifier is unavailable, and
    callers may inject a better classifier through
    ``BattleTelemetrySampler(move_kind=...)``.
    """
    cached = _MOVE_KIND_CACHE.get(move_label)
    if cached is not None:
        return cached
    global _CLASSIFIER
    kind = "unknown"
    try:
        if _CLASSIFIER is None:
            from src.core.combat import EnemyPredictor

            _CLASSIFIER = EnemyPredictor()
        from src.core.combat import MoveCategory

        category = _CLASSIFIER._get_move_category(move_label)
        kind = "status" if category is MoveCategory.STATUS else "damaging"
    except Exception:  # the classifier is an optional convenience, not a gate
        kind = "unknown"
    _MOVE_KIND_CACHE[move_label] = kind
    return kind


# ── identity and encounter bookkeeping ──────────────────────────────────────

_RUN_ID = re.compile(r"^[A-Za-z0-9_]+$")


@dataclass(frozen=True)
class TelemetryIdentity:
    """The run identity every record carries (contract §3.1)."""

    run_id: str
    episode: int
    decision_arm: str
    model_decision: str | None = None
    model_vision: str | None = None
    provider: str | None = None

    def __post_init__(self) -> None:
        if not _RUN_ID.match(self.run_id):
            raise ValueError(
                f"run_id {self.run_id!r} must match [A-Za-z0-9_]+ "
                "(contract §4.1: the partition filename parses it)"
            )
        if self.episode < 1:
            raise ValueError(f"episode must be >= 1, got {self.episode}")


@dataclass
class BattleEncounter:
    """One encounter's bookkeeping — the manifest-entry surface (§4.3)."""

    run_id: str
    episode: int
    ordinal: int
    map_name: str
    map_resolved: bool
    battle_type: str
    opponent_species: str
    opponent_level: int
    started: str
    turns: int = 0
    records: int = 0
    outcome: str = "unknown"
    ended: str | None = None

    @property
    def encounter_id(self) -> str:
        """``ep<EEE>-enc<CCC>`` (contract §3.1)."""
        return f"ep{self.episode:03d}-enc{self.ordinal:03d}"

    @property
    def opponent_species_resolved(self) -> bool:
        return _UNRESOLVED_SPECIES.match(self.opponent_species) is None

    def partition_filename(self) -> str:
        """``battle-<run_id>-ep<EEE>-enc<CCC>.jsonl`` (contract §4.1)."""
        return f"battle-{self.run_id}-{self.encounter_id}.jsonl"


@dataclass(frozen=True)
class _Action:
    """One detected action: which side acted, with which move."""

    side: str
    move: str

    @property
    def move_resolved(self) -> bool:
        return _UNRESOLVED_MOVE.match(self.move) is None


# ── the passive sampler ─────────────────────────────────────────────────────


class BattleTelemetrySampler:
    """Passive observer: one contract-shaped record per observed attack event.

    Call :meth:`sample` on a cadence faster than a battle turn. Each call reads
    the source once, diffs against the previous sample and emits records for the
    actions the diff proves. Between calls the previous snapshot is retained, so
    an HP delta that spans a full exchange (player hit + enemy counter) yields
    both records from one sample.

    The object is a pure observer: it holds no emulator handle and only ever
    calls ``read_battle_state()`` and ``current_map_name()`` on *source*.
    """

    def __init__(
        self,
        source: BattleStateSource,
        identity: TelemetryIdentity,
        *,
        resolver: BattleAddressResolver | None = None,
        clock: Callable[[], datetime] = _utc_now,
        move_kind: Callable[[str], str] = default_move_kind_classifier,
    ) -> None:
        self._source = source
        self._identity = identity
        self._resolver = resolver if resolver is not None else BattleAddressResolver()
        self._clock = clock
        self._move_kind = move_kind
        self._previous: BattleSnapshot | None = None
        self._encounter: BattleEncounter | None = None
        self._closed: list[BattleEncounter] = []
        self._ordinals: dict[int, int] = {}
        self._turn = 0
        self._records: list[dict[str, Any]] = []
        self._dropped: list[dict[str, Any]] = []
        self._unattributed_hp_deltas = 0
        self._skipped_actions = 0

    # ── introspection (no emulator access) ──

    @property
    def resolver(self) -> BattleAddressResolver:
        return self._resolver

    @property
    def records(self) -> list[dict[str, Any]]:
        """Every record emitted so far, in emission order."""
        return list(self._records)

    @property
    def dropped_records(self) -> int:
        """Records refused under §3.3 R2 (visible loss, never a null)."""
        return len(self._dropped)

    @property
    def dropped_details(self) -> list[dict[str, Any]]:
        return list(self._dropped)

    @property
    def unattributed_hp_deltas(self) -> int:
        """HP deltas seen with no attributable action (never fabricated)."""
        return self._unattributed_hp_deltas

    @property
    def skipped_actions(self) -> int:
        """Extra player actions a coarse cadence collapsed into one sample."""
        return self._skipped_actions

    @property
    def turn(self) -> int:
        """Current 1-based player-action index of the open encounter."""
        return self._turn

    @property
    def current_encounter(self) -> BattleEncounter | None:
        return self._encounter

    @property
    def encounters(self) -> list[BattleEncounter]:
        """Closed encounters plus the open one, in observation order."""
        result = list(self._closed)
        if self._encounter is not None:
            result.append(self._encounter)
        return result

    # ── driver surface ──

    def start_episode(self, episode: int, *, ts: str | None = None) -> None:
        """Close the open encounter and move to *episode* of the same run."""
        if episode < 1:
            raise ValueError(f"episode must be >= 1, got {episode}")
        stamp = ts or _iso(self._clock())
        self._close_encounter(outcome="unknown", ended=stamp)
        self._identity = TelemetryIdentity(
            run_id=self._identity.run_id,
            episode=episode,
            decision_arm=self._identity.decision_arm,
            model_decision=self._identity.model_decision,
            model_vision=self._identity.model_vision,
            provider=self._identity.provider,
        )
        self._previous = None
        self._turn = 0

    def close_encounter(
        self, outcome: str = "unknown", *, ts: str | None = None
    ) -> BattleEncounter | None:
        """Close the open encounter with a final outcome (§4.3 rewrite hook)."""
        if outcome not in ENCOUNTER_OUTCOMES:
            raise ValueError(
                f"encounter outcome {outcome!r} not in {ENCOUNTER_OUTCOMES}"
            )
        stamp = ts or _iso(self._clock())
        return self._close_encounter(outcome=outcome, ended=stamp)

    def sample(self, ts: str | None = None) -> list[dict[str, Any]]:
        """Read the source once and return the records this sample proves."""
        snapshot = read_snapshot(self._source)
        stamp = ts or _iso(self._clock())

        if not snapshot.in_battle:
            self._close_encounter(outcome="unknown", ended=stamp)
            self._previous = None
            return []

        if self._encounter is None:
            self._open_encounter(snapshot, stamp)
            self._previous = snapshot
            return []

        if self._opponent_changed(snapshot):
            self._close_encounter(outcome="unknown", ended=stamp)
            self._open_encounter(snapshot, stamp)
            self._previous = snapshot
            return []

        previous = self._previous
        self._previous = snapshot
        if previous is None:  # pragma: no cover - guarded by the branches above
            return []

        player_action, enemy_action, skipped = self._detect_actions(previous, snapshot)
        self._skipped_actions += skipped
        emitted: list[dict[str, Any]] = []

        if player_action is not None:
            self._turn += 1
            record = self._make_record(player_action, previous, snapshot, stamp)
            if record is not None:
                emitted.append(record)
        if enemy_action is not None:
            if self._turn < 1:
                # The enemy's response belongs to the player's current turn
                # (§10 O-3); without a visible player action that is turn 1.
                self._turn = 1
            record = self._make_record(enemy_action, previous, snapshot, stamp)
            if record is not None:
                emitted.append(record)
        if player_action is None and enemy_action is None:
            self._count_unattributed(previous, snapshot)
        return emitted

    # ── encounter lifecycle ──

    def _opponent_changed(self, snapshot: BattleSnapshot) -> bool:
        if self._encounter is None:
            return True
        return snapshot.enemy.species != self._encounter.opponent_species

    def _open_encounter(self, snapshot: BattleSnapshot, stamp: str) -> None:
        episode = self._identity.episode
        ordinal = self._ordinals.get(episode, 0) + 1
        self._ordinals[episode] = ordinal
        self._encounter = BattleEncounter(
            run_id=self._identity.run_id,
            episode=episode,
            ordinal=ordinal,
            map_name=snapshot.map_name,
            map_resolved=snapshot.map_resolved,
            battle_type=snapshot.battle_type,
            opponent_species=snapshot.enemy.species,
            opponent_level=snapshot.enemy.level,
            started=stamp,
        )
        self._turn = 0

    def _close_encounter(self, outcome: str, ended: str) -> BattleEncounter | None:
        encounter = self._encounter
        if encounter is None:
            return None
        if encounter.outcome == "unknown" and outcome != "unknown":
            encounter.outcome = outcome
        encounter.ended = ended
        self._closed.append(encounter)
        self._encounter = None
        return encounter

    # ── action detection (§10 O-2 / O-3) ──

    def _detect_actions(
        self, previous: BattleSnapshot, current: BattleSnapshot
    ) -> tuple[_Action | None, _Action | None, int]:
        """Return (player action, enemy action, collapsed extra player actions)."""
        player_action, skipped = self._detect_player_action(previous, current)
        enemy_action = self._detect_enemy_action(previous, current)
        return player_action, enemy_action, skipped

    def _detect_player_action(
        self, previous: BattleSnapshot, current: BattleSnapshot
    ) -> tuple[_Action | None, int]:
        pp_before = previous.player.pp_total
        pp_after = current.player.pp_total
        pp_channels = bool(previous.player.moves) and bool(current.player.moves)
        move = self._used_move(previous.player, current.player)

        if pp_channels and pp_after < pp_before:
            return _Action(side="player", move=move), (pp_before - pp_after) - 1

        if not pp_channels and current.enemy.hp < previous.enemy.hp:
            # No PP channel at all: an enemy-HP drop is the only player-action
            # evidence. The move label stays honestly unresolved.
            fallback = current.player.first_move_label
            return _Action(side="player", move=fallback), 0
        return None, 0

    def _detect_enemy_action(
        self, previous: BattleSnapshot, current: BattleSnapshot
    ) -> _Action | None:
        player_hp_drop = current.player.hp < previous.player.hp
        enemy_pp_drop = current.enemy.pp_total < previous.enemy.pp_total
        if not (player_hp_drop or enemy_pp_drop):
            return None
        return _Action(
            side="enemy", move=self._used_move(previous.enemy, current.enemy)
        )

    @staticmethod
    def _used_move(previous: MonSnapshot, current: MonSnapshot) -> str:
        """Label of the slot whose PP decreased (``Move#0`` when unknown)."""
        before = previous.pp_by_slot
        after = current.pp_by_slot
        for slot in sorted(after):
            if slot in before and after[slot] < before[slot]:
                label = current.move_label(slot)
                if label is not None:
                    return label
        return current.first_move_label

    def _count_unattributed(
        self, previous: BattleSnapshot, current: BattleSnapshot
    ) -> None:
        deltas = (
            previous.enemy.hp > current.enemy.hp
            or previous.player.hp > current.player.hp
        )
        if deltas:
            self._unattributed_hp_deltas += 1

    # ── record construction (§3.1 + §3.2) ──

    def _make_record(
        self,
        action: _Action,
        previous: BattleSnapshot,
        current: BattleSnapshot,
        stamp: str,
    ) -> dict[str, Any] | None:
        encounter = self._encounter
        if encounter is None:  # pragma: no cover - sample() always opens one
            return None

        attacker = current.player if action.side == "player" else current.enemy
        defender_before = previous.enemy if action.side == "player" else previous.player
        defender_after = current.enemy if action.side == "player" else current.player

        hp_before = defender_before.hp
        hp_after = defender_after.hp
        damage = max(0, hp_before - hp_after)
        max_hp = defender_after.max_hp or defender_before.max_hp
        outcome = self._outcome(damage, action.move)

        if hp_after == 0 and hp_before > 0:
            # §3.3 R5: HP clamps at 0, so the delta IS the remaining HP.
            encounter.outcome = "won" if action.side == "player" else "lost"

        record: dict[str, Any] = {
            # ── identity keys (§3.1) ──
            "run_id": self._identity.run_id,
            "episode": self._identity.episode,
            "encounter_id": encounter.encounter_id,
            "turn": self._turn,
            "map": encounter.map_name,
            "map_resolved": encounter.map_resolved,
            "ts": stamp,
            "model_decision": self._identity.model_decision,
            "model_vision": self._identity.model_vision,
            "provider": self._identity.provider,
            "decision_arm": self._identity.decision_arm,
            # ── event fields (§3.2) ──
            "attacker_side": action.side,
            "attacker_species": attacker.species,
            "attacker_species_resolved": _UNRESOLVED_SPECIES.match(attacker.species)
            is None,
            "attacker_level": attacker.level,
            "defender_species": defender_after.species,
            "defender_species_resolved": _UNRESOLVED_SPECIES.match(
                defender_after.species
            )
            is None,
            "defender_level": defender_after.level,
            "battle_type": encounter.battle_type,
            "move": action.move,
            "move_resolved": action.move_resolved,
            "outcome": outcome,
            "damage": damage,
            "damage_pct_of_max": self._damage_percent(damage, max_hp, hp_before),
            "defender_hp_before": hp_before,
            "defender_hp_after": hp_after,
            "defender_max_hp": max_hp,
            "encounter_outcome": encounter.outcome,
        }

        violations = self._validate(record)
        if violations:
            self._dropped.append(
                {
                    "encounter_id": encounter.encounter_id,
                    "turn": self._turn,
                    "attacker_side": action.side,
                    "violations": violations,
                }
            )
            return None

        encounter.records += 1
        encounter.turns = max(encounter.turns, self._turn)
        self._records.append(record)
        return record

    def _outcome(self, damage: int, move: str) -> str:
        if damage > 0:
            return "damage"
        if _UNRESOLVED_MOVE.match(move):
            return "unknown"
        kind = self._move_kind(move)
        if kind == "status":
            return "no_damage"
        if kind == "damaging":
            return "miss"
        return "unknown"

    @staticmethod
    def _damage_percent(damage: int, max_hp: int, hp_before: int) -> float | None:
        """Percent of max (§3.2) — null when the max HP is not knowable."""
        if max_hp < 1 or max_hp < hp_before:
            return None
        return round(damage / max_hp * 100, 1)

    @staticmethod
    def _validate(record: Mapping[str, Any]) -> list[str]:
        """§3.3 R2: out-of-range values drop the record, never null it."""
        violations: list[str] = []
        for side in ("attacker", "defender"):
            level = record[f"{side}_level"]
            if not isinstance(level, int) or not LEVEL_MIN <= level <= LEVEL_MAX:
                violations.append(
                    f"{side}_level {level!r} outside {LEVEL_MIN}..{LEVEL_MAX}"
                )
        for name in (
            "defender_hp_before",
            "defender_hp_after",
            "defender_max_hp",
            "damage",
            "turn",
        ):
            value = record[name]
            if not isinstance(value, int) or value < 0:
                violations.append(f"{name} {value!r} is not a non-negative int")
        if record["turn"] < 1:
            violations.append(f"turn {record['turn']!r} is not >= 1")
        expected = max(0, record["defender_hp_before"] - record["defender_hp_after"])
        if record["damage"] != expected:
            violations.append(
                f"damage {record['damage']} != before-after delta {expected} (R4)"
            )
        if record["outcome"] in ("no_damage", "miss", "immune") and record["damage"]:
            violations.append(
                f"outcome {record['outcome']} with damage {record['damage']} (R4)"
            )
        return violations
