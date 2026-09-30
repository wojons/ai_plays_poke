#!/usr/bin/env python3
"""Prove auto-vision re-reads when the screen changes, with no button pressed."""

from __future__ import annotations

import json
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any

C = "http://127.0.0.1:8899"
REPO = Path("/home/kara/ai_plays_poke")


def get(path: str, timeout: int = 30) -> dict[str, Any]:
    with urllib.request.urlopen(C + path, timeout=timeout) as r:
        data: Any = json.loads(r.read())
    return data if isinstance(data, dict) else {}


def post(path: str, body: dict[str, Any], timeout: int = 60) -> dict[str, Any]:
    req = urllib.request.Request(
        C + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data: Any = json.loads(r.read())
    return data if isinstance(data, dict) else {}


def wait_idle(limit: int = 240) -> None:
    for _ in range(limit // 5):
        if not (get("/api/state").get("vision_job") or {}).get("running"):
            return
        time.sleep(5)


print("waiting for any in-flight read to settle...")
wait_idle()

st = get("/api/state")
before_snap = st.get("vision_snap")
before_ts = (st.get("vision_meta") or {}).get("when")
before_tile = (st.get("game") or {}).get("tile")
print(f"  before: snap={before_snap} ts={before_ts} tile={before_tile}")
print(
    f"  auto on: {(st.get('auto_vision') or {}).get('on')} | runs={(st.get('auto_vision') or {}).get('runs')}"
)

print("\nmoving the game (no vision button touched)...")
post("/api/press", {"buttons": ["RIGHT"]})
time.sleep(1.5)
post("/api/press", {"buttons": ["RIGHT"]})
time.sleep(2)
after_tile = (get("/api/state").get("game") or {}).get("tile")
print(f"  tile now: {after_tile}")

print("\nwaiting for auto-vision to notice (it polls every 3s, min gap 25s)...")
new_snap = None
for i in range(60):
    time.sleep(5)
    st = get("/api/state")
    job = st.get("vision_job") or {}
    cur = st.get("vision_snap")
    if job.get("running"):
        print(f"  t+{(i + 1) * 5}s: a read started on its own (snap {cur})")
        new_snap = cur
        break
    if cur and cur != before_snap:
        print(f"  t+{(i + 1) * 5}s: new reading already landed (snap {cur})")
        new_snap = cur
        break
if not new_snap:
    print("  FAIL: nothing started within 300s")

if new_snap:
    print("\nwaiting for it to land...")
    wait_idle(300)
    st = get("/api/state")
    vm = st.get("vision_meta") or {}
    av = st.get("auto_vision") or {}
    print(
        f"  after:  snap={st.get('vision_snap')} ts={vm.get('when')} reason={av.get('last_reason')} runs={av.get('runs')}"
    )
    print(f"  new reading taken after the move: {st.get('vision_snap') != before_snap}")
    print(
        f"  vision rows now {len(st.get('vision') or [])}x{(len((st.get('vision') or [''])[0]) if st.get('vision') else 0)}"
    )
    evs = [
        e
        for e in (st.get("events") or [])
        if e.get("kind") in ("vision_auto", "vision_request", "vision_done")
    ]
    print("  recent vision events:")
    for e in evs[-5:]:
        print(
            f"    {e.get('ts', '')} {e.get('who')} {e.get('kind')} {e.get('reason') or e.get('snap_id') or ''}"
        )

# restore the tile we moved from
print("\nrestoring the game from its save...")
subprocess.run(
    [
        str(REPO / ".venv/bin/python"),
        "scripts/play.py",
        "load",
        "pallet_outside_house_20260929",
    ],
    cwd=REPO,
    capture_output=True,
    timeout=120,
)
time.sleep(2)
print("  tile now:", (get("/api/state").get("game") or {}).get("tile"))
