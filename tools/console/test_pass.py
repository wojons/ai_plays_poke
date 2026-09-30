#!/usr/bin/env python3
"""Full test pass for the operator console.

Exercises every surface against the running system, prints a PASS/FAIL table, and restores the
game to the recorded baseline afterwards (the emulator is live, so a movement test must be undone
rather than left to drift).

Run it and read the table; do not trust a summary.
"""
from __future__ import annotations

import json
import re
import struct
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

C = "http://127.0.0.1:8899"
REPO = Path("/home/kara/ai_plays_poke")
PY = str(REPO / ".venv/bin/python")
RESULTS: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, "PASS" if ok else "FAIL", detail))
    print(f"{'PASS' if ok else 'FAIL':4s} | {name}" + (f"  [{detail}]" if detail else ""), flush=True)


def get(path: str, timeout: int = 30, raw: bool = False):
    try:
        with urllib.request.urlopen(C + path, timeout=timeout) as r:
            body = r.read()
            return r.status, (body if raw else json.loads(body))
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}"


def post(path: str, body: dict, timeout: int = 600):
    try:
        req = urllib.request.Request(C + path, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}"


def sh(cmd: str, cwd: Path | None = None, t: int = 120) -> tuple[int, str]:
    p = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=t)
    return p.returncode, (p.stdout + p.stderr).strip()


def tile(st: dict):
    return (st.get("game") or {}).get("tile")


print("=" * 78)
print("OPERATOR CONSOLE — FULL TEST PASS")
print("=" * 78)

# ── A. service ──────────────────────────────────────────────────────────────
rc, out = sh("systemctl --user is-active aipp-console")
check("service active", out == "active", out)
rc, out = sh("systemctl --user is-enabled aipp-console")
check("service enabled (survives reboot)", out == "enabled", out)
code, h = get("/api/health")
check("/api/health 200", code == 200 and isinstance(h, dict) and h.get("ok") is True, f"HTTP {code}")

# ── B. endpoints ────────────────────────────────────────────────────────────
code, st = get("/api/state")
check("/api/state 200 + JSON", code == 200 and isinstance(st, dict), f"HTTP {code}")
code, png = get("/api/frame.png", raw=True)
dims = ""
if code == 200 and isinstance(png, bytes) and png[:8] == b"\x89PNG\r\n\x1a\n":
    w, hh = struct.unpack(">II", png[16:24])
    dims = f"{w}x{hh}"
check("/api/frame.png is a real 160x144 PNG", dims == "160x144", f"HTTP {code}, {dims}")
code, db = get("/api/duckbrain?ns=pokemon-global&limit=5")
check("/api/duckbrain returns records", code == 200 and isinstance(db, dict) and db.get("keys", 0) > 0,
      f"HTTP {code}, keys {db.get('keys') if isinstance(db, dict) else '?'}")
# Compare MATCHED, not shown: shown is capped by limit and reads the same for any result set, so
# comparing it can never detect narrowing. That is what this check got wrong the first time.
code, dbq = get("/api/duckbrain?ns=pokemon-global&q=grass&limit=200")
check("DuckBrain search narrows results",
      code == 200 and isinstance(dbq, dict) and 0 < dbq.get("matched", 0) < (db.get("keys") or 0),
      f"matched {dbq.get('matched') if isinstance(dbq, dict) else '?'} of {db.get('keys')}")
code, dbn = get("/api/duckbrain?ns=pokemon-global&q=zzzznotarealkeyzzzz&limit=200")
check("DuckBrain search with no hits reports zero honestly",
      code == 200 and isinstance(dbn, dict) and dbn.get("matched") == 0 and dbn.get("rows") == [])
code, rev = get("/review.html", raw=True)
rev_ok = code == 200 and isinstance(rev, bytes) and b"Questions I need answered" in rev
check("/review.html served with its sections", rev_ok, f"HTTP {code}, {len(rev) if isinstance(rev, bytes) else 0} bytes")
code, idx = get("/index.html", raw=True)
check("/index.html served", code == 200 and isinstance(idx, bytes) and b"ai-plays-poke console" in idx, f"HTTP {code}")

