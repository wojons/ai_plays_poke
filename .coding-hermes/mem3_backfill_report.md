# MEM-3 DuckBrain Run Backfill Report

## Real backfill result

The one-shot backfill ran against `http://127.0.0.1:3000` in namespace
`pokemon-global` and exited 0.

```text
DuckBrain auth: accepted foreman-status.token
Episode JSONL files scanned: 4
Runs found: 534
save/current records listed: 0
save/current folded count: 0
Summaries written: 534
Summary upserts: created=534
Index written: 1 (created, entries=10)
Mechanics written: 3 (created, created, created)
```

No `/game/save/current` records existed in the namespace at backfill time, so the
folded count is 0. The backfill did not delete or modify any save/current key.

## Read-back verification

A fresh verifier rebuilt the expected deterministic content from the source
JSONLs, fetched each sample through the authenticated DuckBrain HTTP API, and
compared the returned content byte-for-byte.

- Unique summary keys present under `/game/runs/`: **534**
- `/game/runs/index`: **10 entries** (required maximum: 10)
- `/game/mechanics/controls`: domain `concept`, 251 non-empty characters, exact match
- `/game/mechanics/menus`: domain `concept`, 244 non-empty characters, exact match
- `/game/mechanics/battle`: domain `concept`, 294 non-empty characters, exact match

Sample GET evidence:

| Key | Domain | Evidence |
| --- | --- | --- |
| `/game/runs/index` | `event` | exact content match; 10 entries; SHA-256 `1b82fb1f6cd19818868345790bb137f6ad5a00268898775de7aac1abd8839366` |
| `/game/runs/long_0927_llm2_ep028/summary` | `event` | exact content match; outcome `goal_achieved`; final map `Viridian City`; SHA-256 `aa52483f6dc6f934aac81f58d8e73e7057673910ff65ea00e504da9a765bcc6e` |
| `/game/runs/long_0927_llm2_ep027/summary` | `event` | exact content match; outcome `completed`; final map `Route 1`; SHA-256 `e5fb22e693237c9f5857f8eab78b39ede2cc0bd98d8f0ad08879508eaf73de8f` |

## Local checks

- AST parse: PASS
- `python3 -m py_compile scripts/backfill_runs.py`: PASS
- Ruff format and lint checks on `scripts/backfill_runs.py`: PASS
- Idempotence sample: index, two summaries, and all three mechanics keys returned
  `unchanged` through the script's upsert path
