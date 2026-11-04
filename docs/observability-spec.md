# Observability Spec — ai-plays-poke

Status: **audit + spec, no code changed.** Every claim below cites a file:line or a command that was actually run.
Audit date: 2026-11-03. Product repo: `/home/kara/ai_plays_poke`.

---

## 0. Verdict

**Before: FLYING BLIND.**

The product has **zero** Prometheus instrumentation. Not "weak" — zero:

```
$ grep -rn "prometheus" src/ scripts/ tests/ cron_runner.py --include=*.py | wc -l
0
$ grep -in "prometheus\|opentelemetry\|statsd" requirements.txt pyproject.toml
(no output)
```

The static-scan hypothesis (`EMITS / python_prom=9 / otel=157`) was **wrong**, and the reason is a scan defect:
those hits come from the in-repo virtualenvs (`.venv/lib/python3.13/site-packages/...`,
`venv/lib/python3.11/site-packages/litellm/integrations/prometheus.py`) and from the
`.vfs/graph/.symbols_cache.json` symbol dump — never from product source. The single
`/metrics` string in real source is a JSON dashboard route, not an exposition endpoint (§1.2).

The product is **not** silent internally. It writes a genuinely rich per-run JSONL ledger
(`cron_logs/run_<id>.jsonl`, 442 rows in the newest run) that already contains most of what an
operator wants. The gap is purely the **transport**: nothing translates that ledger, or any live
state, into a scrapeable form. A human must `ssh` in and read JSON lines.

**After (target state of this spec):** one `/metrics` exposition endpoint on the existing
dashboard FastAPI app, backed by `prometheus_client`, carrying 5 P0 metrics; plus a
completed-run textfile record for the cron lane, which is short-lived and must not be scraped.

---

## 1. Proven current state

### 1.1 What the product is

Three distinct execution surfaces, all reading the same 10k-line game loop:

| Surface | Entry | Lifetime | HTTP? |
|---|---|---|---|
| Autonomous cron lane | `.coding-hermes/cron.sh` → `cron_runner.py` (`CYCLES = 20`, cron_runner.py:51-53) | short (one run, ≤20 cycles) | none |
| Operator dashboard | `python3 -m src.dashboard.main` (src/dashboard/main.py:562-580) | long-running (uvicorn, `PTP_DASHBOARD_PORT` default 8000) | yes, FastAPI |
| Single-cycle CLI | `run_cycle.py` | seconds | none |
| Emulator bridge (MCP/console backend) | `scripts/game_bridge.py`, loopback TCP 127.0.0.1 (scripts/game_bridge.py:511) | long-running | raw TCP, not HTTP-scrapable |
| Live viewer | `web_viewer.py` FastAPI (web_viewer.py:25) | long-running | yes, read-only log/screenshot viewer |

### 1.2 The `/metrics` route is NOT a metrics endpoint

`src/dashboard/main.py:355-360`:

```python
@app.get("/metrics")
async def get_metrics(_x_api_key: bool = Depends(verify_api_key), session_id: str = "default"):
    session = get_session(session_id)
    return session.get_metrics()
```

It returns **JSON** (`Content-Type: application/json`), it is **API-key gated**
(`Depends(verify_api_key)`), and its payload is session-scoped and volatile
(src/dashboard/main.py:224-260 — `ticks_per_second`, `total_ticks`, `success_rate`,
`avg_confidence`, `total_cost_estimate`, …). A Prometheus scrape would get a 401, and even
authorized would get a JSON object, not the text exposition format. Three further problems make
it unusable as-is:

- `total_cost = 0.0` is a **hardcoded literal** and is never incremented (src/dashboard/main.py:225) — the field `total_cost_estimate` is permanently `0.0`.
- All counters live in an **in-process dict** per session; a restart resets them, so a rate() over them is meaningless.
- It only knows about sessions the *dashboard* started. The cron lane (`cron_runner.py`) never touches this object, so the real 3am producer is invisible here.

### 1.3 No Prometheus client, no OTel

Not in source, not in `requirements.txt`, not in `pyproject.toml` `[project].dependencies`
(pyproject.toml:10-33). Nothing to uninstall; this is a greenfield addition.

### 1.4 Logging exists but is bypassed (the biggest surprise)

