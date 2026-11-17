"""Coverage for ordered vision model registry configuration."""

from __future__ import annotations

import json

import pytest

from src.core.vision_model_registry import (
    configured_vision_models,
    parse_vision_models,
)
from scripts.vision_model_score import score_grids
from src.core.vision_grid import GRID_COLS, GRID_ROWS


def test_parses_ordered_provider_model_pairs() -> None:
    entries = parse_vision_models(
        json.dumps(
            [
                {"provider": "openrouter", "model": "openai/gpt-4o-mini"},
                {"provider": "openrouter", "model": "google/gemma-3-12b-it"},
            ]
        )
    )
    assert [(entry.provider, entry.model) for entry in entries] == [
        ("openrouter", "openai/gpt-4o-mini"),
        ("openrouter", "google/gemma-3-12b-it"),
    ]


def test_legacy_single_model_environment_becomes_one_entry() -> None:
    entries = configured_vision_models({"AIPP_VISION_MODEL": "legacy/model"})
    assert [(entry.provider, entry.model) for entry in entries] == [
        ("openrouter", "legacy/model")
    ]


def test_per_run_model_selection_is_recorded_and_printed(monkeypatch, capsys) -> None:
    import numpy as np

    from src.core import vision

    monkeypatch.setenv(
        "AIPP_VISION_MODELS",
        '[{"provider":"openrouter","model":"model/first"},'
        '{"provider":"openrouter","model":"model/second"}]',
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(vision, "OpenRouterClient", lambda **_: _FakeOpenRouter())
    client = vision.VisionClient()
    result = client.analyze(
        np.zeros((144, 160, 3), dtype=np.uint8), model="model/second"
    )
    assert result["model"] == "model/second"
    assert "model/second" in capsys.readouterr().out


class _FakeOpenRouter:
    def chat_completion(self, **kwargs):
        assert kwargs["model"] == "model/second"
        return {"content": '{"screen_type":"overworld"}', "usage": {}}


@pytest.mark.parametrize("raw", ["{}", "[]", "not json", '[{"model":"x"}'])
def test_rejects_invalid_registry(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_vision_models(raw)


def test_structure_score_demotes_all_floor_answer() -> None:
    # Fixture geometry comes from the one definition (10x9): a 9-wide row would be
    # rejected by score_grids, which is the geometry defect this suite guards.
    expected = ["." * GRID_COLS for _ in range(GRID_ROWS)]
    expected[2] = "..B" + "." * (GRID_COLS - 3)
    expected[4] = "....2" + "." * (GRID_COLS - 5)
    all_floor = ["." * GRID_COLS for _ in range(GRID_ROWS)]
    accurate = expected.copy()

    lazy = score_grids(expected, all_floor)
    careful = score_grids(expected, accurate)

    assert lazy["total_score"] > 95.0
    assert lazy["structure_score"] == 0.0
    assert careful["structure_score"] == 100.0
    assert careful["structure_score"] > lazy["structure_score"]
