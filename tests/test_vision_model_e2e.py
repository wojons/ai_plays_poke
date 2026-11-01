"""Live, two-model smoke test for selection, image reads, recording and scoring."""

from __future__ import annotations
import json
import os
import time
from pathlib import Path

import numpy as np
import pytest

from scripts.vision_model_score import score_grids, score_records
from src.core.vision_model_registry import configured_vision_models, parse_vision_models
from src.core.vision import VisionClient
from scripts import vision_model_record

ROOT = Path(__file__).resolve().parents[1]


def _load_repo_env() -> str | None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        env_path = Path("/home/kara/ai_plays_poke/.env")
    if not env_path.exists():
        return None
    repo_key: str | None = None
    for line in env_path.read_text().splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            parsed_key = key.strip()
            parsed_value = value.strip().strip("'\"")
            if parsed_key == "OPENROUTER_API_KEY":
                repo_key = parsed_value
            else:
                os.environ.setdefault(parsed_key, parsed_value)
    return repo_key


def test_record_and_score_path_uses_two_configured_models(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    models = parse_vision_models(
        json.dumps(
            [
                {"provider": "openrouter", "model": "openai/gpt-4o-mini"},
                {"provider": "openrouter", "model": "amazon/nova-lite-v1"},
            ]
        )
    )
    monkeypatch.setattr(vision_model_record, "obs", lambda: {"tick": 1})
    monkeypatch.setattr(
        vision_model_record, "capture", lambda _: tmp_path / "frame.png"
    )
    reference = ["........." for _ in range(9)]
    reference[2] = "..B......"
    monkeypatch.setattr(vision_model_record, "ram_grid", lambda _: "\n".join(reference))
    monkeypatch.setattr(
        vision_model_record,
        "vision_grid",
        lambda _frame, model: (
            reference if model == models[0].model else ["........." for _ in range(9)],
            {"_usage": {"total_tokens": 12}},
        ),
    )

    destination = tmp_path / "runs.jsonl"
    records = vision_model_record.record_models(destination, models)
    persisted = [json.loads(line) for line in destination.read_text().splitlines()]
    scores = score_records(persisted)

    assert [row["model"] for row in records] == [model.model for model in models]
    assert [row["model"] for row in persisted] == [model.model for model in models]
    assert len(scores) == 2
    assert scores[models[0].model]["structure_score"] == 100.0
    assert scores[models[1].model]["structure_score"] == 0.0
    assert all(row["tokens"] == 12 for row in persisted)


@pytest.mark.integration
def test_two_models_select_read_record_and_score(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_key = _load_repo_env()
    if repo_key:
        monkeypatch.setenv("OPENROUTER_API_KEY", repo_key)
    if not os.environ.get("OPENROUTER_API_KEY"):
        pytest.fail("OPENROUTER_API_KEY missing from environment and repository .env")
    models = configured_vision_models()
    if len(models) < 2:
        models = parse_vision_models(
            json.dumps(
                [
                    {"provider": "openrouter", "model": "openai/gpt-4o-mini"},
                    {"provider": "openrouter", "model": "amazon/nova-lite-v1"},
                ]
            )
        )
    assert len(models) >= 2
    models = models[:2]
    monkeypatch.setenv(
        "AIPP_VISION_MODELS",
        json.dumps(
            [{"provider": model.provider, "model": model.model} for model in models]
        ),
    )
    frame_path = ROOT / "play_frames/PG_6.png"
    if not frame_path.exists():
        pytest.fail(f"live vision test frame missing: {frame_path}")
    from PIL import Image

    image = np.asarray(Image.open(frame_path).convert("RGB"))
    # Keep each screenshot read to one API request; fail immediately rather than retrying.
    client = VisionClient()
    recorded: list[dict[str, object]] = []
    for model in models[:2]:
        started = time.monotonic()
        result = client.analyze(image, model=model.model)
        elapsed = time.monotonic() - started
        assert result.get("model") == model.model, (
            f"model read failed: {model.model} -> {result}"
        )
        recorded.append(
            {
                "model": model.model,
                "latency_seconds": elapsed,
                "usage": result.get("usage"),
                "result": result,
            }
        )
    output = tmp_path / "vision-recordings.json"
    output.write_text(json.dumps(recorded, indent=2))
    assert json.loads(output.read_text()) == recorded
    for item in recorded:
        usage = item["usage"]
        tokens = usage.get("total_tokens") if isinstance(usage, dict) else None
        print(
            f"LIVE_MEASURED model={item['model']} latency_seconds={item['latency_seconds']:.3f} tokens={tokens}"
        )

    # Scoring path is exercised against a labeled 9x9 calibration fixture;
    # live grid labels are not available from VisionClient's screen-state response.
    reference = ["........." for _ in range(9)]
    reference[2] = "..B......"
    reference[4] = "....2...."
    assert score_grids(reference, reference)["structure_score"] == 100.0
