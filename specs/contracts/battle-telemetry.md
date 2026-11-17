# Battle telemetry data contract

**Row:** BTL-SCHEMA-1 (P1) — battle-telemetry data contract
**Status:** CONTRACT ONLY. No reader, no RAM addresses, no store implementation lives here.
**Children that must be implementable straight from this text:** BTL-RAM-1 (reader), BTL-STORE-1 (store),
BTL-COMPARE-1 (comparison reader).
**Matrix entry:** CT-08 in `specs/contracts/_matrix.md`; graded requirements R-011..R-014.

---

## 1. Purpose and scope

The benchmark's whole reason to exist is comparing **different models playing the same game segment**.
Today the evidence that survives a run is: the per-run decision log `cron_logs/run_<run_id>.jsonl`
(`cron_runner.py:955-958`), the episode log (`scripts/long_run.py:37`, one row per episode at
`scripts/long_run.py:488`), and a handful of DuckBrain summary records (`cron_runner.py:5703-5713`).
None of those carries **battle-level** facts: which attack was used, how much damage it dealt, against
which defender at which level, on which map, on which turn. Battle outcome is only aggregate
(`cron_runner.py:5746` counts rows whose event name starts with `battle_`).

This contract fixes the **shape** of a battle-telemetry record and the **partitioning** that makes a
comparison cheap. It fixes nothing else:

- It does **not** name a RAM address, an offset, or a symbol-address pair (§8).
- It does **not** specify how the store writes (batching, transport, retries) beyond the file layout and
  append doctrine in §4 and §9.
- It does **not** specify the comparison implementation; it specifies the keys that make exclusion
  decidable (§5) so BTL-COMPARE-1 has no design freedom on that point.
- Where a decision genuinely cannot be made from this repo's code today, it is recorded as `OPEN:` in §10
  instead of being invented.

## 2. Operator law this contract encodes

Verbatim intent, 2026-11-11: *DuckBrain becomes a real database for battle telemetry, and the design
constraint is PARTITIONING — never one large file; many SMALL files that can easily be excluded from
read-in, each carrying clean data keys. Purpose: compare runs of different models playing the same game
segment, so the keys must make like-for-like slices trivial (same map, same encounter, same opponent).*

Read as testable consequences:

1. A comparison query must be able to **exclude a partition without opening it** (§5).
2. A telemetry file must be **bounded** in a way a judge can count (§7).
3. Records must carry **identity keys** sufficient to say which run, which model, which encounter, which
   turn (§3).
4. There must be **no** per-run, per-model, or per-map aggregate file; aggregates are computed at read
   time (§7, N8).

---

## 3. Record schema

**One record = one observed attack event inside one encounter.** An exchange of blows produces two
records (one with `attacker_side = "player"`, one with `attacker_side = "enemy"`); a player action that
whiffs produces exactly one record with `outcome = "miss"` and `damage = 0`. A non-damaging move produces
one record with `outcome = "no_damage"` and `damage = 0`. A knockout produces one record whose
`damage` is the defender's **remaining** HP (see 3.3 R5).

### 3.1 Identity keys — required on every record

