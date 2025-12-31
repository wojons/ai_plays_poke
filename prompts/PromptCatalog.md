# PTP-01X Prompt Library Catalog (JSON Format)

```json
{
  "library_version": "1.0",
  "total_prompts": 55,
  "categories": {
    "battle": {
      "count": 16,
      "prompts": [
        {"name": "basic_fighting", "priority": 3, "triggers": ["battle", "combat"]},
        {"name": "move_selection", "priority": 5, "triggers": ["move_menu", "attack_selection"]},
        {"name": "switch_decision", "priority": 5, "triggers": ["switch_prompt", "team_view"]},
        {"name": "status_management", "priority": 4, "triggers": ["status_condition", "paralysis", "poison"]},
        {"name": "catch_strategy", "priority": 4, "triggers": ["wild_encounter", "capture_attempt"]},
        {"name": "boss_preparation", "priority": 5, "triggers": ["gym_leader", "elite_four", "champion"]},
        {"name": "type_matchup", "priority": 4, "triggers": ["type_check", "new_pokemon_enter"]},
        {"name": "priority_moves", "priority": 4, "triggers": ["priority_check", "low_hp_enemy"]},
        {"name": "setup_sweeper", "priority": 3, "triggers": ["setup_opportunity", "boost_moves"]},
        {"name": "cleanup_role", "priority": 3, "triggers": ["late_game", "enemy_team_low"]},
        {"name": "hazard_control", "priority": 3, "triggers": ["entry_hazard", "stealth_rock", "spikes"]},
        {"name": "weather_strategy", "priority": 3, "triggers": ["weather_active", "sun", "rain", "sand", "hail"]},
        {"name": "tailwind_support", "priority": 3, "triggers": ["speed_control", "tailwind"]},
        {"name": "terrain_strategy", "priority": 3, "triggers": ["terrain_active", "electric", "psychic", "grass", "misty"]},
        {"name": "reversal_mind", "priority": 4, "triggers": ["prediction", "mind_games", "switch_prediction"]},
        {"name": "endgame_timing", "priority": 4, "triggers": ["victory_close", "final_pokemon"]}
      ]
    },
    "exploration": {
      "count": 11,
      "prompts": [
        {"name": "pathfinding", "priority": 3, "triggers": ["navigation", "overworld"]},
        {"name": "route_planning", "priority": 3, "triggers": ["travel", "multi_stop"]},
        {"name": "hm_usage", "priority": 4, "triggers": ["hm_required", "blocked_path"]},
        {"name": "area_mapping", "priority": 2, "triggers": ["unknown_area", "new_region"]},
        {"name": "safe_routes", "priority": 3, "triggers": ["low_level", "danger_avoidance"]},
        {"name": "shortest_path", "priority": 2, "triggers": ["efficiency", "time_critical"]},
        {"name": "resource_gathering", "priority": 2, "triggers": ["item_farming", "money_making"]},
        {"name": "hidden_item_hunting", "priority": 2, "triggers": ["item_search", "secret_area"]},
        {"name": "legendary_encounter", "priority": 5, "triggers": ["legendary_area", "rare_pokemon"]},
        {"name": "cave_exploration", "priority": 2, "triggers": ["cave", "underground"]},
        {"name": "water_route_planning", "priority": 3, "triggers": ["surf", "water_area", "dive"]}
      ]
    },
    "dialog": {
      "count": 11,
      "prompts": [
        {"name": "text_flow", "priority": 3, "triggers": ["dialog", "text_box"]},
        {"name": "shop_navigation", "priority": 4, "triggers": ["shop", "mart", "store"]},
        {"name": "trainer_intro", "priority": 4, "triggers": ["trainer_challenge", "battle_start"]},
        {"name": "story_advancement", "priority": 5, "triggers": ["cutscene", "story_event", "cutscene_choice"]},
        {"name": "item_description", "priority": 2, "triggers": ["item_info", "item_details"]},
        {"name": "npc_conversation", "priority": 3, "triggers": ["npc_talk", "dialogue"]},
        {"name": "yes_no_decisions", "priority": 4, "triggers": ["choice", "yes_no", "confirm"]},
        {"name": "menu_selection", "priority": 3, "triggers": ["menu", "options", "settings"]},
        {"name": "save_prompt", "priority": 3, "triggers": ["save_point", "save_menu"]},
        {"name": "gift_receiving", "priority": 3, "triggers": ["gift", "reward", "bonus"]},
        {"name": "rival_interaction", "priority": 4, "triggers": ["rival", "rival_battle", "rival_encounter"]}
      ]
    },
    "menu": {
      "count": 1,
      "prompts": [
        {"name": "navigation", "priority": 3, "triggers": ["menu_open", "inventory", "options"]}
      ]
    },
    "strategic": {
      "count": 16,
      "prompts": [
        {"name": "game_planning", "priority": 3, "triggers": ["strategic", "planning"]},
        {"name": "badge_progress", "priority": 4, "triggers": ["gym_approach", "badge_check"]},
        {"name": "team_gaps", "priority": 3, "triggers": ["team_analysis", "type_check"]},
        {"name": "experience_allocation", "priority": 3, "triggers": ["leveling", "exp_sharing"]},
        {"name": "long_term_goals", "priority": 2, "triggers": ["multi_session", "future_planning"]},
        {"name": "ev_optimal", "priority": 2, "triggers": ["ev_training", "stat_optimization"]},
        {"name": "iv_breeding", "priority": 2, "triggers": ["breeding", "iv_check", "perfect_iv"]},
        {"name": "nature_selection", "priority": 2, "triggers": ["nature_choice", "stat_boost"]},
        {"name": "move_tutor_priority", "priority": 2, "triggers": ["move_tutor", "tutor_available"]},
        {"name": "tm_acquisition", "priority": 3, "triggers": ["tm_shop", "tm_location"]},
        {"name": "berry_strategy", "priority": 2, "triggers": ["berry", "held_item", "harvest"]},
        {"name": "contest_training", "priority": 1, "triggers": ["contest", "beauty", "poffin"]},
        {"name": "pokedex_completion", "priority": 2, "triggers": ["pokedex", "missing_pokemon"]},
        {"name": "money_management", "priority": 2, "triggers": ["budget", "purchase_planning"]},
        {"name": "trading_strategy", "priority": 2, "triggers": ["trade", "npc_trade", "trade_evolution"]},
        {"name": "post_game_content", "priority": 2, "triggers": ["post_game", "battle_frontier", "endgame"]}
      ]
    }
  },
  "selection_rules": {
    "primary_factor": "game_state_type",
    "secondary_factors": ["context_keywords", "ai_preference", "priority_weighting"],
    "fallback_prompt": "game_planning",
    "max_prompts_per_decision": 3
  }
}
```

## Quick Reference: Trigger Words to Prompts

| Trigger Word | Primary Prompt | Secondary Prompts |
|--------------|----------------|-------------------|
| battle | basic_fighting | type_matchup, move_selection |
| gym | boss_preparation | badge_progress, team_gaps |
| wild | catch_strategy | basic_fighting, item_description |
| switch | switch_decision | type_matchup, priority_moves |
| story | story_advancement | dialog_flow, yes_no_decisions |
| shop | shop_navigation | money_management, item_description |
| trainer | trainer_intro | battle_planning, team_gaps |
| navigate | pathfinding | route_planning, shortest_path |
| hm | hm_usage | route_planning, area_mapping |
| legendary | legendary_encounter | catch_strategy, boss_preparation |
| level | experience_allocation | ev_optimal, nature_selection |
| team | team_gaps | badge_progress, type_matchup |
| save | save_prompt | menu_navigation, game_planning |
| trade | trading_strategy | pokemon_selection, iv_breeding |