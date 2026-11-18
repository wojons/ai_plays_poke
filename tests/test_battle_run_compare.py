"""Tests for the cross-model battle-run comparison (row BTL-COMPARE-1).

Contract: ``specs/contracts/battle-telemetry.md``.

The fixtures written here are EXPLICITLY LABELLED fixtures, not game runs:
every one is materialised through the real store (``BattleTelemetryStore``) into
a tmp namespaces root, exactly as a real writer would, but the events are
hand-authored so the expected arithmetic can be stated by hand. §6's worked
example ("deepseek-v4-flash" vs "glm-5.3-flash" on Viridian Forest / wild Weedle
level 3 / max HP 15) is reproduced record for record so the table the contract
prints is the table this engine prints.

Covered, in contract order:

- §5.2 steps 1-3: only the two named runs are listed, only their manifests are
  read first, and E1..E6 each exclude their own partition — with the key named.
- "excluded without opening" is proved by deleting every excluded file and
  getting the identical table.
- §5.2 step 4 (E8): the per-record turn window.
- §6: the table reproduces the contract's numbers (15/15 damage, 4/6 turns,
  4/4 and 4/6 hits, 3.75/2.50 damage per turn, 0 whiffs vs 2).
- Acceptance 2: one damage figure is re-read from its raw record (file:line +
  record identity) and every summed record is accounted for.
- Acceptance 3: partitions read and excluded are reported with reasons.
- The extras the row asks for: damage dealt vs taken, overkill estimate,
  turns per encounter, wild-vs-trainer split, per-level-band efficiency, and
  the two metrics the record shape cannot answer (items, switches).
- Honesty: a run with no manifest, a partition missing from the index, and a
  manifest naming a traversing path are all named as gaps, never counted.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core import battle_telemetry_store as store_mod  # noqa: E402
from src.core import duckbrain_client  # noqa: E402
from src.core.battle_run_compare import (  # noqa: E402
    DATA_GAP_NO_BATTLE_PARTITIONS,
    DATA_GAP_REAL_PAIRED_RUNS,
    JOIN_RULE,
    NOT_DERIVABLE,
    ComparisonError,
    ComparisonReport,
    MetricRow,
    Segment,
    analyse_run,
    compare_runs,
    select_run,
    store_census,
)
from src.core.battle_telemetry_store import (  # noqa: E402
    BattleTelemetryStore,
    manifest_key,
    record_identity,
)

NAMESPACE = "pokemon-battle"

#: §6's two runs — the worked example's own run ids.
RUN_A = "20261117_090000"
RUN_B = "20261117_093000"
MODEL_A = "deepseek-v4-flash"
MODEL_B = "glm-5.3-flash"

#: §6's segment.
SEGMENT_SIX = Segment(
    map_name="Viridian Forest",
    opponent_species="Weedle",
    level_lo=3,
    level_hi=3,
    battle_type="wild",
)

_UNRESOLVED_SPECIES = re.compile(r"^#\d+$")
_UNRESOLVED_MOVE = re.compile(r"^Move#\d+$")
_UNRESOLVED_MAP = re.compile(r"^Map_[0-9A-F]{2}$")


# ── fixtures (materialised through the real store, into a tmp root) ─────────


@pytest.fixture()
def namespaces_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A tmp namespaces root, also installed on the client module."""
    path = tmp_path / "namespaces"
    monkeypatch.setattr(duckbrain_client, "DUCKBRAIN_ROOT", path)
    return path


@pytest.fixture()
def data_dir(namespaces_root: Path) -> Path:
    return namespaces_root / NAMESPACE / "data"


def make_store(
    namespaces_root: Path,
    *,
    model: str | None,
    provider: str | None,
    arm: str = "llm",
) -> BattleTelemetryStore:
    """One store per run: the manifest identity comes from the store overrides."""
    return BattleTelemetryStore(
        root=namespaces_root,
        decision_arm=arm,
        model_decision=model,
        provider=provider,
    )


def make_record(**overrides: Any) -> dict[str, Any]:
    """One contract-valid record; ``*_resolved`` flags are recomputed."""
    record: dict[str, Any] = {
        "run_id": "r",
        "episode": 1,
        "encounter_id": "ep001-enc001",
        "turn": 1,
        "map": "M",
        "map_resolved": True,
        "ts": "2026-11-17T09:00:00Z",
        "model_decision": None,
        "model_vision": None,
        "provider": None,
        "decision_arm": "a",
        "attacker_side": "player",
        "attacker_species": "CHARMANDER",
        "attacker_species_resolved": True,
        "attacker_level": 5,
        "defender_species": "Weedle",
        "defender_species_resolved": True,
        "defender_level": 3,
        "battle_type": "wild",
        "move": "TACKLE",
        "move_resolved": True,
        "outcome": "damage",
        "damage": 1,
        "damage_pct_of_max": None,
        "defender_hp_before": 2,
        "defender_hp_after": 1,
        "defender_max_hp": 15,
        "encounter_outcome": "won",
    }
    record.update(overrides)
    record["attacker_species_resolved"] = (
        _UNRESOLVED_SPECIES.match(str(record["attacker_species"])) is None
    )
    record["defender_species_resolved"] = (
        _UNRESOLVED_SPECIES.match(str(record["defender_species"])) is None
    )
    record["move_resolved"] = _UNRESOLVED_MOVE.match(str(record["move"])) is None
    record["map_resolved"] = _UNRESOLVED_MAP.match(str(record["map"])) is None
    return record