# ── C. state integrity ──────────────────────────────────────────────────────
need = {"game", "ram", "collision", "vision", "verdict", "events", "notes", "checklist", "panels",
        "agent_tools"}
check("state carries every panel's data", need.issubset(set((st or {}).keys())),
      f"missing {sorted(need - set((st or {}).keys()))}")
ram = (st or {}).get("ram") or []
check("RAM grid is 5x5", len(ram) == 5 and all(len(r) == 5 for r in ram), f"{len(ram)} rows")
syn = (st or {}).get("game") or {}
check("game block is populated", bool(syn.get("map")) and bool(syn.get("tile")),
      f"{syn.get('map')} {syn.get('tile')} facing {syn.get('facing')}")

# self-consistency: recompute the verdict from the grids and compare to what the panel claims
import importlib.util as _u
spec = _u.spec_from_file_location("srv", "/home/kara/aipp-console/server.py")
m = _u.module_from_spec(spec)
spec.loader.exec_module(m)
vis = (st or {}).get("vision") or []
if vis:
    re_v = m.compute_verdict(ram, vis)
    rep = (st or {}).get("verdict") or {}
    same = all(re_v.get(k) == rep.get(k) for k in ("rows", "agree", "conflict", "both_unknown", "facing"))
    check("verdict is self-consistent (recomputed == reported)", same,
          f"recomputed agree {re_v.get('agree')} conflict {re_v.get('conflict')} facing {re_v.get('facing')}"
          f" vs reported {rep.get('agree')}/{rep.get('conflict')}/{rep.get('facing')}")
    check("vision grid is 5x5", len(vis) == 5 and all(len(r) == 5 for r in vis), f"{len(vis)} rows")
    # the facing rule specifically: arrows must not score as agreement
    unit = m.compute_verdict(["\u2190\u2190\u2190\u2190\u2190"], ["\u2191\u2191\u2191\u2191\u2191"])
    check("facing rule: opposite arrows are F, not agreement",
          unit["facing"] == 5 and unit["agree"] == 0, f"facing {unit['facing']} agree {unit['agree']}")

# ── D. controls, against the live emulator ──────────────────────────────────
base_tile = tile(st)
base_facing = syn.get("facing")
print(f"-- baseline: tile {base_tile} facing {base_facing}")
moved = False
for i in range(4):
    post("/api/press", {"buttons": ["RIGHT"]})
    time.sleep(0.6)
    _, st2 = get("/api/state")
    if tile(st2) != base_tile:
        moved = True
        break
check("operator press moves the game", moved, f"{base_tile} -> {tile(st2)} after {i+1} press(es)")
_, st3 = get("/api/state")
evs = (st3 or {}).get("events") or []
check("press appears in the operator event log",
      any(e.get("kind") == "press" and e.get("who") == "operator" for e in evs),
      f"{sum(1 for e in evs if e.get('kind')=='press')} press rows")

# ── E. stores ───────────────────────────────────────────────────────────────
code, _ = post("/api/notes", {"op": "add", "who": "operator", "text": "TEST PASS note"})
_, stn = get("/api/state")
nid = next((n["id"] for n in (stn.get("notes") or []) if n.get("text") == "TEST PASS note"), None)
check("note write + read-back", code == 200 and nid is not None, f"id {nid}")
code, _ = post("/api/notes", {"op": "add", "who": "operator", "text": "TEST PASS nested", "parent": nid})
_, stn2 = get("/api/state")
kid = next((n for n in (stn2.get("notes") or []) if n.get("text") == "TEST PASS nested"), None)
check("nested note keeps its parent link", bool(kid and kid.get("parent") == nid),
      f"parent {kid.get('parent') if kid else None} vs {nid}")
