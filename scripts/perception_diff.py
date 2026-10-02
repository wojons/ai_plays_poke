#!/usr/bin/env python3
"""Diff the two channels cell-by-cell on ONE frame, in the one shared 9x9 grid.

This is the check that makes every other perception claim cheap to re-verify: RAM and
vision are asked for the same window (9x9, player at the middle cell 4,4), so cell (c,r)
means the same thing on both sides and the two grids can be subtracted.

Cell classes:
  RAM    '.' floor   'B' blocked   '?' off-map/none
  VISION '.' floor   digit object  '?' unknown   (plus the arrow at the player)

Nothing here infers walkability from appearance. A disagreement is a FINDING, not a
formatting difference to smooth over - that is the whole point of the exercise.

Geometry note: the window is centred on the PLAYER's pixel (80,72), not divided evenly
over the screen. Cell (c,r) covers x 72+(c-4)*16 .. +16 and y 64+(r-4)*16 .. +16, so the
mask must use that mapping. An even division of 160x144 into 9x9 is a different (wrong)
grid - it was correct for the old whole-screen 10x9 and is not correct here.
"""

from __future__ import annotations

import base64
import io
import json
import os
import socket
import sys
from pathlib import Path
from typing import Any, cast

REPO = Path("/home/kara/proj-wt-cmp-grid")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from PIL import Image  # noqa: E402

from src.core.ram_reader import RAMReader  # noqa: E402
from vision_blueprint_probe import parse_json  # noqa: E402

ROM = Path(
    "/home/kara/ai_plays_poke/data/rom/Pokemon - Blue Version (USA, Europe) "
    "(SGB Enhanced).gb"
)
PROMPT = REPO / "prompts/exploration/vision_map_blueprint.md"
OUTDIR = Path("/tmp/perception")
COLS, ROWS = 10, 9  # the screen in game cells: 160/16 x 144/16
CELL = 16  # one game cell in pixels
PLAYER_CELL = (4, 3)  # where the player sits on screen, measured from the sprite box


# ── live state ──
def obs() -> dict[str, Any]:
    tok = Path.home().joinpath(".hermes/aipp_bridge/session.token").read_text().strip()
    s = socket.create_connection(("127.0.0.1", 8770), timeout=30)
    s.sendall((json.dumps({"cmd": "raw", "token": tok}) + "\n").encode())
    o = json.loads(s.recv(65536).decode().strip())["obs"]
    s.close()
    # json.loads returns Any; cast so the declaration is honest (the guard's mypy caught
    # the un-cast version on the first attempt, and I had only checked ram_reader.py).
    return cast(dict[str, Any], o)


def capture(label: str) -> Path:
    tok = Path.home().joinpath(".hermes/aipp_bridge/session.token").read_text().strip()
    s = socket.create_connection(("127.0.0.1", 8770), timeout=60)
    s.sendall(
        (json.dumps({"cmd": "frame", "token": tok, "label": label}) + "\n").encode()
    )
    r = json.loads(s.recv(65536).decode().strip())
    s.close()
    return Path(r["frame"])


# ── the two channels ──
def ram_grid(o: dict[str, Any]) -> str:
    r = RAMReader(emulator=None, rom_path=str(ROM))
    r.player_tile_x = lambda: int(o["player_tile_x"])  # type: ignore[method-assign]
    r.player_tile_y = lambda: int(o["player_tile_y"])  # type: ignore[method-assign]
    r.player_facing = lambda: str(o["player_facing"])  # type: ignore[method-assign]
    r.current_map_id = lambda: int(o["map_id"])  # type: ignore[method-assign]
    r.current_map_name = lambda: str(o["map_name"])  # type: ignore[method-assign]
    return r.render_tile_grid(cols=COLS, rows=ROWS)


def vision_grid(png: Path) -> tuple[list[str], dict[str, Any]]:
    key = ""
    for line in Path("/home/kara/ai_plays_poke/.env").read_text().splitlines():
        if line.startswith("OPENROUTER_API_KEY="):
            key = line.split("=", 1)[1].strip().strip('"').strip("'")
    key = key or os.environ.get("OPENROUTER_API_KEY", "")
    img = Image.open(png).convert("RGB")
    if 0 < img.width < 1024:
        img = img.resize((img.width * 6, img.height * 6), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    body = {
        "model": "openai/gpt-5.6-luna",
        # 9000 to match vision_blueprint_probe.py. This model burns ~4500 output tokens
        # REASONING before it emits the JSON, so a 1500 cap truncates the answer away
        # and
        # parse_json gets nothing - which is exactly what happened on the first run.
        "max_tokens": 9000,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT.read_text()},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    },
                ],
            }
        ],
    }
    import urllib.request

    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=240) as r:
        resp = json.loads(r.read().decode())
    got = parse_json(resp["choices"][0]["message"].get("content") or "") or {}
    return list(got.get("grid") or []), got