`src/core/logger.py` is a **890-line, production-quality logging framework**: `JSONFormatter` (:69),
`CategoryFilter` (:159), `RotationFileHandler` with gzip + retention (:179-268), a singleton
`AILogger` (:283) with per-category file handlers (`logs/api`, `logs/battles`, `logs/decisions`,
`logs/errors`, `logs/performance`) writing JSON lines — exactly the schema a log pipeline wants.

**It is dead code.** Repo-wide, the only non-test imports are:

```
$ grep -rn "from src.core.logger\|core.logger" --include=*.py src scripts tests cron_runner.py
src/core/failsafe.py:23:from src.core.logger import LogCategory      # enum only, no logging call
tests/test_logger.py:11
```

`grep -rn "get_logger\|AILogger()" src scripts cron_runner.py` → only `logger.py` itself.
The game loop uses `print` and a `safe_print` wrapper (cron_runner.py:18-23) and a module-level
`json.dumps(...)` append (cron_runner.py:5913). `import logging` / `getLogger` appear **nowhere** in
`cron_runner.py`, `scripts/game_bridge.py`, or `src/dashboard/main.py`.

Consequence, verified on disk: `logs/api/api.log`, `logs/battles/battles.log`,
`logs/decisions/decisions.log`, `logs/errors/errors.log` are **0 bytes, last written Jun 26**
(`ls -la logs/*/*.log`). They look like evidence that logging happens. It does not. Any dashboard
or alert built on those files is built on nothing.

### 1.5 What durable output actually exists

| Artifact | Path | Written by | Contents |
|---|---|---|---|
| Per-run decision ledger | `cron_logs/run_<run_id>.jsonl` | `cron_runner.py:950`, `_append_run_event` :5905-5914 (append + flush) | per-cycle decision rows, navigation, teacher escalation |
| End-of-run autonomy block | same file, `event: run_autonomy` (`_write_autonomy_row` :5395) | cron_runner.py | counters, ratios, rates |
| Episode summary | `cron_logs/*_episodes.jsonl` | `scripts/dist1_episodes.py`, `run_base1_baseline.py`, `benchmark_llm_vs_jev.py` | wall time, exit code, cost, map sequence, errors |
| Long-run status | `long_run_status.json` | `scripts/long_run.py` | goal, ladder, elapsed, totals |
| Screenshots | `screenshots/run_<id>/` | `_save_cycle_screenshot` :2252 | per-cycle PNG |
| DuckBrain | remote memory namespace | `_record_run_memory`, etc. | run lessons, world facts |

Rich, and **structurally unobservable**: nothing counts it, ages it, or exports it.

### 1.6 Observed real values (from `cron_logs/run_df17plan2.jsonl`, 442 rows)

These are what the metric names in §3 would have carried:

```json
{"event":"run_autonomy","decisions_total":80,"jev_answered":56,"escalated":40,
 "autonomy_ratio":0.7,"jev_transport_failures":0,"degraded":false,
 "teacher_escalations":{"count":64,"improved":31},
 "map_transitions_observed":26,"backtrack_events":48,"backtrack_rate":0.6076,
 "handoff_trigger_counts":{"gap":45,"confidence":19},"memory_navigation_hits":24}
```

and per-escalation `teacher_escalation` rows already carry `latency_s` (observed 3.99–7.85) and
`cost_usd` (observed 0.00116–0.00156).

---

## 2. What "healthy" means

The product is healthy when **all** of the following hold:

1. **It is up and working.** A cron run completes within its expected wall time and reports
   `run_completed: true`; the dashboard answers `/health` (src/dashboard/main.py:516-518).
2. **It is progressing.** Maps are being crossed (`map_transitions_observed` grows across runs) and
   the persistent goal marker advances up the ladder in `long_run_status.json`. A run with many
   decisions and zero map transitions over hours is the canonical failure — it is "working" by every
   in-process counter and has achieved nothing.
3. **It is not looping.** `backtrack_rate` stays below ~0.75; the reference run above sat at 0.6076.
4. **It is not quietly falling back.** `jev_transport_failure_rate` near 0; `degraded == false`;
   escalation/teacher load bounded.
5. **It is not spending without limit.** Teacher/model spend per run stays inside budget, and a
   credential or quota failure surfaces as an event rather than 20 silent cycles.
6. **Its emulator is truthful.** RAM tile readings agree with the frame; a desync shows up as an
   anomaly, not as "the agent wandered near a wall for six hours".
7. **Its data is not silently exploding or vanishing.** `cron_logs/` and `screenshots/` growth is
   known, and the run ledger is being written at all.

---

## 3. Metric catalogue