| field | type | unit | may be null | why |
|---|---|---|---|---|
| `run_id` | string | — | **no** | The run that produced the fact. Shape is the repo's existing run id: `%Y%m%d_%H%M%S` for `cron_runner` (`cron_runner.py:957`), `long_%m%d_%H%M` for the long-run harness (`scripts/long_run.py:36`). Both are `[A-Za-z0-9_]+`, which is what makes the filename parse (§4.1). |
| `episode` | int ≥ 1 | episode index | **no** | Episode is the benchmark's outer unit and already exists as a log column (`scripts/long_run.py:488`). A record with no episode cannot be placed on a run timeline. |
| `encounter_id` | string | — | **no** | `"ep<EEE>-enc<CCC>"`, EEE/CCC zero-padded 3-digit. **Run-scoped, NOT a cross-run join key** — two models walking the same route meet different encounters in a different order, so equality of `encounter_id` across runs means nothing. Cross-run joins use `map` + `opponent_species` + level band (§5.3). |
| `turn` | int ≥ 1 | player-action index within the encounter | **no** | 1-based count of the **player's** attack/action slots. It is writer-derived, not a game counter: the only turn counter in the repo is Python-side in the legacy vision path (`src/game_loop.py:228`, incremented at `src/game_loop.py:975`). Deriving it is BTL-RAM-1's job (`OPEN:` O-2). Nullability is refused because a null turn makes "damage per turn" undefined, which is the comparison's primary metric. |
| `map` | string | ROM map name | **no** | The map the encounter started on, i.e. the `map_name` already carried on every decision row (`cron_runner.py:5723-5730`) and resolvable from RAM (`src/core/ram_reader.py:1179-1181`). Never null, but may be the **unresolved placeholder** `Map_XX` — flagged by `map_resolved` below, never silently joined. |
| `map_resolved` | bool | — | **no** | `false` exactly when `map` is the placeholder form `Map_[0-9A-F]{2}` that the reader emits for an unknown map id. Exclusion rule E1 keys on it. |
| `ts` | string | ISO-8601 UTC | **no** | Writer clock at observation. The repo's record idiom already stamps `created_at` in UTC (`src/core/duckbrain_client.py:55`) and `ts` on digests (`cron_runner.py:5952`). |
| `model_decision` | string | — | **yes** | The model (or arm label) that produced the decision. Null is legal **only** for a non-LLM arm; when null, `decision_arm` must be non-null. Grounded precedent: the run row already stamps `decision_mode` and a possibly-null `decision_model`/`decision_provider` (`cron_runner.py:5513-5522`), and the recorder signature types them optional (`cron_runner.py:5475-5478`). |
| `model_vision` | string | — | **yes** | The vision model, when the run used one. Null when battle state came from RAM only — that is a real configuration today (`cron_runner.py:9941-9947` fills `battle_state` from the RAM reader; `cron_runner.py:942-944` shows the vision client is a debug-only switch). |
| `provider` | string | — | **yes** | Provider that served `model_decision`. Null when the arm is unrecorded (e.g. the JEV-only arm), same grounds as `model_decision`. |
| `decision_arm` | string | — | **no** | The decision-architecture label (`DECISION_MODE` family, `cron_runner.py:5513-5514`). Always present so a run whose `model_decision` is null is still identifiable. |

### 3.2 Event fields — required on every record

| field | type | unit | may be null | why |
|---|---|---|---|---|
| `attacker_side` | enum `player` \| `enemy` | — | **no** | Damage-per-turn is only comparable when the sides are distinguished; the reader's battle state already separates `player` and `enemy` blocks (`src/core/ram_reader.py:1901-1931`). |
| `attacker_species` | string | — | **no** | May be the **unresolved placeholder** `#<id>` (`src/core/ram_reader.py:1808-1812`, whose last fallback is the raw id). Exclusion rule E2 keys on it. |
| `attacker_species_resolved` | bool | — | **no** | `false` when `attacker_species` matches `^#\d+$`. Mechanical, so a comparison never joins on an unresolved label. |
| `attacker_level` | int 2..100 | level | **no** | Level band is a head-line exclusion key (§5). A record whose level reads outside 2..100 MUST be dropped, never written with a null (3.3 R2). |
| `defender_species` | string | — | **no** | As `attacker_species`. |
| `defender_species_resolved` | bool | — | **no** | As `attacker_species_resolved`. |
| `defender_level` | int 2..100 | level | **no** | The opponent level band is the cross-run join key when the map does not repeat an encounter. |
| `battle_type` | enum `wild` \| `trainer` \| `unknown` | — | **no** | Wild-vs-trainer is a closed three-value set in the reader today (`src/core/ram_reader.py:1898-1900`) and decides whether fleeing was even legal — which is why flee counts are per-`battle_type`. |
| `move` | string | — | **no** | The move label. May be the **unresolved placeholder** `Move#<id>` (`src/core/ram_reader.py:1815-1817`). |
| `move_resolved` | bool | — | **no** | `false` when `move` matches `^Move#\d+$`. |
| `outcome` | enum `damage` \| `no_damage` \| `miss` \| `immune` \| `unknown` | — | **no** | Required so "0 damage" is unambiguous: a whiff (`miss`) and a status move (`no_damage`) both deal 0 but mean different things, and whiff count is a comparison metric (§6). `unknown` is legal only when the HP delta could not be attributed (e.g. the defender struct was unreadable that tick). |
| `damage` | int ≥ 0 | HP points | **no** | Observed defender HP delta for this event, clamped at 0 — the repo already clamps HP at 0 (`src/core/combat.py:198`), so overkill is never counted and two models that both KO the same defender report the same `damage` total (§6). |
| `damage_pct_of_max` | float 0.0..100.0, 1 dp | percent | **yes** | Null when the defender's max HP is not knowable — a real case: the reader substitutes current HP for max when the max read is out of range (`src/core/ram_reader.py:1881-1882`), and a percentage derived from that substitution would be a fabricated 100 %. |
| `defender_hp_before` | int ≥ 0 | HP points | **no** | Pre-event defender HP. Required because `damage` alone cannot tell a KO from a partial hit at equal damage values. |
| `defender_hp_after` | int ≥ 0 | HP points | **no** | Post-event defender HP (0 on a KO). |
| `defender_max_hp` | int ≥ 0 | HP points | **no** | Carried so a reader can compute percentages itself and so `0` means "unknown max" explicitly rather than being inferred from `damage_pct_of_max` being null. |
| `encounter_outcome` | enum `won` \| `lost` \| `fled` \| `caught` \| `unknown` | — | **no** | Stamped on every record of the encounter by ONE final rewrite of the partition at encounter close; a partition listed in a completed run's manifest is immutable afterwards. A partition still open (run crashed, battle unresolved) keeps `unknown` on its records rather than being rewritten from a second process. |

