# SITREP PRD — AI Plays Pokémon (ai-plays-poke)

**Project:** PTP-01X — Autonomous Pokémon (Gen 1) Gameplay AI Benchmark
**SITREP Date:** 2026-08-02 | **Report by:** Hermes (Luna/DeepSeek controller work)
**Status:** 🟢 STABLE — NAVIGATION & VISION PIPELINE OPERATIONAL
**Repo:** `/home/kara/ai_plays_poke` | **HEAD:** `3f921de` (340 commits)

---

## 1. EXECUTIVE SUMMARY

The project is a **fully autonomous Pokémon Red/Blue gameplay agent** that reads live
emulator RAM state, sees screenshots (Luna vision via OpenRouter), plans button
sequences with an LLM controller, and executes them in a real Game Boy emulator.

**This reporting period delivered three capability milestones:**

1. **Luna (vision model) became the gameplay controller** — switched from GPT-4o-class
   text-only to `openai/gpt-5.6-luna` via Bane's discounted OpenRouter key, with
   live screenshot vision.
2. **The agent can now navigate indoors** — Oak's Lab was previously *invisible*
   (tileset 5 unclassified → 100% unknown tiles → void-lock loop). Fixed: agent
   now sees the lab, walks around it, and talks to Professor Oak.
3. **Persistent frame cache with UUID references** — repeated screenshots (same
   tile, dialog boxes, looping flow) are referenced by UUID instead of
   re-sent as images. **65% cache hit rate, ~$0.67 per 80-cycle run.**

**Current capability:** Reaches Oak's Lab reliably (cycle 19), navigates the lab,
advances dialog correctly (A-advance, no more START/B traps). Next milestone:
pick the starter Pokémon and leave the lab.

---

## 2. SYSTEM ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────────┐
│                    cron_runner.py (main loop)                  │
│                                                                 │
│  ┌────────────┐   ┌──────────────┐   ┌──────────────────────┐  │
│  │  Emulator  │──▶│  RAM Reader  │──▶│  Spatial Summary      │  │
│  │ (pyboy GB) │   │ (wCurMap,    │   │  (map, tiles, facing, │  │
│  │            │   │  tiles, NPCs)│   │   exits, text)        │  │
│  └────────────┘   └──────────────┘   └──────────┬───────────┘  │
│         │                                        │             │
│         ▼                                        ▼             │
│  ┌────────────┐   ┌──────────────────┐   ┌──────────────────┐  │
│  │ Screenshot │──▶│  Frame Cache     │──▶│  Controller:     │  │
│  │ (PNG)      │   │  (md5 → UUID,    │   │  Luna (vision)   │  │
│  │            │   │   LRU 1000,      │   │  via OpenRouter  │  │
│  │            │   │   disk-persisted)│   │  → JSON plan     │  │
│  └────────────┘   └──────────────────┘   └────────┬─────────┘  │
│                                                   │            │
│                                                   ▼            │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Plan executor: max 6 actions/cycle, RLE cap (3 same-dir),│  │
│  │  spatial filter, fast-forward, stuck/void/dialog recovery │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

**Key components (src/core/):**
| Module | Role |
|---|---|
| `emulator.py` | pyboy Game Boy wrapper — buttons, fast-forward, save states |
| `ram_reader.py` | Live RAM state: map ID, player tile, adjacent tiles (block-classified per tileset), screen text, NPCs |
| `frame_cache.py` | **NEW** — persistent md5→UUID screenshot cache (LRU 1000, disk-backed) |
| `ai_client.py` | OpenRouter client (Luna, discounted pricing) |
| `state_window.py` | Dialog/battle/menu state machine |
| `cron_runner.py` | Orchestration + recovery ladder |

---

## 3. SCREENSHOT REPORT (live frames from Luna run v9)

### 3.1 Pallet Town — start of the run (cycle 1-2)
![Pallet Town](screenshots/run_luna_v9_20260801_160906/step_0002.png)
*Overworld spawn. RAM reader identifies: map_id=0 (Pallet Town), player at (2,3).
Tileset 0 classification: 61/90 known (grass, floor, walls, ledges).*