Naming: `<product>_<subsystem>_<thing>_<unit>`. Prefix is **`aipp_`** (short, stable; the repo's
own package name is `ptp-01x-pokemon-ai` but every internal identifier says `aipp` — e.g.
`src/ptp_cli`, `scripts/aipp_mcp.py` — so `aipp_` is the name operators will grep for).

Label budget is deliberately tiny. **Allowed labels only:** `mode` (decision_mode_family),
`pipeline` (`jev`/`memory_nav`/…), `outcome` (`ok`/`error`/`timeout`/`rate_limited`), `screen`,
`surface` (`cron`/`dashboard`/`bridge`), `class` (missing_class). **Forbidden:** run_id, cycle,
map_name, tile, prompt, model raw string, file path, any timestamp. Run identity goes to logs
(Loki), never to a Prometheus label — a per-run label turns one series into thousands.

### 3.1 Existing — already observable today

| Metric | Source | Available as a Prometheus series? |
|---|---|---|
| decisions per run | `run_autonomy.decisions_total` | **No** — JSONL only |
| autonomy ratio | `run_autonomy.autonomy_ratio` | No |
| escalation rate by class | `run_autonomy.escalation_rate_by_missing_class` | No |
| JEV transport failure rate | `run_autonomy.jev_transport_failure_rate` | No |
| map transitions | `run_autonomy.map_transitions_observed` | No |
| backtrack rate | `run_autonomy.backtrack_rate` | No |
| teacher latency / cost | `teacher_escalation.latency_s`, `.cost_usd` | No |
| tick rate / commands / success rate | `DashboardSession.get_metrics()` (src/dashboard/main.py:224-260) | No — JSON behind API key, restart-volatile |
| cost | `total_cost_estimate` | No — **hardcoded `0.0`** (src/dashboard/main.py:228) |

**Existing scrapeable series from this product: 0.**

### 3.2 Required — the catalogue

#### P0 — minimal viable set (first row of work)

| # | Metric | Type | Unit | Labels | The one question it answers |
|---|---|---|---|---|---|
| 1 | `aipp_run_cycles_total` | counter | cycles | `mode`,`pipeline` | Is the agent doing work right now, and at what rate? |
| 2 | `aipp_decision_duration_seconds` | histogram | seconds | `mode`,`pipeline` | How long does one decision take (the latency that gates everything)? |
| 3 | `aipp_model_calls_total` | counter | calls | `model_family`,`outcome` | How often do we call a model, and how often does it fail? |
| 4 | `aipp_model_cost_usd_total` | counter | USD | `model_family` | How much is this run costing, right now? |
| 5 | `aipp_runner_up` | gauge | 0/1 | `surface` | Is the producer alive at all? (staleness alarm) |

#### P1 — episode progress and quality

| # | Metric | Type | Unit | Labels | Question |
|---|---|---|---|---|---|
| 6 | `aipp_map_transitions_total` | counter | transitions | — | Is the agent actually getting somewhere? |
| 7 | `aipp_episode_decisions_total` | counter | decisions | `mode` | How much work per unit of progress? |
| 8 | `aipp_backtrack_events_total` | counter | events | — | Is it going in circles? |
| 9 | `aipp_run_completed_total` | counter | runs | `outcome` (`completed`,`error`,`gave_up`) | How often does a run end badly, and how? |
| 10 | `aipp_run_duration_seconds` | histogram | seconds | `outcome` | How long does a run take; is it drifting? |
| 11 | `aipp_teacher_escalations_total` | counter | escalations | `improved` (`true`,`false`) | Is the expensive tier earning its cost? |

#### P2 — model call cost/errors, in depth

| # | Metric | Type | Unit | Labels | Question |
|---|---|---|---|---|---|
| 12 | `aipp_model_call_duration_seconds` | histogram | seconds | `model_family` | Is the provider slow, or are we? |
| 13 | `aipp_model_tokens_total` | counter | tokens | `model_family`,`direction` | Is context growth eating the budget? |
| 14 | `aipp_model_retries_total` | counter | retries | `model_family`,`reason` | Are we failing over because of auth, quota or 5xx? |
| 15 | `aipp_credential_valid` | gauge | 0/1 | `key_name` | Which API key is dead? (see §5 on cardinality) |
| 16 | `aipp_decision_escalations_total` | counter | escalations | `class` | Which capability is missing? |

#### P3 — emulator integrity and data growth

