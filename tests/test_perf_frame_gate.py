"""Regression tests for PERF-1 frame-save and video gap handling."""

from __future__ import annotations

import json
from pathlib import Path
import shutil

import numpy as np
from PIL import Image
import pytest

import cron_runner
import make_run_video


def _frame(value: int) -> np.ndarray:
    return np.full((4, 5, 3), value, dtype=np.uint8)


def test_cycle_screenshot_gate_saves_identical_frame_once(tmp_path: Path) -> None:
    screenshot = _frame(7)
    frame_hash = cron_runner._cycle_frame_hash(screenshot)
    last_saved_hash = ""

    for cycle in (1, 2):
        last_saved_hash = cron_runner._save_cycle_screenshot(
            Image.fromarray(screenshot),
            cycle=cycle,
            frame_hash=frame_hash,
            last_saved_frame_hash=last_saved_hash,
            screenshot_dir=tmp_path,
        )

    assert [path.name for path in tmp_path.glob("step_*.png")] == ["step_0001.png"]


def test_cycle_screenshot_gate_saves_changed_frame(tmp_path: Path) -> None:
    last_saved_hash = ""
    for cycle, screenshot in enumerate((_frame(7), _frame(8)), start=1):
        frame_hash = cron_runner._cycle_frame_hash(screenshot)
        last_saved_hash = cron_runner._save_cycle_screenshot(
            Image.fromarray(screenshot),
            cycle=cycle,
            frame_hash=frame_hash,
            last_saved_frame_hash=last_saved_hash,
            screenshot_dir=tmp_path,
        )

    assert [path.name for path in sorted(tmp_path.glob("step_*.png"))] == [
        "step_0001.png",
        "step_0002.png",
    ]


def test_gapped_step_files_drive_selection_and_srt_cycles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shots = tmp_path / "shots"
    logs = tmp_path / "logs"
    shots.mkdir()
    logs.mkdir()
    for name in ("step_0001.png", "step_0003.png", "step_bad.png"):
        (shots / name).write_bytes(b"png")

    log_rows = [
        {"cycle": 1, "screen": "overworld", "action": "UP"},
        {"cycle": 2, "screen": "dialog", "action": "A"},
        {"cycle": 3, "screen": "battle", "action": "B"},
    ]
    (logs / "run_gap.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in log_rows), encoding="utf-8"
    )
    monkeypatch.setattr(make_run_video, "LOGS", logs)

    frames = make_run_video.select_step_frames(shots)
    assert [(frame.cycle, frame.path.name) for frame in frames] == [
        (1, "step_0001.png"),
        (3, "step_0003.png"),
    ]

    entries = make_run_video.load_log("gap")
    srt = make_run_video.build_srt(entries, [frame.cycle for frame in frames], 2.0)
    assert "Cycle 1  overworld | UP" in srt
    assert "Cycle 2" not in srt
    assert "Cycle 3  battle | B" in srt
    assert "2\n00:00:00,500 --> 00:00:01,000\nCycle 3" in srt

    concat_path = tmp_path / "frames.ffconcat"
    make_run_video.write_concat_manifest(frames, concat_path, 2.0)
    manifest = concat_path.read_text(encoding="utf-8")
    assert "step_0001.png" in manifest
    assert "step_0003.png" in manifest
    assert "step_0002.png" not in manifest


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")
def test_make_video_encodes_gapped_step_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shots_root = tmp_path / "screenshots"
    shot_dir = shots_root / "run_encode-gap"
    logs = tmp_path / "logs"
    out_dir = tmp_path / "videos"
    shot_dir.mkdir(parents=True)
    logs.mkdir()
    for cycle, value in ((1, 20), (4, 180)):
        Image.fromarray(np.full((144, 160, 3), value, dtype=np.uint8)).save(
            shot_dir / f"step_{cycle:04d}.png"
        )
    (logs / "run_encode-gap.jsonl").write_text(
        '{"cycle": 1, "screen": "overworld"}\n{"cycle": 4, "screen": "battle"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(make_run_video, "SHOTS", shots_root)
    monkeypatch.setattr(make_run_video, "LOGS", logs)
    monkeypatch.setattr(make_run_video, "OUT_DIR", out_dir)

    result = make_run_video.make_video("encode-gap", fps=2.0)

    assert result == out_dir / "encode-gap.mp4"
    assert result is not None and result.stat().st_size > 0
    assert not (out_dir / ".encode-gap.frames.ffconcat").exists()
    assert "Cycle 4  battle" in (out_dir / "encode-gap.srt").read_text(encoding="utf-8")