def battle_records(
    run_id: str,
    *,
    episode: int,
    ordinal: int,
    specs: Sequence[Mapping[str, Any]],
    map_name: str,
    battle_type: str,
    outcome: str,
    player_species: str = "CHARMANDER",
    player_level: int = 5,
    opponent: str = "Weedle",
    opponent_level: int = 3,
) -> list[dict[str, Any]]:
    """Turn a compact per-event spec into contract records for one encounter."""
    records: list[dict[str, Any]] = []
    # R3: ``turn`` is non-decreasing within a file, and the enemy's response to
    # turn n carries turn n — so order by turn, player side first, and the
    # authored order cannot violate the store's rule.
    ordered = sorted(
        specs,
        key=lambda spec: (
            int(spec["turn"]),
            0 if str(spec.get("side", "player")) == "player" else 1,
        ),
    )
    for spec in ordered:
        side = str(spec.get("side", "player"))
        attacker_species = (
            player_species if side == "player" else str(spec.get("species", opponent))
        )
        attacker_level = (
            player_level if side == "player" else int(spec.get("level", opponent_level))
        )
        defender_species = str(
            spec.get("against", opponent if side == "player" else player_species)
        )
        defender_level = int(
            spec.get(
                "against_level", opponent_level if side == "player" else player_level
            )
        )
        records.append(
            make_record(
                run_id=run_id,
                episode=episode,
                encounter_id=f"ep{episode:03d}-enc{ordinal:03d}",
                turn=int(spec["turn"]),
                map=map_name,
                attacker_side=side,
                attacker_species=attacker_species,
                attacker_level=attacker_level,
                defender_species=defender_species,
                defender_level=defender_level,
                battle_type=battle_type,
                move=str(spec.get("move", "TACKLE")),
                outcome=str(spec.get("outcome", "damage")),
                damage=int(spec["damage"]),
                defender_hp_before=int(spec["before"]),
                defender_hp_after=int(spec["after"]),
                defender_max_hp=int(spec["max_hp"]),
                encounter_outcome=outcome,
            )
        )
    return records


def write_encounter(
    store: BattleTelemetryStore,
    run_id: str,
    *,
    episode: int,
    ordinal: int,
    specs: Sequence[Mapping[str, Any]],
    map_name: str = "Viridian Forest",
    battle_type: str = "wild",
    outcome: str = "won",
    player_level: int = 5,
    opponent: str = "Weedle",
    opponent_level: int = 3,
) -> None:
    """Write one encounter's records through the real store writer."""
    records = battle_records(
        run_id,
        episode=episode,
        ordinal=ordinal,
        specs=specs,
        map_name=map_name,
        battle_type=battle_type,
        outcome=outcome,
        player_level=player_level,
        opponent=opponent,
        opponent_level=opponent_level,
    )
    store.append_encounter(
        records,
        run_id=run_id,
        episode=episode,
        encounter_ordinal=ordinal,
        map_name=map_name,
        battle_type=battle_type,
        outcome=outcome,
    )


# §6's two event lists, verbatim (turn, damage, hp_before -> hp_after, max 15).
SIX_A_EVENTS: list[dict[str, Any]] = [
    {"turn": 1, "damage": 4, "before": 15, "after": 11, "max_hp": 15},
    {"turn": 2, "damage": 5, "before": 11, "after": 6, "max_hp": 15},
    {"turn": 3, "damage": 4, "before": 6, "after": 2, "max_hp": 15},
    {"turn": 4, "damage": 2, "before": 2, "after": 0, "max_hp": 15},
]
SIX_B_EVENTS: list[dict[str, Any]] = [
    {
        "turn": 1,
        "damage": 0,
        "before": 15,
        "after": 15,
        "max_hp": 15,
        "outcome": "miss",
    },
    {"turn": 2, "damage": 3, "before": 15, "after": 12, "max_hp": 15},
    {"turn": 3, "damage": 4, "before": 12, "after": 8, "max_hp": 15},
    {"turn": 4, "damage": 0, "before": 8, "after": 8, "max_hp": 15, "outcome": "miss"},
    {"turn": 5, "damage": 4, "before": 8, "after": 4, "max_hp": 15},
    {"turn": 6, "damage": 4, "before": 4, "after": 0, "max_hp": 15},
]

#: Two filler events for every decoy partition.
DECOY_EVENTS: list[dict[str, Any]] = [
    {"turn": 1, "damage": 3, "before": 12, "after": 9, "max_hp": 12},
    {"turn": 2, "damage": 3, "before": 9, "after": 6, "max_hp": 12},
]


