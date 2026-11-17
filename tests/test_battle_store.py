"""Tests for the partitioned battle-telemetry store (row BTL-STORE-1).

Contract: ``specs/contracts/battle-telemetry.md``.

Covers, in contract order:

- §4.1 partition naming and the parse round-trip.
- §4.2 both caps: the 512-record cap and the 262144-byte cap, each splitting an
  over-long encounter into the next ``enc<CCC>`` partition with
  ``continued_from`` set, and neither cap ever exceeded on disk.
- §3.3 R2 (drop + count), R3 (turn regression), R4 (damage arithmetic),
  R5 (KO damage = remaining HP), R6 (resolved flags recomputed).
- §4.3 idempotence: a re-write adds no lines and no second index entry.
- §5 E1..E6: every exclusion key is present on every manifest entry.
- §7 N1/N8/N9: path, aggregate-name and memory-file refusals.
- §7.1/N6: the continuation records carry the encounter_id their filename says.

Nothing here touches a real ``~/duckbrain``: the store root is a tmp path and the
client module's root is monkeypatched, so the manifest read-back really does run
through ``duckbrain_client.get()`` / ``recall()``.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core import battle_telemetry_store as store_mod  # noqa: E402
from src.core import duckbrain_client  # noqa: E402
from src.core.battle_telemetry_store import (  # noqa: E402
    EVENT_KEYS,
    IDENTITY_KEYS,
    MAX_BYTES_PER_FILE,
    MAX_MANIFEST_ENCOUNTERS,
    MAX_RECORDS_PER_FILE,
    AggregateFileError,
    BattleTelemetryStore,
    MemoryFileWriteError,
    PartitionRef,
    RecordValidationError,
    StorePathError,
    TurnOrderError,
    manifest_key,
    parse_partition_filename,
    partition_filename,
)

RUN_ID = "20261117_090000"
NAMESPACE = "pokemon-battle"

#: Exclusion keys a manifest entry must carry (§5.1 E1..E6).
EXCLUSION_KEYS = (
    "map",
    "map_resolved",
    "opponent_species",
    "opponent_species_resolved",
    "opponent_level",
    "encounter_id",
    "turns",
    "battle_type",
    "file",
)


# ── fixtures and record builders ────────────────────────────────────────────


@pytest.fixture()
def namespaces_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A tmp namespaces root, also installed on the client module."""
    path = tmp_path / "namespaces"
    monkeypatch.setattr(duckbrain_client, "DUCKBRAIN_ROOT", path)
    return path


@pytest.fixture()
def store(namespaces_root: Path) -> BattleTelemetryStore:
    return BattleTelemetryStore(root=namespaces_root)


@pytest.fixture()
def data_dir(namespaces_root: Path) -> Path:
    return namespaces_root / NAMESPACE / "data"


def make_record(**overrides: Any) -> dict[str, Any]:
    """One minimal, contract-valid record (every §3.1/§3.2 key present)."""
    record: dict[str, Any] = {
        "run_id": "r",
        "episode": 1,
        "encounter_id": "ep001-enc001",
        "turn": 1,
        "map": "R",
        "map_resolved": True,
        "ts": "t",
        "model_decision": None,
        "model_vision": None,
        "provider": None,
        "decision_arm": "a",
        "attacker_side": "player",
        "attacker_species": "A",
        "attacker_species_resolved": True,
        "attacker_level": 2,
        "defender_species": "B",
        "defender_species_resolved": True,
        "defender_level": 2,
        "battle_type": "wild",
        "move": "T",
        "move_resolved": True,
        "outcome": "damage",
        "damage": 1,
        "damage_pct_of_max": None,
        "defender_hp_before": 2,
        "defender_hp_after": 1,
        "defender_max_hp": 2,
        "encounter_outcome": "unknown",
    }
    record.update(overrides)
    return record


