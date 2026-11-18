"""Cross-model comparison over the KEYED battle-telemetry partitions.

Contract: ``specs/contracts/battle-telemetry.md`` (row BTL-SCHEMA-1).
Row: BTL-COMPARE-1 — the reader the partition keys were designed for.

What this module is
-------------------
A read-only comparison engine over ``pokemon-battle`` telemetry written by
:mod:`src.core.battle_telemetry_store` (row BTL-STORE-1). Given two run ids and
one game segment, it produces a side-by-side metric table, the list of
partitions it read and excluded, and — for every damage figure — the raw
``file:line`` records it was summed from.

How it reads (contract §5.2, in this exact order)
-------------------------------------------------
1. Resolve the candidate runs by ``run_id`` (E7). No other run is listed or
   opened — not even a directory glob is taken outside the two named runs.
2. Read **only** ``/game/battle/<run_id>/manifest`` for each run.
3. Apply E1..E6 to the manifest ``index`` entries in memory. The survivors name
   the files to open; everything else is excluded **without being opened**, and
   the reason is reported per key.
4. Open exactly those files and apply E8 (per-record ``turn`` window) while
   scanning.
5. Report partitions read / excluded and why.

The module imports the store READ-ONLY: it uses ``store.read_manifest()``, the
store's public partition-naming helpers and its ``record_identity()``. No store
file is edited, and no aggregate file is ever written (contract N8) — the table
is computed at read time.

Overkill: what the HP clamp allows (contract §3.2, §3.3 R5)
----------------------------------------------------------
``damage`` is the OBSERVED defender HP delta clamped at 0, so on a KO record it
is the defender's remaining HP and true overkill is structurally invisible in
the store. This module therefore reports three separate things instead of
inventing one:

* ``overkill_observed`` — the sum over KO RECORDS of
  ``damage - defender_hp_before``. It is 0 for every contract-conformant
  partition *by construction* (R5 clamps the delta to the remaining HP);
  printing it is the check that the clamp held, and a non-zero value is a
  writer defect rather than a model trait.
* ``overkill_ratio`` — per KO event, the attacker's own demonstrated per-hit
  damage (mean of its non-KO damaging hits) divided by the HP the kill needed;
  an encounter with several KO records reports the MEAN of those per-KO ratios.
  ``ratio > 1`` means a typical blow was bigger than that kill required. The
  scope of the per-hit mean is reported per encounter (``same_encounter`` or, as
  a fallback, ``same_run``); an encounter with no non-KO damaging hit at all is
  counted as ``unestimated`` rather than given a fabricated number.
* ``overkill_damage`` — ``max(0, typical_hit - hp_needed)`` summed over the
  encounter's KO events, i.e. the estimator's answer to "how much damage beyond
  the kill was spent".

That is an ESTIMATE and it is labelled as one everywhere it appears, because a
clamped store cannot answer the question exactly.

Metrics that stored events cannot answer
----------------------------------------
``items_used`` (potions) and ``switches`` have no field in contract §3.2 and
produce no attack event, so they are reported as ``n/a`` with the reason, never
as a zero and never as a guessed count. See :data:`NOT_DERIVABLE`.

Join rule (contract §5.3, restated here because it must appear in every output)
-------------------------------------------------------------------------------
A cross-run comparison joins on ``(map, opponent_species, level band)`` — never
on ``encounter_id`` (ordinals do not align across runs) and never on ``turn``
index alone.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from src.core.battle_telemetry_store import (
    DEFAULT_NAMESPACE,
    BattleTelemetryStore,
    parse_partition_filename,
    record_identity,
)

__all__ = [
    "BAND_WIDTH",
    "DATA_GAP_NO_BATTLE_PARTITIONS",
    "DATA_GAP_REAL_PAIRED_RUNS",
    "DEFAULT_DATA_NOTE",
    "JOIN_RULE",
    "NOT_DERIVABLE",
    "BattleTypeSplit",
    "ComparisonError",
    "ComparisonReport",
    "DamageSpotCheck",
    "EncounterMetrics",
    "ExcludedPartition",
    "LevelBandSplit",
    "MetricRow",
    "RecordRef",
    "RunMetrics",
    "RunSelection",
    "Segment",
    "SelectedPartition",
    "StoreCensus",
    "analyse_run",
    "compare_runs",
    "store_census",
]

#: Width of a level band in the per-level efficiency table.
BAND_WIDTH = 10

#: Contract §5.3 — printed by every report.
JOIN_RULE = (
    "join rule: a cross-run comparison joins on (map, opponent_species, level "
    "band) only — never encounter_id (ordinals do not align across runs), never "
    "turn index alone"
)

#: What this module prints when the store holds no telemetry at all.
DATA_GAP_NO_BATTLE_PARTITIONS = (
    "real paired runs: ABSENT — the telemetry store holds no battle-*.jsonl "
    "partition, so there is nothing to compare"
)

#: What this module prints when the two runs did not both yield encounters.
DATA_GAP_REAL_PAIRED_RUNS = (
    "real paired runs: not established by this report — it states only what it "
    "read; a table built over fixture events must be labelled as a fixture and "
    "is not evidence about two real game runs"
)

#: Default provenance line: the tool never claims more than it can see.
DEFAULT_DATA_NOTE = (
    "unlabeled: this report cannot tell a real game run from a fixture store; "
    "the caller must label it"
)

#: Metrics the contract's record shape cannot answer, with the reason why.
NOT_DERIVABLE: dict[str, str] = {
    "items_used": (
        "n/a — contract §3.2 records one observed ATTACK per record and carries "
        "no item/potion field, so a potion is indistinguishable from an absent "
        "action"
    ),
    "switches": (
        "n/a — a switch emits no attack event, so no stored record exists to "
        "count (§3.2 defines exactly one record per observed attack)"
    ),
}

_FILE_SAFE = re.compile(r"^battle-([A-Za-z0-9_]+)-ep(\d{3})-enc(\d{3})\.jsonl$")


class ComparisonError(Exception):
    """Base error for the comparison engine."""


# ── the segment (E1..E6 filter) ─────────────────────────────────────────────


@dataclass(frozen=True)
class Segment:
    """One game segment: the like-for-like slice two runs are compared on.

    Every field is a *filter*; ``None`` means "do not filter on this key". The
    keys are exactly contract §5.1 E1..E6, applied in that order by
    :meth:`rejection`, so the reported exclusion reason names the key that
    decided it.

    ``require_resolved`` (default) drops entries whose ``map``/``opponent``
    label is the reader's unresolved placeholder. The contract forbids joining
    on an unresolved label (§3.1 E1/E2), so an unresolved encounter is excluded
    even when no explicit map/species filter was asked for.
    """

    map_name: str | None = None
    opponent_species: str | None = None
    level_lo: int | None = None
    level_hi: int | None = None
    battle_type: str | None = None
    turn_lo: int | None = None
    turn_hi: int | None = None
    encounter_ids: tuple[str, ...] = ()
    require_resolved: bool = True

    def __post_init__(self) -> None:
        if self.battle_type is not None and self.battle_type not in (
            "wild",
            "trainer",
            "unknown",
        ):
            raise ComparisonError(
                f"battle_type {self.battle_type!r} not in ('wild', 'trainer', "
                "'unknown')"
            )
        for label, value in (
            ("level_lo", self.level_lo),
            ("level_hi", self.level_hi),
            ("turn_lo", self.turn_lo),
            ("turn_hi", self.turn_hi),
        ):
            if value is not None and value < 0:
                raise ComparisonError(f"{label} must be >= 0, got {value}")
        if (
            self.level_lo is not None
            and self.level_hi is not None
            and self.level_lo > self.level_hi
        ):
            raise ComparisonError(
                f"level_lo {self.level_lo} > level_hi {self.level_hi}"
            )
        if (
            self.turn_lo is not None
            and self.turn_hi is not None
            and self.turn_lo > self.turn_hi
        ):
            raise ComparisonError(f"turn_lo {self.turn_lo} > turn_hi {self.turn_hi}")

    # ── description ──

    def describe(self) -> str:
        """One-line human description of the slice (used in report headers)."""
        if self.is_unfiltered():
            return "all indexed encounters (no E1..E6 filter)"
        parts: list[str] = []
        if self.map_name is not None:
            parts.append(f"map={self.map_name!r}")
        if self.opponent_species is not None:
            parts.append(f"opponent={self.opponent_species}")
        if self.level_lo is not None or self.level_hi is not None:
            lo = "?" if self.level_lo is None else str(self.level_lo)
            hi = "?" if self.level_hi is None else str(self.level_hi)
            parts.append(f"level band {lo}..{hi}")
        if self.battle_type is not None:
            parts.append(f"battle_type={self.battle_type}")
        if self.encounter_ids:
            parts.append("encounter_id in " + ",".join(self.encounter_ids))
        if self.turn_lo is not None or self.turn_hi is not None:
            lo = "?" if self.turn_lo is None else str(self.turn_lo)
            hi = "?" if self.turn_hi is None else str(self.turn_hi)
            parts.append(f"turn window {lo}..{hi}")
        return " · ".join(parts)

    def is_unfiltered(self) -> bool:
        """True when no E1..E6 key narrows the selection."""
        return (
            self.map_name is None
            and self.opponent_species is None
            and self.level_lo is None
            and self.level_hi is None
            and self.battle_type is None
            and self.turn_lo is None
            and self.turn_hi is None
            and not self.encounter_ids
        )

    # ── E1..E6 ──

    def rejection(self, entry: Mapping[str, Any]) -> str | None:
        """The first E-key that excludes *entry*, or ``None`` when it survives.

        Evaluation order is contract §5.2 step 3: E1, E2, E3, E4, E5, E6. The
        returned string starts with the key's name so a report can group the
        exclusions by why they happened.
        """
        # E1 — map (+ map_resolved)
        if self.map_name is not None:
            name = entry.get("map")
            if name != self.map_name:
                return f"E1: map {name!r} != {self.map_name!r}"
        if self.require_resolved and entry.get("map_resolved") is not True:
            return f"E1: map {entry.get('map')!r} is unresolved (map_resolved=false)"

        # E2 — opponent_species (+ opponent_species_resolved)
        if self.opponent_species is not None:
            species = entry.get("opponent_species")
            if species != self.opponent_species:
                return f"E2: opponent_species {species!r} != {self.opponent_species!r}"
        if self.require_resolved and entry.get("opponent_species_resolved") is not True:
            return (
                f"E2: opponent_species {entry.get('opponent_species')!r} is "
                "unresolved (opponent_species_resolved=false)"
            )

        # E3 — opponent_level band
        if self.level_lo is not None or self.level_hi is not None:
            level = entry.get("opponent_level")
            if not isinstance(level, int) or isinstance(level, bool):
                return f"E3: opponent_level {level!r} is not an int"
            if self.level_lo is not None and level < self.level_lo:
                return f"E3: opponent_level {level} < {self.level_lo}"
            if self.level_hi is not None and level > self.level_hi:
                return f"E3: opponent_level {level} > {self.level_hi}"

        # E4 — encounter_id
        if self.encounter_ids:
            encounter_id = entry.get("encounter_id")
            if encounter_id not in self.encounter_ids:
                return f"E4: encounter_id {encounter_id!r} not requested"

        # E5 — turn window (manifest level: only the LOWER bound is decidable —
        # the entry carries the highest turn, so an encounter whose max turn is
        # below the window cannot contain a turn inside it. The upper bound is
        # an E8 per-record refinement, applied while scanning.)
        if self.turn_lo is not None:
            turns = entry.get("turns")
            if not isinstance(turns, int) or isinstance(turns, bool):
                return f"E5: turns {turns!r} is not an int"
            if turns < self.turn_lo:
                return f"E5: turns {turns} < turn_lo {self.turn_lo}"

        # E6 — battle_type
        if self.battle_type is not None:
            battle_type = entry.get("battle_type")
            if battle_type != self.battle_type:
                return f"E6: battle_type {battle_type!r} != {self.battle_type!r}"

        return None

    def admits_turn(self, turn: int) -> bool:
        """E8 — is *turn* inside the requested window?"""
        if self.turn_lo is not None and turn < self.turn_lo:
            return False
        if self.turn_hi is not None and turn > self.turn_hi:
            return False
        return True


# ── selection results (what was read, what was excluded, and why) ───────────


@dataclass(frozen=True)
class SelectedPartition:
    """One manifest entry that survived E1..E6 — the file to open."""

    run_id: str
    encounter_id: str
    file: str
    path: Path
    entry: Mapping[str, Any]


@dataclass(frozen=True)
class ExcludedPartition:
    """One manifest entry (or on-disk file) that was excluded without opening."""

    run_id: str
    encounter_id: str
    file: str
    reason: str


@dataclass(frozen=True)
class RunSelection:
    """Everything §5.2 decided about ONE run before a single event file opens."""

    run_id: str
    manifest_present: bool
    manifest: Mapping[str, Any] | None
    model_decision: str | None
    model_vision: str | None
    provider: str | None
    decision_arm: str | None
    index_entries: int
    encounters_total: int
    index_truncated: bool
    selected: tuple[SelectedPartition, ...]
    excluded: tuple[ExcludedPartition, ...]
    partitions_on_disk: tuple[str, ...]
    unindexed: tuple[str, ...]
    notes: tuple[str, ...] = ()

    @property
    def model_label(self) -> str:
        """How the report names this run's model (never a guess)."""
        if self.model_decision:
            return self.model_decision
        return f"{self.decision_arm or 'unknown'} (no model_decision)"

    @property
    def model_line(self) -> str:
        """``model · provider · arm`` — the identity columns of the table."""
        bits = [self.model_label]
        if self.provider:
            bits.append(f"provider={self.provider}")
        if self.decision_arm:
            bits.append(f"arm={self.decision_arm}")
        if self.model_vision:
            bits.append(f"vision={self.model_vision}")
        return " · ".join(bits)