| # | Metric | Type | Unit | Labels | Question |
|---|---|---|---|---|---|
| 17 | `aipp_emulator_desync_total` | counter | desyncs | — | Is RAM truth diverging from the frame? |
| 18 | `aipp_emulator_frame_stale_seconds` | gauge | seconds | — | Is the emulator advancing? |
| 19 | `aipp_screenshot_bytes` | gauge | bytes | — | Are screenshots accumulating without bound? |
| 20 | `aipp_runlog_bytes` | gauge | bytes | — | Is the run ledger growing per cycle as expected? |
| 21 | `aipp_runlog_last_write_timestamp_seconds` | gauge | unix seconds | — | Has the ledger stopped being written? |
| 22 | `aipp_bridge_requests_total` | counter | requests | `cmd`,`outcome` | Is the bridge serving, erroring, or wedged? |
| 23 | `aipp_bridge_active_connections` | gauge | connections | — | Are we leaking workers (the historical incident, scripts/game_bridge.py:455-462)? |

### 3.3 Where each signal must be emitted (the code that owns the state but never emits it)

| Metric | Owner site | Why it is a blind spot today |
|---|---|---|
| 1,2 | `_run_cycles` loop, `t0 = time.time()` (cron_runner.py:8302) and `elapsed = time.time() - t0` (:8934, :9765, :10023) | elapsed is computed, formatted into a `print`, and thrown away (:8936) |
| 3,12,13,14 | `log_api_call(model, duration_ms, input_tokens, output_tokens, cost, success)` (src/core/ai_client.py:102-118) | every field needed for four metrics arrives **as parameters** and is `print`ed |
| 4 | same; plus `teacher_escalation.cost_usd` (cron_runner.py, run log) | cost is summed nowhere globally; the dashboard's is hardcoded `0.0` |
| 6,7,8 | `_autonomy_counters` (cron_runner.py:4987-...) | counters computed at run **end** from rows, written to JSONL |
| 9,10 | `_write_autonomy_row` (:5395), episode writers in `scripts/` | terminal state never leaves the file |
| 11,16 | `_jev_teacher_escalation` (:3651), `escalation_class_of` (:3729) | escalation counted per-run in a dict |
| 15 | `_probe_api_key` (cron_runner.py:636), `_check_configured_keys` (:675) | probes at boot, result printed once, then forgotten |
| 17,18 | `_cycle_frame_hash` (:2247), `_ow_track_stuck` VOID/same-screen trackers (:8941-8966) | desync proxy is a threshold that triggers *recovery*, not a signal |
| 22,23 | `handle`/`worker` in scripts/game_bridge.py (:440-500) | `except Exception: pass` around every reply (:441-444) |

---

## 4. Exposure mechanism

### 4.1 Rule

- **Dashboard (`src/dashboard/main.py`) — long-running, already FastAPI → add a real `/metrics`.**
  Use `prometheus_client`'s `generate_latest` + `CONTENT_TYPE_LATEST` on a **new, unauthenticated,
  separate route**. Do not reuse, and do not break, the existing `/metrics` JSON contract
  (tests/test_dashboard.py:489-492 assert on it).
- **Cron lane (`cron_runner.py`) — short-lived, ≤20 cycles, exits → do NOT scrape it.**
  Write a **textfile-collector** record at run end (`--textfile-dir`, default
  `/var/lib/node_exporter/textfile_collector/aipp_run.prom`), so node_exporter (already on every
  host) picks up the completed-run counters. The fleet's stated preference is push
  (`remote_write`); a textfile is the push-equivalent for a process that is not alive when the
  scrape arrives, and it needs **no** change to `prometheus.yml`.
- **Bridge (`scripts/game_bridge.py`) — raw loopback TCP, not HTTP.** Do not invent an HTTP server
  for it. Export its counters through the dashboard process if both run on the same box, or accept
  textfile only. Keep it P3.
- **Dogfood rule:** every metric must increment on a real code path, not in a test-only hook. A
  counter that only moves under pytest is worse than none.

### 4.2 Route shape (reference implementation sketch — for the worker, not applied here)

```python
# src/dashboard/main.py — additive only
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

@app.get("/metrics/prometheus")        # NOT "/metrics" — that contract is taken
async def prometheus_metrics() -> Response:
    return Response(content=generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
```

Deliberate choice of `/metrics/prometheus` over `/metrics`: `tests/test_dashboard.py` asserts
`GET /metrics` is 401 without a key and JSON-shaped with one. Renaming would be a silent breaking
change to a tracked contract. The scrape config points at the new path.

