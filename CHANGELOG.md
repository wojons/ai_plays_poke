# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.2.0] - 2026-11-16

### Added

- Monitoring: the cron lane now writes a node_exporter textfile completion record
  (`cron_runner.py`), so run completion is observable from the fleet scrape without
  log parsing (MON-AIPP-2), covered by `tests/test_cron_runner_textfile.py`.

### Fixed

- Packaging: ship the `src` package intact so the wheel is installable —
  `src/game_loop.py` uses package-relative imports and `pyproject.toml` declares the
  package layout, closing the broken-wheel defect carried by `v1.0.0`/`v1.1.0`
  (RELEASE-007), guarded by `tests/test_packaging.py`.
- Tests: `tests/test_vision_model_e2e.py` no longer fails on a hardcoded developer
  `.env` path — `_load_repo_env()` tolerates a missing or unreadable file and the
  test skips instead of failing (QA-AI-PLAYS-POKE-25).

### Notes

- Range `v1.1.0..bb10268`: 17 commits, 3 material (1 feat, 2 fix), 14 bookkeeping
  (10 board, 4 handbook/spec docs).
- No breaking changes in this release (`BREAKING CHANGE:` / `type!:` census = 0).
- The Unreleased section carried four bullets present unchanged since `v1.0.0` and
  unbound to any commit in this range; they were deliberately not claimed by `1.2.0`.
  RELEASE-010 was resolved on 2026-11-17 by binding all four to the commits that landed
  them and filing them under `[1.0.0]` — see that section's "Backfilled provenance" and
  Notes.
- Rollback path: previous release `v1.1.0`.

## [1.1.0] - 2026-11-04

### Added

- Ordered vision model registry with per-run model selection (VIS-MODEL-1 M1/M2),
  recorded live vision model grids (M2), and a vision structure scorer with live
  model comparison (M3/M4).
- ARM-2: runtime-selectable decision models, with per-mode model and provider
  selection recorded on decision rows and run rows (AC3).
- Observability: `GET /metrics/prometheus` exposing five P0 `aipp_*` metrics
  (MON-AIPP-1).

### Fixed

- Navigation: preserve legal dead-end exits, emit a dedicated dead-end event when
  every walkable direction is forbidden, and route to dead-end map exits even when
  the target map is visited (DF-AIPP-17); block immediate model edge recrossing
  (DF-AIPP-21).
- Teacher/escalation: re-arm gap-class re-escalation so gap triggers reach the
  teacher, allow one bounded teacher re-escalation per missing class
  (DF-AIPP-13-R2), and deliver jev gap handoffs with treadmill-regression
  detection (DF-AIPP-13).
- Vision: include the model key in `VisionClient` fallback results; share vision
  cell classes across scorers.
- Dashboard: surface occupied-port failure (DF-AIPP-14) and show an env-warning
  banner when `PTP_API_KEY` is unset (DF-AIPP-15).
- CI/tests: bound `pytest<9.2` so the pytest-benchmark fixture stops erroring
  (INT-CI-2), and preserve Python package initializers for `act`
  (QA-AI-PLAYS-POKE-19).
- QA: retain the newest screenshot during cleanup (QA-AI-PLAYS-POKE-22).
- GitReins: give the tier1 secrets scan load headroom, raise the evaluator
  iteration budget, narrow the secrets allowlist with a `.env.example`
  sensitive-path override (INT-GL-2), and set the effective evaluator iteration
  default.

### Changed

- Dependency reconcile (SUP-DEPS-20261022-AIP): `anthropic` 1.15.0 → 2.3.0 (the
  2.x breaking change is the default API-version date; the `extra_body`
  temperature forward is preserved and covered by
  `TestClaudeClientRealSDKCallShape`), `fastapi` 0.152.0 → 0.162.0. `pyboy` stays
  pinned `<2.8.0` (save-state format break — see `requirements.txt`).

### Notes