def build_six_fixture(namespaces_root: Path) -> None:
    """Materialise §6's two runs plus the six decoy partitions the text names."""
    store_a = make_store(namespaces_root, model=MODEL_A, provider="deepseek")
    # Run A — the selected encounter is ep004-enc002 (§6).
    write_encounter(
        store_a,
        RUN_A,
        episode=1,
        ordinal=1,
        specs=DECOY_EVENTS,
        opponent="Pidgey",
        opponent_level=4,
    )
    write_encounter(
        store_a,
        RUN_A,
        episode=2,
        ordinal=1,
        specs=DECOY_EVENTS,
        opponent="#16",
        opponent_level=3,
    )
    write_encounter(
        store_a,
        RUN_A,
        episode=3,
        ordinal=1,
        specs=DECOY_EVENTS,
        battle_type="trainer",
        outcome="lost",
    )
    write_encounter(
        store_a,
        RUN_A,
        episode=4,
        ordinal=2,
        specs=SIX_A_EVENTS,
    )
    write_encounter(
        store_a,
        RUN_A,
        episode=5,
        ordinal=1,
        specs=DECOY_EVENTS,
        opponent_level=5,
    )
    store_a.write_manifest(run_id=RUN_A)

    store_b = make_store(namespaces_root, model=MODEL_B, provider="zai")
    # Run B — the selected encounter is ep002-enc001 (§6).
    write_encounter(
        store_b,
        RUN_B,
        episode=1,
        ordinal=1,
        specs=DECOY_EVENTS,
        map_name="Route 1",
    )
    write_encounter(
        store_b,
        RUN_B,
        episode=2,
        ordinal=1,
        specs=SIX_B_EVENTS,
    )
    write_encounter(
        store_b,
        RUN_B,
        episode=3,
        ordinal=1,
        specs=DECOY_EVENTS,
        opponent="Caterpie",
        opponent_level=3,
    )
    store_b.write_manifest(run_id=RUN_B)


def build_level_fixture(namespaces_root: Path) -> tuple[str, str]:
    """Two runs whose player levels differ — the overkill-per-level comparison."""
    low, high = "fx_low_level", "fx_high_level"
    store_low = make_store(namespaces_root, model="low-model", provider="p")
    # Level 5 attacker, 4 damage a hit against 12 HP: the kill needs exactly
    # one more typical hit, so the overkill ratio is 1.0.
    write_encounter(
        store_low,
        low,
        episode=1,
        ordinal=1,
        specs=[
            {"turn": 1, "damage": 4, "before": 12, "after": 8, "max_hp": 12},
            {"turn": 2, "damage": 4, "before": 8, "after": 4, "max_hp": 12},
            {"turn": 3, "damage": 4, "before": 4, "after": 0, "max_hp": 12},
            {
                "turn": 1,
                "side": "enemy",
                "damage": 3,
                "before": 20,
                "after": 17,
                "max_hp": 20,
            },
            {
                "turn": 2,
                "side": "enemy",
                "damage": 2,
                "before": 17,
                "after": 15,
                "max_hp": 20,
            },
        ],
        map_name="Route 2",
        opponent="Rattata",
        opponent_level=4,
        player_level=5,
    )
    # A trainer encounter in the same segment: the wild-vs-trainer split.
    write_encounter(
        store_low,
        low,
        episode=2,
        ordinal=1,
        specs=[
            {"turn": 1, "damage": 6, "before": 12, "after": 6, "max_hp": 12},
            {"turn": 2, "damage": 6, "before": 6, "after": 0, "max_hp": 12},
        ],
        map_name="Route 2",
        battle_type="trainer",
        opponent="Rattata",
        opponent_level=4,
        player_level=5,
    )
    store_low.write_manifest(run_id=low)

    store_high = make_store(namespaces_root, model="high-model", provider="p")
    # Level 20 attacker, 9 damage a hit: the kill needed only 3, so a typical
    # blow is 3x what that kill required.
    write_encounter(
        store_high,
        high,
        episode=1,
        ordinal=1,
        specs=[
            {"turn": 1, "damage": 9, "before": 12, "after": 3, "max_hp": 12},
            {"turn": 2, "damage": 3, "before": 3, "after": 0, "max_hp": 12},
            {
                "turn": 1,
                "side": "enemy",
                "damage": 7,
                "before": 40,
                "after": 33,
                "max_hp": 40,
            },
        ],
        map_name="Route 2",
        opponent="Rattata",
        opponent_level=4,
        player_level=20,
    )
    store_high.write_manifest(run_id=high)
    return low, high


@pytest.fixture()
def six_report(namespaces_root: Path) -> ComparisonReport:
    build_six_fixture(namespaces_root)
    return compare_runs(
        RUN_A, RUN_B, SEGMENT_SIX, root=namespaces_root, data_note="fixture"
    )


def rows_by_metric(report: ComparisonReport) -> dict[str, MetricRow]:
    return {row.metric: row for row in report.rows()}


# ── §6: the contract's own table ────────────────────────────────────────────


