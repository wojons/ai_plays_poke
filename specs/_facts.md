# Facts ledger — every claim carries its measurement

One row per fact. Confidence: `measured` (command output on the named date) / `read-from-code` /
`told-by-operator` / `assumed` (can never back a normative statement).

| id | claim | how measured | measured at | confidence |
|---|---|---|---|---|
| FACT-01 | Bridge binds loopback only, port 8770, token required (`secrets.compare_digest`) | `scripts/game_bridge.py:19-25,395-421,527` | 2026-11-11 | read-from-code |
| FACT-02 | Bridge exposes 13 ops: health, observe, press, step, save, load, frame, raw, pause, resume, list_saves, reset, goal | `scripts/game_bridge.py:324-362` | 2026-11-11 | read-from-code |
| FACT-03 | RAM reader renders a tile grid `render_tile_grid(cols=10, rows=9)` | `src/core/ram_reader.py:1490` | 2026-11-11 | read-from-code |
| FACT-04 | Sprite ground truth: `wSpriteStateData1` at `0xC100`, 16 sprites × 16 bytes; player is slot 0 | `src/core/ram_reader.py:96`; probe doc `docs/vision_people_findings.md` | 2026-11-11 | read-from-code |
| FACT-05 | `vision_grid.py` declares a DIFFERENT grid: `GRID_COLS=9, GRID_ROWS=9, PLAYER_CELL=(4,4)` | `src/core/vision_grid.py:3-8` | 2026-11-11 | read-from-code |
| FACT-06 | Live RAM grid places the facing arrow at row 3, col 4 (Pallet Town [5,6] facing down) | console `/api/state` output, 2026-10-01 and 2026-11-11 | 2026-11-11 | measured |
| FACT-07 | The 9×9/`PLAYER_CELL=(4,4)` definition vs the 10×9/row-3 reality is the measured one-row vertical offset | FACT-05 vs FACT-06 | 2026-11-11 | measured |
| FACT-08 | Decision modes resolve AIPP > CRON env > spelling; legacy spellings stay byte-identical (M6) | `cron_runner.py:167-369` | 2026-11-11 | read-from-code |
| FACT-09 | Handoff thresholds: `DEFAULT_HANDOFF_CONFIDENCE = 0.50`, `DEFAULT_HANDOFF_AMBIGUITY = 0.40`, mirroring `jev_client` | `cron_runner.py:369-370` | 2026-11-11 | read-from-code |
| FACT-10 | `scripts/long_run.py:132-138` has its own resolver that still degrades to `'jev'` when unset — violates ARM-2's no-hardcoded-default criterion | grep of `scripts/long_run.py` | 2026-11-11 | measured |
| FACT-11 | Vision upscale ×6 LANCZOS, capped `MAX_IMAGE_WIDTH = 1024`; 1× and 6×-NEAREST measured unreliable | `src/core/vision.py:241-278` | 2026-11-11 | read-from-code |
| FACT-12 | Vision model list resolution: `AIPP_VISION_MODELS` then legacy `AIPP_VISION_MODEL`; default served model `openai/gpt-4o-mini` via OpenRouter | `src/core/vision.py:81-91`; `scripts/vision_people_probe.py:41` | 2026-11-11 | read-from-code |
| FACT-13 | Vision on the live Pallet frame: terse prompt 68.9% cell agreement / 0% unknown; explanatory prompt 36.7% / 41% unknown; hedge removed 54.7% | A/B `diag_prompt_ab.py`, one frozen image, 2026-10-01 | 2026-10-01 | measured |
| FACT-14 | People identification (gpt-4o-mini): 1/3 frames correct, 1/5 RAM person cells matched; model answered `girl@(1,4)` on all three frames incl. two where it is wrong (anchoring) | `scripts/vision_people_probe.py`, doc `docs/vision_people_findings.md` | 2026-10-01 | measured |
| FACT-15 | Console: stdlib ThreadingHTTPServer, port 8899 (`CONSOLE_PORT`), drives the SAME bridge 127.0.0.1:8770; 13 panels; tool surface cached 60 s | `~/aipp-console/server.py:39,58,728-739` | 2026-11-11 | read-from-code |
| FACT-16 | Console toggle endpoints accepted any truthy body until fixed: `_strict_bool` now accepts only real booleans + `true/false/1/0/yes/no/on/off`; `{"on":"false"}` returned live=False after fix (was impossible) | live probe + `server.py` commit `1d2c000` | 2026-10-01 | measured |
| FACT-17 | Ticker freeze: the live world degrades emulator video to a blank ~412-byte frame after ~4,000 stepped frames; bridge restart restores it | measured 2026-09-29/10-01 | 2026-10-01 | measured |
| FACT-18 | Boot checkpoint `data/boot.state` md5 `81e4ec4e8d1b62002bc78f619c5fc79c`, captured from the Blue SGB ROM; ROM mismatch warning exists | `md5sum data/boot.state`; `cron_runner.py:54-60,569-594` | 2026-11-11 | measured |
| FACT-19 | Default cycles 20 (`--cycles N` overrides) | `cron_runner.py:60` | 2026-11-11 | read-from-code |
| FACT-20 | Episode log proves: Sept run (28 eps) reached Viridian City; Oct 27 run reached only ep 4, final map Red's House 1F, log untouched since 2026-10-27 08:49 | `cron_logs/long_run_long_0927_llm2_episodes.jsonl`, `cron_logs/long_run_long_1027_0847_episodes.jsonl` | 2026-11-11 | measured |
| FACT-21 | Release v1.1.0 published (tag commit b846543, wheel 360,028 B, sdist 792,763 B, tag-CI success 41855748286) | releng tick 2026-11-04, `scripts/release_check.py` rc=0 | 2026-11-04 | measured |
| FACT-22 | Wheel packaging was broken (src flattened, no entry point); fixed `70c272b` "ship the src package intact" | releng board event 851 | 2026-11-04 | measured |
| FACT-23 | Monitoring: Prometheus `/metrics/prometheus` (c0e369e) + node_exporter textfile record from the cron lane (1957fe4) | board events 846 + MON-AIPP-1 closeout | 2026-11-04 | measured |
| FACT-24 | Console controls: 26 controls, 25 carry ids derived from function (`press-up`, `step-60`, `livebtn`); checkbox rows are data-addressed | `static/index.html`, id census 2026-10-01 | 2026-10-01 | measured |
| FACT-25 | Console panels self-refresh without interaction: strip 10:15:13→10:15:25, vision age 38s→50s, image src ticking, 57 panels correctly static | browser DOM sampling, 2026-10-01 | 2026-10-01 | measured |
| FACT-26 | Two drivers on one bridge fight; live ticker + agent runs must not overlap | measured 2026-09-29 | 2026-09-29 | measured |