### 4.3 Textfile record for the cron lane

Written by `cron_runner.py` in `_finalize_run` / after `_write_autonomy_row`, one file per run
(overwritten latest-wins, plus a `run_completed` counter that must be accumulated, not replaced —
read the prior file and add, or use a persistent counter file):

```
# TYPE aipp_run_completed_total counter
aipp_run_completed_total{outcome="completed"} 41
aipp_run_last_run_duration_seconds 183.4
aipp_run_last_decisions_total 80
aipp_run_last_map_transitions_total 26
aipp_run_last_backtrack_rate 0.6076
```

The `_last_*` gauges answer "what did the most recent run look like" — timestamps and run ids stay in
the log, not the metric.

---

## 5. Collection path

The fleet monitor (`fleet-monitor`) runs Prometheus 3.15 / Loki / Grafana / Alloy and agents **push**
via `remote_write`. This product is a **scrape-only** target, so it needs exactly one decision:

**Preferred (no monitoring-stack change):** write the textfile into node_exporter's textfile
collector directory on the host that runs the cron lane. node_exporter is already scraped; the series
arrive with the host's existing `host` label. Zero changes to
`/root/fleet-monitoring/prometheus/prometheus.yml`.

**If a direct scrape is wanted** (for the dashboard's live gauges, which a textfile cannot carry
while the process is up), that requires a new job in `prometheus.yml` — **an owner/host action, not
this product's**, and is out of scope here:

```yaml
  - job_name: ai-plays-poke
    static_configs:
      - targets: ["<dashboard-host>:8000"]
    metrics_path: /metrics/prometheus
    scrape_interval: 30s          # the product works in multi-second cycles; 15s is wasteful
    relabel_configs:
      - target_label: product
        replacement: ai-plays-poke
      - target_label: service
        replacement: dashboard
```

Required labels on every series as it reaches Prometheus: `host` (from the scrape target /
node_exporter), `product="ai-plays-poke"`, `service` (`dashboard` | `cron` | `bridge`).
`product` and `service` are applied by the scrape config's `relabel_configs`, **not** by the
application — the app should not know its own deployment name.

