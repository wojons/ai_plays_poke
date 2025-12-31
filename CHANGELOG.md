# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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