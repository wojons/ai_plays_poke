#!/usr/bin/env python3
"""Live game viewer — serves a scrolling timeline with screenshots and actions.

Usage:
    ./venv/bin/python web_viewer.py
    Open http://localhost:8080

Each run gets its own URL. Timeline auto-scrolls and auto-refreshes.
"""

import json
import asyncio
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

BASE = Path(__file__).parent
SCREENSHOTS = BASE / "screenshots"
LOGS = BASE / "cron_logs"
VIDEOS = BASE / "videos"

app = FastAPI(title="Pokémon Blue — Live Viewer")

# ── Static file mounts ──────────────────────────────────────────────
if SCREENSHOTS.exists():
    app.mount("/screenshots", StaticFiles(directory=str(SCREENSHOTS)), name="screenshots")
if VIDEOS.exists():
    app.mount("/videos", StaticFiles(directory=str(VIDEOS)), name="videos")

# ── API ─────────────────────────────────────────────────────────────

def _list_runs() -> list[dict]:
    """Find all runs with screenshots or logs."""
    runs = {}
    # From screenshots
    for d in sorted(SCREENSHOTS.iterdir(), reverse=True):
        if d.is_dir() and d.name.startswith("run_"):
            ts = d.name.replace("run_", "")
            pngs = sorted(d.glob("*.png"))
            runs[ts] = {"id": ts, "screenshots": len(pngs), "log_entries": 0}
    # From logs
    for f in sorted(LOGS.iterdir(), reverse=True):
        if f.suffix == ".jsonl" and f.name.startswith("run_"):
            ts = f.stem.replace("run_", "")
            entries = _read_log(ts)
            if ts in runs:
                runs[ts]["log_entries"] = len(entries)
            else:
                runs[ts] = {"id": ts, "screenshots": 0, "log_entries": len(entries)}
    # Video availability
    if VIDEOS.exists():
        for r in runs.values():
            r["has_video"] = (VIDEOS / f"{r['id']}.mp4").exists()
    return list(runs.values())


