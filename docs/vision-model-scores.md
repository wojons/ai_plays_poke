# Vision model scores (VIS-MODEL-1)

Scoring uses the player-centred 9x9 grid (cell x=72+(c-4)*16, y=64+(r-4)*16), with exact class agreement. Total score includes all 81 cells. Structure score includes only reference cells that are neither floor (`.`) nor unknown (`?`); `B` is blocked and digits are objects. This prevents a mostly-floor frame from making an all-floor answer look structurally strong.

| Model | Latency | Tokens | Total-cell score | Structure score | Evidence |
|---|---:|---:|---:|---:|---|
| openai/gpt-4o-mini | 3.149 s (live smoke) / 2.4 s (prior grid run) | 26,160 (live smoke) / 34 (prior grid run) | 72.2% (prior grid run) | unmeasured | Live test used `play_frames/PG_6.png`; prior grid measurement supplied with task brief |
| amazon/nova-lite-v1 | 2.196 s (live smoke) | 1,956 | unmeasured | unmeasured | Live test used `play_frames/PG_6.png`; no verified 9x9 labels |
| syn:large:vision (Kimi K3) | 97 s (prior grid run) | 5,860 | 62.2% (prior grid run) | unmeasured | Prior measurement supplied with task brief; not called by this run |
| nova-lite (prior model alias) | unmeasured | unmeasured | unmeasured | unmeasured | Prior observation: floor-heavy data inflated raw match; exact measurement/model ID not supplied |

## Measurement boundaries

The historical figures above are preserved as supplied rather than represented as new runs. The current `VisionClient` returns screen-state JSON, not a 9x9 terrain grid. The live end-to-end test records per-model response latency, provider usage, and model selection but cannot derive a defensible live grid agreement score. Every unavailable value is explicitly marked `unmeasured`.

To score grid recordings, put JSONL records containing `model`, `expected_grid`, and `predicted_grid` (optionally `latency_seconds` and `tokens`) in `data/vision_model_runs.jsonl`, then run `./venv/bin/python scripts/vision_model_score.py`. The scorer prints mean total-cell and structure scores per model. A labeled grid is required; no score is inferred from an unlabeled screenshot.
