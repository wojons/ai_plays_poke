#!/usr/bin/env python3
"""Convert a run's screenshot sequence into a review video (MP4).

Burns in a HUD overlay (cycle #, screen type, action taken) using an ASS
subtitle track, upscales the 160x144 Game Boy frames 4x with nearest-
neighbor (crisp pixels), and encodes with libx264.

Usage:
    ./venv/bin/python make_run_video.py <run_id> [--fps 2] [--out dir]

Examples:
    ./venv/bin/python make_run_video.py run_starter_20260802_1440
    ./venv/bin/python make_run_video.py run_luna_v10_20260802_0515

The run_id is the part AFTER the first "run_" prefix in the log filename
(cron_logs/run_<run_id>.jsonl) and the screenshot dir name
(screenshots/run_<run_id>/step_XXXX.png).
"""

import argparse
from dataclasses import dataclass
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

BASE = Path(__file__).parent
SHOTS = BASE / "screenshots"
LOGS = BASE / "cron_logs"
OUT_DIR = BASE / "videos"

FRAME_W, FRAME_H = 160, 144
SCALE = 4
OUT_W, OUT_H = FRAME_W * SCALE, FRAME_H * SCALE
_STEP_RE = re.compile(r"^step_(\d+)\.png$")


@dataclass(frozen=True)
class StepFrame:
    """A saved progress frame and the original run cycle it represents."""

    cycle: int
    path: Path


def find_screenshot_dir(run_id: str) -> Path | None:
    """Screenshot dir is screenshots/run_<run_id> (some runs double-prefix)."""
    cands = [
        SHOTS / f"run_{run_id}",
        SHOTS / run_id,
    ]
    for c in cands:
        if c.is_dir() and any(c.glob("*.png")):
            return c
    return None


def select_step_frames(shot_dir: Path) -> list[StepFrame]:
    """Return exact ``step_N.png`` files ordered by their cycle number."""
    frames: list[StepFrame] = []
    for path in shot_dir.glob("step_*.png"):
        match = _STEP_RE.fullmatch(path.name)
        if match is not None:
            frames.append(StepFrame(cycle=int(match.group(1)), path=path))
    return sorted(frames, key=lambda frame: frame.cycle)


def load_log(run_id: str) -> list[dict[str, Any]]:
    """Load log entries for the run (best-effort; missing log → empty)."""
    for name in (f"run_{run_id}.jsonl", f"{run_id}.jsonl"):
        p = LOGS / name
        if p.exists():
            entries = []
            with open(p) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
            return entries
    return []


def _srt_time(seconds: float) -> str:
    """Format seconds as SRT timestamp HH:MM:SS,mmm."""
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt(entries: list[dict[str, Any]], cycles: list[int], fps: float) -> str:
    """Build subtitles for saved frames, retaining their actual cycle numbers.

    Frame position determines video time, while ``cycles`` maps each selected
    ``step_N.png`` back to cycle N. Gaps therefore neither stop ffmpeg input nor
    shift later HUD/log entries onto the wrong frame.
    """
    by_cycle: dict[int, dict[str, Any]] = {}
    for e in entries:
        c = e.get("cycle")
        if c is not None:
            by_cycle[int(c)] = e

    def fmt_entry(e: dict[str, Any]) -> str:
        screen = str(e.get("screen") or e.get("state") or "?")
        action = ""
        if e.get("plan"):
            action = " -> ".join(str(a) for a in e["plan"][:6])
        elif e.get("action"):
            action = str(e["action"])[:60]
        elif e.get("event"):
            action = f"EVENT {e['event']}"
            if e.get("species_hint"):
                action += f" -- {e['species_hint']}"
        elif e.get("strategy"):
            action = f"RECOVERY: {e['strategy']} ({e.get('reason', '')})"
        intent = str(e.get("intent") or "")[:70]
        line = f"{screen}"
        if action:
            line += f" | {action}"
        if intent:
            line += f" | {intent}"
        return line

    dur = 1.0 / fps
    parts = []
    for i, cycle in enumerate(cycles):
        entry = by_cycle.get(cycle)
        text = f"Cycle {cycle}"
        if entry:
            text += f"  {fmt_entry(entry)}"
        text = text.replace("\n", " ")
        start = _srt_time(i * dur)
        end = _srt_time((i + 1) * dur)
        parts.append(f"{i + 1}\n{start} --> {end}\n{text}\n")
    return "\n".join(parts)