def _read_log(run_id: str) -> list[dict]:
    """Read all log entries for a run."""
    log_path = LOGS / f"run_{run_id}.jsonl"
    if not log_path.exists():
        return []
    entries = []
    with open(log_path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return entries


@app.get("/api/runs")
async def api_runs():
    return _list_runs()


@app.get("/api/run/{run_id}/log")
async def api_run_log(run_id: str, since: int = 0):
    entries = _read_log(run_id)
    return entries[since:]


@app.get("/api/run/{run_id}/stream")
async def api_run_stream(run_id: str, since: int = 0):
    """SSE stream — sends new entries as they appear."""
    async def event_stream():
        last_count = since
        # Initial catch-up
        entries = _read_log(run_id)
        if len(entries) > since:
            for e in entries[since:]:
                yield f"data: {json.dumps(e, default=str)}\n\n"
            last_count = len(entries)

        # Poll for new entries
        while True:
            await asyncio.sleep(2)
            entries = _read_log(run_id)
            if len(entries) > last_count:
                for e in entries[last_count:]:
                    yield f"data: {json.dumps(e, default=str)}\n\n"
                last_count = len(entries)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/screenshot/{run_id}/{filename}")
async def api_screenshot(run_id: str, filename: str):
    path = SCREENSHOTS / f"run_{run_id}" / filename
    if path.exists():
        return FileResponse(str(path))
    return JSONResponse({"error": "not found"}, status_code=404)


# ── HTML Pages ──────────────────────────────────────────────────────

INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Pokémon Blue — Live Viewer</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Courier New', monospace; background: #0a0a0f; color: #c0c0d0; padding: 20px; }
  h1 { color: #60a5fa; border-bottom: 2px solid #1e3a5f; padding-bottom: 10px; margin-bottom: 20px; }
  .run-card {
    background: #12121a;
    border: 1px solid #2a2a3a;
    border-radius: 6px;
    padding: 16px;
    margin-bottom: 12px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .run-card:hover { border-color: #4a6a9a; }
  .run-id { color: #60a5fa; font-size: 18px; }
  .run-stats { color: #888; font-size: 14px; }
  a { color: #60a5fa; text-decoration: none; }
  a:hover { text-decoration: underline; }
  .live-dot { color: #22c55e; animation: pulse 1.5s infinite; }
  @keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:0.3; } }
</style>
</head>
<body>
<h1>⚡ Pokémon Blue — Live Game Viewer</h1>
<div id="runs">Loading...</div>
<script>
async function load() {
  const res = await fetch('/api/runs');
  const runs = await res.json();
  const el = document.getElementById('runs');
  el.innerHTML = runs.map(r => `
    <div class="run-card">
      <div>
        <a href="/run/${r.id}" class="run-id">${r.id}</a>
        <br><span class="run-stats">📸 ${r.screenshots} screenshots | 📋 ${r.log_entries} log entries${r.has_video ? ' | 🎬 <a href="/videos/' + r.id + '.mp4" target="_blank">video</a>' : ''}</span>
      </div>
      ${r.screenshots > 0 ? '<span class="live-dot">● LIVE</span>' : ''}
    </div>
  `).join('') || '<p>No runs yet. Start a game first!</p>';
}
load();
</script>
</body>
</html>"""


TIMELINE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Run __RUN_ID__ — Pokémon Blue Live Viewer</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Courier New', monospace; background: #0a0a0f; color: #c0c0d0; }

  #header {
    position: fixed; top: 0; left: 0; right: 0; z-index: 100;
    background: #0d0d18; border-bottom: 2px solid #1e3a5f;
    padding: 10px 20px; display: flex; justify-content: space-between; align-items: center;
  }
  #header h1 { font-size: 16px; color: #60a5fa; }
  #header .stats { font-size: 12px; color: #888; }
  #header .live { color: #22c55e; }
  #header .idle { color: #888; }

  #timeline {
    margin-top: 60px; padding: 20px;
    max-width: 900px; margin-left: auto; margin-right: auto;
    padding-bottom: 80px;
  }
  .entry {
    background: #12121a; border: 1px solid #2a2a3a;
    border-radius: 8px; padding: 16px; margin-bottom: 20px;
    animation: fadeIn 0.3s ease;
  }
  @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

  .entry-header {
    display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;
  }
  .cycle { color: #60a5fa; font-weight: bold; font-size: 14px; }
  .screen-type {
    padding: 2px 10px; border-radius: 4px; font-size: 12px; font-weight: bold; text-transform: uppercase;
  }
  .screen-overworld { background: #166534; color: #4ade80; }
  .screen-title { background: #1e3a5f; color: #60a5fa; }
  .screen-dialog { background: #713f12; color: #fbbf24; }
  .screen-name_entry { background: #581c87; color: #c084fc; }
  .screen-battle { background: #7f1d1d; color: #f87171; }
  .screen-unknown { background: #333; color: #999; }

  .screenshot-container { margin: 10px 0; text-align: center; }
  .screenshot-container img {
    max-width: 100%; border: 2px solid #2a2a3a; border-radius: 4px;
    image-rendering: pixelated; display: block; margin: 0 auto;
  }
  .screenshot-fallback { display: none; color: #555; font-size: 11px; padding: 8px; }

  .action-row { display: flex; gap: 12px; font-size: 13px; margin-top: 8px; flex-wrap: wrap; }
  .action-label { color: #888; }
  .action-value { color: #e0e0e0; }
  .intent { color: #a0a0b0; font-style: italic; margin-top: 4px; font-size: 12px; }
  .elapsed { color: #666; font-size: 11px; margin-top: 6px; }
  .error-line { color: #f87171; font-size: 12px; margin-top: 4px; }

  .raw-toggle {
    color: #888; font-size: 11px; cursor: pointer; margin-top: 6px; user-select: none;
  }
  .raw-toggle:hover { color: #aaa; }
  .raw-block {
    display: none; background: #0d0d17; border: 1px solid #222; padding: 10px;
    margin-top: 8px; font-size: 11px; max-height: 200px; overflow-y: auto;
    white-space: pre-wrap; color: #789; border-radius: 4px;
  }
  .raw-block.open { display: block; }

  #scroll-bottom {
    position: fixed; bottom: 20px; right: 20px; z-index: 100;
    background: #1e3a5f; color: #60a5fa; border: none;
    padding: 10px 16px; border-radius: 20px; cursor: pointer;
    font-family: inherit; font-size: 13px; display: none;
  }
  #scroll-bottom:hover { background: #2a4a7a; }

  .empty-state { text-align: center; padding: 60px; color: #666; }

  #video-player {
    max-width: 900px; margin: 70px auto 0; padding: 0 20px;
  }
  #video-player video {
    width: 100%; border: 2px solid #2a2a3a; border-radius: 8px;
    background: #000; image-rendering: pixelated;
  }
  #video-player .video-caption {
    color: #888; font-size: 12px; margin-top: 6px; text-align: center;
  }
</style>
</head>
<body>
<div id="header">
  <h1>🎮 Run: <span id="run-id">__RUN_ID__</span></h1>
  <div class="stats">
    Cycles: <span id="cycle-count">0</span> |
    Screens: <span id="screen-list">—</span> |
    <span id="live-indicator" class="idle">◉ IDLE</span>
  </div>
</div>

<div id="video-player" style="display:none">
  <video controls preload="metadata" id="run-video">
    <source src="/videos/__RUN_ID__.mp4" type="video/mp4">
  </video>
  <div class="video-caption">🎬 Replay — screenshots + action HUD burned in</div>
</div>

<div id="timeline"><div class="empty-state">Waiting for game data...</div></div>

<button id="scroll-bottom" onclick="scrollToBottom()">⬇ Latest</button>

<script>
const RUN_ID = "__RUN_ID__";
var allEntries = [];
var autoScroll = true;

function htmlEscape(s) {
  if (typeof s !== 'string') return String(s);
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function scrollToBottom() {
  autoScroll = true;
  window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
}

function screenClass(type) {
  var t = String(type || '').replace(/[ -]/g, '_').toLowerCase();
  var map = {
    'overworld': 'screen-overworld',
    'title': 'screen-title',
    'dialog': 'screen-dialog',
    'name_entry': 'screen-name_entry',
    'battle': 'screen-battle'
  };
  return map[t] || 'screen-unknown';
}

function screenshotUrl(cycle) {
  return '/screenshots/run_' + RUN_ID + '/step_' + String(cycle).padStart(4, '0') + '.png';
}

function toggleRaw(el, idx) {
  var block = document.getElementById('raw-' + idx);
  if (!block) return;
  if (block.classList.toggle('open')) {
    if (!block.textContent) {
      block.textContent = JSON.stringify(allEntries[idx], null, 2);
    }
    el.textContent = '▼ Hide raw';
  } else {
    el.textContent = '▶ Show raw';
  }
}

function buildEntryHTML(e, idx) {
  var screen = e.screen || e.state || '?';
  var cycle = (e.cycle !== undefined && e.cycle !== null) ? e.cycle : null;
  var action = e.action || e.button || '?';
  var intent = e.intent || '';
  var elapsed = e.elapsed_s ? Number(e.elapsed_s).toFixed(1) + 's' : '';
  var err = e.error || '';

  var html = '<div class="entry" id="entry-' + idx + '">';

  // Header: cycle + screen type
  html += '<div class="entry-header">';
  html += '<span class="cycle">Cycle ' + (cycle !== null ? cycle : '?') + '</span>';
  html += '<span class="screen-type ' + screenClass(screen) + '">' + htmlEscape(screen) + '</span>';
  html += '</div>';

  // Screenshot
  if (cycle !== null) {
    html += '<div class="screenshot-container">';
    html += '<img src="' + screenshotUrl(cycle) + '" alt="Step ' + cycle + '" loading="lazy"';
    html += ' onerror="this.style.display=\\'none\\'"';
    html += '<div class="screenshot-fallback">📷 Screenshot not available (step ' + cycle + ')</div>';
    html += '</div>';
  }

  // Action
  html += '<div class="action-row">';
  html += '<span><span class="action-label">Action:</span> <span class="action-value">' + htmlEscape(action) + '</span></span>';
  html += '</div>';

  // Intent
  if (intent) {
    html += '<div class="intent">💭 ' + htmlEscape(intent) + '</div>';
  }

  // Error
  if (err) {
    html += '<div class="error-line">⚠ ' + htmlEscape(err) + '</div>';
  }

  // Elapsed
  if (elapsed) {
    html += '<div class="elapsed">⏱ ' + htmlEscape(elapsed) + '</div>';
  }

  // Raw toggle + block
  html += '<div class="raw-toggle" onclick="toggleRaw(this, ' + idx + ')">▶ Show raw</div>';
  html += '<div class="raw-block" id="raw-' + idx + '"></div>';

  html += '</div>';
  return html;
}

function updateHeader() {
  document.getElementById('cycle-count').textContent = allEntries.length;
  var screens = {};
  for (var i = 0; i < allEntries.length; i++) {
    var s = allEntries[i].screen || allEntries[i].state || '?';
    screens[s] = true;
  }
  var names = Object.keys(screens);
  document.getElementById('screen-list').textContent = names.length ? names.join(', ') : '—';
}

function renderNewEntries(entries, startIdx) {
  var timeline = document.getElementById('timeline');

  // Remove empty state on first data
  if (startIdx === 0) {
    timeline.innerHTML = '';
  }

  var html = '';
  for (var i = 0; i < entries.length; i++) {
    html += buildEntryHTML(entries[i], startIdx + i);
  }
  timeline.insertAdjacentHTML('beforeend', html);
}

async function poll() {
  try {
    var res = await fetch('/api/run/' + RUN_ID + '/log?since=' + allEntries.length);
    if (!res.ok) return;

    var newEntries = await res.json();

    if (newEntries.length === 0) {
      document.getElementById('live-indicator').textContent = '◉ IDLE';
      document.getElementById('live-indicator').className = 'idle';
      return;
    }

    document.getElementById('live-indicator').textContent = '● LIVE';
    document.getElementById('live-indicator').className = 'live';

    var startIdx = allEntries.length;
    for (var i = 0; i < newEntries.length; i++) {
      allEntries.push(newEntries[i]);
    }

    renderNewEntries(newEntries, startIdx);
    updateHeader();

    if (autoScroll) {
      window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
    }
  } catch (err) {
    console.error('Poll error:', err);
  }
}

// Start when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
  // Show video player only if /videos/<run>.mp4 exists
  var v = document.getElementById('run-video');
  if (v) {
    v.addEventListener('error', function() {
      var wrap = document.getElementById('video-player');
      if (wrap) wrap.style.display = 'none';
    });
    v.addEventListener('loadedmetadata', function() {
      var wrap = document.getElementById('video-player');
      if (wrap) wrap.style.display = 'block';
    });
  }
  // Initial load
  poll();
  // Poll every 2 seconds
  setInterval(poll, 2000);
  
  // Auto-scroll detection
  window.addEventListener('scroll', function() {
    var threshold = 200;
    autoScroll = (window.innerHeight + window.scrollY) >= (document.body.scrollHeight - threshold);
    var btn = document.getElementById('scroll-bottom');
    if (btn) btn.style.display = autoScroll ? 'none' : 'block';
  });
});
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def index():
    return INDEX_HTML


@app.get("/run/{run_id}", response_class=HTMLResponse)
async def run_page(run_id: str):
    # Use str.replace on all occurrences in the template
    html = TIMELINE_HTML
    html = html.replace("__RUN_ID__", run_id)
    return html


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--host", default="0.0.0.0")
    args = p.parse_args()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
