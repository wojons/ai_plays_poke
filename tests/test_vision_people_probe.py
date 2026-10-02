"""Focused tests for the RAM-cell people vision probe."""

from __future__ import annotations

from scripts.vision_people_probe import (
    Prediction,
    SPRITE_TABLE,
    TruthPerson,
    parse_predictions,
    score_predictions,
    visible_people,
)


def _reader(values: dict[int, int]):
    return lambda address: values.get(address, 0)


def _sprite(
    values: dict[int, int],
    slot: int,
    *,
    sprite_id: int,
    x: int,
    y: int,
    facing: int = 0,
) -> None:
    base = SPRITE_TABLE + slot * 16
    values[base] = sprite_id
    values[base + 4] = y
    values[base + 6] = x
    values[base + 9] = facing


def test_visible_people_uses_player_relative_9x9_cells_and_filters_objects() -> None:
    memory = {
        SPRITE_TABLE + 4: 60,
        SPRITE_TABLE + 6: 64,
    }
    _sprite(memory, 1, sprite_id=0x0D, x=16, y=78, facing=0x04)
    _sprite(memory, 2, sprite_id=0x3D, x=64, y=76)
    _sprite(memory, 3, sprite_id=0x03, x=48, y=140, facing=0x0C)
    _sprite(memory, 4, sprite_id=0x02, x=240, y=240)

    people = visible_people(_reader(memory))

    assert [(person.sprite_name, person.cell, person.facing) for person in people] == [
        ("girl", (1, 4), "up"),
        ("oak", (3, 8), "right"),
    ]


def test_parse_predictions_requires_name_cell_and_feature() -> None:
    raw = """```json
    {"people":[
      {"name":"girl","cell":[1,4],"feature":"facing up"},
      {"name":"","cell":[2,4],"feature":"dark hair"},
      {"name":"man","cell":[9,4],"feature":"hat"}
    ]}
    ```"""

    predictions, errors = parse_predictions(raw)

    assert predictions == [Prediction("girl", (1, 4), "facing up")]
    assert errors == [
        "people[1] had no name",
        "people[2] cell (9, 4) was outside the 9x9 window",
    ]


def test_score_reports_wrong_cell_missed_and_hallucinated_people() -> None:
    truths = [
        TruthPerson(1, 0x0D, "girl", (1, 4), "up"),
        TruthPerson(2, 0x03, "oak", (3, 8), "right"),
    ]
    predictions = [
        Prediction("girl", (2, 4), "dark hair"),
        Prediction("boy", (7, 2), "cap"),
        Prediction("extra", (8, 8), "coat"),
    ]

    score = score_predictions(truths, predictions)

    assert score.correct is False
    assert score.matched == 0
    assert score.failures == (
        "wrong cell for girl: model (2, 4), RAM (1, 4) (girl)",
        "wrong cell for extra: model (8, 8), RAM (3, 8) (oak)",
        "hallucinated boy at (7, 2)",
    )


def test_facing_conflict_is_diagnostic_but_cell_score_stays_correct() -> None:
    truths = [TruthPerson(1, 0x0D, "girl", (1, 4), "up")]
    predictions = [Prediction("girl", (1, 4), "facing down")]

    score = score_predictions(truths, predictions)

    assert score.correct is True
    assert score.matched == 1
    assert score.failures == ()
    assert score.feature_notes == (
        "wrong feature at (1, 4): model down, RAM facing up (not scored)",
    )


def test_empty_people_is_correct_only_when_ram_is_also_empty() -> None:
    assert score_predictions([], []).correct is True
    assert score_predictions(
        [TruthPerson(1, 0x0D, "girl", (1, 4), "up")], []
    ).failures == ("missed person at (1, 4) (girl)",)