def _ffconcat_path(path: Path) -> str:
    """Quote an absolute path for an ffconcat ``file`` directive."""
    return str(path.resolve()).replace("'", "'\\''")


def write_concat_manifest(
    frames: list[StepFrame], manifest_path: Path, fps: float
) -> None:
    """Write an ffconcat manifest that preserves the selected frame ordering."""
    if not frames:
        raise ValueError("cannot write an empty frame manifest")
    duration = 1.0 / fps
    lines = ["ffconcat version 1.0"]
    for frame in frames:
        lines.append(f"file '{_ffconcat_path(frame.path)}'")
        lines.append(f"duration {duration:.12g}")
    # The concat demuxer ignores the final file's duration unless another file
    # follows it. Repeat the final path; ``-frames:v`` caps output to the real
    # selected-frame count, so this packet supplies timing without an extra frame.
    lines.append(f"file '{_ffconcat_path(frames[-1].path)}'")
    manifest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_video(run_id: str, fps: float, force: bool = False) -> Path | None:
    shot_dir = find_screenshot_dir(run_id)
    if shot_dir is None:
        print(f"[ERR] No screenshots for run '{run_id}'")
        return None

    frames = select_step_frames(shot_dir)
    if not frames:
        print(f"[ERR] No step_*.png in {shot_dir}")
        return None

    OUT_DIR.mkdir(exist_ok=True)
    out_path = OUT_DIR / f"{run_id}.mp4"
    if out_path.exists() and not force:
        print(f"[SKIP] {out_path.name} exists (use --force to rebuild)")
        return out_path

    if not shutil.which("ffmpeg"):
        print("[ERR] ffmpeg not found on PATH")
        return None

    entries = load_log(run_id)
    cycles = [frame.cycle for frame in frames]
    srt_text = build_srt(entries, cycles, fps)
    srt_path = OUT_DIR / f"{run_id}.srt"
    srt_path.write_text(srt_text, encoding="utf-8")
    manifest_path = OUT_DIR / f".{run_id}.frames.ffconcat"
    write_concat_manifest(frames, manifest_path, fps)

    # ffmpeg: concat the explicitly selected files (step numbers may be gapped),
    # scale 4x nearest-neighbor, and burn the cycle-aligned SRT HUD overlay.
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        manifest_path.name,
        "-vf",
        f"scale={OUT_W}:{OUT_H}:flags=neighbor,subtitles={srt_path.name}",
        "-frames:v",
        str(len(frames)),
        "-fps_mode",
        "vfr",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        str(out_path),
    ]
    print(f"[RUN] {len(frames)} frames → {out_path.name} @ {fps}fps")
    try:
        res = subprocess.run(cmd, cwd=OUT_DIR, capture_output=True, text=True)
    finally:
        manifest_path.unlink(missing_ok=True)
    if res.returncode != 0:
        print("[FFMPEG ERR]", res.stderr[-500:])
        return None
    size_kb = out_path.stat().st_size // 1024
    print(
        f"[OK] {out_path.name} ({size_kb} KB, {len(frames)} frames, "
        f"{len(frames) / fps:.0f}s)"
    )
    return out_path


def main() -> None:
    ap = argparse.ArgumentParser(description="Make review video from run screenshots")
    ap.add_argument("run_id", help="run id (after first run_ prefix)")
    ap.add_argument(
        "--fps", type=float, default=2.0, help="frames per second (default 2)"
    )
    ap.add_argument("--force", action="store_true", help="rebuild existing video")
    args = ap.parse_args()
    out = make_video(args.run_id, args.fps, args.force)
    if out is None:
        sys.exit(1)


if __name__ == "__main__":
    main()
