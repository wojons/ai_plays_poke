#!/usr/bin/env python3
"""Run the spatial-blueprint vision prompt on a frame and compare with RAM.

Usage: python scripts/vision_blueprint_probe.py <frame.png> [--no-ram] [--no-mask]

Reads the prompt from prompts/exploration/vision_map_blueprint.md (everything after the
first '---' line), sends the frame to the vision model, and prints the returned grid
beside the RAM reader's overworld_grid for the same instant.

Also computes a deterministic black mask: a cell that is mostly black cannot be
identified as anything, so it is '?' regardless of what the model claims. Black
detection is arithmetic on pixels, not a vision task.
"""

from __future__ import annotations

import base64
import json
import os
import re
import socket
import sys
from pathlib import Path
from typing import Any, cast

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

# load .env (key never printed)
env = REPO / ".env"
if env.exists():
    for line in env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from src.core.ai_client import OpenRouterClient  # noqa: E402


def load_prompt() -> str:
    text = (REPO / "prompts/exploration/vision_map_blueprint.md").read_text()
    parts = text.split("\n---\n", 1)
    return parts[1].strip() if len(parts) > 1 else text


def parse_json(raw: str) -> dict[str, Any] | None:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return None
    try:
        return cast(dict[str, Any], json.loads(m.group(0)))
    except json.JSONDecodeError:
        return None


def ram_view() -> dict[str, Any]:
    tok = Path.home().joinpath(".hermes/aipp_bridge/session.token").read_text().strip()
    s = socket.create_connection(("127.0.0.1", 8770), timeout=30)
    s.sendall((json.dumps({"cmd": "raw", "token": tok}) + "\n").encode())
    obs = json.loads(s.recv(65536).decode().strip())["obs"]
    s.close()
    return cast(dict[str, Any], obs)


def black_mask(png: Path, cols: int, rows: int, thresh: float = 0.55) -> list[str]:
    """Deterministically mark cells that are mostly black as '?'.

    A cell that is >= thresh black cannot be identified as anything, so it is '?'
    no matter what the model says. This is arithmetic on pixels, not a vision task.
    """
    from PIL import Image

    im = Image.open(png).convert("L")
    w, h = im.size
    cw, ch = w / cols, h / rows
    out: list[str] = []
    for r in range(rows):
        row = ""
        for c in range(cols):
            box = im.crop(
                (int(c * cw), int(r * ch), int((c + 1) * cw), int((r + 1) * ch))
            )
            hist = box.histogram()
            black = sum(hist[:60])
            total = sum(hist)
            frac = black / total if total else 0.0
            row += "?" if frac >= thresh else "."
        out.append(row)
    return out


def main() -> int:
    frame = Path(sys.argv[1])
    if not frame.exists():
        print(f"no such frame: {frame}", file=sys.stderr)
        return 2

    client = OpenRouterClient(api_key=os.environ["OPENROUTER_API_KEY"])
    prompt = load_prompt()
    b64 = base64.b64encode(frame.read_bytes()).decode()

    print(f"frame : {frame.name}  ({frame.stat().st_size} bytes)")
    print(
        f"prompt: {len(prompt)} chars from prompts/exploration/vision_map_blueprint.md"
    )
    print("calling vision model ...", flush=True)
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64}"},
                },
            ],
        }
    ]
    res = client.chat_completion(
        model="openai/gpt-5.6-luna",
        messages=messages,
        max_tokens=9000,
        temperature=0.1,
    )
    raw = res.get("content")
    print(f"finish_reason: {res.get('finish_reason')!r}")
    if raw is None:
        print("!! content was null — model produced no final answer")
        return 1
    print(f"raw response ({len(raw)} chars):\n{raw}\n")

    got = parse_json(raw)
    if got is None:
        print("!! could not parse JSON from the response")
        return 1

    cols = int(got.get("width") or 10)
    rows = int(got.get("height") or 9)
    grid = [str(r) for r in got.get("grid", [])]

    print("=== VISION GRID (blueprint format) ===")
    print(f"  space  : {got.get('space')!r}")
    print(f"  size   : {cols}x{rows}")
    print(f"  player : {got.get('player_cell')} facing {got.get('facing')}")
    for row in grid:
        print(f"    {row}")
    print(f"  legend : {json.dumps(got.get('legend'))}")
    print(
        f"  '?'s   : {got.get('undetermined_cells')}  confidence {got.get('confidence')}"
    )

    if "--no-mask" not in sys.argv:
        mask = black_mask(frame, cols, rows)
        forced = 0
        merged = []
        for r, mrow in enumerate(mask):
            grow = grid[r] if r < len(grid) else "." * cols
            out = ""
            for c, mch in enumerate(mrow):
                gch = grow[c] if c < len(grow) else "?"
                if mch == "?" and gch != "?":
                    out += "?"
                    forced += 1
                else:
                    out += gch
            merged.append(out)
        print("\n=== BLACK MASK (computed from pixels, not the model) ===")
        for row in mask:
            print(f"    {row}")
        print(f"  cells forced to '?' that the model had filled in: {forced}")
        print("\n=== MERGED (model's objects + deterministic '?' where black) ===")
        for row in merged:
            print(f"    {row}")
        print(
            f"  model claimed {got.get('undetermined_cells')} unknown; "
            f"pixels say {sum(r.count('?') for r in mask)}; merged {sum(r.count('?') for r in merged)}"
        )

    if "--no-ram" not in sys.argv:
        try:
            o = ram_view()
            print("\n=== RAM GRID (same instant) ===")
            for line in (o.get("overworld_grid") or "").split("\n"):
                print(f"    {line}")
        except Exception as e:  # noqa: BLE001
            print(f"\n(RAM unavailable: {e})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