def pixel_mask(png: Path) -> list[str]:
    """'?' where the cell is mostly black, on the screen's OWN absolute cell grid.

    The window is the whole screen (10 x 9 cells of 16 px), so cell (r, c) is simply the
    pixel box (c*16, r*16). No player anchor: the screen is fixed, and the\
 player's cell is
    wherever their sprite box lands in it. An earlier version centred on the\
 player with a
    +72 px offset, which is half a tile - it shifted every cell by half a cell\
 and was part
    of why the two channels looked like they disagreed at the edges.
    """
    im = Image.open(png).convert("L")
    out = []
    for r in range(ROWS):
        row = ""
        for c in range(COLS):
            x0, y0 = c * CELL, r * CELL
            box = im.crop((x0, y0, x0 + CELL, y0 + CELL))
            hist = box.histogram()
            total = sum(hist) or 1
            row += "?" if sum(hist[:60]) / total >= 0.55 else "."
        out.append(row)
    return out


# ── comparison ──
def cls_ram(ch: str) -> str:
    if ch == "?":
        return "off-map"
    if ch == "B":
        return "blocked"
    if ch == "D":
        return "doorway"
    if ch in "←↑↓→":
        return "player"
    return "floor"


def cls_vis(ch: str) -> str:
    if ch == "?":
        return "unknown"
    if ch in "←↑↓→":
        return "player"
    # 'B' means blocking in the vision blueprint too - the model CAN report blocked
    # cells,
    # and the first version of this classifier scored them as floor, inventing conflicts
    # where the two channels actually agreed.
    if ch == "B":
        return "blocked"
    if ch.isdigit():
        return "object"
    return "floor"


def verdict(a: str, b: str, ra: str, rb: str) -> str:
    """Classify one cell. Compares the ARROW GLYPH, not just the class.

    The first version mapped both channels' arrows to the same class 'player',\
 so a frame
    where RAM said the player faced up and vision said down scored as 'agree'.\
 Bane caught
    it: the verdict showed a match while the directions disagreed. Facing is exactly the
    field we know vision is unreliable on, so a silent pass there is the worst kind.
    """
    if ra in "←↑↓→" and rb in "←↑↓→":
        return "agree" if ra == rb else "FACING-MISMATCH"
    if a in ("off-map", "unknown") and b in ("off-map", "unknown"):
        return "both-?"
    if a == b:
        return "agree"
    if {a, b} == {"floor", "blocked"}:
        return "CONFLICT-walk"
    if "object" in (a, b):
        return "object"
    return "check"


def main() -> int:
    label = sys.argv[1] if len(sys.argv) > 1 else "DIFF"
    o = obs()
    space = str(o.get("map_name"))
    tile = (int(o["player_tile_x"]), int(o["player_tile_y"]))
    print(f"space : {space}   tile {tile}  facing {o['player_facing']}")
    png = capture(label)
    print(f"frame : {png.name}")

    ram = [
        ln
        for ln in ram_grid(o).splitlines()
        if ln.strip()
        and not ln.strip().startswith(("Map:", "Pos:", "Legend:", "Unknown"))
    ]
    ram = [ln.strip() for ln in ram if len(ln.strip()) == COLS][:ROWS]
    vis_raw, vgot = vision_grid(png)
    mask = pixel_mask(png)
    vis = []
    for r in range(ROWS):
        row = vis_raw[r] if r < len(vis_raw) else "?" * COLS
        row = (row + "?" * COLS)[:COLS]
        vis.append("".join("?" if mask[r][c] == "?" else row[c] for c in range(COLS)))

    print("\n     RAM       VISION    VERDICT")
    findings = []
    counts: dict[str, int] = {}
    for r in range(ROWS):
        cells = []
        for c in range(COLS):
            a, b = cls_ram(ram[r][c]), cls_vis(vis[r][c])
            v = verdict(a, b, ram[r][c], vis[r][c])
            counts[v] = counts.get(v, 0) + 1
            cells.append(v)
            if v.startswith("CONFLICT") or v in ("check", "FACING-MISMATCH"):
                dx, dy = c - PLAYER_CELL[0], r - PLAYER_CELL[1]
                findings.append(
                    f"  ({dx:+d},{dy:+d}) rel to player: "
                    f"RAM={a}({ram[r][c]}) vision={b}({vis[r][c]})"
                )
        print(f" {r}   {ram[r]}   {vis[r]}   {' '.join(c[:4] for c in cells)}")

    print(f"\nlegend: {json.dumps(vgot.get('legend'))}")
    print(
        f"RAM '?' cells: {sum(row.count('?') for row in ram)}   "
        f"VISION '?' cells: {sum(row.count('?') for row in vis)}"
    )
    print("\ncounts: " + json.dumps(counts))
    if findings:
        print("\nCELLS THAT NEED A HUMAN LOOK:")
        print("\n".join(findings[:14]))
    OUTDIR.mkdir(parents=True, exist_ok=True)
    out = OUTDIR / f"{label}.json"
    out.write_text(
        json.dumps(
            {
                "space": space,
                "tile": tile,
                "facing": o["player_facing"],
                "frame": str(png),
                "ram": ram,
                "vision": vis,
                "mask": mask,
                "legend": vgot.get("legend"),
                "counts": counts,
                "findings": findings,
            },
            indent=2,
        )
    )
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