def test_six_worked_example_reproduces_the_contract_table(
    six_report: ComparisonReport,
) -> None:
    """The §6 table, number for number, from stored events only."""
    rows = rows_by_metric(six_report)
    assert rows["partitions_read"].a == "1"
    assert rows["partitions_read"].b == "1"
    assert rows["turns_to_ko"].a == "4"
    assert rows["turns_to_ko"].b == "6"
    assert rows["attacks_to_ko"].a == "4"
    assert rows["attacks_to_ko"].b == "6"
    assert rows["hits/attacks"].a == "4 / 4 = 1.000"
    assert rows["hits/attacks"].b == "4 / 6 = 0.667"
    assert rows["whiff_count"].a == "0"
    assert rows["whiff_count"].b == "2"
    assert rows["damage_dealt_total"].a == "15"
    assert rows["damage_dealt_total"].b == "15"
    assert rows["damage_per_turn"].a == "3.75"
    assert rows["damage_per_turn"].b == "2.50"
    assert rows["flee_count"].a == "0"
    assert rows["flee_count"].b == "0"
    assert rows["encounter_outcome"].a == "won"
    assert rows["encounter_outcome"].b == "won"


def test_observed_overkill_is_zero_because_r5_clamps_to_remaining_hp(
    six_report: ComparisonReport,
) -> None:
    """The clamped figure is 0; the estimated figure is where the signal lives."""
    assert six_report.run_a.overkill_observed == 0
    assert six_report.run_b.overkill_observed == 0
    rows = rows_by_metric(six_report)
    assert rows["overkill_observed"].a == "0"
    assert rows["overkill_observed"].b == "0"
    # Run A's typical non-KO hit (4.33) exceeded the 2 HP the kill needed.
    assert six_report.run_a.overkill_ratio == pytest.approx(13 / 3 / 2, rel=1e-3)
    assert six_report.run_a.overkill_damage_total == 2


def test_overkill_ratio_is_per_ko_not_per_encounter(
    namespaces_root: Path,
) -> None:
    """Two KOs in one partition: the ratio is the mean of the per-KO ratios."""
    run = "fx_two_kos"
    store = make_store(namespaces_root, model="m", provider="p")
    write_encounter(
        store,
        run,
        episode=1,
        ordinal=1,
        specs=[
            {"turn": 1, "damage": 9, "before": 12, "after": 3, "max_hp": 12},
            {"turn": 2, "damage": 3, "before": 3, "after": 0, "max_hp": 12},
            {"turn": 3, "damage": 6, "before": 10, "after": 4, "max_hp": 12},
            {"turn": 4, "damage": 4, "before": 4, "after": 0, "max_hp": 12},
        ],
        map_name="Route 4",
        opponent="Rattata",
        opponent_level=4,
    )
    store.write_manifest(run_id=run)

    other = make_store(namespaces_root, model="m2", provider="p")
    write_encounter(
        other,
        "fx_two_kos_b",
        episode=1,
        ordinal=1,
        specs=[{"turn": 1, "damage": 1, "before": 12, "after": 11, "max_hp": 12}],
        map_name="Elsewhere",
        opponent="Pidgey",
        opponent_level=9,
    )
    other.write_manifest(run_id="fx_two_kos_b")

    metrics = analyse_run(
        BattleTelemetryStore(root=namespaces_root),
        run,
        Segment(map_name="Route 4"),
    )
    enc = metrics.encounters[0]
    # Non-KO hits are 9 and 6 -> a 7.5 typical hit; the kills needed 3 and 4.
    assert enc.ko_hp_needed_each == (3, 4)
    assert enc.ko_hp_needed == 7
    assert enc.ko_turn == 4
    assert enc.overkill_ratio == pytest.approx((7.5 / 3 + 7.5 / 4) / 2)
    assert enc.overkill_damage == 8  # (7.5-3) + (7.5-4)
    assert metrics.overkill_observed == 0
    assert metrics.ko_events == 1


def test_table_names_both_models(six_report: ComparisonReport) -> None:
    """Acceptance 1: the table names the models, and states the join rule."""
    table = six_report.render_table()
    assert MODEL_A in table
    assert MODEL_B in table
    assert MODEL_A == six_report.run_a.model_label
    assert MODEL_B == six_report.run_b.model_label
    assert "provider=deepseek" in six_report.run_a.model_line
    assert "provider=zai" in six_report.run_b.model_line
    assert JOIN_RULE in six_report.render()


def test_totals_match_the_encounter_they_came_from(
    six_report: ComparisonReport,
) -> None:
    """Aggregates are sums of the per-encounter numbers, not a second formula."""
    a, b = six_report.run_a, six_report.run_b
    assert a.damage_dealt_total == sum(enc.damage_dealt for enc in a.encounters)
    assert b.damage_dealt_total == sum(enc.damage_dealt for enc in b.encounters)
    assert a.turns_total == 4 and b.turns_total == 6
    assert a.hit_rate == pytest.approx(1.0)
    assert b.hit_rate == pytest.approx(4 / 6)
    assert a.damage_per_turn == pytest.approx(3.75)
    assert b.damage_per_turn == pytest.approx(2.5)