### 3.3 Validation rules (writer MUST enforce, BTL-RAM-1 owns the implementation)

- **R1** — every record carries the 11 identity keys of §3.1 and the 17 event fields of §3.2, spelled
  exactly as tabled. No extra required keys; extra keys are allowed and are additive (§ CT-08 policy).
- **R2** — a record whose `attacker_level`, `defender_level`, `defender_max_hp`, `defender_hp_before` or
  `defender_hp_after` is outside its declared range is **dropped**, not written with a null. The writer
  increments `dropped_records` in the manifest so the loss is visible.
- **R3** — `turn` is non-decreasing within a file; a new player action increments it by exactly 1. The
  enemy's response to turn *n* carries `turn = n` with `attacker_side = "enemy"`.
- **R4** — `damage == defender_hp_before - defender_hp_after` for `outcome = "damage"`;
  `damage == 0` for `outcome ∈ {no_damage, miss, immune}`. This is the arithmetic the comparison
  (§6) relies on.
- **R5** — on a KO record the delta IS the remaining HP, because HP clamps at 0 (`src/core/combat.py:198`);
  a writer MUST NOT compute damage from a damage formula when the observed delta is available.
- **R6** — all `*_resolved` flags are computed from the label form, never asserted by hand.

---

## 4. Partition keys and file layout

### 4.1 Exact path shape

```
~/duckbrain/namespaces/pokemon-battle/data/battle-<run_id>-ep<EEE>-enc<CCC>.jsonl
```

- The namespace root is the repo client's existing layout: one directory per namespace with a `data/`
  subdirectory under `DUCKBRAIN_ROOT` (`src/core/duckbrain_client.py:20`), created on demand by
  `_ensure_namespace()` (`src/core/duckbrain_client.py:24-28`). **Namespace `pokemon-battle`** — a
  dedicated namespace so battle telemetry is excluded from memory reads by construction (N9, §7).
- `<run_id>` matches `[A-Za-z0-9_]+` (source of truth: `cron_runner.py:957`, `scripts/long_run.py:36`).
- `<EEE>` = zero-padded 3-digit `episode`; `<CCC>` = zero-padded 3-digit encounter ordinal within that
  episode, starting at `001`.
- One file per encounter. Nothing else may live in `data/` except `memories-*.jsonl` written by the
  existing client for the manifest (§4.3).

**Why the file is not named `memories-<date>.jsonl`:** the client's memory reader globs exactly
`memories-*.jsonl` (`src/core/duckbrain_client.py:85`, and `:224` in `search()`). A `battle-` prefix is
therefore invisible to `recall()`/`search()` — telemetry can never bloat or slow a memory recall, and a
memory query can never return a battle record by accident. This is a requirement (N9), not an accident
of naming.

### 4.2 "Small" is a pair of hard caps

| cap | value | why this value |
|---|---|---|
| `MAX_RECORDS_PER_FILE` | **512** | A Gen-1 battle is tens of turns; 512 records is >10x the largest plausible encounter, so the cap never truncates an honest battle while still bounding every file a reader may open. |
| `MAX_BYTES_PER_FILE` | **262144** (256 KiB) | ~512 records at ~400 B each plus headroom. Byte cap exists because a record-count cap alone does not bound read-in cost if a record grows. |

Overflow rule (N5): an encounter that reaches 512 records must be **closed** and continued under the next
`enc<CCC>` with `continued_from: "<previous encounter_id>"` in the manifest. Appending past the cap is a
contract violation, not a judgement call.

### 4.3 One manifest per run

The manifest is **one DuckBrain record**, written with the existing client under an exact key so a reader
finds it without scanning:

- key: `/game/battle/<run_id>/manifest`
- domain: `game/battle`
- namespace: `pokemon-battle`
- written by `remember(key=..., domain=..., attributes={...}, embedding_text=..., namespace=...)`
  (`src/core/duckbrain_client.py:31-41`), read back by `get(key=...)`
  (`src/core/duckbrain_client.py:196-205`) or by prefix (`recall(key_prefix="/game/battle/")`,
  `src/core/duckbrain_client.py:130-157`).
