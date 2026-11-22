# Observability Spec — ai-plays-poke

Status: **audit history retained; current state: instrumented.** The audit below is
preserved as written on 2026-11-03 (its own status line said "audit + spec, no code
changed"). MON-AIPP-1/2/3 have since shipped the endpoint, the metrics, and the cron-lane
textfile record this spec proposed — so §0–§3 describe the 2026-11-03 tree, not today's.
Read the dated UPDATE blocks as the current state; nothing historical was rewritten.
Every claim cites a file:line or a command that was actually run, and where a command's
answer has changed, the re-run is shown beside the original.
Audit date: 2026-11-03. Re-verified against tree `031d7b3`: 2026-11-17. Line numbers in the dated
2026-11-17 blocks were re-derived against `f3d7774` on 2026-11-18 (DOC-027), because the tree kept
moving under them.
Citations inside the 2026-11-03 body (§0–§3) are audit history measured on that day's tree; the
dated UPDATE blocks are the ones that resolve against the current tree.
**Citation re-derivation (2026-11-18, DOC-027):** the offset arithmetic this page used to carry
("`metrics.py` +45 lines at :122, `cron_runner.py` +3 at :48, +4 at :8585, +9 at :8461, +94 at
:8680, +4 at :9004, +3 at :10550") is **superseded** — two more waves of work landed after it was
written, so adding those offsets no longer lands on the right line. Every `<file>.py:<line>`
citation on this page was instead resolved against the tree with a throwaway script: the cited
line is read back and must contain the symbol the page names for it. Only **line pointers** were
corrected — no observation, verdict, or quoted command output was rewritten; where a recorded
command's answer moved, the re-run is shown beside the original. Re-run the same check after any
change to `cron_runner.py`, `scripts/game_bridge.py` or `src/observability/metrics.py`, because
absolute line numbers do not survive edits.
Product repo: the checkout this page lives in (`docs/`'s parent — `git rev-parse --show-toplevel`).

---

## UPDATE 2026-11-17 — what has shipped since this audit

Re-measured against the tree at `031d7b3`. Numbers below are from the commands in §0,
re-run verbatim.

| Original command (2026-11-03) | Then | Now (2026-11-17) |
|---|---|---|
| `grep -rn "prometheus" src/ scripts/ tests/ cron_runner.py --include=*.py \| wc -l` | `0` | `13` |
| `grep -in "prometheus\|opentelemetry\|statsd" requirements.txt pyproject.toml` | (no output) | 3 lines: `requirements.txt:48` (comment), `requirements.txt:49` `prometheus-client`, `pyproject.toml:30` `"prometheus-client",  # Prometheus metrics endpoint and runtime instrumentation` |

**The scrape endpoint exists.** `src/dashboard/main.py:358` declares
`@app.get("/metrics/prometheus")`; the handler at `:359-369` returns
`generate_latest(REGISTRY)` with `CONTENT_TYPE_LATEST`. It carries **no** `Depends(...)`,
so it is unauthenticated as §4.1 required, and the old JSON `/metrics` contract is
untouched (now at `src/dashboard/main.py:370`).

**Eleven metric families are defined** in `src/observability/metrics.py`, and every one of
them is incremented from a production code path (not a test hook — §4.1's dogfood rule):

| # (catalogue §3.2) | Metric | Definition | Production increment site |
|---|---|---|---|
| 1 | `aipp_run_cycles_total` | metrics.py:19 | `observe_cycle()` metrics.py:331 ← cron_runner.py:8581 |
| 2 | `aipp_decision_duration_seconds` | metrics.py:25 | `observe_decision_seconds()` metrics.py:338 ← cron_runner.py:9311 |
| 3 | `aipp_model_calls_total` | metrics.py:31 | `observe_model_call()` metrics.py:345 ← src/core/ai_client.py:133 |
| 4 | `aipp_model_cost_usd_total` | metrics.py:37 | `observe_model_call()` metrics.py:345 (the `_MODEL_COST.inc` branch at :351) ← src/core/ai_client.py:133 |
| 5 | `aipp_runner_up` | metrics.py:43 | `set_runner_up()` metrics.py:420 ← cron_runner.py:7934 (`surface="cron"`), src/dashboard/main.py:119 (`surface="dashboard"`) |
| 6 | `aipp_map_transitions_total` | metrics.py:58 | `observe_run_end()` metrics.py:533 (its `_MAP_TRANSITIONS.inc` at :567) ← `_publish_run_metrics()` cron_runner.py:5345, called at :7975 (error close) and :10546 (normal close) |
| 7 | `aipp_episode_decisions_total` | metrics.py:63 | `observe_run_end()` — its `_EPISODE_DECISIONS.inc` at metrics.py:564 (same call sites) |
| 8 | `aipp_backtrack_events_total` | metrics.py:69 | `observe_run_end()` — its `_BACKTRACK_EVENTS.inc` at metrics.py:568 (same call sites) |
| 9 | `aipp_run_completed_total` | metrics.py:74 | `observe_run_end()` — its `_RUN_COMPLETED.inc` at metrics.py:560 (same call sites) |
| 10 | `aipp_run_duration_seconds` | metrics.py:80 | `observe_run_end()` — its `_RUN_DURATION.observe` at metrics.py:561 (same call sites) |
| 11 | `aipp_teacher_escalations_total` | metrics.py:86 | `observe_run_end()` — its two `_TEACHER_ESCALATIONS` increments at metrics.py:569-570 (same call sites) |

**Not shipped: catalogue #16** (`aipp_decision_escalations_total` — the one P2 row outside
MON-AIPP-4's scope). Its neighbours #12–#15 shipped with MON-AIPP-4 (feed points in §3.2), and
all seven P3 rows (#17–#23) shipped with MON-AIPP-5 — see the next block. §3.2 carries a
per-row `Status` column so a reader cannot mistake the catalogue for an inventory.

**MON-AIPP-5 added the seven P3 families** (definitions in `src/observability/metrics.py`,
one production feed site each — table in §3.2):

| # | Metric | Definition | Production feed site |
|---|---|---|---|
| 17 | `aipp_emulator_desync_total` | metrics.py:132 | `_track_emulator_integrity` cron_runner.py:8680 ← `_cycle_header` :8993 — **documented proxy**, §3.3.1 |
| 18 | `aipp_emulator_frame_stale_seconds` | metrics.py:137 | same call (`observe_emulator_frame` metrics.py:472, monotonic clock) |
| 19 | `aipp_screenshot_bytes` | metrics.py:142 | `_publish_data_growth_metrics` cron_runner.py:8728 (per cycle :8585, run end :10550) |
| 20 | `aipp_runlog_bytes` | metrics.py:147 | same call |
| 21 | `aipp_runlog_last_write_timestamp_seconds` | metrics.py:152 | same call — the ledger's `st_mtime`, deliberately not materialized at import (:263) |
| 22 | `aipp_bridge_requests_total` | metrics.py:157 | `handle()`'s `finally` scripts/game_bridge.py:488 + the busy rejection :657 |
| 23 | `aipp_bridge_active_connections` | metrics.py:163 | `serve()` worker pool :593/:607, 0 at bind :578 and shutdown :696 |

**Cron lane:** the node_exporter textfile record is live — see the UPDATE block in §4.3
for the exact path, fields, and write ordering. The bridge's own textfile
(`aipp_bridge.prom`) is described in §4.1.

---

## 0. Verdict (2026-11-03 reading — superseded, see the UPDATE block above)

**Before: FLYING BLIND.**

> Dated framing: everything in §0 through §3 is the 2026-11-03 audit. The endpoint and the
> eleven metric families now exist — the measurements are in the UPDATE block at the top of
> this file. The text below is kept verbatim so the audit history stays checkable.

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

**UPDATE 2026-11-17:** that target state is now the shipped state — 5 P0 + 6 P1 series on
`GET /metrics/prometheus`, plus the cron-lane textfile record. The 2026-11-03 verdict above
is retained verbatim as the audit-of-record; see the UPDATE block at the top of this file
for the measurements.

---

## 1. Proven current state

### 1.1 What the product is

Three distinct execution surfaces, all reading the same 10k-line game loop:

| Surface | Entry | Lifetime | HTTP? |
|---|---|---|---|
| Autonomous cron lane | `.coding-hermes/cron.sh` → `cron_runner.py` (`CYCLES = 20`, cron_runner.py:66-68) | short (one run, ≤20 cycles) | none |
| Operator dashboard | `python3 -m src.dashboard.main` (src/dashboard/main.py:577-580) | long-running (uvicorn, `PTP_DASHBOARD_PORT` default 8000) | yes, FastAPI |
| Single-cycle CLI | `run_cycle.py` | seconds | none |
| Emulator bridge (MCP/console backend) | `scripts/game_bridge.py`, loopback TCP 127.0.0.1 (`srv.bind(("127.0.0.1", port))`, scripts/game_bridge.py:617) | long-running | raw TCP, not HTTP-scrapable |
| Live viewer | `web_viewer.py` FastAPI (web_viewer.py:25) | long-running | yes, read-only log/screenshot viewer |

### 1.2 The `/metrics` route is NOT a metrics endpoint

`src/dashboard/main.py:370-375`:

```python
@app.get("/metrics")
async def get_metrics(_x_api_key: bool = Depends(verify_api_key), session_id: str = "default"):
    session = get_session(session_id)
    return session.get_metrics()
```

It returns **JSON** (`Content-Type: application/json`), it is **API-key gated**
(`Depends(verify_api_key)`), and its payload is session-scoped and volatile
(src/dashboard/main.py:227-262 — `ticks_per_second`, `total_ticks`, `success_rate`,
`avg_confidence`, `total_cost_estimate`, …). A Prometheus scrape would get a 401, and even
authorized would get a JSON object, not the text exposition format. Three further problems make
it unusable as-is:

- `total_cost = 0.0` is a **hardcoded literal** and is never incremented (src/dashboard/main.py:228) — the field `total_cost_estimate` is permanently `0.0`.
- All counters live in an **in-process dict** per session; a restart resets them, so a rate() over them is meaningless.
- It only knows about sessions the *dashboard* started. The cron lane (`cron_runner.py`) never touches this object, so the real 3am producer is invisible here.

> **UPDATE 2026-11-17:** this section is still accurate about `/metrics` — same JSON
> contract, same API-key gate, same hardcoded `total_cost`. Two things moved. (a) The route
> the block above quotes as `:355-360` now sits at `src/dashboard/main.py:370-376`; the
> contract is unchanged and `tests/test_dashboard.py` still asserts 401-without-key. (b) A
> **separate, unauthenticated** route `GET /metrics/prometheus` now serves the Prometheus
> text exposition format (`src/dashboard/main.py:358-369`) — the fix this section's
> criticism called for. Nothing above was rewritten.

### 1.3 No Prometheus client, no OTel (2026-11-03 reading; superseded — see UPDATE)

Not in source, not in `requirements.txt`, not in `pyproject.toml` `[project].dependencies`
(pyproject.toml:10-33). Nothing to uninstall; this is a greenfield addition.

> **UPDATE 2026-11-17:** `prometheus-client` is now a declared dependency
> (`requirements.txt:49`, `pyproject.toml:30`) and imported by
> `src/observability/metrics.py:3` and `src/dashboard/main.py:35`. OpenTelemetry and
> statsd are still absent — the §0 dependency grep, re-run, matches `prometheus` only.
> The heading and body above are the audit-day reading, kept as written.

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
`json.dumps(event, default=str) + "\n"` append + flush (cron_runner.py:6147-6148). `import logging` / `getLogger` appear **nowhere** in
`cron_runner.py`, `scripts/game_bridge.py`, or `src/dashboard/main.py`.

Consequence, verified on disk: `logs/api/api.log`, `logs/battles/battles.log`,
`logs/decisions/decisions.log`, `logs/errors/errors.log` are **0 bytes, last written Jun 26**
(`ls -la logs/*/*.log`). They look like evidence that logging happens. It does not. Any dashboard
or alert built on those files is built on nothing.

### 1.5 What durable output actually exists

| Artifact | Path | Written by | Contents |
|---|---|---|---|
| Per-run decision ledger | `cron_logs/run_<run_id>.jsonl` | `LOG_DIR` (`cron_runner.py:967`), `_append_run_event` :6139-6148 (append + flush) | per-cycle decision rows, navigation, teacher escalation |
| End-of-run autonomy block | same file, `event: run_autonomy` (`_write_autonomy_row` :5629) | cron_runner.py | counters, ratios, rates |
| Episode summary | `cron_logs/*_episodes.jsonl` | `scripts/dist1_episodes.py`, `run_base1_baseline.py`, `benchmark_llm_vs_jev.py` | wall time, exit code, cost, map sequence, errors |
| Long-run status | `long_run_status.json` | `scripts/long_run.py` | goal, ladder, elapsed, totals |
| Screenshots | `screenshots/run_<id>/` | `_save_cycle_screenshot` :2272 | per-cycle PNG |
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
   `run_completed: true`; the dashboard answers `/health` (src/dashboard/main.py:531-532).
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
| tick rate / commands / success rate | `DashboardSession.get_metrics()` (src/dashboard/main.py:227-262) | No — JSON behind API key, restart-volatile |
| cost | `total_cost_estimate` | No — **hardcoded `0.0`** (src/dashboard/main.py:260) |

**Existing scrapeable series from this product: 0.** (Audit-day reading, 2026-11-03.)

> **UPDATE 2026-11-17:** six of the nine signals in the table above now have a series.
> `decisions per run` → `aipp_episode_decisions_total`; `map transitions` →
> `aipp_map_transitions_total`; `backtrack rate` → `aipp_backtrack_events_total` (the
> event counter, **not** the rate — the rate is not exported); `teacher latency / cost` →
> `aipp_teacher_escalations_total` and `aipp_model_cost_usd_total` (per-model cost, not
> per-teacher-call); `escalation rate by class` and `JEV transport failure rate` still have
> **no** series; `tick rate / commands / success rate` remain JSON-only behind the API key;
> `cost` (`total_cost_estimate`) is still hardcoded `0.0` and is **not** what metric #4
> reads. The count sentence and the "No" column above are left as the audit-day record.

### 3.2 Required — the catalogue

#### P0 — minimal viable set (first row of work)

| # | Metric | Type | Unit | Labels | The one question it answers | Status (2026-11-17) |
|---|---|---|---|---|---|---|
| 1 | `aipp_run_cycles_total` | counter | cycles | `mode`,`pipeline` | Is the agent doing work right now, and at what rate? | **SHIPPED** — metrics.py:19 |
| 2 | `aipp_decision_duration_seconds` | histogram | seconds | `mode`,`pipeline` | How long does one decision take (the latency that gates everything)? | **SHIPPED** — metrics.py:25 |
| 3 | `aipp_model_calls_total` | counter | calls | `model_family`,`outcome` | How often do we call a model, and how often does it fail? | **SHIPPED** — metrics.py:31 |
| 4 | `aipp_model_cost_usd_total` | counter | USD | `model_family` | How much is this run costing, right now? | **SHIPPED** — metrics.py:37 |
| 5 | `aipp_runner_up` | gauge | 0/1 | `surface` | Is the producer alive at all? (staleness alarm) | **SHIPPED** — metrics.py:43 |

#### P1 — episode progress and quality

| # | Metric | Type | Unit | Labels | Question | Status (2026-11-17) |
|---|---|---|---|---|---|---|
| 6 | `aipp_map_transitions_total` | counter | transitions | — | Is the agent actually getting somewhere? | **SHIPPED** — metrics.py:58 |
| 7 | `aipp_episode_decisions_total` | counter | decisions | `mode` | How much work per unit of progress? | **SHIPPED** — metrics.py:63 |
| 8 | `aipp_backtrack_events_total` | counter | events | — | Is it going in circles? | **SHIPPED** — metrics.py:69 |
| 9 | `aipp_run_completed_total` | counter | runs | `outcome` (`completed`,`error`,`gave_up`) | How often does a run end badly, and how? | **SHIPPED** — metrics.py:74 |
| 10 | `aipp_run_duration_seconds` | histogram | seconds | `outcome` | How long does a run take; is it drifting? | **SHIPPED** — metrics.py:80 |
| 11 | `aipp_teacher_escalations_total` | counter | escalations | `improved` (`true`,`false`) | Is the expensive tier earning its cost? | **SHIPPED** — metrics.py:86 |

#### P2 — model call cost/errors, in depth

| # | Metric | Type | Unit | Labels | Question | Status (2026-11-17) |
|---|---|---|---|---|---|---|
| 12 | `aipp_model_call_duration_seconds` | histogram | seconds | `model_family` | Is the provider slow, or are we? | **SHIPPED (MON-AIPP-4)** — defined src/observability/metrics.py:99-104; observed `observe_model_duration` src/core/ai_client.py:134 |
| 13 | `aipp_model_tokens_total` | counter | tokens | `model_family`,`direction` (`input`\|`output`) | Is context growth eating the budget? | **SHIPPED (MON-AIPP-4)** — defined src/observability/metrics.py:105-110; observed `observe_model_tokens` src/core/ai_client.py:135 |
| 14 | `aipp_model_retries_total` | counter | retries | `model_family`,`reason` (`auth`\|`quota`\|`5xx`\|`timeout`) | Are we failing over because of auth, quota or 5xx? | **SHIPPED (MON-AIPP-4)** — defined src/observability/metrics.py:111-116; observed `observe_model_retry` src/core/ai_client.py:799 (`quota`), :808 (`5xx`), :892 (`auth`/`timeout`) |
| 15 | `aipp_credential_valid` | gauge | 0/1 | `key_name` (static enum of probed env-var NAMES) | Which API key is dead? (see §5 on cardinality) | **SHIPPED (MON-AIPP-4)** — defined src/observability/metrics.py:117-122; observed cron_runner.py:711 |
| 16 | `aipp_decision_escalations_total` | counter | escalations | `class` | Which capability is missing? | NOT SHIPPED — outside MON-AIPP-4 |

Feed points for 12-15, as shipped:

| Family | Fed from | Label mapping |
|---|---|---|
| 12 | `log_api_call` (`src/core/ai_client.py:109`) on every success, plus the exhausted-retry path at :916 so a dead call still carries its wall time | `model_family()` (`metrics.py:286`) — never a raw model string |
| 13 | same `log_api_call` call (both directions from one call, so output/input needs no second path) | `direction` from the closed pair `input`/`output` |
| 14 | counted where the retry is DECIDED: `_handle_retry_response` (`ai_client.py:780`) for 429/`quota` and >=500/`5xx`; the loop's `except` branch (…:892) for 401\|403/`auth` and socket timeout/`timeout`, classified from the status the branch already holds (`_retry_reason_for_status`, …:150) or the exception class (`_retry_reason_for_exception`, …:166) | closed enum `auth`/`quota`/`5xx`/`timeout`; an unattributable failure is NOT counted rather than bucketed into a guess |
| 15 | `_check_configured_keys` (`cron_runner.py:690`) after each probe — live → 1, dead → 0 | static enum of the env-var NAMES in `cron_runner._KEY_PROBE_URLS` (`metrics.py:186-191`); a test pins the two sets equal |

#### P3 — emulator integrity and data growth

| # | Metric | Type | Unit | Labels | Question | Status (2026-11-17) |
|---|---|---|---|---|---|---|
| 17 | `aipp_emulator_desync_total` | counter | desyncs | — | Is RAM truth diverging from the frame? | **SHIPPED (MON-AIPP-5) — PROXY, not a detector** — defined metrics.py:132; observed `_track_emulator_integrity` cron_runner.py:8680 ← `_cycle_header` cron_runner.py:8993. Semantics in §3.3.1 and §8.6. |
| 18 | `aipp_emulator_frame_stale_seconds` | gauge | seconds | — | Is the emulator advancing? | **SHIPPED (MON-AIPP-5)** — defined metrics.py:137; observed `observe_emulator_frame` metrics.py:472 ← the same tracker call (monotonic clock). |
| 19 | `aipp_screenshot_bytes` | gauge | bytes | — | Are screenshots accumulating without bound? | **SHIPPED (MON-AIPP-5)** — defined metrics.py:142; observed `_publish_data_growth_metrics` cron_runner.py:8728 (per cycle cron_runner.py:8585, run end cron_runner.py:10550). |
| 20 | `aipp_runlog_bytes` | gauge | bytes | — | Is the run ledger growing per cycle as expected? | **SHIPPED (MON-AIPP-5)** — same definition/paths as row 19. |
| 21 | `aipp_runlog_last_write_timestamp_seconds` | gauge | unix seconds | — | Has the ledger stopped being written? | **SHIPPED (MON-AIPP-5)** — ledger **mtime**, not "now": the gauge is minted only when a ledger exists (`_RUNLOG_LAST_WRITE`, metrics.py:263), so an unwritten ledger leaves the §6 query empty instead of alarming on a 1970 stamp. |
| 22 | `aipp_bridge_requests_total` | counter | requests | `cmd`,`outcome` | Is the bridge serving, erroring, or wedged? | **SHIPPED (MON-AIPP-5)** — defined metrics.py:157; observed `handle()`'s single exit scripts/game_bridge.py:488 (every path counts exactly once, including a connection that sent nothing). |
| 23 | `aipp_bridge_active_connections` | gauge | connections | — | Are we leaking workers (the incident `handle()`'s own docstring records at scripts/game_bridge.py:429-433)? | **SHIPPED (MON-AIPP-5)** — defined metrics.py:163; observed `set_bridge_active_connections` around the fixed worker pool scripts/game_bridge.py:593/607, forced to 0 at bind (:578) and at shutdown (:696). |

Status column added 2026-11-17: `SHIPPED` means a metric family with that exact name is
defined in `src/observability/metrics.py` and incremented from a production path (verified
per-metric in the UPDATE block at the top of this file). `NOT SHIPPED` means it is still a
proposal — grep `src/observability/metrics.py` for the name and you get nothing.

**P3 feed points, as shipped** (line numbers re-derived against this page's own commit):

| Family | Fed from | Label mapping / measurement |
|---|---|---|
| 17 | `_track_emulator_integrity` (cron_runner.py:8680), called from `_cycle_header` (cron_runner.py:8993) — the one place both the frame hash (`_cycle_capture`, :8614) and the RAM observation (`_cycle_observe`, :8635) exist, on every screen path including the RAM-reader branch that returns before the cartographer cache | no labels; increments only when the frame hash **and** the RAM tile triple are both unchanged from the previous cycle (§3.3.1) |
| 18 | same call | monotonic `now - last_changed_at`, reset to 0 on the cycle the hash changes — a wall-clock step cannot fake freshness |
| 19,20,21 | `_publish_data_growth_metrics` (cron_runner.py:8728) per cycle and once at run end **after** `log_file.close()` | direct `stat`/`scandir` of `screenshots/run_<id>/` and `cron_logs/run_<id>.jsonl`; the timestamp is the ledger's `st_mtime` |
| 22 | `handle()`'s single exit (scripts/game_bridge.py:488) plus the "server busy" rejection in the accept loop (:657) — connection counting is in the worker pool (:593/:607) | `cmd` = a verb `_dispatch` serves, else `unknown`; `none` when no request line arrived. `outcome` ∈ `ok`,`error`,`unauthorized`,`busy`,`invalid`,`send_failed`,`empty`. A test pins the `cmd` enum to the dispatch table verb for verb |
| 23 | `serve()`'s `active` set (:593 add, :607 discard), 0 at bind (:578) and at shutdown (:696) | point-in-time count of sockets the fixed workers own — a leak shows as a count that never falls back to 0 |

### 3.3 Where each signal must be emitted (2026-11-03 reading; rows 1–11 since wired)

| Metric | Owner site | Why it is a blind spot today |
|---|---|---|
| 1,2 | `_run_cycles` loop, `t0 = time.time()` (cron_runner.py:8586) and `elapsed = time.time() - t0` (:9310, :10142, :10400) | elapsed is computed, formatted into a `print`, and thrown away (:9312) |
| 3,12,13,14 | `log_api_call(model, duration_ms, input_tokens, output_tokens, cost, success)` (src/core/ai_client.py:109-118) | every field needed for four metrics arrives **as parameters** and is `print`ed |
| 4 | same; plus `teacher_escalation.cost_usd` (cron_runner.py, run log) | cost is summed nowhere globally; the dashboard's is hardcoded `0.0` |
| 6,7,8 | `_autonomy_counters` (cron_runner.py:5007-...) | counters computed at run **end** from rows, written to JSONL |
| 9,10 | `_write_autonomy_row` (:5629), episode writers in `scripts/` | terminal state never leaves the file |
| 11,16 | `_jev_teacher_escalation` (:3671), `escalation_class_of` (:3749) | escalation counted per-run in a dict |
| 15 | `_probe_api_key` (cron_runner.py:651), `_check_configured_keys` (:690) | probes at boot, result printed once, then forgotten |
| 17,18 | `_cycle_frame_hash` (:2267), `_ow_track_stuck` VOID/same-screen trackers (:9318 region) | desync proxy is a threshold that triggers *recovery*, not a signal |
| 22,23 | `handle`/`worker` in scripts/game_bridge.py (:440-500) | on the audit-day tree the reply sat inside `except Exception: pass` (:441-444) — **the reply path no longer swallows failures**; see the dated note below |

> **UPDATE 2026-11-17:** catalogue rows 1–11 are now wired, and they emit from exactly the
> owner sites this table names — `observe_cycle`/`observe_decision_seconds`
> (cron_runner.py:8581, :9311), `observe_model_call` (src/core/ai_client.py:133), and
> `_publish_run_metrics` → `observe_run_end` (cron_runner.py:5345, called at :7975 and :10546). Rows 12–15 also shipped (MON-AIPP-4) from the
> `log_api_call` and `_check_configured_keys` sites mapped in row 3,12,13,14,15 above — the
> scrapeable series are listed under "Feed points" in §3.2. Rows 16–23 remain blind spots as
> mapped above. The table is the audit-day mapping, not today's.
>
> **UPDATE 2026-11-17 (later, MON-AIPP-5):** rows 17–23 shipped too. They do NOT reuse the
> two sites the audit mapped:
>
> * Rows 17–18 were believed to live at `_cycle_frame_hash` (:2247, now :2267) and the
>   `_ow_track_stuck` VOID trackers (:8941 region, now :9318). Those two are still
>   *thresholds that trigger recovery*, not signals, and they were left alone: the frame hash
>   is computed in `_cycle_capture` (:8614) and the RAM observation in `_cycle_observe`
>   (:8635), so `_track_emulator_integrity` (:8680) is called from `_cycle_header` (:8993)
>   where BOTH exist. Wiring it inside `_ow_track_stuck` would have missed every
>   battle/dialog/name-entry cycle, because that function only runs on the overworld path.
> * Rows 22–23 needed more than removing the `except Exception: pass` around the reply. The
>   `handle()` function had four exits (`return` before any request line, `return` on a bad
>   token, the dispatch path, and the send failure) and a `return` cannot be counted after the
>   fact — the counter is incremented in a `finally` around the whole connection, so a
>   connection that sends nothing at all still appears as `cmd="none", outcome="empty"`.
>   The connection gauge lives in the worker pool (`serve`), which is the only place that
>   owns the live socket set.
>
> **UPDATE 2026-11-18 (DOC-027) — the reply path no longer swallows failures.**
> Proof, run at `f3d7774`:
>
> ```
> $ git grep -n 'except Exception: pass' -- scripts/game_bridge.py
> scripts/game_bridge.py:430:    — the old `except Exception: pass` around the reply swallowed which requests
> ```
>
> That single hit is the `handle()` docstring describing the **removed** construct, not a live
> handler. The shipped reply path is `try: _send_json(...) / except Exception: outcome =
> "send_failed"` (scripts/game_bridge.py:480-486) inside one `finally` that calls
> `observe_bridge_request` (:487-488) — a failed reply is counted as `send_failed`, never swallowed.
>
> The file is **not** free of the pattern altogether, and the claim is scoped accordingly: the only
> remaining `except Exception:` + `pass` pair is `Game.reset()`'s best-effort `self.emu.stop()`
> (scripts/game_bridge.py:313-316), which touches no request or connection counter. Read the rows
> above as the audit-day defect in the reply path, not as a description of today's `handle()`.
>
> Remaining blind spot: row 16 (`aipp_decision_escalations_total`) — outside MON-AIPP-5.

#### 3.3.1 Desync proxy semantics — what `aipp_emulator_desync_total` does and does not mean

There is **no RAM-vs-frame comparator** in this repo (§8.6, item 6). The reader consumes RAM;
the emulator renders pixels; nothing compares the two. So the counter is a **proxy**, and its
docstring (`cron_runner._track_emulator_integrity`, :8680) says so:

> increments when, over two consecutive cycles, the **frame hash is byte-identical** AND the
> **RAM tile triple** `(map_id, player_tile_x, player_tile_y)` **is unchanged**.

Read it as *"cycles that were indistinguishable from a desync"*, never as *"desyncs that
happened"*. A legitimately idle frame — an open dialog nobody is dismissing, an NPC blocking
the path, a paused battle — produces the same shadow. Two behaviours follow from that and are
deliberate:

* An observation with **no tile coordinates** (cartographer/vision frames omit them) never
  increments: "unknown == unknown" is not evidence of a still tile.
* The counter is **not** an error signal on its own. The operational sequence is
  `aipp_emulator_desync_total` rising **while** `aipp_emulator_frame_stale_seconds` keeps
  climbing **and** `aipp_map_transitions_total` stays flat — the last one is what separates
  "stuck screen" from "desynced".

`aipp_emulator_frame_stale_seconds` carries no such caveat: it is a direct monotonic-clock
measurement of the last frame **hash** change, so a frozen emulator is visible there even when
the tile did move (RAM advancing while pixels do not is the other half of the same failure).

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
  Status (MON-AIPP-5): **textfile only**, because the "export through the dashboard" half of this
  rule is not implementable as written — `prometheus_client`'s `REGISTRY` is per-process, so a
  dashboard in another process cannot see the bridge's counters no matter which host they share.
  The bridge writes `/var/lib/node_exporter/textfile_collector/aipp_bridge.prom` (constant
  `DEFAULT_METRICS_FILE`, `scripts/game_bridge.py:68`), atomically, once per finished connection plus
  once at bind and once at shutdown — the only three moments either family moves. `--metrics-file`
  overrides the path; `serve(metrics_file=None)` (the library default, used by the tests) writes
  nothing at all, so importing the module never touches `/var/lib`.
- **Dogfood rule:** every metric must increment on a real code path, not in a test-only hook. A
  counter that only moves under pytest is worse than none.

### 4.2 Route shape (reference sketch, 2026-11-03 — now applied as `src/dashboard/main.py:358`)

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

#### UPDATE 2026-11-17 — the record as shipped

The sketch above is the 2026-11-03 design. The implementation is live and differs in ways that
matter to an operator, so this block is the reference. Read it, not the sketch, when you need
to know what is on disk. (Original text above retained as the audit record.)

**Landing commits:** `1957fe4` (2026-11-04, MON-AIPP-2 — the completion record and its
`tests/test_cron_runner_textfile.py`) and `a77047b` (2026-11-16, MON-AIPP-3 — the
progress-vs-effort families).

**Path and flag** (`cron_runner.py`):

| Thing | Value | Line |
|---|---|---|
| Default directory | `Path("/var/lib/node_exporter/textfile_collector")` — `DEFAULT_TEXTFILE_DIR` | :55 |
| File name | `aipp_run.prom` (so the full default path is `/var/lib/node_exporter/textfile_collector/aipp_run.prom`) | :5803 |
| Flag | `--textfile-dir PATH`, `type=Path`, `default=DEFAULT_TEXTFILE_DIR`; help text `node_exporter textfile collector directory (default: /var/lib/node_exporter/textfile_collector).` | :7792-7800 |
| Threaded through | `S.textfile_dir = args.textfile_dir` at run setup (:8383); the normal close-out passes `getattr(S, "textfile_dir", DEFAULT_TEXTFILE_DIR)` (:10536), the error path passes `getattr(args, "textfile_dir", DEFAULT_TEXTFILE_DIR)` (:7964) | :8383, :10536, :7964 |
| Directory creation | `target_dir.mkdir(parents=True, exist_ok=True)` — the collector dir is created if absent, so there is no separate provisioning step (and no complaint when it is the wrong directory) | :5250 |
| Temp sibling | `temporary = target.with_name(f"{target.name}.tmp")` | :5252 |

**The other half of the lane: node_exporter must be told to read that directory.** The product
writes the file; the exporter only reads it when its own textfile-collector flag points at the same
directory. That flag is **`--collector.textfile.directory`**, and its value must be the SAME
directory as `DEFAULT_TEXTFILE_DIR` (`cron_runner.py:55`) — or whatever `--textfile-dir` was set
to. Nothing validates the pair, and a mismatch is silent on the product's side: the writer creates
its own directory (:5250), so it never fails either way, and an exporter pointed at a directory
nobody writes to reports no `aipp_*` series at all rather than "the product is not writing here".
The symptom is a file that exists and grows on disk while the scrape returns nothing for it:
`curl -s localhost:9100/metrics | grep aipp_run` prints no lines.

```ini
# /etc/systemd/system/node_exporter.service.d/textfile.conf
# This value must be the SAME directory as DEFAULT_TEXTFILE_DIR (cron_runner.py:55).
[Service]
ExecStart=
ExecStart=/usr/bin/node_exporter \
  --collector.textfile.directory=/var/lib/node_exporter/textfile_collector
```

Point the cron lane somewhere else and the exporter flag has to move with it — one value, two
places:

```bash
cron_runner.py --textfile-dir /srv/aipp/textfiles
node_exporter --collector.textfile.directory=/srv/aipp/textfiles
```

The textfile collector re-emits a file's samples together with its `# HELP` / `# TYPE` lines, so
the scrape carries exactly the families listed below — `job`, `instance` and any `host` label come
from the Prometheus scrape config, not from the file:

```
$ curl -s localhost:9100/metrics | grep '^aipp_run'
aipp_run_completed_total{outcome="completed"} 2
aipp_run_last_run_duration_seconds 142.408
aipp_run_last_decisions_total 20
aipp_run_last_map_transitions_total 0
aipp_run_last_backtrack_rate 0.4211
```

Those five samples are the real contents of `/var/lib/node_exporter/textfile_collector/aipp_run.prom`
on the host where this block was written (798 bytes, mtime `2026-11-04 13:35:44 -0500`) — a cron run
from before MON-AIPP-3, which is why it has no progress families. The `curl` itself is
**unexecuted** there: no `node_exporter` binary exists on that host and nothing listens on port 9100. Run it
where the exporter is up; the verification block at the end of this section says which checks need
that and which do not.

**Every line the writer emits.** Order is fixed by the code; `{…}` marks labels, `<…>` the
substituted value. `%g` formatting is why a duration of 12.0 prints as `12`:

| # | Emitted line (verbatim template) | Type | Value source | Emitted at |
|---|---|---|---|---|
| 1 | `# HELP aipp_run_completed_total Completed cron runs by outcome.` | — | literal | :5259 |
| 2 | `# TYPE aipp_run_completed_total counter` | — | literal | :5260 |
| 3 | `aipp_run_completed_total{outcome="completed"} <accumulated>` | counter | prior file value + 1 when this run's outcome is `completed` | :5262-5265 |
| 4 | `aipp_run_completed_total{outcome="error"} <accumulated>` | counter | same | :5262-5265 |
| 5 | `aipp_run_completed_total{outcome="gave_up"} <accumulated>` | counter | same | :5262-5265 |
| 6 | `# HELP aipp_run_last_run_duration_seconds Duration of the last cron run.` | — | literal | :5823 |
| 7 | `# TYPE aipp_run_last_run_duration_seconds gauge` | — | literal | :5269 |
| 8 | `aipp_run_last_run_duration_seconds <%g>` | gauge | `duration_s` (wall clock from `run_started_at` to close-out) | :5270 |
| 9 | `# HELP aipp_run_last_decisions_total Decisions observed in the last cron run.` | — | literal | :5826 |
| 10 | `# TYPE aipp_run_last_decisions_total gauge` | — | literal | :5272 |
| 11 | `aipp_run_last_decisions_total <int>` | gauge | `autonomy["decisions_total"]` | :5273 |
| 12 | `# HELP aipp_run_last_map_transitions_total Map transitions observed in the last cron run.` | — | literal | :5829 |
| 13 | `# TYPE aipp_run_last_map_transitions_total gauge` | — | literal | :5275 |
| 14 | `aipp_run_last_map_transitions_total <int>` | gauge | `autonomy["map_transitions_observed"]` | :5276-5277 |
| 15 | `# HELP aipp_run_last_backtrack_rate Backtrack rate in the last cron run.` | — | literal | :5839 |
| 16 | `# TYPE aipp_run_last_backtrack_rate gauge` | — | literal | :5285 |
| 17 | `aipp_run_last_backtrack_rate <%g>` | gauge | `autonomy["backtrack_rate"]` — **this trio is emitted only when that key is not `None`** (:5280-5281) | :5286 |
| 18 | `# HELP aipp_map_transitions_total Map transitions observed across cron runs.` | — | literal in the family table (:5174) | :5321 |
| 19 | `# TYPE aipp_map_transitions_total counter` | — | kind from the family table (:5727) | :5322 |
| 20 | `aipp_map_transitions_total <merged>` | counter | prior + `autonomy["map_transitions_observed"]` (:5305); no labels | :5332 |
| 21 | `# HELP aipp_backtrack_events_total Decision rows that repeated or revisited an already-seen tile state.` | — | literal (:5178) | :5321 |
| 22 | `# TYPE aipp_backtrack_events_total counter` | — | kind (:5177) | :5322 |
| 23 | `aipp_backtrack_events_total <merged>` | counter | prior + `autonomy["backtrack_events"]` (:5307); no labels | :5332 |
| 24 | `# HELP aipp_episode_decisions_total Gameplay decisions taken across cron runs, by decision mode.` | — | literal (:5182) | :5321 |
| 25 | `# TYPE aipp_episode_decisions_total counter` | — | kind (:5181) | :5322 |
| 26 | `aipp_episode_decisions_total{mode="<family>"} <merged>` | counter | prior + `autonomy["decisions_total"]` (:5309), labelled by `decision_mode_label()` (:5298) | :5332 |
| 27 | `# HELP aipp_teacher_escalations_total Teacher escalations by whether they improved the decision.` | — | literal (:5186) | :5321 |
| 28 | `# TYPE aipp_teacher_escalations_total counter` | — | kind (:5185) | :5322 |
| 29 | `aipp_teacher_escalations_total{improved="true"} <merged>` | counter | prior + `improved` (:5312), clamped so it cannot exceed the escalation count (:5302) | :5332 |
| 30 | `aipp_teacher_escalations_total{improved="false"} <merged>` | counter | prior + `escalations - improved` (:5313) | :5332 |
| 31 | `# HELP aipp_run_duration_seconds_count Number of finished cron runs contributing to the duration sum.` | — | literal (:5190) | :5321 |
| 32 | `# TYPE aipp_run_duration_seconds_count counter` | — | kind (:5189) | :5322 |
| 33 | `aipp_run_duration_seconds_count{outcome="<label>"} <merged>` | counter | prior + 1.0 (:5315), labelled by `run_outcome_label()` (:5299) | :5332 |
| 34 | `# HELP aipp_run_duration_seconds_sum Total wall-clock seconds spent in finished cron runs.` | — | literal (:5194) | :5321 |
| 35 | `# TYPE aipp_run_duration_seconds_sum counter` | — | kind (:5193) | :5322 |
| 36 | `aipp_run_duration_seconds_sum{outcome="<label>"} <merged>` | counter | prior + `max(0, duration_s)` (:5317) | :5332 |

Three properties of that list an operator should not assume away:

- **`aipp_run.prom` carries no buckets.** `aipp_run_duration_seconds` is a real histogram in
  the dashboard export (`src/observability/metrics.py:80`), but the textfile writes only the
  `_count` / `_sum` components as **counter** families (family table :5743-5750), with no
  `# TYPE … histogram` and no `_bucket` lines. A `histogram_quantile()` over the textfile alone
  therefore returns nothing — take quantiles from the dashboard scrape, and use the textfile for
  totals. The two surfaces sharing the `aipp_run_duration_seconds` base name is the one place they
  can look inconsistent in a scrape; the shapes above are what each actually exports.
- **Accumulation is read-modify-write against the previous file.** `_read_textfile_totals()`
  (:5199-5219) parses the existing samples (:5213), keyed by family then by the sorted
  `(label, value)` pairs (:5217), and each new value is `merged[key] = merged.get(key, 0.0) + delta`
  (:5329). Every label set the writer has ever emitted is retained (:5323-5327), so a mode or
  outcome that did not run today does not vanish from the scrape. `aipp_run_completed_total` is
  accumulated separately by `_TEXTFILE_COUNTER_PATTERN` (:5154-5158), and the loop over its three
  outcomes only emits a label whose accumulated value is non-zero or which is this run's own
  outcome (:5262-5265).
- **`run_id` is a function parameter, not a field.** It appears only in the failure message
  (`:5338`). Run identity stays in the JSONL log, per the label budget in §3.

**Atomic write.** The writer composes the whole record in memory, writes it to a sibling
temporary file (`temporary = target.with_name(f"{target.name}.tmp")`, :5249) and then
`os.replace(temporary, target)` (:5338). Both paths are in the collector directory, so the
rename is same-filesystem and atomic on POSIX: a scrape sees either the complete previous
record or the complete new one, never a half-written file. There is no lock — the file is
per-host, and concurrent cron runs on one host would race the accumulate step.

**When it is written, relative to the run log.** Normal close-out, in code order:

1. `_write_autonomy_row(...)` — appends the `run_autonomy` row to `cron_logs/run_<id>.jsonl` (:10520-10530)
2. `_write_degradation_row(...)` — only when the degradation gate tripped (:10531)
3. outcome/duration computed (`gave_up` if the run gave up, else `completed`) (:10532-10534)
4. `_write_textfile_record(...)` — the `.prom` file (:10535-10543)
5. `_publish_run_metrics(outcome, ...)` — the in-process Prometheus series (:10546)
6. `log_file.close()` (:10547)

So the run log already carries the same numbers when the textfile is written (both are fed
from the same `autonomy` block), and the scrape-visible file is published before the log
handle closes. On the failure path the order is identical in substance: `_write_textfile_record(..., "error", ...)`
at :7963-7971 immediately followed by `_publish_run_metrics("error", ...)` at :7975, before the
exception is re-raised (:7976) — a run that died still records its outcome.

**Failure is best-effort.** The whole body is wrapped in `try/except Exception`, which prints
`[TEXTFILE] <run_id> failed: <exc>` via `safe_print` and returns `None` (:5340-5342). A
collector path that is not writable costs the run its metrics line, never the run.

**If the process dies before close-out, the previous record survives untouched and looks healthy.**
The file has exactly two write sites and both are at close-out (:10535 normal, :7963 error), nothing
writes it mid-run, and the file carries no timestamp, run id, or heartbeat (the run id appears only
in the failure message, :5341). A SIGKILL, a host reboot, or an OOM during the loop therefore leaves
the **previous** run's sample set in place, byte-for-byte, with its previous mtime: a stale record is
indistinguishable from a fresh one by content, because every value in it is plausible. The live shape
is worth keeping in mind — the file on the host where this block was written was 13 days old,
predated MON-AIPP-3, and still read `aipp_run_completed_total{outcome="completed"} 2` with no progress
families at all.

Two ways to tell stale from fresh, and neither is optional:

1. **mtime against the run window.** Close-out rewrites the file, so its mtime is at or after the
   run's start: `stat -c '%y %s' /var/lib/node_exporter/textfile_collector/aipp_run.prom`, compared
   with the run's own window in `cron_logs/run_<id>.jsonl` (the `preflight` row opens it, the
   `run_autonomy` row closes it, :10520-10530). An mtime older than the newest `run_autonomy` row
   means that run never reached the write.
2. **the counter family.** `aipp_run_completed_total` rises by exactly one per finished run (:5259),
   so a sample that did not move across a run which produced a `run_autonomy` row is a lost write —
   and if the write was attempted and failed, stdout carries `[TEXTFILE] <run_id> failed: <exc>`
   (:5338). The `aipp_run_last_*` gauges are the trap: they are named "last", so a stale one cannot
   be spotted from its value, only from the two checks above.

**Only the cron lane writes this record.** `_write_textfile_record` has exactly two call sites, both
in `cron_runner.py`'s cron entrypoint (`:10535` in `_finalize_run`, `:7963` in the `except` of `__main__`);
the dashboard process and the single-cycle CLI (`run_cycle.py`) never call it, so their runs increment
only the in-process `/metrics/prometheus` series (§4.2). Every number in `aipp_run.prom` therefore
counts cron-lane runs and nothing else: a 40-minute dashboard run leaves
`aipp_run_last_run_duration_seconds` untouched.

**Closed label vocabularies.** Two of the labelled families map their label through a closed set in
`src/observability/metrics.py`; the other two are literal pairs in the writer. `<family>` and
`<label>` in the table above are finite sets, not free text:

| Family | Label | Values | Computed or asserted | Source |
|---|---|---|---|---|
| `aipp_episode_decisions_total` | `mode` | `system1`, `system2`, `system1+system2`, `jev`, `hybrid`, `llm`, `agentic`, `unknown` | **computed** — `decision_mode_label()` strips+lowercases and falls back to `unknown` for anything outside the set | set `_DECISION_MODE_LABELS` metrics.py:171-182, map `decision_mode_label()` metrics.py:270-276, applied cron_runner.py:5863 |
| `aipp_run_duration_seconds_count`, `aipp_run_duration_seconds_sum` | `outcome` | `completed`, `error`, `gave_up`, `unknown` | **computed** — `run_outcome_label()`; exact match only (no normalisation), else `unknown` | tuple `_RUN_OUTCOME_LABELS` metrics.py:183, map `run_outcome_label()` metrics.py:279-283, applied cron_runner.py:5302 |
| `aipp_run_completed_total` | `outcome` | `completed`, `error`, `gave_up` — **no `unknown`** | **asserted** — the caller passes the literal and the writer iterates a hardcoded tuple; the accumulator's regex only recognises those three | cron_runner.py:5265-5268, regex `_TEXTFILE_COUNTER_PATTERN` :5157-5158, call sites :10535 / :7963 |
| `aipp_teacher_escalations_total` | `improved` | `true`, `false` | **asserted** — literal label pairs in the writer | cron_runner.py:5315-5316 |
| `aipp_map_transitions_total`, `aipp_backtrack_events_total` | — | no labels | n/a | cron_runner.py:5307, :5310 |
| `aipp_bridge_requests_total` (MON-AIPP-5) | `cmd` | the 14 verbs `_dispatch` serves (`health`, `observe`, `press`, `step`, `save`, `load`, `frame`, `raw`, `pause`, `resume`, `list_saves`, `delete_save`, `reset`, `goal`) plus `unknown` and `none` | **computed** — `bridge_cmd_label()` strips+lowercases; anything outside the set becomes `unknown`, and `none` means the connection never sent a request line. `tests/test_mon_aipp5.py` re-parses `_dispatch` and fails if a verb is added without extending the enum | set `_BRIDGE_CMD_LABELS` metrics.py:198-217, map `bridge_cmd_label()` metrics.py:427-433 |
| `aipp_bridge_requests_total` (MON-AIPP-5) | `outcome` | `ok`, `error`, `unauthorized`, `busy`, `invalid`, `send_failed`, `empty`, `unknown` | **computed** — one outcome per connection, chosen by the single exit in `handle()`; `unknown` only for a spelling outside the set (never produced by the bridge itself) | set `_BRIDGE_OUTCOME_LABELS` metrics.py:222-233, map `bridge_outcome_label()` metrics.py:436-440 |

The asymmetry is deliberate and worth naming: `outcome="unknown"` is representable on the two
duration families and NOT on the completed counter, so a scrape can carry
`aipp_run_duration_seconds_count{outcome="unknown"}` while `aipp_run_completed_total{outcome="unknown"}`
does not exist. Neither appears from the cron lane in practice — both call sites pass a literal
(`completed`/`gave_up` at :10535, `error` at :7963) — but the dashboard surface DOES run
`aipp_run_completed_total` through `run_outcome_label()` (metrics.py:279, called at :557), so the same family name can
carry `unknown` on one surface and not the other.

**Verifying this without a live game run.** The probe below calls the shipped writer twice into a
scratch directory. It needs the repo's venv and nothing else — no game run, no cron lane, no
node_exporter:

```bash
$ ./venv/bin/python /tmp/textfile_probe.py /tmp/tf-probe3
DEFAULT_TEXTFILE_DIR = /var/lib/node_exporter/textfile_collector
parser default       = /var/lib/node_exporter/textfile_collector
# HELP aipp_run_completed_total Completed cron runs by outcome.
# TYPE aipp_run_completed_total counter
aipp_run_completed_total{outcome="completed"} 1
aipp_run_completed_total{outcome="error"} 1
...
aipp_run_last_backtrack_rate 0.6076
# HELP aipp_map_transitions_total Map transitions observed across cron runs.
# TYPE aipp_map_transitions_total counter
aipp_map_transitions_total 52
# HELP aipp_backtrack_events_total Decision rows that repeated or revisited an already-seen tile state.
# TYPE aipp_backtrack_events_total counter
aipp_backtrack_events_total 96
# HELP aipp_episode_decisions_total Gameplay decisions taken across cron runs, by decision mode.
# TYPE aipp_episode_decisions_total counter
aipp_episode_decisions_total{mode="jev"} 80
aipp_episode_decisions_total{mode="system1+system2"} 80
# HELP aipp_teacher_escalations_total Teacher escalations by whether they improved the decision.
# TYPE aipp_teacher_escalations_total counter
aipp_teacher_escalations_total{improved="false"} 66
aipp_teacher_escalations_total{improved="true"} 62
# HELP aipp_run_duration_seconds_count Number of finished cron runs contributing to the duration sum.
# TYPE aipp_run_duration_seconds_count counter
aipp_run_duration_seconds_count{outcome="completed"} 1
aipp_run_duration_seconds_count{outcome="error"} 1
# HELP aipp_run_duration_seconds_sum Total wall-clock seconds spent in finished cron runs.
# TYPE aipp_run_duration_seconds_sum counter
aipp_run_duration_seconds_sum{outcome="completed"} 183.4
aipp_run_duration_seconds_sum{outcome="error"} 12
```

The `...` above is rows 6–16 of the table (the `last_*` HELP/TYPE lines and the three integer
gauges); the order and text are exactly what the table lists. Run the probe against an empty
directory — the writer accumulates across calls, so a second run into the same dir doubles the
counters. The probe itself:

```python
# /tmp/textfile_probe.py — no game run, no cron lane, no node_exporter
import sys
from pathlib import Path
sys.path.insert(0, ".")
import cron_runner

out = Path(sys.argv[1]).resolve()
autonomy = {"decisions_total": 80, "map_transitions_observed": 26,
            "backtrack_events": 48, "backtrack_rate": 0.6076}
print("DEFAULT_TEXTFILE_DIR =", cron_runner.DEFAULT_TEXTFILE_DIR)
print("parser default       =",
      cron_runner._main_parser().parse_args([]).textfile_dir)
for run_id, outcome, seconds, mode in (("run-probe-a", "completed", 183.4, "system1+system2"),
                                       ("run-probe-b", "error", 12.0, "jev")):
    cron_runner._write_textfile_record(out, run_id, outcome, seconds, autonomy,
                                       mode=mode, teacher={"count": 64, "improved": 31})
print((out / "aipp_run.prom").read_text(encoding="utf-8"))
```

The same two constants, without the script:

```bash
$ ./venv/bin/python -c "import cron_runner as c; print(c.DEFAULT_TEXTFILE_DIR)"
/var/lib/node_exporter/textfile_collector
$ ./venv/bin/python -c "import cron_runner as c; print(c._main_parser().parse_args([]).textfile_dir)"
/var/lib/node_exporter/textfile_collector
```

Static checks — the call-site census behind "only the cron lane writes it":

```bash
$ grep -n "_write_textfile_record" cron_runner.py
5229:def _write_textfile_record(
7960:        _write_textfile_record(
10429:    _write_textfile_record(
```

Re-run at `f3d7774` on 2026-11-18 (DOC-027) — the same three sites, all moved:

```bash
$ grep -n "_write_textfile_record" cron_runner.py
5232:def _write_textfile_record(
7963:        _write_textfile_record(
10535:    _write_textfile_record(
```

**Two checks need a live host, and only these two.** The first needs a host where the cron lane has
actually run; the second needs `node_exporter` up and pointed at the same directory (the flag in the
config snippet above):

```bash
$ ls -l /var/lib/node_exporter/textfile_collector/aipp_run.prom
-rw-rw-r-- 1 kara kara 798 Nov  4 13:35 /var/lib/node_exporter/textfile_collector/aipp_run.prom

$ curl -s localhost:9100/metrics | grep '^aipp_run'
```

The `ls` output above is real (that is the 2026-11-04 record quoted earlier). The `curl` was not run:
there is no `node_exporter` binary and nothing listening on port 9100 on the host where this was written, so its
output stays unverified until someone runs it where the exporter is up.

---

## 5. Collection path

The fleet monitor (`fleet-monitor`) runs Prometheus 3.15 / Loki / Grafana / Alloy and agents **push**
via `remote_write`. This product is a **scrape-only** target, so it needs exactly one decision:

**Preferred (no monitoring-stack change):** write the textfile into node_exporter's textfile
collector directory on the host that runs the cron lane. node_exporter is already scraped; the series
arrive with the host's existing `host` label, and the exporter reads the file only when its
`--collector.textfile.directory` points at that same directory (§4.3).
Zero changes to
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

Cardinality budget, restated as measured (MON-AIPP-4): the original "≤40 live series" line was written
before any histogram existed, and a histogram is not one series — the client emits one `_bucket` per
ladder step plus `_sum`/`_count`/`_created`, so a single label-set of
`aipp_model_call_duration_seconds` costs **18** sample lines (measured: 15 `le` buckets including
`+Inf`, plus the three suffixes). Measured on a fresh import with no run and no key probe,
`generate_latest(REGISTRY)` carries **80** `aipp_` sample lines — 59 from the P0/P1 families that
shipped earlier, 21 from MON-AIPP-4 (duration 18, tokens 2, retries 1); with both keys probed it is
82. The binding constraint is therefore the ENUM sizes, not a flat sample count:

- `model_family` — 6 values max (`claude`,`gpt`,`deepseek`,`gemini`,`local`,`other`); a live run
  normally shows 1-2, so the new families add ~21 lines typical and 144 worst case
  (18+2+4 per family × 6).
- `reason` — 4 values, `direction` — 2 values; both fixed.
- `key_name` (metric 15) — **the only family that can grow with configuration**, so it keeps the
  original rule: a **static enum of the env-var NAMES this repo probes**
  (`OPENROUTER_API_KEY`, `DEEPSEEK_API_KEY` — the names, never the values, never a rotated key
  identity), and the gauge is NOT materialized at import: `_check_configured_keys` mints one series
  per CONFIGURED name only, so a key-less host exports zero `key_name` series and this host exports
  at most 2 (`grep -c 'key_name='` = 2, budget ≤3).

If a `prometheus.<product>_series_count` guard exists in the stack, its 100-series alarm is already
inside the histogram arithmetic above and should be set from the per-family bound, not from 40;
trimming the bucket ladder is the knob if it ever fires.

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
# run one real cycle (not a test): python3 cron_runner.py --decision-mode jev --cycles 5
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

# emulator frozen, or frozen AND RAM still (P3 #17,18) — the §3.3.1 pair
max(aipp_emulator_frame_stale_seconds) > 300
  and increase(aipp_emulator_desync_total[30m]) > 0

# bridge serving, erroring or wedged (P3 #22,23)
sum(rate(aipp_bridge_requests_total{outcome="ok"}[15m])) == 0
  and sum(rate(aipp_bridge_requests_total[15m])) > 0
max_over_time(aipp_bridge_active_connections[15m]) > 0   # leak: never falls back

# data growth (P3 #19,20) — the disk question, not the health question
delta(aipp_runlog_bytes[1h])
aipp_screenshot_bytes
```

**Step 4 — textfile lane**

```bash
ls -l /var/lib/node_exporter/textfile_collector/aipp_run.prom
ls -l /var/lib/node_exporter/textfile_collector/aipp_bridge.prom   # bridge, P3 #22,23
```
The file existing is only half of it: node_exporter must be running with
`--collector.textfile.directory=/var/lib/node_exporter/textfile_collector` (the same directory as
`DEFAULT_TEXTFILE_DIR` — §4.3), otherwise nothing scrapes it and the file sits there unread.
then from Prometheus: `aipp_run_completed_total{outcome="completed"}` → a non-zero sample with the
right `host` label. Done: series present **and** `aipp_run_last_decisions_total` equal to the
`decisions_total` in the newest `cron_logs/run_*.jsonl` (cross-check the number, not just the presence).

**Done definition for the whole spec:** all five P0 queries return data, Step 2 returns `MOVED`, and
the §1.4 dead-logger state is either fixed or explicitly re-classified as dead (see §8).

> **UPDATE 2026-11-17 — what was measured and what was not.** Steps 1–4 above were **not**
> run: there is no dashboard process and no reachable Prometheus on the host where this
> update was written, so the `curl` checks and the PromQL remain unexecuted. What IS proven
> is static and cited in the UPDATE block at the top: the route, the client library, the 11
> metric definitions, and one production call site per family. Treat "the endpoint answers
> 200 with the right content type" as **unverified** until a reviewer on a host with the
> dashboard running executes Step 1 — the code path exists, but nobody has watched it serve.

---

## 7. Deliberately NOT instrumented

| Not instrumented | Why |
|---|---|
| `run_id`, `cycle`, `map_name`, `tile`, `prompt`, model raw string as labels | Unbounded cardinality. A 20-cycle run with per-run labels makes a new series every hour forever. This is what Loki is for. |
| per-request user/session labels | Single-operator product; adds cardinality, answers nothing. |
| Screenshot content / vision verdicts as metrics | Semantic content, not health. Belongs in the run log; already there (`vision_usage`, `screen`). |
| Grouping by `missing_class` beyond a fixed enum | `missing_class` is already an enum (`none`, `map_topology`, …); anything free-form must be bucketed to `other` before it becomes a label. |
| `logs/api/*.log` etc. ingestion | The files are empty and the writer is dead (§1.4). Instrumenting them would create a metric measuring a phantom. |
| Exact per-token cost per model | Cost is already summed with `cost_usd` per call across all clients (src/core/ai_client.py:109-118). A second derivation would drift. |

---

## 8. Known risks for the implementing worker

1. **`/metrics` is taken.** Use a new path. Do not modify `tests/test_dashboard.py:122,489-492`.
2. **The cron lane must not try to serve HTTP.** It exits; a scrape will never catch it. Textfile only.
3. **`src/core/logger.py` is a trap.** It looks like the logging solution and is 100% unwired. Do not
   assume it runs. If step 1 of the work "fixes logging" by calling `get_logger()`, verify the files
   actually grow (`wc -c logs/errors/errors.log`) — that is a separate, larger piece of work than metrics.
4. **`total_cost_estimate` is hardcoded `0.0`** (`total_cost = 0.0`, src/dashboard/main.py:228). Do not wire metric 4 to it
   — it would export a dead zero with a live-looking `# HELP`. Wire it to the `log_api_call` cost
   parameter path, and if the dashboard field is to be fixed, fix it as a deliberate change with its
   own evidence.
   Status (MON-AIPP-4): metric 4 is fed exactly that way — `log_api_call`
   (src/core/ai_client.py:109) publishes the per-call cost through
   `observe_model_call`, and it is the sole cost producer for every model call (the P2 latency/token
   families ride the same call). The dashboard JSON field is untouched and still `0.0`; it remains
   not a metric source.
5. **Do not add a scrape job yourself.** `prometheus.yml` is the monitoring stack's; the textfile path
   needs no change at all.
6. **Metric 17 (desync) has no clean primitive yet.** There is a frame-hash (:2247) and stuck trackers
   (:9318) but no RAM-vs-frame comparison. Implement it as a bounded proxy (repeated frame hash with
   unchanged RAM tile) and document the proxy, or defer it — do not claim a true desync detector exists.
   Status (MON-AIPP-5): shipped exactly as this item asked. `_track_emulator_integrity`
   (cron_runner.py:8680) increments the counter when the frame hash is unchanged **and** the RAM
   tile triple is unchanged, the docstring says in so many words that "a true desync cannot be
   detected here", and §3.3.1 states the reading. The VOID/same-frame thresholds were NOT
   converted into signals: they still trigger recovery, which is a different job. The one
   remaining false-positive source is a legitimately idle screen (dialog page, NPC block) —
   that is inherent to the proxy and is why the counter must be read with
   `aipp_emulator_frame_stale_seconds` and `aipp_map_transitions_total`, not alone.

---

## 9. Open / unverified items

| Item | Why unverified |
|---|---|
| Whether the dashboard is actually running anywhere right now | No network access from the audit host; no process check was possible. The `/health` and `/metrics/prometheus` curl checks are unrun. |
| Actual Prometheus series count for this product today | Requires querying Prometheus on `fleet-monitor`; not reachable from here. Static analysis says 0. |
| Real desync rate | No sensor exists (§8.6). The `[VOID]` print (:9892) is the closest proxy and is not persisted. |
| Whether any external dashboard already reads `cron_logs/*.jsonl` | Only `web_viewer.py` (`/api/run/{run_id}/log`) was found reading run logs; no evidence of a fleet-side consumer either way. |
| Whether `logs/*/*.log` were ever populated | Files are 0 bytes with Jun 26 mtimes; whether they were ever non-empty is not recoverable from the repo. |

> **UPDATE 2026-11-17:** the second row above still holds in its *last* clause only —
> static analysis no longer says 0. It now counts 11 defined `aipp_*` families in
> `src/observability/metrics.py` (listed in the UPDATE block at the top), each with a
> production increment site. The first question is still open the same way: no Prometheus
> on `fleet-monitor` was reachable from this host, so the number of series actually
> **scraped** is unverified — defined ≠ ingested.
>
> **UPDATE 2026-11-17 (MON-AIPP-5):** the count above is corrected to **22** families —
> `grep -n '^_[A-Z_]* = _metric(' src/observability/metrics.py` prints 22 assignments and 22
> distinct `aipp_*` names: the top block's original 11, the 4 MON-AIPP-4 P2 families, and the
> 7 MON-AIPP-5 P3 families. The "11" was written before MON-AIPP-4 landed and was never
> updated then; it stays in the sentence above as the record of that block. The "Real desync
> rate" row now has a **proxy** answer and still no sensor: `aipp_emulator_desync_total`
> (§3.3.1) counts cycles that were *indistinguishable* from a desync, so an actual desync
> **rate** remains unmeasurable — and no run has been graded with it yet, on this host or any
> other, so even the proxy's real-world magnitude is unmeasured.
