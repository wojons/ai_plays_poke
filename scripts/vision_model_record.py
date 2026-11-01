#!/usr/bin/env python3
"""Capture one live frame and record grid predictions for configured models."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from perception_diff import capture, obs, ram_grid, vision_grid  # noqa: E402
from src.core.vision_grid import GRID_COLS, GRID_ROWS  # noqa: E402
from src.core.vision_model_registry import configured_vision_models  # noqa: E402


def _grid_from_ram(raw: str) -> list[str]:
    rows = [
        line.strip()
        for line in raw.splitlines()
        if line.strip()
        and len(line.strip()) == GRID_COLS
        and not line.strip().startswith(("Map:", "Pos:", "Legend:", "Unknown"))
    ][:GRID_ROWS]
    if len(rows) != GRID_ROWS:
        raise ValueError(f"RAM bridge returned {len(rows)} grid rows, expected 9")
    return rows


def record_models(
    output: Path, models: list[Any] | None = None
) -> list[dict[str, Any]]:
    """Capture once, make one vision call per model, and append measured rows."""
    selected = models if models is not None else configured_vision_models()
    if not selected:
        raise ValueError("no vision models are configured")

    observation = obs()
    png = capture("VISION_MODEL_SCORE")
    expected = _grid_from_ram(ram_grid(observation))
    records: list[dict[str, Any]] = []
    failures: list[str] = []
    for entry in selected:
        started = time.monotonic()
        try:
            predicted, response = vision_grid(png, model=entry.model)
            latency = time.monotonic() - started
            if len(predicted) != GRID_ROWS or any(
                len(row) != GRID_COLS for row in predicted
            ):
                shape = [len(row) for row in predicted if isinstance(row, str)]
                raise ValueError(
                    f"model response grid shape was {len(predicted)}x{shape}, expected 9x9"
                )
            usage = response.get("_usage", {})
            tokens = usage.get("total_tokens")
            if tokens is None and isinstance(usage, dict):
                tokens = int(usage.get("prompt_tokens", 0)) + int(
                    usage.get("completion_tokens", 0)
                )
            if tokens is None:
                raise ValueError("provider response omitted token usage")
            records.append(
                {
                    "model": entry.model,
                    "expected_grid": expected,
                    "predicted_grid": predicted,
                    "latency_seconds": latency,
                    "tokens": int(tokens),
                }
            )
        except Exception as exc:
            failures.append(f"{entry.model}: {type(exc).__name__}: {exc}")

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    for failure in failures:
        print(f"UNAVAILABLE {failure}", file=sys.stderr)
    print(f"RECORDED {len(records)} model(s); unavailable={len(failures)}")
    return records


def main() -> int:
    output = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else ROOT / "data/vision_model_runs.jsonl"
    )
    records = record_models(output)
    return 0 if records else 1


if __name__ == "__main__":
    raise SystemExit(main())