- It lands in the namespace's date-partitioned `memories-<date>.jsonl`
  (`src/core/duckbrain_client.py:67-71`) — that is the client's existing write path and this contract
  does not change it. One record per run keeps that file small.

**Cap:** `MAX_MANIFEST_ENCOUNTERS = 1000` index entries. Beyond that the manifest sets
`truncated: true` and `encounters_total` to the true count; a run with >1000 encounters is not a
comparable benchmark run and its index must say so rather than growing an unbounded file.

The precedent for this shape is in-repo: `_record_run_index()` keeps one bounded record under
`/game/runs/index`, prepending this run's digest and keeping the last 10 (`cron_runner.py:5935-5966`).

Manifest `attributes`:

| field | type | may be null | purpose |
|---|---|---|---|
| `schema_version` | int = 1 | no | Contract version this run's files satisfy. |
| `run_id` | string | no | Redundant with the key on purpose: the record must be self-describing. |
| `decision_arm` | string | no | As §3.1. |
| `model_decision` / `model_vision` / `provider` | string | yes | As §3.1; nullability rules identical. |
| `started` / `ended` | ISO-8601 UTC | `ended` yes while running | Run window; `started` never null. |
| `episodes` | int ≥ 0 | no | Episodes completed. |
| `encounters_total` | int ≥ 0 | no | True encounter count, even when `index` is truncated. |
| `truncated` | bool | no | True when `index` is shorter than `encounters_total` or any encounter file was truncated at the record cap. |
| `dropped_records` | int ≥ 0 | no | Records the writer refused to write under §3.3 R2. Visible loss, not silent loss. |
| `index` | list of encounter entries (below) | no (may be empty) | The selection surface: everything §5 filters on. |

Encounter entry (one per partition):

| field | type | notes |
|---|---|---|
| `encounter_id` | string | `ep<EEE>-enc<CCC>`; unique within the run. |
| `file` | string | Basename under `data/`. Never an absolute path — the namespace root is derivable. |
| `map` | string | As §3.1. |
| `map_resolved` | bool | As §3.1. |
| `opponent_species` | string | The defending species. |
| `opponent_species_resolved` | bool | As §3.1. |
| `opponent_level` | int | The defending level. |
| `battle_type` | enum | As §3.1. |
| `turns` | int ≥ 0 | Highest player turn observed. Makes turn-window exclusion decidable. |
| `records` | int ≥ 0 | Record count in the file (≤ 512). |
| `outcome` | enum | As §3.1 `encounter_outcome`. |
| `continued_from` | string \| null | The `encounter_id` this partition continues after a cap split (§4.2). |
| `truncated` | bool | True when this partition hit the record cap. |

---

## 5. Exclusion by key

Exclusion must be decidable **from the manifest alone**. No event file may be opened to decide whether
it should be opened. This is the whole point of the operator law (§2).

### 5.1 The keys a comparison query filters on

| # | key | source | where it is read from |
|---|---|---|---|
| E1 | `map` (+ `map_resolved`) | manifest entry | manifest only |
| E2 | `opponent_species` (+ `opponent_species_resolved`) | manifest entry | manifest only |
| E3 | `opponent_level` → **level band** `[lo, hi]` | manifest entry | manifest only |
| E4 | `encounter_id` | manifest entry | manifest only |
| E5 | turn window `[t_lo, t_hi]` | manifest entry `turns` | manifest only |
| E6 | `battle_type` | manifest entry | manifest only |
| E7 | `run_id` | filename prefix **and** manifest | directory listing + manifest |
| E8 | per-record turn/attacker refinement (`turn`, `attacker_side`, `outcome`) | record | event file — **after** it was selected by E1..E7 |

### 5.2 Decision procedure (fixed; BTL-COMPARE-1 must implement exactly this order)

1. Resolve the candidate runs by `run_id` (E7). A run not named by the caller is never listed or opened.
2. For each candidate run, read **only** `/game/battle/<run_id>/manifest`.
3. Apply E1..E6 to `index` entries in memory. The surviving entries name the files to open.
4. Open exactly those files. Apply E8 while scanning.
5. Report, in the answer, the number of partitions **read** and **excluded**, and why (per key).

An implementation that opens a file whose manifest entry fails E1..E6 is a contract violation even if its
numbers are right — the read cost is the thing being controlled.

### 5.3 Worked exclusion examples

Assume run `20261117_090000` has 5 index entries and run `20261117_093000` has 3.