def _partition_files(store: BattleTelemetryStore, run_id: str) -> tuple[str, ...]:
    """E7 — the named run's own partition files, by path only.

    Only ``battle-<run_id>-*.jsonl`` is globbed; a file of any other run is
    never listed. A name that does not parse, or parses to a different run, is
    reported (N2/N6) rather than silently dropped.
    """
    if not store.data_dir.is_dir():
        return ()
    names = sorted(
        path.name for path in store.data_dir.glob(f"battle-{run_id}-*.jsonl")
    )
    return tuple(names)


def select_run(
    store: BattleTelemetryStore,
    run_id: str,
    segment: Segment,
) -> RunSelection:
    """Apply contract §5.2 steps 1-3 to one run (no event file is opened)."""
    on_disk = _partition_files(store, run_id)
    manifest = store.read_manifest(run_id)
    if manifest is None:
        note = (
            f"manifest_missing: /game/battle/{run_id}/manifest is absent, so "
            f"§5.2 cannot select by key — none of {run_id}'s "
            f"{len(on_disk)} partition file(s) was read"
        )
        return RunSelection(
            run_id=run_id,
            manifest_present=False,
            manifest=None,
            model_decision=None,
            model_vision=None,
            provider=None,
            decision_arm=None,
            index_entries=0,
            encounters_total=0,
            index_truncated=False,
            selected=(),
            excluded=(),
            partitions_on_disk=on_disk,
            unindexed=on_disk,
            notes=(note,),
        )

    attributes = manifest.get("attributes")
    if not isinstance(attributes, Mapping):
        return RunSelection(
            run_id=run_id,
            manifest_present=True,
            manifest=manifest,
            model_decision=None,
            model_vision=None,
            provider=None,
            decision_arm=None,
            index_entries=0,
            encounters_total=0,
            index_truncated=False,
            selected=(),
            excluded=(),
            partitions_on_disk=on_disk,
            unindexed=on_disk,
            notes=(
                f"manifest_malformed: /game/battle/{run_id}/manifest carries no "
                "attributes mapping, so no partition of it was read",
            ),
        )

    raw_index = attributes.get("index")
    index: list[Mapping[str, Any]] = [
        entry for entry in (raw_index or []) if isinstance(entry, Mapping)
    ]
    model_decision = _optional_str(attributes.get("model_decision"))
    model_vision = _optional_str(attributes.get("model_vision"))
    provider = _optional_str(attributes.get("provider"))
    decision_arm = _optional_str(attributes.get("decision_arm"))
    encounters_total = attributes.get("encounters_total")
    total = int(encounters_total) if isinstance(encounters_total, int) else len(index)
    truncated = bool(attributes.get("truncated")) or total > len(index)

    selected: list[SelectedPartition] = []
    excluded: list[ExcludedPartition] = []
    indexed_files: set[str] = set()
    notes: list[str] = []

    for entry in index:
        encounter_id = str(entry.get("encounter_id") or "")
        file_name = entry.get("file")
        if not isinstance(file_name, str) or not file_name:
            excluded.append(
                ExcludedPartition(
                    run_id,
                    encounter_id,
                    "",
                    "manifest: entry carries no 'file', so it cannot be opened",
                )
            )
            continue
        indexed_files.add(file_name)
        unsafe = _unsafe_filename_reason(file_name, run_id)
        if unsafe is not None:
            excluded.append(ExcludedPartition(run_id, encounter_id, file_name, unsafe))
            continue
        reason = segment.rejection(entry)
        if reason is not None:
            excluded.append(ExcludedPartition(run_id, encounter_id, file_name, reason))
            continue
        selected.append(
            SelectedPartition(
                run_id=run_id,
                encounter_id=encounter_id,
                file=file_name,
                path=store.data_dir / file_name,
                entry=entry,
            )
        )

    unindexed = tuple(name for name in on_disk if name not in indexed_files)
    if truncated:
        notes.append(
            f"index_truncated: {run_id}'s manifest index lists {len(index)} of "
            f"{total} encounters; unindexed partitions cannot be selected by key "
            "and are not read"
        )
    if unindexed:
        notes.append(
            f"unindexed_partitions: {len(unindexed)} file(s) of {run_id} exist on "
            "disk but are absent from the manifest index and were NOT read: "
            + ", ".join(unindexed)
        )
    missing = [sel.file for sel in selected if not sel.path.is_file()]
    if missing:
        notes.append(
            f"missing_files: {run_id}'s manifest names {len(missing)} file(s) "
            "that are not on disk: " + ", ".join(sorted(missing))
        )

    return RunSelection(
        run_id=run_id,
        manifest_present=True,
        manifest=manifest,
        model_decision=model_decision,
        model_vision=model_vision,
        provider=provider,
        decision_arm=decision_arm,
        index_entries=len(index),
        encounters_total=total,
        index_truncated=truncated,
        selected=tuple(selected),
        excluded=tuple(excluded),
        partitions_on_disk=on_disk,
        unindexed=unindexed,
        notes=tuple(notes),
    )