- Range `v1.0.0..v1.1.0`: 159 commits, 26 material (6 feat, 19 fix, 1 perf).
  Board/harness bookkeeping (47 board, 36 foreman, 5 releng, 3 pm, 7 qa-cron,
  12 chore, 9 docs, 8 merge) is not itemized here.
- No breaking changes in this release (`BREAKING CHANGE:` / `type!:` census = 0).
- Rollback path: previous release `v1.0.0`.

## [1.0.0] - 2025-12-31

### Added

- Initial project setup for PTP-01X Pokemon AI
- **CLI flag system** with 56 configurable flags for run control
- **Mode duration tracking** with 10 core classes (ModeClassifier, DurationTracker, DurationProfileLearner, AnomalyDetector, BreakoutManager, etc.)
- **Hierarchical State Machine** with 69 states across 8 categories (BOOT, TITLE, MENU, DIALOG, OVERWORLD, BATTLE, EMERGENCY, TRANSITION)
- **Vision & Perception Engine** with 5 modules:
  - VisionPipeline (normalization, ROI extraction)
  - OCREngine (text extraction from dialog/menus)
  - SpriteRecognizer (Pokemon sprite identification)
  - BattleAnalyzer (battle state analysis)
  - LocationDetector (overworld location identification)
- **Tactical Combat Heuristics** with Gen 1 damage formula implementation
- **World Navigation** with A* pathfinding and HM dependencies (Cut, Surf, Strength, Flash, etc.)
- **GOAP Decision Core** with 6 goal types (DefeatGym, CatchPokemon, ReachLocation, HealParty, TrainPokemon, ObtainItem) and 4 action types
- **Observability Dashboard** with FastAPI REST endpoints and WebSocket streaming
- **AI Client Layer** with:
  - OpenRouter integration for GPT-4o family
  - Claude API support (Anthropic SDK ready)
  - PromptManager for structured prompt selection
  - RobustJSONParser with 5 recovery strategies
  - TokenTracker for cost tracking (accurate to $0.001)
  - RateLimiter with exponential backoff
  - CircuitBreaker pattern for API resilience
  - ModelRouter for provider selection
  - CostOptimizer for budget management
  - PerformanceTracker for metrics monitoring
- **Prompt Library** with 55 prompts across 5 categories:
  - Battle (16): basic_fighting, move_selection, switch_decision, status_management, catch_strategy, boss_preparation, type_matchup, priority_moves, setup_sweeper, cleanup_role, hazard_control, weather_strategy, tailwind_support, terrain_strategy, reversal_mind, endgame_timing
  - Exploration (11): pathfinding, route_planning, hm_usage, area_mapping, safe_routes, shortest_path, resource_gathering, hidden_item_hunting, legendary_encounter, cave_exploration, water_route_planning
  - Dialog (11): text_flow, shop_navigation, trainer_intro, story_advancement, item_description, npc_conversation, yes_no_decisions, menu_selection, save_prompt, gift_receiving, rival_interaction
  - Menu (1): navigation
  - Strategic (16): game_planning, badge_progress, team_gaps, experience_allocation, long_term_goals, ev_optimal, iv_breeding, nature_selection, move_tutor_priority, tm_acquisition, berry_strategy, contest_training, pokedex_completion, money_management, trading_strategy, post_game_content
- **Architecture Documentation** in docs/architecture.md with:
  - System overview diagram (Mermaid)
  - Component relationships and data flow
  - State machine diagrams
  - Memory architecture (tri-tier: Observer/Strategist/Tactician)
  - Technology stack documentation

#### Backfilled provenance (RELEASE-010)

These four entries describe behaviour that was in the `v1.0.0` tree but sat under
the Unreleased heading without a commit binding. Two things are stated separately here,
because a RELEASE-010 review showed they had been conflated:

- **Who wrote the text:** all four bullets were authored by `9d54337` (2026-10-02,
  `chore(release): canonical version 1.0.0 + release-check tooling`). That commit added
  the sentences; it did not land any of the behaviour. Bounded to commits up to
  2026-11-16, `git log --all -S "<phrase>" --until=2026-11-16 -- CHANGELOG.md` returns
  `9d54337` alone for every one of the four phrases. The unbounded query adds only the
  RELEASE-010 provenance edits, which quote the phrases in the entries below by
  construction.
- **What landed the behaviour:** the feature commits named per entry below, verified by
  `git log -S` on the CODE each sentence describes (never on this file — none of them
  touched `CHANGELOG.md`). Dates are the landing dates.

- RAM-reader-first gameplay pipeline for fast, zero-cost state extraction — `RAMReader`
  (`src/core/ram_reader.py`) landed in `b0c6d2a` (2026-07-05); wired as the primary
  observation pipeline, replacing the vision cartographer, in `4ecd316` (2026-07-08).
- `cron_runner.py` boot-state checkpoints and setup preflight validation — the known-good
  `data/boot.state` checkpoint plus `DEFAULT_BOOT_STATE` resolution and
  `_resolve_boot_state()` in `31d990f` (2026-08-16, GAP-028); the `_dry_run_precheck()`
  setup validator in `8575fd8` (2026-08-23, GAP-032). Two commits because the entry named
  two mechanisms.
- `game_bridge.py` bounded workers and serialized emulator access — bounded connection
  concurrency (`max_workers`, `queue.Queue(maxsize=max_workers)`) and one shared
  `game_lock` serializing every Game/RAMReader access, in `640476c` (2026-09-30).
- Persisted RAM-derived save and run summaries, with prior memory injected at boot —
  the MEM-1 end-of-run recorder writing `/game/runs/<id>/summary` and
  `/game/save/{party,items,location}` from run truth in `ee67e9f` (2026-09-23); the MEM-2
  once-per-run boot-memory block (mechanics, save state, runs index, learning) appended
  to the controller system prompt in `1fe0d3c` (2026-09-23).

### Changed

- Updated requirements.txt with correct dependencies
- Fixed mode_duration.py bugs (None handling, type errors)
- Stabilized integration tests (all passing)

### Fixed

- ModeClassifier evolution cutscene classification
- DurationTracker cumulative duration calculation
- State machine transition validation
- JSON parsing fallback strategies

### Removed

- Unused dependencies (openai, anthropic, streamlit, pandas, matplotlib - available but optional)

### Security

- API key handling with environment variable configuration
- Circuit breaker for API failure isolation
- Rate limiting to prevent API abuse

### Notes

- Provenance backfill (2026-11-17, RELEASE-010): the four entries under "Backfilled
  provenance" spent the `v1.0.0`→`v1.2.0` span under the Unreleased heading with no
  commit binding. Each is now filed under the release whose tag tree actually contains
  it,
  verified two ways per entry: `git tag --contains <sha>` (all report `v1.0.0`) and a
  read of the tag's own tree — `git ls-tree v1.0.0 src/core/ram_reader.py data/boot.state`,
  plus `git show v1.0.0:cron_runner.py` (`DEFAULT_BOOT_STATE`, `_build_boot_memory_blocks`)
  and `git show v1.0.0:scripts/game_bridge.py` (`max_workers`).
- This section's date (2025-12-31) predates those commits (2026-07-05 … 2026-09-30).
  Provenance here is bound to the tag's tree, which is what `git checkout v1.0.0` gives
  an operator, not to the section header's date.

## Dependencies

### Core Runtime
- Python 3.12+
- PyBoy (emulator interface)
- OpenCV, PIL (image processing)
- NumPy (numeric computing)
- requests (HTTP client)
- SQLite (persistent storage)

### Optional
- python-dotenv (.env support)
- anthropic (Claude SDK)
- FastAPI + WebSocket (dashboard)

[1.0.0]: https://github.com/nickbaumann98/ai_plays_poke/releases/tag/v1.0.0