**Q1 — "all wild encounters in Viridian Forest, both runs".**
Filter: `map == "Viridian Forest" && map_resolved && battle_type == "wild"`.
Reads: `battle-20261117_090000-ep004-enc002.jsonl`, `…-ep005-enc001.jsonl`;
`battle-20261117_093000-ep002-enc001.jsonl`.
Excluded without opening: the other 3 + 2 partitioned files in the two runs (their `map` or `battle_type`
fails), and **every file of every other run** (never listed — E7 is applied at the path level).
Decidable from: 2 manifests, 0 event files.

**Q2 — "same opponent: Pidgey, levels 3..5, any run".**
Filter: `opponent_species == "Pidgey" && opponent_species_resolved && 3 <= opponent_level <= 5`.
Reads: only entries passing it. Excluded without opening: entries whose `opponent_species` is the
unresolved form `#<id>` (`opponent_species_resolved == false`, rule E2), entries at level 2 or 6
(E3 band), and everything in Q1 that is not a Pidgey.
Decidable from: manifests only.

**Q3 — "only encounters that last 8 turns or more".**
Filter: `turns >= 8`.
Reads: entries with `turns >= 8`. Excluded without opening: every short encounter — the turn window is a
manifest property (`turns`), so a reader never has to scan a file to learn a battle was short.
Decidable from: manifests only.

**Q4 — "replay one encounter: run A, episode 4, encounter 2".**
Filter: `encounter_id == "ep004-enc002"`.
Reads: 1 file. Excluded: all others by E4. Note Q4 is **not** how two models are compared — see the
`encounter_id` warning in §3.1: ordinals do not align across runs.