def _unsafe_filename_reason(file_name: str, run_id: str) -> str | None:
    """A manifest-named file must be a plain, run-matching partition name."""
    if "/" in file_name or "\\" in file_name or file_name in (".", ".."):
        return f"manifest: {file_name!r} is not a bare filename (path traversal)"
    match = _FILE_SAFE.match(file_name)
    if match is None:
        return f"N2: {file_name!r} does not parse to battle-<run_id>-ep<EEE>-enc<CCC>.jsonl"
    if match.group(1) != run_id:
        return f"N6: {file_name!r} names run {match.group(1)!r}, not {run_id!r}"
    return None


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


# ── records and their provenance ────────────────────────────────────────────


@dataclass(frozen=True)
class RecordRef:
    """One stored event, identified by the exact line that carries it.

    ``file`` + ``line`` is the raw address: re-reading that line reproduces the
    record, and ``identity`` (the store's own ``record_identity`` hash) proves
    the line is the record the metric used.
    """

    run_id: str
    file: str
    line: int
    identity: str
    encounter_id: str
    turn: int
    attacker_side: str
    attacker_level: int
    outcome: str
    damage: int
    defender_hp_before: int
    defender_hp_after: int
    encounter_outcome: str

    @property
    def ref(self) -> str:
        """``file:line`` — the raw-record address printed in the report."""
        return f"{self.file}:{self.line}"

    @property
    def is_ko(self) -> bool:
        """True on the record whose blow took the defender to 0 HP."""
        return self.defender_hp_after == 0 and self.defender_hp_before > 0


@dataclass(frozen=True)
class _PartitionRead:
    """What one selected partition yielded when it was opened (E8 applied)."""

    partition: SelectedPartition
    refs: tuple[RecordRef, ...]
    records: int
    malformed: int
    rejected: int