# ── §5.2: selection, exclusion, and reading only what survives ──────────────


def test_partitions_read_and_excluded_are_reported_with_the_key(
    six_report: ComparisonReport,
) -> None:
    """Acceptance 3: every read partition and every exclusion, with its key."""
    assert six_report.partitions_read == (
        f"battle-{RUN_A}-ep004-enc002.jsonl",
        f"battle-{RUN_B}-ep002-enc001.jsonl",
    )
    reasons = {item.file: item.reason for item in six_report.partitions_excluded}
    assert len(reasons) == 6  # §6's six excluded partitions
    assert reasons[f"battle-{RUN_A}-ep001-enc001.jsonl"].startswith("E2")
    assert reasons[f"battle-{RUN_A}-ep002-enc001.jsonl"].startswith("E2")
    assert reasons[f"battle-{RUN_A}-ep003-enc001.jsonl"].startswith("E6")
    assert reasons[f"battle-{RUN_A}-ep005-enc001.jsonl"].startswith("E3")
    assert reasons[f"battle-{RUN_B}-ep001-enc001.jsonl"].startswith("E1")
    assert reasons[f"battle-{RUN_B}-ep003-enc001.jsonl"].startswith("E2")
    text = six_report.render()
    assert "PARTITIONS READ (2)" in text
    assert "PARTITIONS EXCLUDED (6)" in text


def test_unresolved_labels_are_never_joined(
    six_report: ComparisonReport,
) -> None:
    """E1/E2 refuse an unresolved label even when no filter names one."""
    unfiltered = Segment()
    assert unfiltered.rejection(
        {"map": "Map_0A", "map_resolved": False, "opponent_species": "Weedle"}
    ).startswith("E1")
    assert unfiltered.rejection(
        {
            "map": "M",
            "map_resolved": True,
            "opponent_species": "#16",
            "opponent_species_resolved": False,
        }
    ).startswith("E2")


@pytest.mark.parametrize(
    ("segment", "file_name", "prefix"),
    [
        (
            Segment(encounter_ids=("ep004-enc002",)),
            f"battle-{RUN_A}-ep005-enc001.jsonl",
            "E4",
        ),
        (Segment(turn_lo=3), f"battle-{RUN_A}-ep005-enc001.jsonl", "E5"),
        (Segment(battle_type="trainer"), f"battle-{RUN_A}-ep001-enc001.jsonl", "E6"),
        (Segment(level_lo=3, level_hi=3), f"battle-{RUN_A}-ep005-enc001.jsonl", "E3"),
        (Segment(map_name="Route 1"), f"battle-{RUN_A}-ep004-enc002.jsonl", "E1"),
        (
            Segment(opponent_species="Weedle", level_lo=3, level_hi=3),
            f"battle-{RUN_B}-ep003-enc001.jsonl",
            "E2",
        ),
    ],
)
def test_each_exclusion_key_names_itself(
    namespaces_root: Path,
    segment: Segment,
    file_name: str,
    prefix: str,
) -> None:
    build_six_fixture(namespaces_root)
    store = BattleTelemetryStore(root=namespaces_root)
    run_id = file_name.split("-")[1]
    selection = select_run(store, run_id, segment)
    reasons = {item.file: item.reason for item in selection.excluded}
    assert file_name in reasons, sorted(reasons)
    assert reasons[file_name].startswith(prefix), reasons[file_name]


def test_excluded_partitions_are_never_opened(six_report: ComparisonReport) -> None:
    """Deleting every excluded file must not change a single number."""
    before_rows = [(row.metric, row.a, row.b) for row in six_report.rows()]
    for item in six_report.partitions_excluded:
        path = Path(six_report.data_dir) / item.file
        assert path.is_file()
        path.unlink()
    again = compare_runs(
        RUN_A,
        RUN_B,
        SEGMENT_SIX,
        root=Path(six_report.store_root),
        data_note="fixture",
    )
    after_rows = [(row.metric, row.a, row.b) for row in again.rows()]
    assert after_rows == before_rows
    assert again.comparable


def test_turn_window_refines_per_record(
    namespaces_root: Path,
) -> None:
    """E8: a turn window trims records, and E5 drops short encounters first."""
    build_six_fixture(namespaces_root)
    report = compare_runs(
        RUN_A, RUN_B, Segment(turn_lo=3, turn_hi=4), root=namespaces_root
    )
    a_enc = report.run_a.encounters[0]
    # Run A only has turns 1..4, so the window keeps turns 3 and 4 (4 + 2 HP).
    assert a_enc.turns == 4
    assert a_enc.damage_dealt == 6
    # Run B's selected encounter has turns 1..6; the window keeps 3 and 4 only.
    b_enc = report.run_b.encounters[0]
    assert b_enc.damage_dealt == 4
    assert b_enc.whiffs == 1


# ── acceptance 2: every number traceable to a raw record ────────────────────


