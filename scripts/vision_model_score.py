"""Score vision grid recordings against the RAM/reference grid.

Usage: python scripts/vision_model_score.py [recordings.jsonl]
Each JSONL row has model, expected_grid, predicted_grid, latency_seconds, tokens.
"""

from __future__ import annotations
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.core.vision_grid import GRID_COLS, GRID_ROWS  # noqa: E402


def _valid_grid(grid: list[str]) -> bool:
    return len(grid) == GRID_ROWS and all(len(row) == GRID_COLS for row in grid)


def _class(cell: str) -> str:
    if cell == ".":
        return "floor"
    if cell == "B":
        return "blocked"
    if cell.isdigit():
        return "object"
    return "unknown"


def score_grids(expected: list[str], predicted: list[str]) -> dict[str, float | int]:
    """Return total-cell and non-floor/non-unknown exact class agreement."""
    if not _valid_grid(expected) or not _valid_grid(predicted):
        raise ValueError("expected and predicted grids must both be 9x9")
    cells = [
        (truth, guess)
        for erow, prow in zip(expected, predicted)
        for truth, guess in zip(erow, prow)
    ]
    total_correct = sum(_class(truth) == _class(guess) for truth, guess in cells)
    structure = [(truth, guess) for truth, guess in cells if truth not in ".?"]
    structure_correct = sum(
        _class(truth) == _class(guess) for truth, guess in structure
    )
    return {
        "total_score": 100.0 * total_correct / len(cells),
        "total_cells": len(cells),
        "structure_score": 100.0 * structure_correct / len(structure)
        if structure
        else 0.0,
        "structure_cells": len(structure),
    }


def score_records(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        result = score_grids(record["expected_grid"], record["predicted_grid"])
        result.update(
            {key: record[key] for key in ("latency_seconds", "tokens") if key in record}
        )
        grouped[str(record["model"])].append(result)
    return {
        model: {
            "total_score": sum(float(row["total_score"]) for row in rows) / len(rows),
            "structure_score": sum(float(row["structure_score"]) for row in rows)
            / len(rows),
            "latency_seconds": sum(float(row["latency_seconds"]) for row in rows)
            / len(rows)
            if all("latency_seconds" in row for row in rows)
            else None,
            "tokens": sum(int(row["tokens"]) for row in rows)
            if all("tokens" in row for row in rows)
            else None,
            "samples": len(rows),
        }
        for model, rows in grouped.items()
    }


def main() -> int:
    source = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else ROOT / "data/vision_model_runs.jsonl"
    )
    records = (
        [json.loads(line) for line in source.read_text().splitlines() if line.strip()]
        if source.exists()
        else []
    )
    scores = score_records(records)
    if not scores:
        print(
            "No recorded grid comparisons; total-score and structure-score are unmeasured."
        )
        return 0
    for model, score in scores.items():
        print(
            f"{model}: total={score['total_score']:.1f}% structure={score['structure_score']:.1f}% samples={score['samples']} latency_s={score['latency_seconds']} tokens={score['tokens']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