def _as_int(value: Any) -> int | None:
    """An int (never a bool), or ``None`` — the narrowing mypy needs."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _ref_from_record(
    record: Mapping[str, Any],
    *,
    run_id: str,
    file_name: str,
    line: int,
) -> RecordRef | None:
    """Build a :class:`RecordRef`, or ``None`` when the record is unusable."""
    side = record.get("attacker_side")
    if side not in ("player", "enemy"):
        return None
    encounter_id = record.get("encounter_id")
    if not isinstance(encounter_id, str):
        return None
    turn = _as_int(record.get("turn"))
    damage = _as_int(record.get("damage"))
    before = _as_int(record.get("defender_hp_before"))
    after = _as_int(record.get("defender_hp_after"))
    level = _as_int(record.get("attacker_level"))
    if (
        turn is None
        or damage is None
        or before is None
        or after is None
        or level is None
    ):
        return None
    outcome = record.get("outcome")
    encounter_outcome = record.get("encounter_outcome")
    return RecordRef(
        run_id=run_id,
        file=file_name,
        line=line,
        identity=record_identity(record),
        encounter_id=encounter_id,
        turn=turn,
        attacker_side=str(side),
        attacker_level=level,
        outcome=str(outcome) if isinstance(outcome, str) else "unknown",
        damage=damage,
        defender_hp_before=before,
        defender_hp_after=after,
        encounter_outcome=(
            encounter_outcome if isinstance(encounter_outcome, str) else "unknown"
        ),
    )


def read_partition(partition: SelectedPartition, segment: Segment) -> _PartitionRead:
    """Open ONE selected partition and apply E8 while scanning it."""
    path = partition.path
    if not path.is_file():
        return _PartitionRead(partition, refs=(), records=0, malformed=0, rejected=0)

    refs: list[RecordRef] = []
    records = 0
    malformed = 0
    rejected = 0
    expected = partition.encounter_id
    with open(path, encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                parsed: Any = json.loads(line)
            except json.JSONDecodeError:
                malformed += 1
                continue
            if not isinstance(parsed, Mapping):
                malformed += 1
                continue
            records += 1
            record = dict(parsed)
            # N6: a record that disagrees with the filename it sits in is not
            # this partition's event; refuse it rather than count it twice.
            if record.get("run_id") != partition.run_id:
                rejected += 1
                continue
            if expected and record.get("encounter_id") != expected:
                rejected += 1
                continue
            ref = _ref_from_record(
                record,
                run_id=partition.run_id,
                file_name=partition.file,
                line=number,
            )
            if ref is None:
                rejected += 1
                continue
            # E8 — per-record refinement.
            if not segment.admits_turn(ref.turn):
                continue
            refs.append(ref)
    return _PartitionRead(
        partition,
        refs=tuple(refs),
        records=records,
        malformed=malformed,
        rejected=rejected,
    )


# ── per-encounter metrics ───────────────────────────────────────────────────


@dataclass(frozen=True)
class EncounterMetrics:
    """Every metric of ONE encounter, with the records behind it."""

    run_id: str
    encounter_id: str
    file: str
    map_name: str
    battle_type: str
    opponent_species: str
    opponent_level: int
    player_level: int | None
    player_levels: tuple[int, ...]
    turns: int
    attacks: int
    hits: int
    whiffs: int
    no_damage: int
    unknown_outcome: int
    damage_dealt: int
    damage_taken: int
    damage_per_turn: float | None
    ko_turn: int | None
    ko_hp_needed: int
    ko_hp_needed_each: tuple[int, ...]
    overkill_observed: int
    encounter_outcome: str
    overkill_ratio: float | None
    overkill_damage: int | None
    overkill_scope: str | None
    typical_hit: float | None
    record_count: int
    damage_sources: tuple[RecordRef, ...]
    damage_taken_sources: tuple[RecordRef, ...]
    malformed_lines: int = 0
    rejected_records: int = 0

    @property
    def estimated(self) -> bool:
        """True when this encounter's overkill ratio is estimated, not clamped."""
        return self.overkill_ratio is not None


def _mode_level(refs: Sequence[RecordRef]) -> tuple[int | None, tuple[int, ...]]:
    """The attacker level most of *refs* report, plus the distinct levels."""
    levels = sorted({ref.attacker_level for ref in refs})
    if not levels:
        return None, ()
    counts = Counter(ref.attacker_level for ref in refs)
    ranked = sorted(counts.items(), key=lambda item: (-item[1], -item[0]))
    return ranked[0][0], tuple(levels)


def _encounter_outcome(refs: Sequence[RecordRef]) -> str:
    """Last non-``unknown`` encounter outcome stamped on the partition."""
    for ref in reversed(refs):
        if ref.encounter_outcome not in ("unknown", ""):
            return ref.encounter_outcome
    return "unknown"


def encounter_metrics(part: _PartitionRead) -> EncounterMetrics:
    """Derive one encounter's metrics from the records read for it."""
    entry = part.partition.entry
    refs = part.refs
    player = [ref for ref in refs if ref.attacker_side == "player"]
    enemy = [ref for ref in refs if ref.attacker_side == "enemy"]

    turns = max((ref.turn for ref in player), default=0)
    if turns == 0:
        turns = max((ref.turn for ref in refs), default=0)

    damage_dealt = sum(ref.damage for ref in player)
    damage_taken = sum(ref.damage for ref in enemy)
    hits = sum(1 for ref in player if ref.outcome == "damage")
    whiffs = sum(1 for ref in player if ref.outcome == "miss")
    no_damage = sum(1 for ref in player if ref.outcome == "no_damage")
    unknown_outcome = sum(1 for ref in player if ref.outcome == "unknown")
    attacks = sum(1 for ref in player if ref.outcome != "no_damage")
    kos = [ref for ref in player if ref.is_ko]
    ko_turn = max((ref.turn for ref in kos), default=None)
    ko_hp_needed = sum(ref.defender_hp_before for ref in kos)
    level, levels = _mode_level(player)

    return EncounterMetrics(
        run_id=part.partition.run_id,
        encounter_id=part.partition.encounter_id,
        file=part.partition.file,
        map_name=str(entry.get("map", "unknown")),
        battle_type=str(entry.get("battle_type", "unknown")),
        opponent_species=str(entry.get("opponent_species", "unknown")),
        opponent_level=int(entry.get("opponent_level") or 0),
        player_level=level,
        player_levels=levels,
        turns=turns,
        attacks=attacks,
        hits=hits,
        whiffs=whiffs,
        no_damage=no_damage,
        unknown_outcome=unknown_outcome,
        damage_dealt=damage_dealt,
        damage_taken=damage_taken,
        damage_per_turn=(damage_dealt / turns) if turns else None,
        ko_turn=ko_turn,
        ko_hp_needed=ko_hp_needed,
        ko_hp_needed_each=tuple(ref.defender_hp_before for ref in kos),
        # R5: on a KO record the reported damage IS the defender's remaining
        # HP, so this is 0 unless the writer broke the clamp.
        overkill_observed=sum(ref.damage - ref.defender_hp_before for ref in kos),
        encounter_outcome=_encounter_outcome(refs),
        overkill_ratio=None,
        overkill_damage=None,
        overkill_scope=None,
        typical_hit=None,
        record_count=part.records,
        damage_sources=tuple(player),
        damage_taken_sources=tuple(enemy),
        malformed_lines=part.malformed,
        rejected_records=part.rejected,
    )


def _mean(values: Iterable[int]) -> float | None:
    items = list(values)
    if not items:
        return None
    return sum(items) / len(items)


def apply_overkill(
    encounters: Sequence[EncounterMetrics],
) -> tuple[EncounterMetrics, ...]:
    """Fill each encounter's overkill estimate from its own (or the run's) hits.

    The per-hit rate comes from the encounter's NON-KO damaging player hits; an
    encounter with none borrows the run's, and an encounter with neither stays
    ``unestimated`` (``overkill_ratio is None``) rather than being given a
    fabricated ratio. The scope used is reported on every encounter.
    """
    run_rate = _mean(
        ref.damage
        for enc in encounters
        for ref in enc.damage_sources
        if ref.outcome == "damage" and not ref.is_ko
    )

    resolved: list[EncounterMetrics] = []
    for enc in encounters:
        local = _mean(
            ref.damage
            for ref in enc.damage_sources
            if ref.outcome == "damage" and not ref.is_ko
        )
        rate = local if local is not None else run_rate
        scope = "same_encounter" if local is not None else None
        if local is None and run_rate is not None:
            scope = "same_run"
        needed = enc.ko_hp_needed_each
        if rate is None or not needed:
            resolved.append(replace(enc, typical_hit=rate, overkill_scope=scope))
            continue
        ratios = [rate / hp for hp in needed if hp > 0]
        if not ratios:
            resolved.append(replace(enc, typical_hit=rate, overkill_scope=scope))
            continue
        resolved.append(
            replace(
                enc,
                overkill_ratio=sum(ratios) / len(ratios),
                overkill_damage=int(round(sum(max(0.0, rate - hp) for hp in needed))),
                overkill_scope=scope,
                typical_hit=rate,
            )
        )
    return tuple(resolved)


