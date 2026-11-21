# JEV-404 — live-run evidence (repo-visible projection)

The 80-cycle claims for `JEV-404` come from runtime logs under `cron_logs/`, which this
repo gitignores on purpose (same class as `play_frames/`, `game_saves/`, `screenshots/`).
A repo-reading evaluator cannot see them, so this directory carries the machine-readable
projection: aggregates in `run-evidence.json`, one row per decision cycle in
`run_jev404c-cycles.jsonl`.

| measurement | pre-fix (`df1120a`) | post-fix (`jev404c`) |
|---|---|---|
| cycles | 80 | 80 |
| `teacher_escalation` rows | 78 | **4** |
| wall clock | 611.90 s | 55.38 s |
| blocked handoff rows | — | 76 |

Fix commit: `bcc61b6` (`fix(jev): bound sufficiency-floor teacher escalations`).
Superseded verdict: `.gitreins/history/2026-11-21/4772c000` — tier2 INCOMPLETE on the
live-run half only, because the log was never committed.

## Reproduce

```bash
./venv/bin/python cron_runner.py --run-id jev404c --cycles 80 --decision-mode jev
```

## Verify from the tracked tree

```bash
jq -r '.comparison.claim_confirmed' .coding-hermes/evidence/JEV-404/run-evidence.json
jq -r '.post_fix.teacher_escalation_rows' .coding-hermes/evidence/JEV-404/run-evidence.json
jq -r 'select(.escalated) | .cycle' .coding-hermes/evidence/JEV-404/run_jev404c-cycles.jsonl | wc -l
jq -r 'select(.handoff_blocked_reason != null) | .handoff_blocked_reason' \
  .coding-hermes/evidence/JEV-404/run_jev404c-cycles.jsonl | sort | uniq -c
```

## Residual risk (stated, not hidden)

The projection is derived from logs outside git, so the original bytes cannot be re-hashed
from the repo alone. `source_log_sha256` for both runs is recorded so a reader with host
access can cross-check, and the reproduction command regenerates an equivalent log.