def test_damage_figure_spot_checks_to_its_raw_record(
    six_report: ComparisonReport,
) -> None:
    """The summed damage re-reads from ``file:line`` and the identity agrees."""
    check = six_report.spot_check_damage("a")
    assert check.matches is True
    assert check.metric == "damage_dealt_total"
    assert check.run_id == RUN_A
    assert check.model_label == MODEL_A
    assert check.ref.file == f"battle-{RUN_A}-ep004-enc002.jsonl"
    assert check.ref.line >= 1
    assert check.raw["damage"] == check.ref.damage
    assert check.raw["turn"] == check.ref.turn
    assert record_identity(dict(check.raw)) == check.ref.identity
    assert "MATCH" in check.summary

    other = six_report.spot_check_damage("b", index=1)
    assert other.matches is True
    assert other.run_id == RUN_B


def test_every_damage_contribution_is_accounted_for(
    six_report: ComparisonReport,
) -> None:
    """damage_dealt_total is exactly the sum of the referenced records."""
    for metrics in (six_report.run_a, six_report.run_b):
        assert metrics.damage_dealt_total == sum(
            ref.damage for ref in metrics.damage_sources
        )
        assert metrics.damage_taken_total == sum(
            ref.damage for ref in metrics.damage_taken_sources
        )
    # Run B's six player records all appear; run A's four.
    assert len(six_report.run_a.damage_sources) == 4
    assert len(six_report.run_b.damage_sources) == 6


def test_spot_check_rejects_an_unknown_run_or_index(
    six_report: ComparisonReport,
) -> None:
    with pytest.raises(ComparisonError):
        six_report.spot_check_damage("zzz")
    with pytest.raises(ComparisonError):
        six_report.spot_check_damage("a", index=99)


# ── the row's extra metrics ─────────────────────────────────────────────────


def test_damage_dealt_vs_taken_and_wild_trainer_split(
    namespaces_root: Path,
) -> None:
    low, high = build_level_fixture(namespaces_root)
    report = compare_runs(low, high, Segment(map_name="Route 2"), root=namespaces_root)

    assert report.run_a.damage_dealt_total == 24  # 12 wild + 12 trainer
    assert report.run_a.damage_taken_total == 5  # enemy hits 3 + 2
    assert report.run_a.damage_ratio == pytest.approx(24 / 5)
    assert report.run_b.damage_taken_total == 7
    assert report.run_b.damage_ratio == pytest.approx(12 / 7)

    splits = {split.battle_type: split for split in report.run_a.by_battle_type}
    assert splits["wild"].encounters == 1
    assert splits["wild"].damage_dealt == 12
    assert splits["trainer"].encounters == 1
    assert splits["trainer"].damage_dealt == 12
    assert report.run_b.by_battle_type[0].battle_type == "wild"


def test_higher_level_attacker_overkills_more(
    namespaces_root: Path,
) -> None:
    """The per-level-band question, answered from the records themselves."""
    low, high = build_level_fixture(namespaces_root)
    report = compare_runs(low, high, Segment(map_name="Route 2"), root=namespaces_root)

    # Level 5: hits of 4 against a 4 HP finishing blow -> ratio 1.0, no waste.
    assert report.run_a.overkill_ratio == pytest.approx(1.0)
    assert report.run_a.overkill_damage_total == 0
    # Level 20: 9-damage blows against a 3 HP finishing blow -> 3x.
    assert report.run_b.overkill_ratio == pytest.approx(3.0)
    assert report.run_b.overkill_damage_total == 6

    bands_a = {split.label: split for split in report.run_a.by_level_band}
    bands_b = {split.label: split for split in report.run_b.by_level_band}
    # 12 + 12 damage over 3 + 2 attacks in the level 1-10 band.
    assert bands_a["level 1-10"].damage_dealt == 24
    assert bands_a["level 1-10"].attacks == 5
    assert bands_a["level 1-10"].damage_per_attack == pytest.approx(4.8)
    assert bands_b["level 11-20"].damage_per_attack == pytest.approx(6.0)
    assert bands_a["level 1-10"].overkill_ratio == pytest.approx(1.0)
    assert bands_b["level 11-20"].overkill_ratio == pytest.approx(3.0)
    # The report prints one row per band, for both runs.
    rows = rows_by_metric(report)
    assert rows["overkill_ratio @ level 11-20"].b == "3.00"
    assert rows["overkill_ratio @ level 11-20"].a == "n/a"


def test_overkill_scope_is_stated_and_unestimable_is_counted(
    namespaces_root: Path,
) -> None:
    run = "fx_single_hit"
    store = make_store(namespaces_root, model="m", provider="p")
    # A one-hit KO: no non-KO hit exists, so nothing may be invented.
    write_encounter(
        store,
        run,
        episode=1,
        ordinal=1,
        specs=[{"turn": 1, "damage": 12, "before": 12, "after": 0, "max_hp": 12}],
        map_name="Route 3",
        opponent="Pidgey",
        opponent_level=3,
    )
    store.write_manifest(run_id=run)

    other = make_store(namespaces_root, model="m2", provider="p")
    write_encounter(
        other,
        "fx_other",
        episode=1,
        ordinal=1,
        specs=[{"turn": 1, "damage": 1, "before": 12, "after": 11, "max_hp": 12}],
        map_name="Elsewhere",
        opponent="Pidgey",
        opponent_level=9,
    )
    other.write_manifest(run_id="fx_other")

    report = compare_runs(
        run, "fx_other", Segment(map_name="Route 3"), root=namespaces_root
    )
    enc = report.run_a.encounters[0]
    assert enc.overkill_ratio is None
    assert enc.overkill_scope is None
    assert report.run_a.overkill_estimated == 0
    assert report.run_a.overkill_unestimated == 1
    rows = rows_by_metric(report)
    assert rows["overkill_estimated / unestimated"].a == "0/1"


