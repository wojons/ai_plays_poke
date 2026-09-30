#!/usr/bin/env python3
"""The accuracy comparison: which fast model actually READS the screen?

Speed and cost are settled (nova-lite 0.79s / 58 tokens against the current model's 187s / 0 rows at a
4k cap). What is still unmeasured is ACCURACY, and a fast wrong answer is worse than a slow right one.

Two corrections from the run that produced all-400s: fetch the frame with a retry and VALIDATE its
size before sending (an empty base64 was being posted, which the API rejects), and skip the current
model as a baseline - its behaviour is already characterised (187s, 0 rows at 4k) and it would add
three minutes to every pass for no new information.

Scoring is against the reader's RAM grid, cell by cell. Stated plainly: the RAM grid is a REFERENCE,
not truth - its terrain labels measured 83.6% against ROM collision. So the score answers 'reads the
screen the way the reader does', which is the property a cell-by-cell verdict depends on.
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image

HOME = Path.home()
C = "http://127.0.0.1:8899"


def env(name: str, path: Path) -> str:
    try:
        for line in path.read_text(errors="replace").splitlines():
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


KEY = env("OPENROUTER_API_KEY", HOME / "ai_plays_poke/.env")

# load check first: benchmarks belong on a calm box
la = os.getloadavg()
print(f"load average: {la[0]:.1f} / {la[1]:.1f} / {la[2]:.1f}")
if la[0] > 40 and os.environ.get("AIPP_IGNORE_LOAD") != "1":
    print("  box is busy - results would be timing noise. Re-run when calm.")
    raise SystemExit(0)
if la[0] > 40:
    # Accuracy is unaffected by local load: the model runs remotely, only the wall-clock is noise.
    print(
        "  box is busy - TREAT THE LATENCY COLUMN AS NOISE, the match % is still valid"
    )

# frame, with a retry and a size check (an empty image is what caused the earlier 400s)
png = b""
for attempt in range(6):
    try:
        with urllib.request.urlopen(
            f"{C}/api/frame.png?t={time.time()}", timeout=30
        ) as r:
            png = r.read()
    except Exception:
        png = b""
    if len(png) > 500:
        break
    print(f"  frame attempt {attempt + 1}: only {len(png)} bytes, retrying")
    time.sleep(1.5)
if len(png) < 500:
    raise SystemExit(
        f"could not get a real frame (last {len(png)} bytes) - bridge likely starved"
    )

with urllib.request.urlopen(f"{C}/api/state", timeout=30) as r:
    st = json.loads(r.read())
ram = [row for row in (st.get("ram") or []) if row]
print(f"frame {len(png)} bytes; reference grid {len(ram)}x{len(ram[0]) if ram else 0}")
for row in ram:
    print("   ", row)

im = Image.open(io.BytesIO(png)).convert("RGB")
scale = min(6, max(1, 1024 // max(im.size)))
big = im.resize((im.width * scale, im.height * scale), Image.Resampling.LANCZOS)
buf = io.BytesIO()
big.save(buf, format="PNG")
png_sent = buf.getvalue()
b64 = base64.b64encode(png_sent).decode()
print(
    f"sent upscaled x{scale} -> {big.size[0]}x{big.size[1]} ({len(png_sent)} bytes)",
    flush=True,
)

PROMPT = (
    "Report this Game Boy screen as a grid of 10 columns by 9 rows. One character per cell: "
    ". floor you can walk on, B blocking structure or furniture, T tree, G tall grass, W water, "
    "D doorway, N another person, ? unknown, and use an arrow for the player's own cell. "
    "Answer with 9 lines of exactly 10 characters, nothing else."
)
GRIDCHARS = set(".BGWTDN $?0123456789\u2190\u2191\u2193\u2192")
MODELS = [
    "amazon/nova-lite-v1",
    "qwen/qwen3-vl-32b-instruct",
    "mistralai/mistral-small-3.2-24b-instruct",
    "openai/gpt-4o-mini",
    "anthropic/claude-haiku-4.5",
]


def parse(text: str) -> list[str]:
    rows = []
    for line in (text or "").splitlines():
        s = line.strip()
        m = re.match(r"^ROW\s*\d\s*[:.]\s*(.+)$", s, re.I)
        if m:
            s = m.group(1)
        s = s.strip().replace(" ", "")
        if len(s) >= 8 and set(s) <= GRIDCHARS:
            rows.append(s[:10])
    return rows[:9]


def score(grid: list[str]) -> tuple[int, int]:
    n = m = 0
    for r in range(min(len(grid), len(ram))):
        for c in range(min(len(grid[r]), len(ram[r]))):
            n += 1
            if grid[r][c] == ram[r][c]:
                m += 1
    return n, m


print("\n=== accuracy vs speed, same upscaled frame ===", flush=True)
out = []
for model in MODELS:
    body = json.dumps(
        {
            "model": model,
            "max_tokens": 300,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"},
                        },
                    ],
                }
            ],
        }
    ).encode()
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.loads(r.read())
        dt = time.time() - t0
        grid = parse(d["choices"][0]["message"].get("content"))
        n, m = score(grid)
        pct = 100 * m / n if n else 0
        out.append(
            (pct, dt, model, n, d.get("usage", {}).get("completion_tokens"), grid)
        )
        print(
            f"  {model:44s} {dt:5.2f}s  match {pct:5.1f}%  ({m}/{n} cells)  "
            f"toks={d.get('usage', {}).get('completion_tokens')}",
            flush=True,
        )
        for line in grid[:3]:
            print(f"        {line}", flush=True)
    except urllib.error.HTTPError as e:
        print(f"  {model:44s} HTTP {e.code}: {e.read().decode()[:90]}", flush=True)
    except Exception as e:
        print(f"  {model:44s} {type(e).__name__}: {str(e)[:80]}", flush=True)

print("\n=== ranked: accuracy first, speed beside it ===")
for pct, dt, model, n, toks, _ in sorted(out, key=lambda x: (-x[0], x[1])):
    print(f"  {pct:5.1f}%  {dt:5.2f}s  {model:44s} cells={n} toks={toks}")
print("\n  reference grid for comparison:\n    " + "\n    ".join(ram))
