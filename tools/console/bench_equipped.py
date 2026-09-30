"""Is the fast model unequipped? Test the thing Bane is actually worried about.

Two axes, both models, one frame:
  1. reads the grid?      - scored cell by cell against the reader's RAM grid
  2. sees the people?     - asked directly: who is on screen, where, and what do they look like

The second one is the point. Reading a 10x9 grid of terrain is pattern matching, and a small model can
be good enough at it. Knowing a sprite is a PERSON and which person it is needs semantic
understanding - and that is what Bane asked for ("being able to identify the people in the scene").
So measure both, and report the speed and the tokens next to them, not instead of them.

The old model is a reasoning model: it needs a big ceiling or it burns its whole budget thinking and
returns an empty string with no error. That is not slowness, it is a trap, so give it room.
"""

from __future__ import annotations

import base64
import io
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image

HOME = Path.home()
C = "http://127.0.0.1:8899"


def env(name, path):
    try:
        for line in Path(path).read_text(errors="replace").splitlines():
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


OR_KEY = env("OPENROUTER_API_KEY", HOME / "ai_plays_poke/.env")
SYN_KEY = env("SYNTHETIC_API_KEY", HOME / ".hermes/.env")

# a real frame, with the retry that a starved bridge needs
png = b""
for _ in range(8):
    try:
        with urllib.request.urlopen(
            f"{C}/api/frame.png?t={time.time()}", timeout=30
        ) as r:
            png = r.read()
    except Exception:
        png = b""
    if len(png) > 500:
        break
    time.sleep(1.5)
if len(png) < 500:
    raise SystemExit(f"no real frame ({len(png)} bytes)")
with urllib.request.urlopen(f"{C}/api/state", timeout=30) as r:
    st = json.loads(r.read())
ram = [x for x in (st.get("ram") or []) if x]
print(f"frame {len(png)} bytes; reader's grid {len(ram)}x{len(ram[0])}")
for row in ram:
    print("   ", row)

im = Image.open(io.BytesIO(png)).convert("RGB")
scale = min(6, max(1, 1024 // max(im.size)))
im = im.resize((im.width * scale, im.height * scale), Image.Resampling.LANCZOS)
buf = io.BytesIO()
im.save(buf, format="PNG")
b64 = base64.b64encode(buf.getvalue()).decode()
print(f"sent x{scale} -> {im.size[0]}x{im.size[1]}\n")

PROMPT = (
    "This is a Game Boy screen from Pokemon. Answer with exactly two sections.\n"
    "GRID: 10 columns x 9 rows, one character per cell - . floor, B blocking wall/furniture, "
    "T tree, G tall grass, W water, D doorway, N another person, $ a real thing with no other "
    "symbol, ? cannot tell. Use < > ^ v for the player's own cell. Exactly 9 lines of 10 characters.\n"
    "PEOPLE: list every PERSON visible (the player is one). For each give their grid cell as "
    "(column,row) counting from 0,0 at the top left, and what they look like - hair colour, "
    "clothing colour, which way they face. If there are no other people, say 'only the player'."
)

MODELS = [
    (
        "openai/gpt-4o-mini",
        "https://openrouter.ai/api/v1/chat/completions",
        OR_KEY,
        512,
    ),
    (
        "amazon/nova-lite-v1",
        "https://openrouter.ai/api/v1/chat/completions",
        OR_KEY,
        512,
    ),
    (
        "syn:large:vision (Kimi K3)",
        "https://api.synthetic.new/v1/chat/completions",
        SYN_KEY,
        65536,
    ),
]
GRIDCHARS = set(".BGWTDN $?0123456789<>^v\u2190\u2191\u2193\u2192")


def parse_grid(text):
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


for label, url, key, ceiling in MODELS:
    if not key:
        print(f"{label}: no key, skipped")
        continue
    body = json.dumps(
        {
            "model": label.split(" (")[0],
            "max_tokens": ceiling,
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
        url,
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    t0 = time.time()
    print(f"--- {label} ---", flush=True)
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            d = json.loads(r.read())
        dt = time.time() - t0
        msg = d["choices"][0]["message"]
        text = (msg.get("content") or "") + "\n" + str(msg.get("reasoning") or "")
        u = d.get("usage", {})
        grid = parse_grid(msg.get("content"))
        n = m = 0
        for i in range(min(len(grid), len(ram))):
            for j in range(min(len(grid[i]), len(ram[i]))):
                n += 1
                m += grid[i][j] == ram[i][j]
        print(
            f"  {dt:.2f}s   tokens in={u.get('prompt_tokens')} out={u.get('completion_tokens')}"
            f"   grid rows={len(grid)}   match={100 * m / n if n else 0:.1f}%"
        )
        for row in grid:
            print("     ", row)
        # the people section, verbatim - this is the part that needs real understanding
        pm = re.search(r"PEOPLE\s*:?\s*(.*)", text, re.S | re.I)
        print(
            "  PEOPLE answer:",
            (pm.group(1).strip()[:400] if pm else "(no PEOPLE section)"),
        )
    except urllib.error.HTTPError as e:
        print(
            f"  HTTP {e.code} after {time.time() - t0:.1f}s: {e.read().decode()[:200]}"
        )
    except Exception as e:
        print(f"  {type(e).__name__} after {time.time() - t0:.1f}s: {str(e)[:150]}")
    print(flush=True)
