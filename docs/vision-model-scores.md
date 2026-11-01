# Vision model scores (VIS-MODEL-1)

Scoring uses the player-centred 9x9 grid (cell x=72+(c-4)*16, y=64+(r-4)*16), with exact class agreement. Total score includes all 81 cells. Structure score includes only reference cells that are neither floor (`.`) nor unknown (`?`); `B` is blocked and digits are objects. This prevents a mostly-floor frame from making an all-floor answer look structurally strong.

| Model | Latency | Tokens | Total-cell score | Structure score | Evidence |
|---|---:|---:|---:|---:|---|
| openai/gpt-4o-mini | 4.710 s (recorded grid call) / 3.149 s (historical live smoke) | 27,644 (recorded grid call) / 26,160 (historical live smoke) | 33.3% | 5.6% | `data/vision_model_runs.jsonl`; scorer output, 1 sample |
| amazon/nova-lite-v1 | 1.701 s (recorded grid call) / 2.196 s (historical live smoke) | 3,428 (recorded grid call) / 1,956 (historical live smoke) | 77.8% | 0.0% | `data/vision_model_runs.jsonl`; scorer output, 1 sample |
| syn:large:vision (Kimi K3) | 97 s (historical) | 5,860 (historical) | 62.2% (historical) | unmeasured | Prior measurement supplied with task brief; not called by this run |
| nova-lite (prior model alias) | unmeasured | unmeasured | unmeasured | unmeasured | Prior observation: floor-heavy data inflated raw match; exact measurement/model ID not supplied |

## Measurement boundaries

The current grid records were produced from live bridge observations with the same RAM 9x9 map and the same scoring implementation. The two successfully shaped model answers were obtained in separate captures after model responses intermittently violated the required grid dimensions; therefore these scores compare models on the observed RAM map, but are not a same-image paired trial. Each retained row is a real model response with measured wall latency and provider-reported total tokens. A response that does not return exactly 9 strings of 9 characters is not scored or reshaped. Unavailable field (failed blueprint shape; intentionally not scored): `amazon/nova-lite-v1` returned non-9x9 grids on other calls, `openai/gpt-5.6-luna` returned a missing/non-9x9 grid, `openai/gpt-4o` returned one 8-character row, and `google/gemma-3-12b-it` returned 19-character rows. These failures are not represented as successful score rows.

The score table's current total-cell and structure scores, latency, and tokens are calculated from `data/vision_model_runs.jsonl` by `./venv/bin/python scripts/vision_model_score.py`. The `VisionClient` screen-state response in the existing E2E smoke test is distinct from these blueprint grid predictions and does not supply terrain labels. Historical results remain explicitly marked historical; fields without a defensible current measurement are named `unmeasured`.

## Trace

ch:trace row=VIS-MODEL-1 spec=.coding-hermes/board/tasks.jsonl#VIS-MODEL-1 wave=.coding-hermes/waves/ai-plays-poke-foreman-2026-11-01-12-09-08.json#VIS-MODEL-1-R2 test=tests/test_vision_model_e2e.py+tests/test_vision_model_registry.py doc=docs/vision-model-scores.md prompt=none:dispatch-brief-file evidence=data/vision_model_runs.jsonl witness=terminal:scorer-prints-2-models verdict=none:judge-runs-post-merge commit=none:self-referential-hash memory=none:foreman-writes
STATUS: complete
TIER: T3 (invoked and observed: full pytest suite, scorer CLI, live two-model record run)
EVIDENCE: data/vision_model_runs.jsonl