# ── per-run metrics ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BattleTypeSplit:
    """Wild-vs-trainer (contract §3.2 E6) slice of a run."""

    battle_type: str
    encounters: int
    damage_dealt: int
    damage_taken: int
    turns: int
    turns_per_encounter: float | None
    overkill_ratio: float | None
    ko_events: int


@dataclass(frozen=True)
class LevelBandSplit:
    """Damage efficiency per attacker level band (the "does a higher level
    overkill more?" table)."""

    lo: int
    hi: int
    encounters: int
    damage_dealt: int
    attacks: int
    damage_per_attack: float | None
    overkill_ratio: float | None
    ko_events: int

    @property
    def label(self) -> str:
        return f"level {self.lo}-{self.hi}"


@dataclass(frozen=True)
class RunMetrics:
    """One run's metrics over the selected segment, plus its read accounting."""

    selection: RunSelection
    encounters: tuple[EncounterMetrics, ...]
    turns_total: int
    turns_per_encounter: float | None
    turns_min: int
    turns_max: int
    attacks: int
    hits: int
    whiffs: int
    hit_rate: float | None
    damage_dealt_total: int
    damage_taken_total: int
    damage_ratio: float | None
    damage_per_turn: float | None
    ko_events: int
    overkill_ratio: float | None
    overkill_damage_total: int
    overkill_estimated: int
    overkill_unestimated: int
    overkill_observed: int
    flee_count: int
    outcome_counts: Mapping[str, int]
    by_battle_type: tuple[BattleTypeSplit, ...]
    by_level_band: tuple[LevelBandSplit, ...]
    damage_sources: tuple[RecordRef, ...]
    damage_taken_sources: tuple[RecordRef, ...]
    malformed_lines: int
    rejected_records: int
    gaps: tuple[str, ...]

    @property
    def run_id(self) -> str:
        return self.selection.run_id

    @property
    def model_label(self) -> str:
        return self.selection.model_label

    @property
    def model_line(self) -> str:
        return self.selection.model_line

    @property
    def partitions_read(self) -> tuple[str, ...]:
        return tuple(part.file for part in self.selection.selected)

    @property
    def has_encounters(self) -> bool:
        return bool(self.encounters)

    def outcome_summary(self) -> str:
        """``won`` / ``won×2 + fled×1`` — the encounter outcomes, compactly."""
        if not self.outcome_counts:
            return "none"
        parts = [
            f"{name}×{count}" if count > 1 else name
            for name, count in sorted(self.outcome_counts.items())
        ]
        return " + ".join(parts)


