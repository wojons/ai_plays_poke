"""Every input control on the console: enumerated from the page, then exercised.

Bane asked whether the testing agent covers the input boxes. It does not - the QA lane tests the
ai_plays_poke repo, and this console is a separate app with no lane of its own. So find out what is
actually there and what actually works.

Nothing here presses a game button. Bane's rule is no in-game action without approval, and a d-pad
press moves the player, so the movement controls are listed and left alone. Everything else - the
toggles, the read endpoints, the chat box, the validation - is exercised for real.
"""

import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

C = "http://127.0.0.1:8899"
HTML = Path("/home/kara/aipp-console/static/index.html").read_text()


def call(
    path: str,
    body: dict[str, Any] | None = None,
    method: str | None = None,
    timeout: int = 25,
) -> tuple[int | None, float, str]:
    """Return (status, seconds, body-head). Never raises - a dead endpoint is a finding."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        C + path, data=data, headers={"Content-Type": "application/json"}, method=method
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, time.time() - t0, r.read(160).decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, time.time() - t0, e.read(160).decode(errors="replace")
    except Exception as e:
        return None, time.time() - t0, f"{type(e).__name__}: {e}"


print("=== controls found in the page ===")
# buttons and inputs, with their onclick / id / name so each can be traced to an endpoint
for m in re.finditer(r"<(button|input|select)\b[^>]*>", HTML):
    tag = m.group(0)
    ident = (re.search(r'id="([^"]+)"', tag) or [None, ""])[1]
    onclick = (re.search(r'onclick="([^"]{0,70})', tag) or [None, ""])[1]
    typ = (re.search(r'type="([^"]+)"', tag) or [None, ""])[1]
    ph = (re.search(r'placeholder="([^"]{0,40})', tag) or [None, ""])[1]
    kind = m.group(1)
    if ident or onclick or ph:
        print(
            f"  {kind:6s} id={ident:22s} type={typ:9s} {('ph=' + ph) if ph else ''} -> {onclick}"
        )

print("\n=== do the endpoints behind them actually answer? ===")
# read-only / harmless. Game-press endpoints are deliberately NOT called (they move the player).
CHECKS = [
    ("GET", "/api/state", None),
    ("GET", "/api/events", None),
    ("GET", "/api/notes", None),
    ("GET", "/api/tools", None),
    ("GET", "/api/health", None),
    ("GET", "/api/maps", None),
    ("GET", "/api/checklist", None),
    ("GET", "/api/frame.png", None),
]
for method, path, body in CHECKS:
    st, dt, head = call(path, body, method)
    mark = "OK " if st == 200 else "!! "
    print(
        f"  {mark}{method:4s} {path:22s} {str(st):5s} {dt:6.3f}s  {head[:60].replace(chr(10), ' ')}"
    )

print("\n=== toggles: do they accept input and report it back? ===")
toggles: list[tuple[str, dict[str, Any]]] = [
    ("/api/live", {"on": False}),
    ("/api/auto", {"on": True}),
    ("/api/auto", {"on": False}),
]
for path, body in toggles:
    st, dt, head = call(path, body, "POST")
    print(f"  POST {path:14s} {str(st):5s} {dt:6.3f}s  {head[:70]}")

print("\n=== malformed input: does it fail loudly or lie about succeeding? ===")
# NOT probing /api/press here. An unrecognised button can still fall through to a default, and any
# press moves the player - Bane's rule is no in-game action without approval. So the movement path
# is enumerated and left alone; only input that cannot move anything is exercised.
malformed: list[tuple[str, dict[str, Any]]] = [
    ("/api/live", {"on": "not-a-bool"}),
    ("/api/live", {"nonsense": 1}),
    ("/api/auto", {"on": "nope"}),
]
for path, body in malformed:
    st, dt, head = call(path, body, "POST")
    print(f"  POST {path:12s} {json.dumps(body):34s} -> {str(st):5s} {head[:60]}")

print("\n=== the chat box: where does what you type actually go? ===")
st, dt, head = call("/api/chat", {"message": "control check"}, "POST")
print(f"  POST /api/chat -> {st} {head[:120]}")
print(
    "  (the reply comes back over SSE, so a status here only proves the box is wired)"
)

print("\n=== live state after all this ===")
st, dt, head = call("/api/state")

with urllib.request.urlopen(C + "/api/state", timeout=25) as r:
    d = json.loads(r.read())
print(
    f"  tile {(d.get('game') or {}).get('tile')} facing {(d.get('game') or {}).get('facing')}"
    f" | live {(d.get('live') or {}).get('on')} | auto {(d.get('auto') or {}).get('on')}"
    f" | panels {len(d.get('panels') or [])}"
)