### 3.2 Oak's Lab — first entry (cycle 19)
![Oak's Lab entry](screenshots/run_luna_v9_20260801_160906/step_0019.png)
*Agent walked from Pallet Town north into Oak's Lab (map_id=40, tileset 5).
Before the tileset-5 fix this screen was 100% "unknown" → agent was blind.
Now: 30/30 blocks classified (floor 0x05, walls 0x65-0x6B, machines 0x6D/0x6E).*

### 3.3 Rival dialog — Oak's Lab (cycle 30)
![Rival dialog](screenshots/run_luna_v9_20260801_160906/step_0030.png)
*"AAAAAAA: Heh, I don..." — the rival's introduction. The A-mash intro bypass
leaves the default name. Dialog handled via **dialog_advance recovery** (12× A),
NOT the old START→B→B menu_redraw trap.*

### 3.4 Professor Oak — starter selection approaching (cycle 80, end of run)
![Oak dialog](screenshots/run_luna_v9_20260801_160906/step_0080.png)
*"Go ah..." = "Go ahead! Take it!" — the starter-selection dialog. The agent
is mid-conversation with Oak, one step from receiving a starter Pokémon.*

---

## 4. MILESTONES & CAPABILITY MATRIX

| Capability | Status | Evidence |
|---|---|---|
| Boot ROM, skip intro, name entry | ✅ | A-mash bypass, deterministic |
| Navigate Pallet Town | ✅ | 8 cycles, 6+ positions |
| Enter Oak's Lab (map transition) | ✅ | Reached at cycle 19 (run v9) |
| See & navigate indoor lab | ✅ **NEW** | Tileset 5 fix — 30/30 blocks known |
| Dialog advance (A-mash) | ✅ **NEW** | dialog_advance recovery, no menu_redraw trap |
| Rival/Oak conversation | ✅ | Screenshots 3.3-3.4 |
| Starter selection | 🟡 NEXT | Currently at "Go ahead! Take it!" |
| Route 1 / wild battles | ⏳ | Not yet reached |
| Vision dedup (frame cache) | ✅ **NEW** | 65% hit rate, UUID refs, cross-run persistence |

---

## 5. PERFORMANCE & COST (Luna runs, OpenRouter)

| Metric | Run v9 (80 cyc) |
|---|---|
| Controller calls | 48 |
| **Cache hit rate** | **65%** (31/48 calls = text-ref, no image) |
| Tokens saved | ~7,750 (31 × ~250 image tokens) |
| **Total API cost** | **$0.67** (avg $0.0139/call) |
| Recoveries | 4 (3× dialog_advance, 1× alternate_direction) |
| Void-locks / give-ups | **0 / 0** |
| Latency | ~2.5-4.3s/call (Luna vision) |

**All Luna runs (9 runs, 127 controller calls): 47 cache hits (37%).**
Cache compounds: 45 unique frames learned → every future run starts warm.

---

## 6. RECENT FIXES (this reporting period)

| Commit | Fix |
|---|---|
| `0f80f4d` | Sol RCA session: PRESS_FRAMES 120→5, STEP_FORWARD 300→15, north-exit fix, coordinate-aware hints → reached Oak's Lab |
| `39088d5` | **Vision dedup** (changed-frame only), **dialog A-advance**, **tileset 5/1 block classes** (Oak's Lab visible) |
| `7940955` | **Persistent FrameCache** — UUID references, LRU 1000, disk-backed, cross-run |
| `94d7a40` | MYPY full-repo sweep — 40+ errors cleared, 0 remaining |
| `88970ae` | CI parity — ruff pinned, CI green |

---

## 7. QUALITY GATES (T66 audit, all green)

| Gate | Result |
|---|---|
| Tests | **3,821 collected** / 3,808 passed / 8 skipped / 0 failed |
| mypy | 0 errors / 61 files |
| ruff | PASS |
| compileall | PASS |
| gitleaks (secrets) | CLEAN — 339 commits scanned |
| CI (GitHub Actions) | GREEN 5/5 |
| GitReins tasks | 3/3 complete, 0 pending |
| Scheduler | Enabled, CooldownS=7200 |
| hilo graph | 128,584 edges / 17,907 files |

---

## 8. NEXT STEPS (priority order)

1. **P1 — Get the starter**: extend run past the "Go ahead! Take it!" dialog —
   likely needs a starter-selection decision branch (press A on a Poké Ball
   choice) + post-choice state detection (party count via RAM).
2. **P2 — E2E-001** (recurring fixture, due T67): full front-to-back gameplay test.
3. **P3 — Route 1 navigation**: tileset 1/0 coverage already good; needs
   grass-transition + wild-battle handling (battle screen state machine exists).
4. **P4 — Cache tuning**: bump `MAX_ENTRIES` 1000 → 5000 if disk is fine;
   add per-frame context (map name) to the ref marker for Luna's benefit.

---

## 9. RISKS & NOTES

- **Cost**: vision calls ~$0.014 each; frame cache is the main lever — at 65%
  hit rate an 80-cycle run is $0.67. Longer runs amortize better.
- **Latency**: 2.5-4.3s/API call is the bottleneck (~4-6s/cycle). Options:
  raise CART_STEPS 6→12 (halve calls) at slight navigation accuracy cost.
- **Name "AAAAAAA"**: intro bypass leaves the rival's default name — cosmetic,
  affects dialog text only.
- **Emulator state**: ROM-gated tests; full suite needs the ROM present
  (present locally, gitignored).

---

*Prepared by Hermes Agent — ai-plays-poke SITREP. Data from live runs
(run_luna_v9_20260801_160906.jsonl), frame cache, and T64-T66 audits.*