def _band_of(level: int) -> tuple[int, int]:
    lo = ((level - 1) // BAND_WIDTH) * BAND_WIDTH + 1
    return lo, lo + BAND_WIDTH - 1


def analyse_run(
    store: BattleTelemetryStore,
    run_id: str,
    segment: Segment,
) -> RunMetrics:
    """Select, read and measure one run (§5.2 steps 1-4 for *run_id*)."""
    selection = select_run(store, run_id, segment)

    encounters: list[EncounterMetrics] = []
    malformed = 0
    rejected = 0
    for part in selection.selected:
        read = read_partition(part, segment)
        malformed += read.malformed
        rejected += read.rejected
        encounters.append(encounter_metrics(read))

    encounters = list(apply_overkill(encounters))

    turns_total = sum(enc.turns for enc in encounters)
    attacks = sum(enc.attacks for enc in encounters)
    hits = sum(enc.hits for enc in encounters)
    damage_dealt = sum(enc.damage_dealt for enc in encounters)
    damage_taken = sum(enc.damage_taken for enc in encounters)
    ko_events = sum(1 for enc in encounters if enc.ko_turn is not None)
    ratios = [
        enc.overkill_ratio for enc in encounters if enc.overkill_ratio is not None
    ]
    estimated = len(ratios)
    overkill_damage = sum(
        enc.overkill_damage or 0 for enc in encounters if enc.overkill_damage
    )
    # §3.3 R5: on a KO the reported damage IS the remaining HP, so the observed
    # "damage beyond the kill" is 0 by construction. Non-zero means a writer
    # broke the clamp, and the report says so rather than hiding it.
    overkill_observed = sum(enc.overkill_observed for enc in encounters)

    outcome_counts = Counter(enc.encounter_outcome for enc in encounters)
    damage_sources = tuple(ref for enc in encounters for ref in enc.damage_sources)
    damage_taken_sources = tuple(
        ref for enc in encounters for ref in enc.damage_taken_sources
    )

    gaps: list[str] = list(selection.notes)
    if not encounters:
        gaps.append(
            f"run {run_id}: 0 encounters survived the segment filter "
            f"({len(selection.excluded)} excluded, {len(selection.selected)} "
            "selected and read)"
        )
    if malformed:
        gaps.append(f"run {run_id}: {malformed} unparseable line(s) were skipped")
    if rejected:
        gaps.append(
            f"run {run_id}: {rejected} record(s) disagreed with their partition's "
            "run_id/encounter_id and were refused (N6)"
        )

    metrics = RunMetrics(
        selection=selection,
        encounters=tuple(encounters),
        turns_total=turns_total,
        turns_per_encounter=(turns_total / len(encounters) if encounters else None),
        turns_min=min((enc.turns for enc in encounters), default=0),
        turns_max=max((enc.turns for enc in encounters), default=0),
        attacks=attacks,
        hits=hits,
        whiffs=sum(enc.whiffs for enc in encounters),
        hit_rate=(hits / attacks) if attacks else None,
        damage_dealt_total=damage_dealt,
        damage_taken_total=damage_taken,
        damage_ratio=(damage_dealt / damage_taken) if damage_taken else None,
        damage_per_turn=(damage_dealt / turns_total) if turns_total else None,
        ko_events=ko_events,
        overkill_ratio=(sum(ratios) / estimated) if estimated else None,
        overkill_damage_total=overkill_damage,
        overkill_estimated=estimated,
        overkill_unestimated=ko_events - estimated,
        overkill_observed=overkill_observed,
        flee_count=sum(1 for enc in encounters if enc.encounter_outcome == "fled"),
        outcome_counts=dict(outcome_counts),
        by_battle_type=_battle_type_splits(encounters),
        by_level_band=_level_band_splits(encounters),
        damage_sources=damage_sources,
        damage_taken_sources=damage_taken_sources,
        malformed_lines=malformed,
        rejected_records=rejected,
        gaps=tuple(gaps),
    )
    return metrics


def _battle_type_splits(
    encounters: Sequence[EncounterMetrics],
) -> tuple[BattleTypeSplit, ...]:
    groups: dict[str, list[EncounterMetrics]] = {}
    for enc in encounters:
        groups.setdefault(enc.battle_type, []).append(enc)
    splits: list[BattleTypeSplit] = []
    for battle_type in sorted(groups):
        items = groups[battle_type]
        turns = sum(enc.turns for enc in items)
        ratios = [enc.overkill_ratio for enc in items if enc.overkill_ratio is not None]
        splits.append(
            BattleTypeSplit(
                battle_type=battle_type,
                encounters=len(items),
                damage_dealt=sum(enc.damage_dealt for enc in items),
                damage_taken=sum(enc.damage_taken for enc in items),
                turns=turns,
                turns_per_encounter=(turns / len(items)) if items else None,
                overkill_ratio=(sum(ratios) / len(ratios)) if ratios else None,
                ko_events=sum(1 for enc in items if enc.ko_turn is not None),
            )
        )
    return tuple(splits)


def _level_band_splits(
    encounters: Sequence[EncounterMetrics],
) -> tuple[LevelBandSplit, ...]:
    groups: dict[tuple[int, int], list[EncounterMetrics]] = {}
    for enc in encounters:
        if enc.player_level is None:
            continue
        groups.setdefault(_band_of(enc.player_level), []).append(enc)
    splits: list[LevelBandSplit] = []
    for (lo, hi), items in sorted(groups.items()):
        attacks = sum(enc.attacks for enc in items)
        damage = sum(enc.damage_dealt for enc in items)
        ratios = [enc.overkill_ratio for enc in items if enc.overkill_ratio is not None]
        splits.append(
            LevelBandSplit(
                lo=lo,
                hi=hi,
                encounters=len(items),
                damage_dealt=damage,
                attacks=attacks,
                damage_per_attack=(damage / attacks) if attacks else None,
                overkill_ratio=(sum(ratios) / len(ratios)) if ratios else None,
                ko_events=sum(1 for enc in items if enc.ko_turn is not None),
            )
        )
    return tuple(splits)


# ── store census (what telemetry exists at all) ─────────────────────────────


@dataclass(frozen=True)
class StoreCensus:
    """What the telemetry store holds — read from names, never from contents."""

    data_dir: str
    event_files: tuple[str, ...]
    run_ids: tuple[str, ...]
    runs_with_manifest: tuple[str, ...]
    runs_without_manifest: tuple[str, ...]

    def summary(self) -> str:
        if not self.event_files:
            return f"store holds no battle-*.jsonl partition ({self.data_dir})"
        return (
            f"store holds {len(self.event_files)} partition file(s) across "
            f"{len(self.run_ids)} run(s) ({self.data_dir}); "
            f"{len(self.runs_with_manifest)} with a manifest, "
            f"{len(self.runs_without_manifest)} without"
        )


def store_census(store: BattleTelemetryStore) -> StoreCensus:
    """Enumerate the store's battle partitions by filename (no content read)."""
    files: tuple[str, ...] = ()
    run_ids: tuple[str, ...] = ()
    if store.data_dir.is_dir():
        files = tuple(
            sorted(path.name for path in store.data_dir.glob("battle-*.jsonl"))
        )
        found: set[str] = set()
        for name in files:
            try:
                found.add(parse_partition_filename(name).run_id)
            except ValueError:
                continue
        run_ids = tuple(sorted(found))
    with_manifest: list[str] = []
    without: list[str] = []
    for run_id in run_ids:
        if store.read_manifest(run_id) is not None:
            with_manifest.append(run_id)
        else:
            without.append(run_id)
    return StoreCensus(
        data_dir=str(store.data_dir),
        event_files=files,
        run_ids=run_ids,
        runs_with_manifest=tuple(with_manifest),
        runs_without_manifest=tuple(without),
    )


# ── the comparison report ───────────────────────────────────────────────────


@dataclass(frozen=True)
class MetricRow:
    """One line of the side-by-side table."""

    metric: str
    a: str
    b: str
    note: str = ""
    derivable: bool = True


@dataclass(frozen=True)
class DamageSpotCheck:
    """One damage figure re-read from the raw record it was summed from."""

    metric: str
    run_id: str
    model_label: str
    ref: RecordRef
    raw: Mapping[str, Any]
    matches: bool

    @property
    def summary(self) -> str:
        verdict = "MATCH" if self.matches else "MISMATCH"
        return (
            f"{self.metric} ← {self.ref.ref} "
            f"(identity {self.ref.identity[:12]}…, damage={self.ref.damage}, "
            f"turn={self.ref.turn}, side={self.ref.attacker_side}) → raw record "
            f"{verdict}"
        )


@dataclass(frozen=True)
class ComparisonReport:
    """Two runs, one segment: the table, the read accounting and the gaps."""

    segment: Segment
    run_a: RunMetrics
    run_b: RunMetrics
    store_root: str
    namespace: str
    data_dir: str
    census: StoreCensus
    data_note: str = DEFAULT_DATA_NOTE
    extra_gaps: tuple[str, ...] = ()

    # ── comparability ──

    @property
    def comparable(self) -> bool:
        return self.run_a.has_encounters and self.run_b.has_encounters

    @property
    def partitions_read(self) -> tuple[str, ...]:
        return self.run_a.partitions_read + self.run_b.partitions_read

    @property
    def partitions_excluded(self) -> tuple[ExcludedPartition, ...]:
        return self.run_a.selection.excluded + self.run_b.selection.excluded

    @property
    def gaps(self) -> tuple[str, ...]:
        collected: list[str] = []
        if not self.census.event_files:
            collected.append(DATA_GAP_NO_BATTLE_PARTITIONS)
        if not self.comparable:
            collected.append(DATA_GAP_REAL_PAIRED_RUNS)
        collected.extend(self.extra_gaps)
        collected.extend(self.run_a.gaps)
        collected.extend(self.run_b.gaps)
        return tuple(dict.fromkeys(collected))

    # ── the table ──

    def rows(self) -> list[MetricRow]:
        """The side-by-side metric rows, in the contract §6 order then extras."""
        a, b = self.run_a, self.run_b
        rows: list[MetricRow] = [
            MetricRow(
                "partitions_read",
                str(len(a.partitions_read)),
                str(len(b.partitions_read)),
            ),
            MetricRow("encounters", str(len(a.encounters)), str(len(b.encounters))),
            MetricRow("turns_total", str(a.turns_total), str(b.turns_total)),
            MetricRow(
                "turns_per_encounter",
                _num(a.turns_per_encounter, 2),
                _num(b.turns_per_encounter, 2),
            ),
            MetricRow(
                "turns_to_ko",
                str(sum(enc.ko_turn or 0 for enc in a.encounters)),
                str(sum(enc.ko_turn or 0 for enc in b.encounters)),
                "sum of the max turn at KO (contract §6)",
            ),
            MetricRow(
                "attacks_to_ko",
                str(a.attacks),
                str(b.attacks),
                "player records with outcome != no_damage (contract §6)",
            ),
            MetricRow(
                "hits/attacks",
                _ratio(a.hits, a.attacks),
                _ratio(b.hits, b.attacks),
                "contract §6 shape",
            ),
            MetricRow(
                "whiff_count",
                str(a.whiffs),
                str(b.whiffs),
                "player records with outcome == miss",
            ),
            MetricRow(
                "damage_dealt_total",
                str(a.damage_dealt_total),
                str(b.damage_dealt_total),
                f"{len(a.damage_sources)} / {len(b.damage_sources)} records summed",
            ),
            MetricRow(
                "damage_taken_total",
                str(a.damage_taken_total),
                str(b.damage_taken_total),
                f"{len(a.damage_taken_sources)} / "
                f"{len(b.damage_taken_sources)} enemy records summed",
            ),
            MetricRow(
                "damage_ratio (dealt/taken)",
                _num(a.damage_ratio, 2),
                _num(b.damage_ratio, 2),
                "n/a when the run took no damage",
            ),
            MetricRow(
                "damage_per_turn",
                _num(a.damage_per_turn, 2),
                _num(b.damage_per_turn, 2),
                "damage_dealt_total / turns_total",
            ),
            MetricRow("ko_events", str(a.ko_events), str(b.ko_events)),
            MetricRow(
                "overkill_ratio (est.)",
                _num(a.overkill_ratio, 2),
                _num(b.overkill_ratio, 2),
                "typical non-KO hit / HP the kill needed; >1 = blow bigger than needed",
            ),
            MetricRow(
                "overkill_damage (est.)",
                str(a.overkill_damage_total),
                str(b.overkill_damage_total),
                "estimated damage beyond the kill, summed",
            ),
            MetricRow(
                "overkill_estimated / unestimated",
                f"{a.overkill_estimated}/{a.overkill_unestimated}",
                f"{b.overkill_estimated}/{b.overkill_unestimated}",
                "KO events with / without a measurable per-hit rate",
            ),
            MetricRow(
                "overkill_observed",
                str(a.overkill_observed),
                str(b.overkill_observed),
                "0 by contract §3.3 R5 (HP clamps at 0, so a KO cannot report "
                "overkill); non-zero = writer defect",
            ),
            MetricRow("flee_count", str(a.flee_count), str(b.flee_count)),
            MetricRow(
                "encounter_outcome",
                a.outcome_summary(),
                b.outcome_summary(),
            ),
            MetricRow(
                "wild encounters / damage_dealt",
                _battle_type_cell(a, "wild"),
                _battle_type_cell(b, "wild"),
                "battle_type == wild",
            ),
            MetricRow(
                "trainer encounters / damage_dealt",
                _battle_type_cell(a, "trainer"),
                _battle_type_cell(b, "trainer"),
                "battle_type == trainer",
            ),
            MetricRow(
                "items_used",
                "n/a",
                "n/a",
                NOT_DERIVABLE["items_used"],
                derivable=False,
            ),
            MetricRow(
                "switches",
                "n/a",
                "n/a",
                NOT_DERIVABLE["switches"],
                derivable=False,
            ),
        ]
        rows.extend(self._level_rows())
        return rows

    def _level_rows(self) -> list[MetricRow]:
        bands: dict[tuple[int, int], None] = {}
        for run in (self.run_a, self.run_b):
            for split in run.by_level_band:
                bands[(split.lo, split.hi)] = None
        rows: list[MetricRow] = []
        for lo, hi in sorted(bands):
            rows.append(
                MetricRow(
                    f"damage_per_attack @ level {lo}-{hi}",
                    _band_cell(self.run_a, lo, hi, "damage_per_attack"),
                    _band_cell(self.run_b, lo, hi, "damage_per_attack"),
                    "damage dealt / player attacks in the band",
                )
            )
            rows.append(
                MetricRow(
                    f"overkill_ratio @ level {lo}-{hi}",
                    _band_cell(self.run_a, lo, hi, "overkill_ratio"),
                    _band_cell(self.run_b, lo, hi, "overkill_ratio"),
                    "the 'does a higher level overkill more?' comparison",
                )
            )
        return rows

    def render_table(self) -> str:
        """The side-by-side table with both models named in the header."""
        a_name = self.run_a.model_label
        b_name = self.run_b.model_label
        rows = self.rows()
        width_metric = max([len("metric"), *(len(row.metric) for row in rows)])
        width_a = max([len(a_name), *(len(row.a) for row in rows)])
        width_b = max([len(b_name), *(len(row.b) for row in rows)])
        header = f"{'metric':<{width_metric}}  {a_name:<{width_a}}  {b_name:<{width_b}}"
        lines = [header, "-" * len(header)]
        for row in rows:
            line = (
                f"{row.metric:<{width_metric}}  {row.a:<{width_a}}  {row.b:<{width_b}}"
            )
            if row.note:
                line = f"{line}  # {row.note}"
            lines.append(line)
        return "\n".join(lines)

    def render(self) -> str:
        """The full report: header, table, partitions, provenance, gaps."""
        lines: list[str] = []
        lines.append(
            "COMPARISON: "
            f"{self.run_a.run_id} ({self.run_a.model_line})  vs  "
            f"{self.run_b.run_id} ({self.run_b.model_line})"
        )
        lines.append(f"segment: {self.segment.describe()}")
        lines.append(JOIN_RULE)
        lines.append("")
        lines.append(self.render_table())
        lines.append("")
        lines.extend(self._render_partitions())
        lines.append("")
        lines.extend(self._render_provenance())
        lines.append("")
        lines.extend(self._render_gaps())
        return "\n".join(lines)

    def _render_partitions(self) -> list[str]:
        read = self.partitions_read
        excluded = self.partitions_excluded
        lines = [f"PARTITIONS READ ({len(read)}):"]
        if not read:
            lines.append("  (none)")
        for run, name in (
            (self.run_a, self.run_a.partitions_read),
            (self.run_b, self.run_b.partitions_read),
        ):
            for file_name in name:
                lines.append(f"  {file_name}  [{run.run_id} — {run.model_label}]")
        lines.append(f"PARTITIONS EXCLUDED ({len(excluded)}):")
        if not excluded:
            lines.append("  (none)")
        for item in excluded:
            label = item.file or f"(entry {item.encounter_id or '?'})"
            lines.append(f"  {label}  [E/why: {item.reason}]")
        return lines

    def _render_provenance(self) -> list[str]:
        lines = [
            "DATA PROVENANCE:",
            f"  store root: {self.store_root}",
            f"  namespace:  {self.namespace}",
            f"  data dir:   {self.data_dir}",
            f"  census:     {self.census.summary()}",
            f"  label:      {self.data_note}",
            "  every number above is computed at read time from the records named "
            "in the notes column; no aggregate file is written (contract N8)",
        ]
        return lines

    def _render_gaps(self) -> list[str]:
        gaps = self.gaps
        lines = [f"DATA GAPS / NOT DERIVABLE ({len(gaps)}):"]
        if not gaps:
            lines.append("  (none)")
        for gap in gaps:
            lines.append(f"  - {gap}")
        return lines

    # ── provenance of one figure (acceptance: spot-check a damage figure) ──

    def spot_check_damage(self, run: str = "a", index: int = 0) -> DamageSpotCheck:
        """Re-read the raw record behind the ``index``-th damage contribution.

        The figure checked is ``damage_dealt_total``: the sources are exactly
        the records summed for it, so re-reading one of them from
        ``<data dir>/<file>`` at the recorded line proves the number.
        """
        metrics = self._run(run)
        sources = metrics.damage_sources
        if not sources:
            raise ComparisonError(
                f"run {run!r} ({metrics.run_id}) has no player damage record to "
                "spot-check"
            )
        if index < 0 or index >= len(sources):
            raise ComparisonError(
                f"index {index} outside 0..{len(sources) - 1} for run {run!r}"
            )
        ref = sources[index]
        path = Path(self.data_dir) / ref.file
        raw: Mapping[str, Any] = {}
        with open(path, encoding="utf-8") as handle:
            for number, line in enumerate(handle, 1):
                if number != ref.line:
                    continue
                parsed: Any = json.loads(line)
                if isinstance(parsed, Mapping):
                    raw = dict(parsed)
                break
        matches = bool(raw) and (
            raw.get("damage") == ref.damage and record_identity(raw) == ref.identity
        )
        return DamageSpotCheck(
            metric="damage_dealt_total",
            run_id=metrics.run_id,
            model_label=metrics.model_label,
            ref=ref,
            raw=raw,
            matches=matches,
        )

    def _run(self, key: str) -> RunMetrics:
        if key in ("a", "run_a", self.run_a.run_id):
            return self.run_a
        if key in ("b", "run_b", self.run_b.run_id):
            return self.run_b
        raise ComparisonError(f"unknown run key {key!r}; use 'a', 'b' or a run id")

    # ── machine-readable form ──

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready report (same numbers, same provenance, same gaps)."""
        return {
            "segment": {
                "map": self.segment.map_name,
                "opponent_species": self.segment.opponent_species,
                "level_lo": self.segment.level_lo,
                "level_hi": self.segment.level_hi,
                "battle_type": self.segment.battle_type,
                "turn_lo": self.segment.turn_lo,
                "turn_hi": self.segment.turn_hi,
                "encounter_ids": list(self.segment.encounter_ids),
                "description": self.segment.describe(),
            },
            "join_rule": JOIN_RULE,
            "comparable": self.comparable,
            "runs": {
                "a": _run_dict(self.run_a),
                "b": _run_dict(self.run_b),
            },
            "table": [
                {
                    "metric": row.metric,
                    "a": row.a,
                    "b": row.b,
                    "note": row.note,
                    "derivable": row.derivable,
                }
                for row in self.rows()
            ],
            "partitions_read": list(self.partitions_read),
            "partitions_excluded": [
                {
                    "run_id": item.run_id,
                    "encounter_id": item.encounter_id,
                    "file": item.file,
                    "reason": item.reason,
                }
                for item in self.partitions_excluded
            ],
            "provenance": {
                "store_root": self.store_root,
                "namespace": self.namespace,
                "data_dir": self.data_dir,
                "census": self.census.summary(),
                "label": self.data_note,
            },
            "gaps": list(self.gaps),
        }


def _run_dict(run: RunMetrics) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "model_decision": run.selection.model_decision,
        "model_vision": run.selection.model_vision,
        "provider": run.selection.provider,
        "decision_arm": run.selection.decision_arm,
        "model_label": run.model_label,
        "manifest_present": run.selection.manifest_present,
        "index_entries": run.selection.index_entries,
        "encounters_total": run.selection.encounters_total,
        "index_truncated": run.selection.index_truncated,
        "partitions_read": list(run.partitions_read),
        "partitions_excluded": [
            {
                "encounter_id": item.encounter_id,
                "file": item.file,
                "reason": item.reason,
            }
            for item in run.selection.excluded
        ],
        "encounters": [
            {
                "encounter_id": enc.encounter_id,
                "file": enc.file,
                "map": enc.map_name,
                "battle_type": enc.battle_type,
                "opponent_species": enc.opponent_species,
                "opponent_level": enc.opponent_level,
                "player_level": enc.player_level,
                "turns": enc.turns,
                "attacks": enc.attacks,
                "hits": enc.hits,
                "whiffs": enc.whiffs,
                "damage_dealt": enc.damage_dealt,
                "damage_taken": enc.damage_taken,
                "ko_turn": enc.ko_turn,
                "ko_hp_needed": enc.ko_hp_needed,
                "overkill_observed": enc.overkill_observed,
                "overkill_ratio": enc.overkill_ratio,
                "overkill_damage": enc.overkill_damage,
                "overkill_scope": enc.overkill_scope,
                "typical_hit": enc.typical_hit,
                "encounter_outcome": enc.encounter_outcome,
                "damage_source_refs": [ref.ref for ref in enc.damage_sources],
            }
            for enc in run.encounters
        ],
        "totals": {
            "turns_total": run.turns_total,
            "turns_per_encounter": run.turns_per_encounter,
            "attacks": run.attacks,
            "hits": run.hits,
            "whiffs": run.whiffs,
            "hit_rate": run.hit_rate,
            "damage_dealt_total": run.damage_dealt_total,
            "damage_taken_total": run.damage_taken_total,
            "damage_ratio": run.damage_ratio,
            "damage_per_turn": run.damage_per_turn,
            "ko_events": run.ko_events,
            "overkill_ratio": run.overkill_ratio,
            "overkill_damage_total": run.overkill_damage_total,
            "overkill_estimated": run.overkill_estimated,
            "overkill_unestimated": run.overkill_unestimated,
            "overkill_observed": run.overkill_observed,
            "flee_count": run.flee_count,
            "outcome_counts": dict(run.outcome_counts),
        },
        "by_battle_type": [
            {
                "battle_type": split.battle_type,
                "encounters": split.encounters,
                "damage_dealt": split.damage_dealt,
                "damage_taken": split.damage_taken,
                "turns": split.turns,
                "turns_per_encounter": split.turns_per_encounter,
                "overkill_ratio": split.overkill_ratio,
                "ko_events": split.ko_events,
            }
            for split in run.by_battle_type
        ],
        "by_level_band": [
            {
                "band": split.label,
                "encounters": split.encounters,
                "damage_dealt": split.damage_dealt,
                "attacks": split.attacks,
                "damage_per_attack": split.damage_per_attack,
                "overkill_ratio": split.overkill_ratio,
                "ko_events": split.ko_events,
            }
            for split in run.by_level_band
        ],
        "damage_source_count": len(run.damage_sources),
        "gaps": list(run.gaps),
        "not_derivable": dict(NOT_DERIVABLE),
    }


# ── formatting helpers ──────────────────────────────────────────────────────


def _num(value: float | None, digits: int) -> str:
    """Fixed-point number, or ``n/a`` when the metric is undefined."""
    if value is None:
        return "n/a"
    return f"{value:.{digits}f}"


def _ratio(numerator: int, denominator: int) -> str:
    if not denominator:
        return f"{numerator} / {denominator} = n/a"
    return f"{numerator} / {denominator} = {numerator / denominator:.3f}"


def _battle_type_cell(run: RunMetrics, battle_type: str) -> str:
    for split in run.by_battle_type:
        if split.battle_type == battle_type:
            return f"{split.encounters} / {split.damage_dealt}"
    return "0 / 0"


def _band_cell(run: RunMetrics, lo: int, hi: int, field_name: str) -> str:
    for split in run.by_level_band:
        if split.lo == lo and split.hi == hi:
            if field_name == "overkill_ratio":
                return _num(split.overkill_ratio, 2)
            return _num(split.damage_per_attack, 2)
    return "n/a"


# ── entry point ─────────────────────────────────────────────────────────────


def compare_runs(
    run_a: str,
    run_b: str,
    segment: Segment | None = None,
    *,
    store: BattleTelemetryStore | None = None,
    root: Path | str | None = None,
    namespace: str = DEFAULT_NAMESPACE,
    data_note: str = DEFAULT_DATA_NOTE,
    extra_gaps: Sequence[str] = (),
) -> ComparisonReport:
    """Compare two runs on one segment and return the rendered-report object.

    ``run_a`` and ``run_b`` must be different runs: the whole purpose of the
    keys is comparing two models, and a run compared with itself would produce
    a table of identical numbers that says nothing.
    """
    if run_a == run_b:
        raise ComparisonError(
            f"run_a and run_b are both {run_a!r}; a run cannot be compared with itself"
        )
    active = (
        store
        if store is not None
        else BattleTelemetryStore(namespace=namespace, root=root)
    )
    segment = segment if segment is not None else Segment()
    census = store_census(active)
    run_metrics_a = analyse_run(active, run_a, segment)
    run_metrics_b = analyse_run(active, run_b, segment)
    return ComparisonReport(
        segment=segment,
        run_a=run_metrics_a,
        run_b=run_metrics_b,
        store_root=str(active.root),
        namespace=active.namespace,
        data_dir=str(active.data_dir),
        census=census,
        data_note=data_note,
        extra_gaps=tuple(extra_gaps),
    )