def encounter_records(
    count: int,
    *,
    episode: int = 1,
    ordinal: int = 1,
    payload: int = 0,
    **overrides: Any,
) -> list[dict[str, Any]]:
    """*count* distinct records of one encounter with non-decreasing turns.

    Every record differs from its neighbours in the observed HP pair, so no two
    records share a record identity (identical records are the SAME record and
    are de-duplicated by the store, by design).
    """
    encounter_id = f"ep{episode:03d}-enc{ordinal:03d}"
    records: list[dict[str, Any]] = []
    for index in range(count):
        before = 1000 - index
        values: dict[str, Any] = {
            "episode": episode,
            "encounter_id": encounter_id,
            "turn": index // 2 + 1,
            "defender_hp_before": before,
            "defender_hp_after": before - 1,
            "damage": 1,
            "defender_max_hp": 1000,
        }
        if payload:
            values["move"] = "T" * payload
        values.update(overrides)
        records.append(make_record(**values))
    return records


def line_bytes(record: dict[str, Any]) -> int:
    return len((json.dumps(record, sort_keys=True) + "\n").encode("utf-8"))


def read_lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# ── §4.1 naming ─────────────────────────────────────────────────────────────


def test_contract_caps_and_key_vectors() -> None:
    """The constants under test are the contract's, not convenient stand-ins."""
    assert MAX_RECORDS_PER_FILE == 512
    assert MAX_BYTES_PER_FILE == 262144
    assert MAX_MANIFEST_ENCOUNTERS == 1000
    assert len(IDENTITY_KEYS) == 11
    assert len(EVENT_KEYS) == 17


def test_partition_filename_round_trip(data_dir: Path) -> None:
    ref = PartitionRef(RUN_ID, 4, 2)
    assert ref.encounter_id == "ep004-enc002"
    assert ref.filename == f"battle-{RUN_ID}-ep004-enc002.jsonl"
    assert partition_filename(ref) == ref.filename
    assert parse_partition_filename(ref.filename) == ref


@pytest.mark.parametrize(
    "name",
    [
        "battle-20261117_090000-ep4-enc2.jsonl",
        "battle-20261117-090000-ep004-enc002.jsonl",
        "battle-20261117_090000-ep004-enc002.json",
        "ep004-enc002.jsonl",
    ],
)
def test_partition_parse_rejects_non_conforming_names(name: str) -> None:
    with pytest.raises(ValueError):
        parse_partition_filename(name)


def test_partition_ref_rejects_impossible_values() -> None:
    with pytest.raises(ValueError):
        PartitionRef("2026-11-17 09:00", 1, 1)
    with pytest.raises(ValueError):
        PartitionRef(RUN_ID, 1, 1000)


def test_run_id_containing_an_aggregate_token_is_still_a_partition() -> None:
    """N8 must not fire on a legitimate run_id like ``smallrun``."""
    ref = PartitionRef("smallrun", 1, 1)
    assert parse_partition_filename(ref.filename) == ref


# ── §4.1/§4.3 first write ───────────────────────────────────────────────────


def test_first_write_lands_one_line_per_record(
    store: BattleTelemetryStore, data_dir: Path
) -> None:
    records = encounter_records(4)
    result = store.append_encounter(records, run_id="r", episode=1, encounter_ordinal=1)

    path = data_dir / "battle-r-ep001-enc001.jsonl"
    assert path.is_file()
    lines = read_lines(path)
    assert len(lines) == 4
    assert result.written == 4 and result.skipped == 0 and result.dropped == 0
    assert result.files == ("battle-r-ep001-enc001.jsonl",)
    assert lines[0]["turn"] == 1 and lines[-1]["turn"] == 2
    assert store.index[0]["records"] == 4


# ── §4.2 caps ───────────────────────────────────────────────────────────────