def test_turns_per_encounter_and_level_bands(
    namespaces_root: Path,
) -> None:
    low, high = build_level_fixture(namespaces_root)
    report = compare_runs(low, high, Segment(map_name="Route 2"), root=namespaces_root)
    assert report.run_a.encounters and len(report.run_a.encounters) == 2
    assert report.run_a.turns_total == 5
    assert report.run_a.turns_per_encounter == pytest.approx(2.5)
    assert report.run_b.turns_per_encounter == pytest.approx(2.0)
    assert report.run_a.ko_events == 2


def test_items_and_switches_are_reported_as_not_derivable(
    six_report: ComparisonReport,
) -> None:
    """A metric the record shape cannot answer is named, never zeroed."""
    rows = rows_by_metric(six_report)
    assert rows["items_used"].a == "n/a"
    assert rows["switches"].b == "n/a"
    assert rows["items_used"].derivable is False
    assert "§3.2" in NOT_DERIVABLE["items_used"]
    assert "switch" in NOT_DERIVABLE["switches"].lower()
    assert "items_used" in six_report.render()
    payload = six_report.to_dict()
    assert payload["runs"]["a"]["not_derivable"]["items_used"].startswith("n/a")


# ── honesty: what the store cannot answer is a named gap ────────────────────


def test_missing_manifest_names_the_gap_and_reads_nothing(
    namespaces_root: Path,
) -> None:
    store = make_store(namespaces_root, model="m", provider="p")
    write_encounter(store, "fx_no_manifest", episode=1, ordinal=1, specs=SIX_A_EVENTS)
    # Deliberately no write_manifest() call: the run has partitions, no keys.

    selection = select_run(
        BattleTelemetryStore(root=namespaces_root), "fx_no_manifest", Segment()
    )
    assert selection.manifest_present is False
    assert selection.selected == ()
    assert selection.partitions_on_disk == ("battle-fx_no_manifest-ep001-enc001.jsonl",)
    assert any("manifest_missing" in note for note in selection.notes)

    report = compare_runs("fx_no_manifest", RUN_B, Segment(), root=namespaces_root)
    assert report.comparable is False
    assert report.partitions_read == ()
    assert DATA_GAP_REAL_PAIRED_RUNS in report.gaps


def test_partition_missing_from_the_index_is_named_not_read(
    namespaces_root: Path,
) -> None:
    build_six_fixture(namespaces_root)
    store_a = make_store(namespaces_root, model=MODEL_A, provider="deepseek")
    # Written AFTER the manifest: on disk, absent from the index.
    write_encounter(
        store_a,
        RUN_A,
        episode=9,
        ordinal=1,
        specs=DECOY_EVENTS,
        opponent="Weedle",
        opponent_level=3,
    )
    metrics = analyse_run(
        BattleTelemetryStore(root=namespaces_root), RUN_A, SEGMENT_SIX
    )
    assert "battle-20261117_090000-ep009-enc001.jsonl" in (metrics.selection.unindexed)
    assert "battle-20261117_090000-ep009-enc001.jsonl" not in metrics.partitions_read
    assert any("unindexed_partitions" in gap for gap in metrics.gaps)


def test_a_traversing_manifest_path_is_excluded_not_opened(
    namespaces_root: Path,
) -> None:
    run = "fx_traversal"
    store = make_store(namespaces_root, model="m", provider="p")
    write_encounter(store, run, episode=1, ordinal=1, specs=SIX_A_EVENTS)
    attributes: dict[str, Any] = {
        "schema_version": 1,
        "run_id": run,
        "decision_arm": "llm",
        "model_decision": "m",
        "model_vision": None,
        "provider": "p",
        "started": "2026-11-17T09:00:00Z",
        "ended": None,
        "episodes": 1,
        "encounters_total": 1,
        "truncated": False,
        "dropped_records": 0,
        "index": [
            {
                "encounter_id": "ep001-enc001",
                "file": "../evil.jsonl",
                "map": "Viridian Forest",
                "map_resolved": True,
                "opponent_species": "Weedle",
                "opponent_species_resolved": True,
                "opponent_level": 3,
                "battle_type": "wild",
                "turns": 4,
                "records": 4,
                "outcome": "won",
                "continued_from": None,
                "truncated": False,
            }
        ],
    }
    with store_mod.client_root(namespaces_root):
        duckbrain_client.remember(
            key=manifest_key(run),
            domain="game/battle",
            attributes=attributes,
            embedding_text="fixture manifest",
            namespace=NAMESPACE,
        )

    selection = select_run(BattleTelemetryStore(root=namespaces_root), run, Segment())
    assert selection.selected == ()
    assert len(selection.excluded) == 1
    assert "path traversal" in selection.excluded[0].reason