**Join rule (must be stated in every comparison output):** a cross-run comparison joins on
`(map, opponent_species, level band)`, never on `encounter_id` and never on `turn` index alone (two
models' turn 3 are different game moments unless the segment matches).

---

## 6. Worked example — two models on one shared segment

**Segment:** Viridian Forest, wild `Weedle`, level 3, defender max HP **15**.
**Run A** `20261117_090000` — `model_decision = deepseek-v4-flash`, `provider = deepseek`.
**Run B** `20261117_093000` — `model_decision = glm-5.3-flash`, `provider = zai`.

Selection (E1..E3): run A's partition `ep004-enc002`, run B's partition `ep002-enc001`. Two files read.

Run A records (`attacker_side = player`, `battle_type = wild`, `map = Viridian Forest`):

| turn | move | outcome | damage | defender_hp_before | defender_hp_after |
|---|---|---|---|---|---|
| 1 | TACKLE | damage | 4 | 15 | 11 |
| 2 | TACKLE | damage | 5 | 11 | 6 |
| 3 | TACKLE | damage | 4 | 6 | 2 |
| 4 | TACKLE | damage | 2 | 2 | 0 (KO) |

Run B records:

| turn | move | outcome | damage | defender_hp_before | defender_hp_after |
|---|---|---|---|---|---|
| 1 | TACKLE | miss | 0 | 15 | 15 |
| 2 | TACKLE | damage | 3 | 15 | 12 |
| 3 | TACKLE | damage | 4 | 12 | 8 |
| 4 | TACKLE | miss | 0 | 8 | 8 |
| 5 | TACKLE | damage | 4 | 8 | 4 |
| 6 | TACKLE | damage | 4 | 4 | 0 (KO) |

Comparison table (the deliverable of the query):

| metric | run A (deepseek-v4-flash) | run B (glm-5.3-flash) |
|---|---|---|
| partitions read | 1 | 1 |
| `turns_to_ko` (max `turn` at KO) | 4 | 6 |
| `attacks_to_ko` (player records, outcome ≠ `no_damage`) | 4 | 6 |
| `hits` / `attacks` | 4 / 4 = 1.000 | 4 / 6 = 0.667 |
| `whiff_count` (`outcome == "miss"`) | 0 | 2 |
| `damage_dealt_total` | 15 | 15 |
| `damage_per_turn` = total / `turns_to_ko` | 3.75 | 2.50 |
| `flee_count` (`encounter_outcome == "fled"`) | 0 | 0 |
| `encounter_outcome` | won | won |

**Arithmetic actually used (stated so it can be re-checked):**
- A damage: 4 + 5 + 4 + 2 = **15**; 15 / 4 = **3.75**; hits 4 of 4 = **1.000**.
- B damage: 0 + 3 + 4 + 0 + 4 + 4 = **15**; 15 / 6 = **2.50**; hits 4 of 6 = **0.6667 ≈ 0.667**.
- Both totals equal the defender's max HP (15) because `damage` is an observed HP delta clamped at 0
  (§3.2, `src/core/combat.py:198`): a KO turn cannot report overkill, so a fast and a slow model that
  both win report the same total damage and differ only in turns, hits and whiffs — which is exactly the
  comparison the operator asked for.

**Partitions NOT read, enumerated:** run A's four other partitions
(`ep001-enc001`, `ep002-enc001`, `ep003-enc001`, `ep005-enc001`), run B's two other partitions
(`ep001-enc001`, `ep003-enc001`) — 6 files excluded inside the two selected runs — plus the entire
`battle-<run_id>-*` set of every other run, excluded at the path level by E7 without a manifest read.
Total opened for the table above: **2 files, 10 records**.

---

## 7. THE NEVER-ONE-BIG-FILE RULE

Nine numbered requirements. The first script in §7.1 covers N1 (repo half), N2, N3, N4 and N6
mechanically, and its root-listing pass covers N8 and N9; N5 is enforced by N2+N3 together (a continuation
that appended to the same file would breach N3, and a continuation under a new `enc` is what N2's parse
accepts); N7 has its own script in §7.1.

- **N1** — every telemetry event file lives under
  `~/duckbrain/namespaces/pokemon-battle/data/`. No telemetry file may be written to `cron_logs/`,
  `data/`, or any repo path.
- **N2** — every event file path matches `battle-<run_id>-ep<EEE>-enc<CCC>.jsonl` with
  `run_id` matching `[A-Za-z0-9_]+`. A file that does not parse is a violation, not an orphan.
- **N3** — no event file contains more than **512** records.
- **N4** — no event file is larger than **262144** bytes.
- **N5** — exactly one encounter per file; a cap overflow continues in a **new** `enc<CCC>` partition
  with `continued_from` set. No append may ever push a file past N3/N4.
- **N6** — every record carries the §3.1 identity keys, and its `run_id`/`episode`/`encounter_id` agree
  with the values parsed from the filename.
- **N7** — exactly one manifest per run (key `/game/battle/<run_id>/manifest`), with
  `len(index) <= 1000`; when `len(index) < encounters_total`, `truncated` must be `true`.
- **N8** — no aggregate, rollup, or "all runs" telemetry file exists. Aggregates are computed at read
  time (§6). A file named e.g. `battle-all.jsonl` fails N2 and therefore fails this rule too.
- **N9** — telemetry files are never named `memories-*.jsonl`, so the client's memory readers
  (`src/core/duckbrain_client.py:85`, `:224`) never scan them. The only `memories-*.jsonl` content in
  this namespace is the manifest record.

### 7.1 The check (paste and run)

Runs with plain `python3` — no venv, no repo imports. Exits 0 with `NO_TELEMETRY_FILES` while no
telemetry exists yet (a vacuous pass, reported as such), 1 on any violation.

```bash
python3 - <<'PY'
import json, os, re, subprocess, sys
from pathlib import Path

NS = "pokemon-battle"
root = Path(os.path.expanduser(f"~/duckbrain/namespaces/{NS}/data"))
MAX_RECORDS, MAX_BYTES = 512, 262144
NAME = re.compile(r"^battle-([A-Za-z0-9_]+)-ep(\d{3})-enc(\d{3})\.jsonl$")
REQUIRED = ("run_id", "episode", "encounter_id", "turn", "map", "map_resolved", "ts",
            "model_decision", "model_vision", "provider", "decision_arm")

bad = []

# N1/N8: no telemetry anywhere in the repo tree
try:
    stray = subprocess.run(
        ["git", "ls-files", "-z", "--", "*battle*.jsonl"],
        capture_output=True, text=True, check=False,
    ).stdout.split("\0")
    stray = [p for p in stray if p]
except OSError:
    stray = []
for p in stray:
    bad.append(f"N1: telemetry inside the repo: {p}")

# N1/N8: nothing in the namespace data dir but battle-*.jsonl and the client's memories-*.jsonl
if root.is_dir():
    for p in sorted(root.iterdir()):
        if p.is_file() and not (
            (p.name.startswith("battle-") and p.suffix == ".jsonl")
            or (p.name.startswith("memories-") and p.suffix == ".jsonl")
        ):
            bad.append(f"N1/N8: unexpected file in telemetry root: {p.name}")

# N9: the only memories-*.jsonl content in this namespace is the manifest record(s)
if root.is_dir():
    for p in sorted(root.glob("memories-*.jsonl")):
        for i, ln in enumerate([x for x in p.read_text().splitlines() if x.strip()], 1):
            try:
                rec = json.loads(ln)
            except json.JSONDecodeError as exc:
                bad.append(f"N9: {p.name}:{i} is not JSON ({exc})")
                continue
            if not str(rec.get("key", "")).startswith("/game/battle/"):
                bad.append(f"N9: {p.name}:{i} carries a non-manifest key {rec.get('key')!r}")

files = sorted(root.glob("battle-*.jsonl")) if root.is_dir() else []
if not files:
    print(f"NO_TELEMETRY_FILES: {root} holds no battle-*.jsonl yet — N2..N6 are vacuously satisfied")
    print("STRAY_IN_REPO: none" if not bad else "STRAY_IN_REPO: " + "; ".join(bad))
    sys.exit(0 if not bad else 1)

total = 0
for p in files:
    m = NAME.match(p.name)
    if not m:
        bad.append(f"N2: {p.name} does not parse to run_id+episode+encounter_id")
        continue
    run_id, ep, enc = m.group(1), int(m.group(2)), int(m.group(3))
    expect_eid = f"ep{ep:03d}-enc{enc:03d}"
    if p.stat().st_size > MAX_BYTES:
        bad.append(f"N4: {p.name} is {p.stat().st_size} B > {MAX_BYTES}")
    lines = [ln for ln in p.read_text().splitlines() if ln.strip()]
    if len(lines) > MAX_RECORDS:
        bad.append(f"N3: {p.name} has {len(lines)} records > {MAX_RECORDS}")
    for i, ln in enumerate(lines, 1):
        try:
            rec = json.loads(ln)
        except json.JSONDecodeError as exc:
            bad.append(f"N6: {p.name}:{i} is not JSON ({exc})")
            continue
        missing = [k for k in REQUIRED if k not in rec]
        if missing:
            bad.append(f"N6: {p.name}:{i} missing {missing}")
        if rec.get("run_id") != run_id:
            bad.append(f"N6: {p.name}:{i} run_id {rec.get('run_id')!r} != path {run_id!r}")
        if rec.get("encounter_id") != expect_eid:
            bad.append(f"N6: {p.name}:{i} encounter_id {rec.get('encounter_id')!r} != {expect_eid!r}")
    total += len(lines)

if bad:
    print(f"BATTLE_TELEMETRY_PARTITION: FAIL ({len(bad)} violations)")
    for b in bad:
        print("  -", b)
    sys.exit(1)
print(f"BATTLE_TELEMETRY_PARTITION: PASS ({len(files)} files, {total} records, cap {MAX_RECORDS} rec / {MAX_BYTES} B)")
PY
```

N7 has its own one-liner (the manifest is a DuckBrain record, not a file on a glob). Run it from the repo
root: it loads the repo client **by file path**, so `src/core/__init__.py` (which pulls in the mode-duration
package) is never imported.

```bash
python3 - <<'PY'
import importlib.util
spec = importlib.util.spec_from_file_location("aipp_duckbrain_client", "src/core/duckbrain_client.py")
dc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dc)
for rec in dc.recall(key_prefix="/game/battle/", namespace="pokemon-battle", limit=1000):
    a = rec.get("attributes", {})
    idx = a.get("index", [])
    if idx and len(idx) < int(a.get("encounters_total", 0)) and not a.get("truncated"):
        print(f"N7 FAIL {a.get('run_id')}: {len(idx)} of {a.get('encounters_total')} and truncated!=true")
        raise SystemExit(1)
    if len(idx) > 1000:
        print(f"N7 FAIL {a.get('run_id')}: index {len(idx)} > 1000")
        raise SystemExit(1)
print("MANIFEST_RULE: PASS (0 manifests today is a vacuous pass)")
PY
```

---

## 8. Interface boundary — no RAM address is asserted here

1. **This document asserts no RAM address, offset, or symbol-address pair.** A grep for any hex
   address literal in this file must return nothing — that is requirement R-014 in the R-table of
   `_matrix.md`, and it is mechanically checkable with the command written there.
2. The reader row **BTL-RAM-1** derives every address from the ROM symbol map (`data/rom/*.sym`, or the
   repo's existing symbol source if that is what ships). It must never take an address from this
   document, from memory of a previous session, or from a hardcoded literal.
3. Status of the symbol map, stated honestly: **no `.sym` file exists in `data/rom/` today** (only
   `.gb` dumps and `data/rom/README.md`, which documents the ROM path convention and nothing about
   symbols). Until a symbol map is checked in, the only grounded address source in the repo is the
   constant block the existing reader already carries (`src/core/ram_reader.py:31-89`), which the reader
   row may adopt **by moving it behind the symbol-map lookup**, never by copying numbers into this
   contract. `OPEN:` O-1.
4. Battle-state semantics this contract leans on are those the reader already produces — species, level,
   HP, max HP, types, moves and the wild/trainer discriminator of `read_battle_state()`
   (`src/core/ram_reader.py:1825-1932`). The contract's field names are its own; the mapping from that
   dict to these fields is BTL-RAM-1's deliverable.
5. `turn` is **writer-derived** (§3.1). The contract fixes its meaning; deriving it is BTL-RAM-1's job
   (`OPEN:` O-2).

---

## 9. Where the store lives (grounded in existing code)

- **Client:** `src/core/duckbrain_client.py` — file-system JSONL, no MCP/HTTP needed (module docstring,
  `src/core/duckbrain_client.py:1-6`).
- **Root layout:** `DUCKBRAIN_ROOT = ~/duckbrain/namespaces` (`src/core/duckbrain_client.py:20`);
  namespace data dir created by `_ensure_namespace()` (`src/core/duckbrain_client.py:24-28`).
- **Append doctrine:** one JSON object per line, appended with `open(path, "a")` + a trailing newline
  (`src/core/duckbrain_client.py:67-71`); the run harness uses the same idiom for its log rows
  (`cron_runner.py:5979-5988`, `json.dumps(row, default=str) + "\n"`).
- **Read doctrine:** newest-first glob + skip-unparseable lines (`src/core/duckbrain_client.py:76-102`);
  key/prefix/domain/label filters (`src/core/duckbrain_client.py:130-157`); exact-key lookup
  (`src/core/duckbrain_client.py:196-205`).
- **Battle telemetry is a NEW file family in a NEW namespace.** It does not reuse `memories-<date>.jsonl`
  for events (N9) and it does not reuse the `pokemon-global` namespace (`cron_runner.py:5712` writes
  run summaries there). The manifest uses the existing `remember()`/`get()` API unchanged.
- **Battle facts already available to stamp on a record** without any new read: the run's identity
  (`cron_runner.py:957`), the decision arm and model/provider (`cron_runner.py:5513-5522`), and the
  encounter's start event with its `battle_type` (`cron_runner.py:9963-9975`).
- **What the store row must NOT do:** add a byte-identical copy of the run log into telemetry, or write a
  rollup (N8). The event file is written by the telemetry writer only.

---

## 10. OPEN decisions (deliberately not invented here)

- **O-1 — Source of the symbol map.** No `.sym` is present in `data/rom/`. BTL-RAM-1 must either check
  one in (generated from the ROM, not copied from another project) or state which existing constant block
  it treats as the symbol source, and prove each address it uses against that source. This contract
  cannot decide it because the artifact does not exist in the repo yet.
- **O-2 — How `turn` is detected.** `turn` is fixed to "1-based player-action index" (§3.1) but how a
  completed player action is observed (move animation end, defender-HP change, PP decrement) is a reader
  decision. It must be deterministic, or two runs of the SAME model on the SAME segment produce different
  turn counts and every comparison is noise.
- **O-3 — Enemy-side records.** §3 says an exchange produces two records. Whether the enemy's response is
  attributed to the same `turn` (this document's choice) or an offset (`turn n` for the player,
  `turn n + 0.5` conceptually) matters for "damage taken per turn". This contract fixes the choice;
  BTL-COMPARE-1 must not invent a second convention.
- **O-4 — Transport beyond the filesystem.** The client writes locally (`src/core/duckbrain_client.py:1-6`).
  If telemetry must also reach the DuckBrain HTTP server (`POST /api/memories` per fleet practice), the
  store row decides when that happens for event files; this contract only fixes what the files look
  like on disk. Event files are NOT memories and must not be POSTed as memory records (N9).
- **O-5 — Manifest write timing.** Written once at run end (like `_record_run_index`,
  `cron_runner.py:5935-5966`) or incrementally per encounter close. Incremental is friendlier to a
  crashed run; it also re-writes a growing record. Either is compatible with §4.3; BTL-STORE-1 decides
  and must keep `len(index) <= 1000`.

---

## 11. Acceptance the child rows inherit

| row | must satisfy |
|---|---|
| BTL-RAM-1 | produce every §3.1/§3.2 field with the §3.3 rules; derive `turn` (§10 O-2); derive addresses from the symbol map (§8); drop-and-count rather than write a null (R2). |
| BTL-STORE-1 | write the §4.1 path shape, enforce §4.2 caps, write the §4.3 manifest under the exact key with the client's `remember()`; keep `battle-*` out of `memories-*` (N9); pass the §7.1 check with real files. |
| BTL-COMPARE-1 | implement §5.2's decision order exactly, report read/excluded partition counts, join on `(map, opponent_species, level band)` only, and reproduce §6's table shape with the stated arithmetic. |