def test_record_cap_splits_at_512_with_continued_from(
    store: BattleTelemetryStore,
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The 512-record cap closes the encounter and continues in ``enc002``.

    The byte cap is lifted for this test ONLY: a contract-conforming record is
    ~615 B, so at the real 262144-byte cap the byte limit always binds first
    (~426 records). Lifting it is how the RECORD-cap branch is exercised at all
    — ``test_contract_caps_and_key_vectors`` pins the real constants, and
    ``test_byte_cap_binds_before_the_record_cap`` proves the real pairing.
    """
    monkeypatch.setattr(store_mod, "MAX_BYTES_PER_FILE", 10_000_000)
    records = encounter_records(530)

    result = store.append_encounter(records, run_id="r", episode=1, encounter_ordinal=1)

    first = data_dir / "battle-r-ep001-enc001.jsonl"
    second = data_dir / "battle-r-ep001-enc002.jsonl"
    assert first.is_file() and second.is_file()
    assert len(read_lines(first)) == MAX_RECORDS_PER_FILE == 512
    assert len(read_lines(second)) == 530 - 512
    assert result.encounter_ids == ("ep001-enc001", "ep001-enc002")
    assert result.written == 530

    entries = {entry["encounter_id"]: entry for entry in store.index}
    assert entries["ep001-enc001"]["truncated"] is True
    assert entries["ep001-enc001"]["continued_from"] is None
    assert entries["ep001-enc002"]["continued_from"] == "ep001-enc001"
    assert entries["ep001-enc002"]["records"] == 18


def test_byte_cap_binds_before_the_record_cap(
    store: BattleTelemetryStore, data_dir: Path
) -> None:
    """With real constants the 262144-byte cap is the binding one (§4.2)."""
    sample = make_record()
    assert line_bytes(sample) * MAX_RECORDS_PER_FILE > MAX_BYTES_PER_FILE, (
        "premise: 512 contract-shaped records do not fit under the byte cap"
    )

    records = encounter_records(500)
    store.append_encounter(records, run_id="r", episode=1, encounter_ordinal=1)

    files = sorted(data_dir.glob("battle-*.jsonl"))
    assert len(files) == 2, [path.name for path in files]
    counts = [len(read_lines(path)) for path in files]
    for path in files:
        size = path.stat().st_size
        assert size <= MAX_BYTES_PER_FILE, (path.name, size)
        assert len(read_lines(path)) <= MAX_RECORDS_PER_FILE
    assert counts[0] < MAX_RECORDS_PER_FILE, "the byte cap must bind first"
    assert sum(counts) == 500

    entries = {entry["encounter_id"]: entry for entry in store.index}
    assert entries["ep001-enc001"]["truncated"] is True
    assert entries["ep001-enc002"]["continued_from"] == "ep001-enc001"


def test_continuation_records_carry_their_partition_encounter_id(
    store: BattleTelemetryStore, data_dir: Path
) -> None:
    """N6: a record in ``enc002`` must name ``enc002``, not the source ordinal."""
    store.append_encounter(
        encounter_records(500), run_id="r", episode=1, encounter_ordinal=1
    )
    for path in sorted(data_dir.glob("battle-*.jsonl")):
        expected = parse_partition_filename(path.name).encounter_id
        for record in read_lines(path):
            assert record["encounter_id"] == expected


# ── §4.3 idempotence ────────────────────────────────────────────────────────


def test_idempotent_rewrite_adds_no_lines_and_no_second_index_entry(
    store: BattleTelemetryStore, data_dir: Path
) -> None:
    records = encounter_records(6)
    first = store.append_encounter(records, run_id="r", episode=1, encounter_ordinal=1)
    path = data_dir / "battle-r-ep001-enc001.jsonl"
    before = path.read_text()
    index_before = len(store.index)
    written_manifest = store.write_manifest(run_id="r")
    assert written_manifest.written is True
    manifest = store.read_manifest("r")
    assert manifest is not None
    assert len(manifest["attributes"]["index"]) == 1

    second = store.append_encounter(records, run_id="r", episode=1, encounter_ordinal=1)
    again = store.write_manifest(run_id="r")

    assert first.written == 6
    assert second.written == 0 and second.skipped == 6
    assert again.written is False
    assert path.read_text() == before
    assert len(read_lines(path)) == 6
    assert len(store.index) == index_before == 1
    manifest_after = store.read_manifest("r")
    assert manifest_after is not None
    assert len(manifest_after["attributes"]["index"]) == 1
    # Exactly one manifest line: the client is append-only and get() takes the
    # first record for a key, so a second line would shadow the real manifest.
    memory_lines = [
        line
        for memory in sorted(data_dir.glob("memories-*.jsonl"))
        for line in memory.read_text().splitlines()
        if line.strip()
    ]
    assert len(memory_lines) == 1


def test_append_is_append_only(store: BattleTelemetryStore, data_dir: Path) -> None:
    """A second call with NEW records appends; the earlier lines stay byte-equal."""
    store.append_encounter(
        encounter_records(2), run_id="r", episode=1, encounter_ordinal=1
    )
    path = data_dir / "battle-r-ep001-enc001.jsonl"
    prefix = path.read_text()

    more = encounter_records(4)[2:]
    store.append_encounter(more, run_id="r", episode=1, encounter_ordinal=1)

    assert path.read_text().startswith(prefix)
    assert len(read_lines(path)) == 4


# ── §3.3 R2..R6 ─────────────────────────────────────────────────────────────


def test_r2_out_of_range_record_is_dropped_and_counted(
    store: BattleTelemetryStore, data_dir: Path
) -> None:
    records = [
        make_record(turn=1),
        make_record(turn=2, attacker_level=1),  # below the §3.2 range
        make_record(turn=3),
    ]
    result = store.append_encounter(records, run_id="r", episode=1, encounter_ordinal=1)

    path = data_dir / "battle-r-ep001-enc001.jsonl"
    assert len(read_lines(path)) == 2
    assert result.dropped == 1
    assert store.dropped_records == 1
    store.write_manifest(run_id="r")
    manifest = store.read_manifest("r")
    assert manifest is not None
    assert manifest["attributes"]["dropped_records"] == 1

    # A re-write must not inflate the loss count for the same record.
    store.append_encounter(records, run_id="r", episode=1, encounter_ordinal=1)
    assert store.dropped_records == 1
    assert len(read_lines(path)) == 2


def test_r2_drops_rather_than_writing_a_null(
    store: BattleTelemetryStore, data_dir: Path
) -> None:
    records = [make_record(turn=1, defender_hp_after=None)]
    result = store.append_encounter(records, run_id="r", episode=1, encounter_ordinal=1)
    assert result.dropped == 1
    assert not (data_dir / "battle-r-ep001-enc001.jsonl").exists()


def test_r3_turn_regression_raises_and_writes_nothing(
    store: BattleTelemetryStore, data_dir: Path
) -> None:
    records = [
        make_record(turn=1, defender_hp_before=10, defender_hp_after=9),
        make_record(turn=2, defender_hp_before=9, defender_hp_after=8),
        make_record(turn=1, defender_hp_before=8, defender_hp_after=7),
    ]
    with pytest.raises(TurnOrderError, match="R3"):
        store.append_encounter(records, run_id="r", episode=1, encounter_ordinal=1)
    assert not (data_dir / "battle-r-ep001-enc001.jsonl").exists()


def test_turn_order_survives_a_resumed_partition(
    store: BattleTelemetryStore, data_dir: Path
) -> None:
    """R3 is enforced against the records already on disk, not just this call."""
    store.append_encounter(
        encounter_records(4), run_id="r", episode=1, encounter_ordinal=1
    )
    later = [
        make_record(turn=1, defender_hp_before=500, defender_hp_after=499),
    ]
    with pytest.raises(TurnOrderError, match="R3"):
        store.append_encounter(later, run_id="r", episode=1, encounter_ordinal=1)
    assert len(read_lines(data_dir / "battle-r-ep001-enc001.jsonl")) == 4


def test_r4_damage_arithmetic_is_enforced(
    store: BattleTelemetryStore, data_dir: Path
) -> None:
    record = make_record(
        defender_hp_before=15, defender_hp_after=11, damage=5, defender_max_hp=15
    )
    with pytest.raises(RecordValidationError, match="R4"):
        store.append_encounter([record], run_id="r", episode=1, encounter_ordinal=1)
    assert store.dropped_records == 1
    assert not (data_dir / "battle-r-ep001-enc001.jsonl").exists()


def test_r4_zero_damage_outcomes_must_carry_zero(
    store: BattleTelemetryStore,
) -> None:
    record = make_record(
        outcome="miss",
        damage=3,
        defender_hp_before=15,
        defender_hp_after=12,
        defender_max_hp=15,
    )
    with pytest.raises(RecordValidationError, match="R4"):
        store.append_encounter([record], run_id="r", episode=1, encounter_ordinal=1)


def test_r5_ko_damage_is_the_remaining_hp(store: BattleTelemetryStore) -> None:
    """A formula-derived KO number is refused: the delta IS the remaining HP."""
    record = make_record(
        defender_hp_before=2,
        defender_hp_after=0,
        damage=9,  # a damage-formula number, not the observed delta
        defender_max_hp=15,
        encounter_outcome="won",
    )
    with pytest.raises(RecordValidationError, match="R5"):
        store.append_encounter([record], run_id="r", episode=1, encounter_ordinal=1)


def test_r5_overkill_is_refused(store: BattleTelemetryStore) -> None:
    """HP clamps at 0, so damage above the defender's max HP cannot be observed."""
    record = make_record(
        defender_hp_before=15, defender_hp_after=0, damage=15, defender_max_hp=10
    )
    with pytest.raises(RecordValidationError, match="R5"):
        store.append_encounter([record], run_id="r", episode=1, encounter_ordinal=1)


def test_r6_resolved_flags_are_recomputed(store: BattleTelemetryStore) -> None:
    record = make_record(map_resolved=False)  # "R" is not the Map_XX placeholder
    with pytest.raises(RecordValidationError, match="R6"):
        store.append_encounter([record], run_id="r", episode=1, encounter_ordinal=1)

    species = make_record(attacker_species="#12", attacker_species_resolved=True)
    with pytest.raises(RecordValidationError, match="R6"):
        store.append_encounter([species], run_id="r", episode=1, encounter_ordinal=1)


def test_r1_missing_key_is_refused(store: BattleTelemetryStore) -> None:
    record = make_record()
    del record["decision_arm"]
    with pytest.raises(RecordValidationError, match="R1"):
        store.append_encounter([record], run_id="r", episode=1, encounter_ordinal=1)


def test_identity_must_agree_with_the_partition(store: BattleTelemetryStore) -> None:
    record = make_record(encounter_id="ep001-enc009")
    with pytest.raises(RecordValidationError, match="N6"):
        store.append_encounter([record], run_id="r", episode=1, encounter_ordinal=1)


# ── §4.3 manifest + §5 exclusion keys ───────────────────────────────────────


def test_manifest_carries_every_exclusion_key(
    store: BattleTelemetryStore,
) -> None:
    store.append_encounter(
        encounter_records(
            3,
            map="Viridian Forest",
            map_resolved=True,
            defender_species="Weedle",
            defender_level=3,
            battle_type="wild",
        ),
        run_id="r",
        episode=1,
        encounter_ordinal=1,
    )
    store.write_manifest(run_id="r")

    manifest = store.read_manifest("r")
    assert manifest is not None
    attributes = manifest["attributes"]
    assert attributes["schema_version"] == 1
    assert attributes["run_id"] == "r"
    assert attributes["encounters_total"] == 1
    assert attributes["truncated"] is False
    assert attributes["dropped_records"] == 0
    assert len(attributes["index"]) == 1

    entry = attributes["index"][0]
    for key in EXCLUSION_KEYS:
        assert key in entry, (key, entry)
    assert entry["map"] == "Viridian Forest"
    assert entry["map_resolved"] is True
    assert entry["opponent_species"] == "Weedle"
    assert entry["opponent_species_resolved"] is True
    assert entry["opponent_level"] == 3
    assert entry["battle_type"] == "wild"
    assert entry["turns"] == 2
    assert entry["file"] == "battle-r-ep001-enc001.jsonl"
    assert entry["continued_from"] is None


def test_manifest_key_domain_and_namespace(
    store: BattleTelemetryStore, data_dir: Path
) -> None:
    store.append_encounter(
        encounter_records(2), run_id="r", episode=1, encounter_ordinal=1
    )
    store.write_manifest(run_id="r")
    record = duckbrain_client.get(manifest_key("r"), namespace=NAMESPACE)
    assert record is not None
    assert record["key"] == "/game/battle/r/manifest"
    assert record["domain"] == "game/battle"

    # N9: the only memories-*.jsonl content in this namespace is the manifest.
    memory_files = sorted(data_dir.glob("memories-*.jsonl"))
    assert memory_files
    for path in memory_files:
        for line in path.read_text().splitlines():
            if line.strip():
                assert json.loads(line)["key"].startswith("/game/battle/")


def test_manifest_read_back_through_recall(store: BattleTelemetryStore) -> None:
    store.append_encounter(
        encounter_records(2), run_id="r", episode=1, encounter_ordinal=1
    )
    store.write_manifest(run_id="r")
    found = duckbrain_client.recall(
        key_prefix="/game/battle/", namespace=NAMESPACE, limit=10
    )
    assert len(found) == 1
    assert found[0]["attributes"]["run_id"] == "r"


def test_manifest_conflict_is_refused(store: BattleTelemetryStore) -> None:
    """A second, DIFFERENT manifest for one run is refused, not silently shadowed."""
    store.append_encounter(
        encounter_records(2), run_id="r", episode=1, encounter_ordinal=1
    )
    store.write_manifest(run_id="r")
    store.append_encounter(
        encounter_records(2, ordinal=2), run_id="r", episode=1, encounter_ordinal=2
    )
    with pytest.raises(store_mod.ManifestConflictError, match="already exists"):
        store.write_manifest(run_id="r")


def test_manifest_index_is_built_from_disk_not_memory(
    namespaces_root: Path,
) -> None:
    """A LATER process must index partitions an earlier process wrote (§4.3)."""
    first = BattleTelemetryStore(root=namespaces_root)
    first.append_encounter(
        encounter_records(2), run_id="r", episode=1, encounter_ordinal=1
    )

    second = BattleTelemetryStore(root=namespaces_root)
    second.append_encounter(
        encounter_records(2, ordinal=2), run_id="r", episode=1, encounter_ordinal=2
    )
    second.write_manifest(run_id="r")

    manifest = second.read_manifest("r")
    assert manifest is not None
    attributes = manifest["attributes"]
    assert attributes["encounters_total"] == 2
    assert len(attributes["index"]) == 2
    assert attributes["episodes"] == 1


def test_rewrite_ignores_a_distinct_next_encounter(namespaces_root: Path) -> None:
    """A re-write of encounter *n* must not be turn-checked against encounter *n+1*."""
    store = BattleTelemetryStore(root=namespaces_root)
    first = encounter_records(4)
    store.append_encounter(first, run_id="r", episode=1, encounter_ordinal=1)
    store.append_encounter(
        encounter_records(2, ordinal=2), run_id="r", episode=1, encounter_ordinal=2
    )

    again = store.append_encounter(first, run_id="r", episode=1, encounter_ordinal=1)
    assert again.written == 0 and again.skipped == 4


def test_rewrite_of_a_split_encounter_skips_every_record(
    store: BattleTelemetryStore, data_dir: Path
) -> None:
    """De-duplication spans the whole continuation chain (§4.2 + idempotence)."""
    records = encounter_records(500)
    first = store.append_encounter(records, run_id="r", episode=1, encounter_ordinal=1)
    assert len(first.files) == 2
    snapshot = {path.name: path.read_text() for path in data_dir.glob("battle-*.jsonl")}

    again = store.append_encounter(records, run_id="r", episode=1, encounter_ordinal=1)

    assert again.written == 0 and again.skipped == 500
    assert {
        path.name: path.read_text() for path in data_dir.glob("battle-*.jsonl")
    } == snapshot


def test_new_records_for_an_earlier_encounter_stay_in_its_own_file(
    store: BattleTelemetryStore, data_dir: Path
) -> None:
    """A distinct next encounter must not be mistaken for a continuation (§4.2)."""
    store.append_encounter(
        encounter_records(2), run_id="r", episode=1, encounter_ordinal=1
    )
    store.append_encounter(
        encounter_records(2, ordinal=2), run_id="r", episode=1, encounter_ordinal=2
    )

    more = encounter_records(4)[2:]  # turns 2, 2
    result = store.append_encounter(more, run_id="r", episode=1, encounter_ordinal=1)

    assert result.files == ("battle-r-ep001-enc001.jsonl",)
    assert len(read_lines(data_dir / "battle-r-ep001-enc001.jsonl")) == 4
    assert len(read_lines(data_dir / "battle-r-ep001-enc002.jsonl")) == 2


def test_index_cap_truncates_and_keeps_the_true_total(
    store: BattleTelemetryStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(store_mod, "MAX_MANIFEST_ENCOUNTERS", 3)
    for ordinal in range(1, 6):
        store.append_encounter(
            encounter_records(1, ordinal=ordinal),
            run_id="r",
            episode=1,
            encounter_ordinal=ordinal,
        )
    store.write_manifest(run_id="r")

    manifest = store.read_manifest("r")
    assert manifest is not None
    attributes = manifest["attributes"]
    assert attributes["encounters_total"] == 5
    assert len(attributes["index"]) == 3
    assert attributes["truncated"] is True
    assert store.encounters_total == 5


# ── §7 guard rails ──────────────────────────────────────────────────────────


def test_n1_refuses_a_path_outside_the_namespace_data_dir(
    store: BattleTelemetryStore, data_dir: Path, tmp_path: Path
) -> None:
    outside = tmp_path / f"battle-{RUN_ID}-ep001-enc001.jsonl"
    with pytest.raises(StorePathError, match="N1"):
        store._append_lines(outside, ["{}\n"])
    nested = data_dir / "nested" / f"battle-{RUN_ID}-ep001-enc001.jsonl"
    with pytest.raises(StorePathError, match="N1"):
        store._append_lines(nested, ["{}\n"])
    assert not outside.exists()
    assert not nested.exists()


def test_n8_refuses_an_aggregate_filename(
    store: BattleTelemetryStore, data_dir: Path
) -> None:
    with pytest.raises(AggregateFileError, match="N8"):
        store._append_lines(data_dir / "battle-all.jsonl", ["{}\n"])
    with pytest.raises(AggregateFileError, match="N8"):
        store._append_lines(data_dir / "battle-summary.jsonl", ["{}\n"])


def test_n9_refuses_a_memory_filename(
    store: BattleTelemetryStore, data_dir: Path
) -> None:
    with pytest.raises(MemoryFileWriteError, match="N9"):
        store._append_lines(data_dir / "memories-2026-11-17.jsonl", ["{}\n"])


# ── the CLI ─────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def cli() -> Any:
    path = REPO_ROOT / "scripts" / "store_battle_telemetry.py"
    spec = importlib.util.spec_from_file_location("aipp_store_battle_telemetry", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_help_exits_zero(cli: Any) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--help"])
    assert excinfo.value.code == 0


def test_cli_writes_and_verifies(
    cli: Any,
    namespaces_root: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    records = encounter_records(
        4, map="Viridian Forest", defender_species="Weedle", defender_level=3
    )
    source = tmp_path / "records.jsonl"
    source.write_text("".join(json.dumps(r) + "\n" for r in records))

    rc = cli.main(["--records", str(source), "--store-root", str(namespaces_root)])
    assert rc == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["written"] == 4
    assert summary["manifests"]["r"]["index"] == 1

    rc = cli.main(["--verify", "--store-root", str(namespaces_root)])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "BATTLE_TELEMETRY_PARTITION: PASS" in out
    assert "MANIFEST_RULE: PASS" in out


def test_cli_refuses_a_record_and_still_records_the_loss(
    cli: Any,
    namespaces_root: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bad = make_record(damage=7)
    source = tmp_path / "bad.jsonl"
    source.write_text(json.dumps(bad) + "\n")

    rc = cli.main(["--records", str(source), "--store-root", str(namespaces_root)])
    assert rc == 2
    assert "refused" in capsys.readouterr().err

    store = BattleTelemetryStore(root=namespaces_root)
    manifest = store.read_manifest("r")
    assert manifest is not None
    assert manifest["attributes"]["dropped_records"] == 1