Cardinality budget: ≤40 live series. If a `prometheus.<product>_series_count` style guard exists in
the stack, the alarm is at 100 series. The single risk is metric 15 (`key_name`): the label must be a
**static enum of key names** (`OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `DUCKBRAIN_TOKEN` — the
names, never the values), not a rotated key identity.

Logs (not part of the metric path, but the same blind spot): `cron_logs/run_<id>.jsonl` and
stdout should be shipped by Alloy to Loki with `product="ai-plays-poke"`. Today they are local files
only. Fixing the dead `src/core/logger.py` (§1.4) would give that pipeline a JSON schema for free.

---

## 6. Verification — what a reviewer runs to prove each metric is live

**Step 1 — the endpoint exists and is Prometheus format**

```bash
curl -s -D- http://127.0.0.1:8000/metrics/prometheus | head -20
```
Done looks like: HTTP 200, `Content-Type: text/plain; version=0.0.4; charset=utf-8`, and at least
`# HELP aipp_runner_up` + one sample. If it returns JSON, the worker wired the wrong route.
Non-negotiable negative test — the old contract must be intact:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/metrics      # expect 401
```

**Step 2 — the metrics move under real work**

```bash
before=$(curl -s localhost:8000/metrics/prometheus | awk '/^aipp_run_cycles_total/{print $2}')
# run one real cycle (not a test): python3 cron_runner.py --cycles 5
sleep 5
after=$(curl -s localhost:8000/metrics/prometheus | awk '/^aipp_run_cycles_total/{print $2}')
test "$after" -gt "$before" && echo MOVED
```
Done: `MOVED`. A counter that prints but never increments fails here, which is the whole point.

**Step 3 — PromQL, after the series reach Prometheus** (Grafana Explore on `fleet-monitor`):

```promql
# is it alive and working? (P0 #1)
sum by (pipeline) (rate(aipp_run_cycles_total[10m]))

# decision latency p95 (P0 #2)
histogram_quantile(0.95, sum by (le,mode) (rate(aipp_decision_duration_seconds_bucket[10m])))

# model error ratio (P0 #3)
sum(rate(aipp_model_calls_total{outcome!="ok"}[30m]))
  / sum(rate(aipp_model_calls_total[30m]))

# spend per hour (P0 #4)
sum(increase(aipp_model_cost_usd_total[1h]))

# stale producer alarm (P0 #5) — alert if < 1 for 15m
max_over_time(aipp_runner_up[15m])

# progress vs effort (P1 #6,7) — the "working but achieving nothing" alarm
sum(increase(aipp_map_transitions_total[6h])) == 0
  and sum(increase(aipp_episode_decisions_total[6h])) > 100

# dead credential (P2 #15)
min by (key_name) (aipp_credential_valid) == 0

# ledger stopped writing (P3 #21)
time() - aipp_runlog_last_write_timestamp_seconds > 3600
```

**Step 4 — textfile lane**

```bash
ls -l /var/lib/node_exporter/textfile_collector/aipp_run.prom
```
then from Prometheus: `aipp_run_completed_total{outcome="completed"}` → a non-zero sample with the
right `host` label. Done: series present **and** `aipp_run_last_decisions_total` equal to the
`decisions_total` in the newest `cron_logs/run_*.jsonl` (cross-check the number, not just the presence).

**Done definition for the whole spec:** all five P0 queries return data, Step 2 returns `MOVED`, and
the §1.4 dead-logger state is either fixed or explicitly re-classified as dead (see §8).

---

## 7. Deliberately NOT instrumented

| Not instrumented | Why |
|---|---|
| `run_id`, `cycle`, `map_name`, `tile`, `prompt`, model raw string as labels | Unbounded cardinality. A 20-cycle run with per-run labels makes a new series every hour forever. This is what Loki is for. |
| per-request user/session labels | Single-operator product; adds cardinality, answers nothing. |
| Screenshot content / vision verdicts as metrics | Semantic content, not health. Belongs in the run log; already there (`vision_usage`, `screen`). |
| Grouping by `missing_class` beyond a fixed enum | `missing_class` is already an enum (`none`, `map_topology`, …); anything free-form must be bucketed to `other` before it becomes a label. |
| `logs/api/*.log` etc. ingestion | The files are empty and the writer is dead (§1.4). Instrumenting them would create a metric measuring a phantom. |
| Exact per-token cost per model | Cost is already summed with `cost_usd` per call across all clients (src/core/ai_client.py:102-118). A second derivation would drift. |

---

## 8. Known risks for the implementing worker

1. **`/metrics` is taken.** Use a new path. Do not modify `tests/test_dashboard.py:122,489-492`.
2. **The cron lane must not try to serve HTTP.** It exits; a scrape will never catch it. Textfile only.
3. **`src/core/logger.py` is a trap.** It looks like the logging solution and is 100% unwired. Do not
   assume it runs. If step 1 of the work "fixes logging" by calling `get_logger()`, verify the files
   actually grow (`wc -c logs/errors/errors.log`) — that is a separate, larger piece of work than metrics.
4. **`total_cost_estimate` is hardcoded `0.0`** (src/dashboard/main.py:225). Do not wire metric 4 to it
   — it would export a dead zero with a live-looking `# HELP`. Wire it to the `log_api_call` cost
   parameter path, and if the dashboard field is to be fixed, fix it as a deliberate change with its
   own evidence.
5. **Do not add a scrape job yourself.** `prometheus.yml` is the monitoring stack's; the textfile path
   needs no change at all.
6. **Metric 17 (desync) has no clean primitive yet.** There is a frame-hash (:2247) and stuck trackers
   (:8941) but no RAM-vs-frame comparison. Implement it as a bounded proxy (repeated frame hash with
   unchanged RAM tile) and document the proxy, or defer it — do not claim a true desync detector exists.

---

## 9. Open / unverified items

| Item | Why unverified |
|---|---|
| Whether the dashboard is actually running anywhere right now | No network access from the audit host; no process check was possible. The `/health` and `/metrics/prometheus` curl checks are unrun. |
| Actual Prometheus series count for this product today | Requires querying Prometheus on `fleet-monitor`; not reachable from here. Static analysis says 0. |
| Real desync rate | No sensor exists (§8.6). The `[VOID]` print (:8951-8953) is the closest proxy and is not persisted. |
| Whether any external dashboard already reads `cron_logs/*.jsonl` | Only `web_viewer.py` (`/api/run/{run_id}/log`) was found reading run logs; no evidence of a fleet-side consumer either way. |
| Whether `logs/*/*.log` were ever populated | Files are 0 bytes with Jun 26 mtimes; whether they were ever non-empty is not recoverable from the repo. |