code, _ = post("/api/checklist", {"op": "add", "who": "agent", "text": "TEST PASS checklist"})
_, stc = get("/api/state")
check("checklist write + read-back",
      any(c.get("text") == "TEST PASS checklist" for c in (stc.get("checklist") or [])))

# ── F. vision (one model call) ──────────────────────────────────────────────
t0 = time.time()
code, vres = post("/api/vision", {}, timeout=420)
vrows = (vres or {}).get("rows") if isinstance(vres, dict) else None
vmeta = (vres or {}).get("meta") if isinstance(vres, dict) else None
check("vision call returns a 5x5 grid",
      code == 200 and isinstance(vrows, list) and len(vrows) == 5 and all(len(r) == 5 for r in vrows),
      f"HTTP {code}, {len(vrows) if vrows else 0} rows, {time.time()-t0:.0f}s")
if vmeta:
    check("vision reports finish_reason + tokens",
          vmeta.get("finish_reason") and vmeta.get("total_tokens") is not None,
          f"{vmeta.get('finish_reason')}, total {vmeta.get('total_tokens')}, "
          f"reasoning {vmeta.get('reasoning_tokens')}, ceiling {vmeta.get('max_tokens')}")

# ── G. chat round trip, proved by nonce ─────────────────────────────────────
code, cres = post("/api/chat", {"text": "Quote the LIVE STATE snapshot id from my message and "
                                        "nothing else."}, timeout=560)
sid = (cres or {}).get("snapshot_id") if isinstance(cres, dict) else None
reply = (cres or {}).get("reply") or "" if isinstance(cres, dict) else ""
check("chat round trip carries the live state (nonce echoed back)",
      bool(sid) and sid in reply, f"sent {sid}, found in reply: {bool(sid and sid in reply)}")
check("chat reply is non-empty", len(reply) > 10, f"{len(reply)} chars")

# ── H. security ─────────────────────────────────────────────────────────────
for probe in ("/../server.py", "/..%2fserver.py", "/static/../server.py"):
    code, _ = get(probe)
    check(f"traversal refused: {probe}", code == 404, f"HTTP {code}")

# ── I. tool surface ─────────────────────────────────────────────────────────
at = (st or {}).get("agent_tools") or {}
tools = at.get("tools") or {}
check("agent tool surface is populated", sum(len(v) for v in tools.values()) >= 20,
      json.dumps(at.get("counts")))
check("no private helpers leaked into the tool list",
      not any(t.startswith("_") for v in tools.values() for t in v),
      f"leaked: {[t for v in tools.values() for t in v if t.startswith('_')]}")
check("no junk entries in the tool list",
      not any(t in ("----", "--") or len(t) < 3 for v in tools.values() for t in v))

# ── J. restore the emulator ─────────────────────────────────────────────────
rc, ls = sh(f"{PY} scripts/play.py list_saves", cwd=REPO)
slots = re.findall(r"([a-z0-9_]+)", ls)
rc2, out2 = sh(f"{PY} scripts/play.py load pallet_outside_house_20260929", cwd=REPO)
time.sleep(1.5)
_, stf = get("/api/state")
# The load restores the SAVE's state, which is the real baseline - the tile/facing at test start may
# already have drifted from earlier manual presses, so comparing against that would be a proxy.
restored = tile(stf) == [5, 6]
check("game restored from the save after the movement test", restored,
      f"now {tile(stf)} facing {(stf.get('game') or {}).get('facing')} (save is [5, 6]/down, "
      f"test started at {base_tile}/{base_facing})")

# ── summary ─────────────────────────────────────────────────────────────────
print("=" * 78)
fails = [r for r in RESULTS if r[1] == "FAIL"]
print(f"TOTAL {len(RESULTS)}  PASS {len(RESULTS)-len(fails)}  FAIL {len(fails)}")
for n, s, d in fails:
    print(f"  FAILED: {n}  [{d}]")
print("=" * 78)
Path("/home/kara/aipp-console/data/test_pass_results.json").write_text(
    json.dumps([{"name": n, "result": s, "detail": d} for n, s, d in RESULTS], indent=2))