def test_empty_store_reports_no_battle_partitions(
    namespaces_root: Path,
) -> None:
    report = compare_runs("x", "y", Segment(), root=namespaces_root)
    assert report.comparable is False
    assert DATA_GAP_NO_BATTLE_PARTITIONS in report.gaps
    census = store_census(BattleTelemetryStore(root=namespaces_root))
    assert census.event_files == ()
    assert "no battle-*.jsonl" in census.summary()


def test_census_counts_runs_and_manifests(six_report: ComparisonReport) -> None:
    census = six_report.census
    assert census.run_ids == (RUN_A, RUN_B)
    assert census.runs_with_manifest == (RUN_A, RUN_B)
    assert len(census.event_files) == 8
    assert "8 partition file(s) across 2 run(s)" in census.summary()


# ── guard rails ─────────────────────────────────────────────────────────────


def test_a_run_cannot_be_compared_with_itself(namespaces_root: Path) -> None:
    with pytest.raises(ComparisonError):
        compare_runs(RUN_A, RUN_A, Segment(), root=namespaces_root)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"level_lo": 9, "level_hi": 3},
        {"turn_lo": 9, "turn_hi": 3},
        {"level_lo": -1},
        {"battle_type": "double"},
    ],
)
def test_segment_rejects_impossible_filters(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ComparisonError):
        Segment(**kwargs)


def test_report_is_json_serialisable(six_report: ComparisonReport) -> None:
    payload = json.loads(json.dumps(six_report.to_dict(), default=str))
    assert payload["comparable"] is True
    assert payload["runs"]["a"]["model_decision"] == MODEL_A
    assert payload["runs"]["b"]["model_decision"] == MODEL_B
    assert payload["provenance"]["label"] == "fixture"
    assert payload["join_rule"] == JOIN_RULE
    assert len(payload["partitions_read"]) == 2
    assert len(payload["partitions_excluded"]) == 6
    rows = {row["metric"]: row for row in payload["table"]}
    assert rows["damage_dealt_total"]["a"] == "15"


# ── the CLI ─────────────────────────────────────────────────────────────────


def test_cli_prints_table_partitions_and_spot_check(
    namespaces_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts.compare_battle_runs import main

    build_six_fixture(namespaces_root)
    code = main(
        [
            "--run-a",
            RUN_A,
            "--run-b",
            RUN_B,
            "--map",
            "Viridian Forest",
            "--opponent",
            "Weedle",
            "--level-lo",
            "3",
            "--level-hi",
            "3",
            "--battle-type",
            "wild",
            "--store-root",
            str(namespaces_root),
            "--note",
            "fixture — labelled synthetic records",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "COMPARISON:" in out
    assert MODEL_A in out and MODEL_B in out
    assert "PARTITIONS READ (2)" in out
    assert "PARTITIONS EXCLUDED (6)" in out
    assert "DATA PROVENANCE:" in out
    assert "fixture — labelled synthetic records" in out
    assert "SPOT CHECK" in out
    assert "MATCH" in out
    assert "damage_dealt_total=15" in out
    assert "NOT DERIVABLE FROM THE RECORD SHAPE:" in out
    assert JOIN_RULE in out


def test_cli_json_mode_carries_the_spot_check(
    namespaces_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts.compare_battle_runs import main

    build_six_fixture(namespaces_root)
    code = main(
        [
            "--run-a",
            RUN_A,
            "--run-b",
            RUN_B,
            "--map",
            "Viridian Forest",
            "--opponent",
            "Weedle",
            "--level-lo",
            "3",
            "--level-hi",
            "3",
            "--battle-type",
            "wild",
            "--store-root",
            str(namespaces_root),
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["comparable"] is True
    assert payload["spot_check"]["matches"] is True
    assert payload["spot_check"]["damage"] >= 1


def test_cli_exits_one_when_there_is_nothing_to_compare(
    namespaces_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts.compare_battle_runs import main

    code = main(
        ["--run-a", "nope_a", "--run-b", "nope_b", "--store-root", str(namespaces_root)]
    )
    out = capsys.readouterr().out
    assert code == 1
    assert DATA_GAP_NO_BATTLE_PARTITIONS in out


def test_cli_census_mode_lists_runs(
    namespaces_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts.compare_battle_runs import main

    build_six_fixture(namespaces_root)
    code = main(["--census", "--store-root", str(namespaces_root)])
    out = capsys.readouterr().out
    assert code == 0
    assert "8 partition file(s) across 2 run(s)" in out
    assert RUN_A in out and RUN_B in out


def test_cli_requires_both_runs(
    namespaces_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts.compare_battle_runs import main

    code = main(["--run-a", RUN_A, "--store-root", str(namespaces_root)])
    assert code == 2
    assert "--run-a and --run-b are required" in capsys.readouterr().err
