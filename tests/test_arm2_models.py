"""ARM-2 runtime-selectable controller and hybrid-teacher models."""

from __future__ import annotations

import io
import json
from types import SimpleNamespace

import pytest

import cron_runner


@pytest.fixture(autouse=True)
def _clean_model_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        *cron_runner.CONTROLLER_MODEL_ENV_VARS,
        "AIPP_TEACHER_MODEL",
        "CRON_TEACHER_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)


def test_teacher_model_resolution_is_flag_then_env_then_controller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIPP_TEACHER_MODEL", "env/teacher")
    monkeypatch.setenv("CRON_TEACHER_MODEL", "secondary/teacher")

    assert (
        cron_runner.resolve_teacher_model("flag/teacher", "resolved/controller")
        == "flag/teacher"
    )
    assert (
        cron_runner.resolve_teacher_model(None, "resolved/controller") == "env/teacher"
    )

    monkeypatch.delenv("AIPP_TEACHER_MODEL")
    assert (
        cron_runner.resolve_teacher_model(None, "resolved/controller")
        == "secondary/teacher"
    )
    monkeypatch.delenv("CRON_TEACHER_MODEL")
    assert (
        cron_runner.resolve_teacher_model(None, "resolved/controller")
        == "resolved/controller"
    )


def test_teacher_and_controller_model_choices_are_independent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CRON_CONTROLLER_MODEL", "controller/model")
    monkeypatch.setenv("AIPP_TEACHER_MODEL", "teacher/model")

    controller = cron_runner.resolve_controller_model()
    teacher = cron_runner.resolve_teacher_model(None, controller)

    assert controller == "controller/model"
    assert teacher == "teacher/model"
    assert controller != teacher


def test_parser_accepts_teacher_model_override() -> None:
    args = cron_runner._main_parser().parse_args(
        [
            "--decision-mode",
            "jev",
            "--controller-model",
            "controller/model",
            "--teacher-model",
            "teacher/model",
        ]
    )

    assert args.controller_model == "controller/model"
    assert args.teacher_model == "teacher/model"


def test_hybrid_teacher_uses_independent_runtime_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_jev_or_none(*_args: object, **kwargs: object) -> None:
        captured.update(kwargs)
        return None

    monkeypatch.setattr(cron_runner, "_jev_or_none", fake_jev_or_none)
    objective = SimpleNamespace(
        decision_text=lambda: "reach route", projection=lambda: {}
    )
    state = SimpleNamespace(
        _navigation_state=SimpleNamespace(
            objective_state=objective,
            visited_maps=(),
        ),
        _tile_visits={},
        results=[],
        _recent_decisions=[],
        _last_direction=None,
        _same_tile_count=0,
        R=SimpleNamespace(
            controller_client=object(),
            controller_model="controller/model",
            teacher_model="teacher/model",
        ),
        _boot_memory="",
        log_file=io.StringIO(),
        _teacher_class_repairs={},
        _teacher_budget={"used": 0},
        _memory_navigation_blocks=cron_runner._MemoryNavigationBlockState(),
    )

    cron_runner._ow_jev_attempt(
        state,
        {
            "patch_data": {"map_name": "Pallet Town"},
            "world_facts": [],
            "cycle": 0,
        },
    )

    assert captured["teacher_model"] == "teacher/model"
    assert state.R.controller_model == "controller/model"


def test_run_autonomy_row_records_both_effective_models() -> None:
    buffer = io.StringIO()

    row = cron_runner._write_autonomy_row(
        buffer,
        "arm2",
        cron_runner._autonomy_counters([]),
        controller_model="controller/model",
        teacher_model="teacher/model",
    )

    assert row["controller_model"] == "controller/model"
    assert row["teacher_model"] == "teacher/model"
    assert json.loads(buffer.getvalue())["teacher_model"] == "teacher/model"
