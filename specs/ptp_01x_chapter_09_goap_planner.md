# PTP-01X Chapter 9: GOAP Decision Core & Goal Planning

**Version:** 1.0  
**Author:** AI Architect  
**Status:** Technical Specification (Implementable)  
**Dependencies:** All previous chapters (Perception → GOAP)

---

## Executive Summary

The GOAP (Goal-Oriented Action Planning) layer orchestrates all subsystems into coherent autonomous behavior. It implements:

1. **Hierarchical Planning**: Strategic (long-term), Tactical (short-term), Reactive (immediate)
2. **Goal Enablement Graph**: Directed acyclic graph of prerequisites and unlocks
3. **Opportunity Cost Scheduling**: Temporal discounting for resource allocation
4. **Plan Repair**: Local replanning on failure (not global replanning)
5. **Utility Learning**: Adapts weights based on success/failure history

This layer transforms reactive subsystems into **proactive intelligence** with human-like foresight.

---

## 1. Goal Architecture

### 1.1 Goal Structure

```python
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable
from enum import Enum

class GoalPriority(Enum):
    """Priority levels with semantic meaning"""
    CRITICAL = 999   # Survival (party wipe imminent)
    HIGH = 85       # Major progression (gym leaders)
    MEDIUM = 70     # Important quests (legendaries)
    LOW = 50        # Optimization (shopping, training)
    MINOR = 30      # Convenience (item pickup)
    IDLE = 10       background tasks

@dataclass
class Goal:
    """Complete goal specification"""
    
    # Identity
    id: str
    name: str
    description: str
    
    # Priority (dynamic)
    priority: int
    base_priority: int
    priority_modifier: float = 0.0
    
    # State
    status: str = "inactive"  # inactive, active, completed, failed
    progress: float = 0.0     # 0.0-1.0
    
    # Dependencies
    prerequisites: List[str] = field(default_factory=list)  # Required goals
    unlocks: List[str] = field(default_factory=list)        # Goals this enables
    
    # Preconditions (world state requirements)
    required_state: Dict[str, any] = field(default_factory=dict)
    
    # Effects (world state changes)
    state_effects: Dict[str, any] = field(default_factory=dict)
    
    # Success criteria
    success_condition: Callable = None
    failure_condition: Callable = None
    
    # Utility factors
    utility_weights: Dict[str, float] = field(default_factory=lambda: {
        'experience': 1.0,
        'money': 0.8,
        'items': 0.9,
        'completion': 1.5
    })
    
    # Temporal discounting
    time_discount_factor: float = 0.95  # Value decreases 5% per cycle delay
    estimated_duration: int = 100       # Estimated cycles to complete
    
    # Attempt tracking
    attempt_count: int = 0
    last_attempt_cycle: int = 0
    success_rate: float = 0.5           # Bayesian prior
    
    def calculate_utility(self, world_state: Dict) -> float:
        """Calculate current utility given world state"""
        
        # Base utility from priority
        utility = self.priority
        
        # Apply temporal discounting
        cycles_since_activation = world_state.get('current_cycle', 0) - self.last_attempt_cycle
        time_discount = self.time_discount_factor ** max(cycles_since_activation, 0)
        utility *= time_discount
        
        # Apply success rate adjustment (lower success rate = lower utility)
        utility *= (0.5 + self.success_rate * 0.5)
        
        # Apply priority modifier
        utility *= (1.0 + self.priority_modifier)
        
        return utility
    
    def can_activate(self, completed_goals: set, world_state: Dict) -> bool:
        """Check if goal can be activated"""
        
        # Check prerequisites
        if not all(prereq in completed_goals for prereq in self.prerequisites):
            return False
        
        # Check required world state
        for key, value in self.required_state.items():
            if world_state.get(key) != value:
                return False
        
        # Check not already completed/failed
        if self.status in ['completed', 'failed']:
            return False
        
        return True
    
    def update_success_rate(self, success: bool):
        """Bayesian update of success rate"""
        self.attempt_count += 1
        
        # Beta-Bernoulli update
        alpha = 1 + (self.success_rate * self.attempt_count)
        beta = 1 + ((1 - self.success_rate) * self.attempt_count)
        
        if success:
            alpha += 1
        else:
            beta += 1
        
        self.success_rate = alpha / (alpha + beta)
```

---

## 2. Goal Enablement Graph

### 2.1 Core Game Goals (Gen 1)

```python
class PokemonGoals:
    """All goals in Pokemon Red/Blue/Yellow GOAP system"""
    
    def __init__(self):
        self.goals = {}
        self._initialize_goals()
        self._build_dependency_graph()
    
    def _initialize_goals(self):
        """Define all game goals"""
        
        # ==== STRATEGIC GOALS (Game Progression) ====
        
        self.goals['defeat_brock'] = Goal(
            id='defeat_brock',
            name="Defeat Brock (Pewter City Gym)",
            description="Win against Brock's Rock-type Pokemon",
            base_priority=GoalPriority.HIGH.value,
            required_state={'current_location': 'pewter_gym'},
            state_effects={'has_boulder_badge': True},
            success_condition=lambda ws: ws.get('badges', {}).get('boulder', False)
        )
        
        self.goals['defeat_misty'] = Goal(
            id='defeat_misty',
            name="Defeat Misty (Cerulean City Gym)",
            description="Win against Misty's Water-type Pokemon",
            base_priority=GoalPriority.HIGH.value,
            prerequisites=['defeat_brock'],
            required_state={'current_location': 'cerulean_gym'},
            state_effects={'has_cascade_badge': True},
            success_condition=lambda ws: ws.get('badges', {}).get('cascade', False),
            utility_weights={'experience': 1.2, 'completion': 1.5}
        )
        
        self.goals['defeat_lt_surge'] = Goal(
            id='defeat_lt_surge',
            name="Defeat Lt. Surge (Vermillion City Gym)",
            description="Win against Lt. Surge's Electric-type Pokemon",
            base_priority=GoalPriority.HIGH.value,
            prerequisites=['defeat_misty'],
            required_state={'has_cut': True},  # Need Cut for SS Anne
            state_effects={'has_thunder_badge': True},
            success_condition=lambda ws: ws.get('badges', {}).get('thunder', False)
        )
        
        self.goals['defeat_erosa'] = Goal(
            id='defeat_erosa',
            name="Defeat Erika (Celadon City Gym)",
            description="Win against Erika's Grass-type Pokemon",
            base_priority=GoalPriority.HIGH.value,
            prerequisites=['defeat_lt_surge'],
            required_state={'current_location': 'celadon_gym'},
            state_effects={'has_rainbow_badge': True},
            success_condition=lambda ws: ws.get('badges', {}).get('rainbow', False)
        )
        
        self.goals['defeat_koga'] = Goal(
            id='defeat_koga',
            name="Defeat Koga (Fuchsia City Gym)",
            description="Win against Koga's Poison-type Pokemon",
            base_priority=GoalPriority.HIGH.value,
            prerequisites=['defeat_erosa'],
            required_state={'current_location': 'fuchsia_gym'},
            state_effects={'has_soul_badge': True},
            success_condition=lambda ws: ws.get('badges', {}).get('soul', False)
        )
        
        self.goals['defeat_sabrina'] = Goal(
            id='defeat_sabrina',
            name="Defeat Sabrina (Saffron City Gym)",
            description="Win against Sabrina's Psychic-type Pokemon",
            base_priority=GoalPriority.HIGH.value,
            prerequisites=['defeat_koga'],
            required_state={'silph_co_clear': True},  # Need to clear Silph Co first
            state_effects={'has_marsh_badge': True},
            success_condition=lambda ws: ws.get('badges', {}).get('marsh', False)
        )
        
        self.goals['defeat_blaine'] = Goal(
            id='defeat_blaine',
            name="Defeat Blaine (Cinnabar Island Gym)",
            description="Win against Blaine's Fire-type Pokemon",
            base_priority=GoalPriority.HIGH.value,
            prerequisites=['defeat_sabrina'],
            required_state={'current_location': 'cinnabar_gym', 'has_secret_key': True},
            state_effects={'has_volcano_badge': True},
            success_condition=lambda ws: ws.get('badges', {}).get('volcano', False)
        )
        
        self.goals['defeat_giovanni'] = Goal(
            id='defeat_giovanni',
            name="Defeat Giovanni (Viridian City Gym)",
            description="Win against Giovanni's Ground-type Pokemon",
            base_priority=GoalPriority.HIGH.value,
            prerequisites=['defeat_blaine'],
            required_state={'current_location': 'viridian_gym'},
            state_effects={'has_earth_badge': True},
            success_condition=lambda ws: ws.get('badges', {}).get('earth', False)
        )
        
        self.goals['defeat_elite_four'] = Goal(
            id='defeat_elite_four',
            name="Defeat the Elite Four",
            description="Win against Lorelei, Bruno, Agatha, and Lance",
            base_priority=GoalPriority.CRITICAL.value,
            prerequisites=['defeat_giovanni'],
            required_state={'current_location': 'indigo_plateau'},
            state_effects={'elite_four_defeated': True},
            estimated_duration=500,
            success_condition=lambda ws: ws.get('elite_four_defeated', False)
        )
        
        self.goals['defeat_champion'] = Goal(
            id='defeat_champion',
            name="Defeat the Champion",
            description="Win against the Pokemon Champion",
            base_priority=GoalPriority.CRITICAL.value,
            prerequisites=['defeat_elite_four'],
            required_state={'current_location': 'indigo_plateau', 'elite_four_defeated': True},
            state_effects={'game_completed': True},
            success_condition=lambda ws: ws.get('game_completed', False),
            time_discount_factor=0.99  # High persistence
        )
        
        # ==== TACTICAL GOALS (Quests & Milestones) ====
        
        self.goals['obtain_cut'] = Goal(
            id='obtain_cut',
            name="Obtain HM01 Cut",
            description="Get Cut from S.S. Anne captain",
            base_priority=GoalPriority.MEDIUM.value,
            prerequisites=['defeat_brock'],
            state_effects={'has_cut': True},
            success_condition=lambda ws: ws.get('has_cut', False),
            utility_weights={'completion': 1.0}
        )
        
        self.goals['obtain_fly'] = Goal(
            id='obtain_fly',
            name="Obtain HM02 Fly",
            description="Get Fly from Route 16",
            base_priority=GoalPriority.MEDIUM.value,
            prerequisites=['defeat_misty'],
            required_state={'has_thunder_badge': True},
            state_effects={'has_fly': True},
            success_condition=lambda ws: ws.get('has_fly', False)
        )
        
        self.goals['obtain_surf'] = Goal(
            id='obtain_surf',
            name="Obtain HM03 Surf",
            description="Get Surf from Safari Zone",
            base_priority=GoalPriority.MEDIUM.value,
            prerequisites=['defeat_erosa'],
            required_state={'current_location': 'safari_zone'},
            state_effects={'has_surf': True},
            success_condition=lambda ws: ws.get('has_surf', False)
        )
        
        self.goals['obtain_strength'] = Goal(
            id='obtain_strength',
            name="Obtain HM04 Strength",
            description="Get Strength from Safari Zone Warden",
            base_priority=GoalPriority.MEDIUM.value,
            prerequisites=['defeat_erosa'],
            required_state={'current_location': 'fuchsia_city', 'has_gold_teeth': True},
            state_effects={'has_strength': True},
            success_condition=lambda ws: ws.get('has_strength', False)
        )
        
        self.goals['obtain_flash'] = Goal(
            id='obtain_flash',
            name="Obtain HM05 Flash",
            description="Get Flash from Professor Oak's aide",
            base_priority=GoalPriority.MEDIUM.value,
            prerequisites=['defeat_brock'],
            required_state={'pokedex_caught': 10},  # Need 10 caught
            state_effects={'has_flash': True},
            success_condition=lambda ws: ws.get('has_flash', False)
        )
        
        # ==== TACTICAL GOALS (Party Optimization) ====
        
        self.goals['train_party'] = Goal(
            id='train_party',
            name="Train Party",
            description="Level up party to target strength",
            base_priority=GoalPriority.LOW.value,
            dynamic_priority=True,  # Recalculated based on need
            success_condition=lambda ws: self._check_party_strength(ws)
        )
        
        self.goals['heal_party'] = Goal(
            id='heal_party',
            name="Heal Party",
            description="Restore all Pokemon to full health",
            base_priority=GoalPriority.CRITICAL.value,
            dynamic_priority=True,
            required_state={'in_town': True},  # Can only heal in town
            success_condition=lambda ws: self._check_party_health(ws)
        )
        
        self.goals['optimize_party'] = Goal(
            id='optimize_party',
            name="Optimize Party",
            description="Rearrange party for optimal coverage",
            base_priority=GoalPriority.LOW.value,
            success_condition=lambda ws: ws.get('party_optimized', False)
        )
        
        self.goals['use_rare_candy'] = Goal(
            id='use_rare_candy',
            name="Use Rare Candy",
            description="Apply Rare Candy to optimal Pokemon",
            base_priority=GoalPriority.MEDIUM.value,
            required_state={'has_rare_candy': True, 'optimal_candy_target': True},
            success_condition=lambda ws: ws.get('rare_candy_used', False)
        )
        
        # ==== MINOR GOALS (Item & Resource Management) ====
        
        self.goals['shop_potions'] = Goal(
            id='shop_potions',
            name="Buy Healing Items",
            description="Purchase potions and status heals",
            base_priority=GoalPriority.MINOR.value,
            required_state={'in_town': True, 'money': 300},
            success_condition=lambda ws: ws.get('potions_stocked', False)
        )
        
        self.goals['shop_pokeballs'] = Goal(
            id='shop_pokeballs',
            name="Buy Pokeballs",
            description="Purchase pokeballs for catching",
            base_priority=GoalPriority.MINOR.value,
            required_state={'in_town': True, 'money': 200},
            success_condition=lambda ws: ws.get('pokeballs_stocked', False)
        )
        
        self.goals['clear_dungeon'] = Goal(
            id='clear_dungeon',
            name="Clear Dungeon",
            description="Defeat all trainers and reach end",
            base_priority=GoalPriority.MEDIUM.value,
            dynamic_priority=True,
            success_condition=lambda ws: ws.get('dungeon_clear', False)
        )
    
    def _build_dependency_graph(self):
        """Build enablement relationships"""
        
        # Badge progression unlocks HMs and areas
        self.goals['defeat_brock'].unlocks = ['obtain_cut', 'defeat_misty']
        self.goals['defeat_misty'].unlocks = ['obtain_fly', 'defeat_lt_surge']
        self.goals['defeat_lt_surge'].unlocks = ['defeat_erosa']
        self.goals['defeat_erosa'].unlocks = ['obtain_surf', 'obtain_strength', 'defeat_koga']
        self.goals['defeat_koga'].unlocks = ['defeat_sabrina']
        self.goals['defeat_sabrina'].unlocks = ['defeat_blaine']
        self.goals['defeat_blaine'].unlocks = ['defeat_giovanni']
        self.goals['defeat_giovanni'].unlocks = ['defeat_elite_four']
        self.goals['defeat_elite_four'].unlocks = ['defeat_champion']
        
        # HM acquisition enables progression
        self.goals['obtain_cut'].unlocks.extend(['access_ss_anne', 'access_lt_surge'])
        self.goals['obtain_surf'].unlocks.extend(['access_route_19', 'access_seafoam'])
        self.goals['obtain_strength'].unlocks.extend(['access_route_12', 'access_safari_zone'])
        self.goals['obtain_flash'].unlocks.extend(['access_mt_moon_b2f', 'access_rock_tunnel'])
        
        self.logger.info(f"Built dependency graph for {len(self.goals)} goals")
    
    def _check_party_health(self, world_state):
        """Check if party needs healing"""
        party = world_state.get('party', [])
        if not party:
            return True  # No party = no healing needed
        
        # Check if any Pokemon below 30% HP
        needs_heal = any(p.get('health_percent', 100) < 30 for p in party)
        
        # Check if any fainted
        has_fainted = any(p.get('current_hp', 1) == 0 for p in party)
        
        return not (needs_heal or has_fainted)
    
    def _check_party_strength(self, world_state):
        """Check if party is strong enough for current area"""
        party = world_state.get('party', [])
        if not party:
            return False
        
        badges = world_state.get('badges', {})
        num_badges = sum(1 for v in badges.values() if v)
        
        # Expected level based on badges
        expected_level = 5 + (num_badges * 10)
        
        # Check if any Pokemon can handle encounters
        has_strong_pokemon = any(p.get('level', 0) >= expected_level for p in party)
        
        # Check type coverage
        has_coverage = self._check_badge_type_coverage(party, badges)
        
        return has_strong_pokemon and has_coverage
    
    def _check_badge_type_coverage(self, party, badges):
        """Check if party has counters for upcoming gym"""
        # Determine next gym
        next_gym = None
        if not badges.get('boulder'):
            next_gym = 'rock'
        elif not badges.get('cascade'):
            next_gym = 'water'
        elif not badges.get('thunder'):
            next_gym = 'electric'
        elif not badges.get('rainbow'):
            next_gym = 'grass'
        elif not badges.get('soul'):
            next_gym = 'poison'
        elif not badges.get('marsh'):
            next_gym = 'psychic'
        elif not badges.get('volcano'):
            next_gym = 'fire'
        elif not badges.get('earth'):
            next_gym = 'ground'
        
        if not next_gym:
            return True  # All badges obtained
        
        # Check for counters
        gym_weaknesses = {
            'rock': ['water', 'grass', 'fighting'],
            'water': ['electric', 'grass'],
            'electric': ['ground'],
            'grass': ['fire', 'flying', 'ice', 'poison'],
            'poison': ['ground', 'psychic'],
            'psychic': ['bug', 'ghost'],
            'fire': ['water', 'ground', 'rock'],
            'ground': ['water', 'grass', 'ice']
        }
        
        party_types = []
        for p in party:
            party_types.extend(p.get('types', []))
        
        needed_types = gym_weaknesses.get(next_gym, [])
        has_counter = any(t in needed_types for t in party_types)
        
        return has_counter
```

---

## 3. GOAP Planner Implementation

### 3.1 Hierarchical Planning System

```python
from collections import deque, defaultdict
import asyncio

class GOAPPlanner:
    """Goal-Oriented Action Planning with hierarchical decomposition"""
    
    def __init__(self, memory_interface, goal_set: PokemonGoals):
        self.memory = memory_interface
        self.goals = goal_set
        self.logger = memory_interface.logger
        
        # World state cache
        self.world_state = {}
        self.last_state_update = 0
        
        # Planning layers
        self.strategic_planner = StrategicPlanner(self, 1000)  # 1000 cycles
        self.tactical_planner = TacticalPlanner(self, 30)      # 30 cycles
        self.reactive_planner = ReactivePlanner(self)          # Immediate
        
        # Current plans
        self.strategic_plan = []
        self.tactical_plan = []
        self.current_action = None
        
        # Plan repair tracking
        self.plan_failures = defaultdict(int)
        self.failure_threshold = 3
        
        self.logger.info("GOAP Planner initialized with hierarchical layers")
    
    async def update(self):
        """Main planning cycle"""
        # Update world state
        await self._update_world_state()
        
        # Run planning layers
        await self.strategic_planner.update()
        await self.tactical_planner.update()
        await self.reactive_planner.update()
        
        # Execute current action
        if self.current_action:
            success = await self._execute_action(self.current_action)
            
            if success:
                self.current_action = None  # Action complete
            else:
                # Action failed - increment failure count
                self.plan_failures[self.current_action.goal.id] += 1
                
                if self.plan_failures[self.current_action.goal.id] >= self.failure_threshold:
                    # Too many failures - mark goal as failed and replan
                    self.current_action.goal.status = 'failed'
                    self.logger.warning(
                        f"Goal failed after {self.failure_threshold} attempts: "
                        f"{self.current_action.goal.name}"
                    )
                    
                    await self._replan_affected_goals(self.current_action.goal)
                
                self.current_action = None
        
        # Select next action
        if not self.current_action:
            self.current_action = await self._select_next_action()
    
    async def _update_world_state(self):
        """Aggregate world state from all systems"""
        if self.memory.get_cycle_count() - self.last_state_update < 10:
            return  # Update every 10 cycles
        
        # Location/Progress
        self.world_state['current_location'] = await self._get_current_location()
        self.world_state['badges'] = await self._get_badges()
        self.world_state['hms'] = await self._get_hms()
        
        # Party state
        party_manager = self.memory.party_manager
        self.world_state['party'] = [
            {
                'species': p.species_name,
                'level': p.level,
                'current_hp': p.current_hp,
                'max_hp': p.max_hp,
                'health_percent': p.health_percentage,
                'types': p.types,
                'moves': p.moves
            }
            for p in party_manager.party if p
        ]
        
        # Inventory
        inventory_manager = self.memory.inventory_manager
        self.world_state['money'] = await self.memory.read_money()
        self.world_state['item_count'] = await self.memory.read_byte(0xD31C)
        self.world_state['candy_count'] = await inventory_manager.get_item_count(0x28)
        self.world_state['pokeball_count'] = await inventory_manager.get_pokeball_count()
        
        # Game flags
        self.world_state['game_completed'] = await self._is_game_completed()
        self.world_state['elite_four_defeated'] = await self._is_elite_four_defeated()
        self.world_state['in_town'] = self._is_in_town(self.world_state['current_location'])
        self.world_state['current_cycle'] = self.memory.get_cycle_count()
        
        # Derived states
        self.world_state['party_strength'] = self._calculate_party_strength()
        self.world_state['party_optimized'] = party_manager.is_party_optimized()
        
        self.last_state_update = self.memory.get_cycle_count()
    
    async def _select_next_action(self) -> Optional['Action']:
        """Select highest-utility achievable action"""
        
        # Get achievable goals (prerequisites met)
        completed_ids = {g.id for g in self.goals.goals.values() if g.status == 'completed'}
        achievable = []
        
        for goal in self.goals.goals.values():
            if goal.can_activate(completed_ids, self.world_state):
                # Dynamic priority recalculation
                if goal.id == 'train_party':
                    goal.priority = self._calculate_training_priority()
                elif goal.id == 'heal_party':
                    goal.priority = self._calculate_healing_priority()
                
                utility = goal.calculate_utility(self.world_state)
                achievable.append((goal, utility))
        
        if not achievable:
            # Fallback: idle goal
            idle_goal = Goal(
                id='explore_current_area',
                name="Explore Current Area",
                description="Look for trainers, items, and wild Pokemon",
                base_priority=GoalPriority.LOW.value
            )
            return Action(idle_goal, self._explore_action)
        
        # Sort by utility
        achievable.sort(key=lambda x: x[1], reverse=True)
        
        # Log top 3 goals
        self.logger.debug(
            f"Top goals: {[(g.name, f'{u:.1f}') for g, u in achievable[:3]]}"
        )
        
        # Create action for highest-utility goal
        best_goal = achievable[0][0]
        action_func = self._get_action_for_goal(best_goal)
        
        return Action(best_goal, action_func)
    
    def _calculate_training_priority(self) -> int:
        """Dynamic priority for training goal"""
        party = self.world_state.get('party', [])
        if not party:
            return GoalPriority.MINOR.value
        
        badges = self.world_state.get('badges', {})
        num_badges = sum(1 for v in badges.values() if v)
        
        # Expected level for current progress
        expected_level = 5 + (num_badges * 10)
        
        # Check if party is underleveled
        avg_level = sum(p['level'] for p in party) / len(party)
        
        level_deficit = expected_level - avg_level
        
        if level_deficit > 5:
            return GoalPriority.MEDIUM.value
        elif level_deficit > 0:
            return GoalPriority.LOW.value
        else:
            return GoalPriority.MINOR.value
    
    def _calculate_healing_priority(self) -> int:
        """Dynamic priority for healing goal"""
        party = self.world_state.get('party', [])
        if not party:
            return GoalPriority.MINOR.value
        
        # Count fainted Pokemon
        fainted = sum(1 for p in party if p.get('current_hp', 1) == 0)
        
        if fainted >= 3:
            return GoalPriority.CRITICAL.value
        elif fainted >= 1:
            return GoalPriority.HIGH.value
        elif fainted >= 2:
            return GoalPriority.MEDIUM.value
        
        # Check low HP
        low_hp = sum(1 for p in party if p.get('health_percent', 100) < 30)
        
        if low_hp >= 3:
            return GoalPriority.HIGH.value
        elif low_hp >= 1:
            return GoalPriority.MEDIUM.value
        
        return GoalPriority.LOW.value
    
    async def _replan_affected_goals(self, failed_goal: Goal):
        """Replan goals that depend on failed goal"""
        affected = [g for g in self.goals.goals.values() if failed_goal.id in g.prerequisites]
        
        if not affected:
            return
        
        self.logger.warning(
            f"Replanning {len(affected)} goals affected by failure: "
            f"{failed_goal.name}"
        )
        
        for goal in affected:
            # Lower priority or find alternative path
            goal.priority_modifier -= 0.3
            goal.status = 'inactive'  # Reset for replanning
            
            self.logger.info(
                f"Adjusted affected goal: {goal.name} "
                f"(new priority: {goal.priority})"
            )
    
    def _get_action_for_goal(self, goal: Goal) -> Callable:
        """Map goal to execution function"""
        
        action_map = {
            'defeat_brock': self._battle_gym_leader_action,
            'defeat_misty': self._battle_gym_leader_action,
            'defeat_lt_surge': self._battle_gym_leader_action,
            'defeat_erosa': self._battle_gym_leader_action,
            'defeat_koga': self._battle_gym_leader_action,
            'defeat_sabrina': self._battle_gym_leader_action,
            'defeat_blaine': self._battle_gym_leader_action,
            'defeat_giovanni': self._battle_gym_leader_action,
            'defeat_elite_four': self._battle_elite_four_action,
            'defeat_champion': self._battle_champion_action,
            
            'obtain_cut': self._obtain_cut_action,
            'obtain_fly': self._obtain_fly_action,
            'obtain_surf': self._obtain_surf_action,
            'obtain_strength': self._obtain_strength_action,
            'obtain_flash': self._obtain_flash_action,
            
            'train_party': self._train_party_action,
            'heal_party': self._heal_party_action,
            'optimize_party': self._optimize_party_action,
            'use_rare_candy': self._use_rare_candy_action,
            
            'shop_potions': self._shop_potions_action,
            'shop_pokeballs': self._shop_pokeballs_action,
            'clear_dungeon': self._clear_dungeon_action,
            
            'explore_current_area': self._explore_action
        }
        
        return action_map.get(goal.id, self._default_action)
    
    async def _execute_action(self, action: 'Action') -> bool:
        """Execute action and return success"""
        try:
            self.logger.info(f"Executing action for: {action.goal.name}")
            
            # Record attempt
            action.goal.attempt_count += 1
            action.goal.last_attempt_cycle = self.world_state['current_cycle']
            
            success = await action.execute()
            
            # Update success rate
            action.goal.update_success_rate(success)
            
            if success:
                # Mark goal complete
                action.goal.status = 'completed'
                action.goal.progress = 1.0
                
                self.logger.success(f"Goal completed: {action.goal.name}")
                
                # Remove failure tracking
                if action.goal.id in self.plan_failures:
                    del self.plan_failures[action.goal.id]
            
            return success
            
        except Exception as e:
            self.logger.error(f"Action execution failed: {e}")
            return False
```

---

## 4. Planning Layers

### 4.1 Strategic Planner

```python
class StrategicPlanner:
    """Long-term planning (1000 cycles)"""
    
    def __init__(self, goap: GOAPPlanner, update_interval: int):
        self.goap = goap
        self.memory = goap.memory
        self.update_interval = update_interval
        self.last_update = 0
        self.strategic_plan = []
    
    async def update(self):
        """Update strategic plan periodically"""
        current_cycle = self.memory.get_cycle_count()
        
        if current_cycle - self.last_update < self.update_interval:
            return
        
        self.last_update = current_cycle
        
        # Analyze current progression
        badges = self.goap.world_state.get('badges', {})
        completed_badges = sum(1 for v in badges.values() if v)
        
        self.memory.logger.info(
            f"Strategic planning: {completed_badges}/8 badges, "
            f"party size: {len(self.goap.world_state.get('party', []))}"
        )
        
        # Build strategic goal sequence
        strategic_sequence = self._build_strategic_sequence()
        
        # Update master plan
        self.strategic_plan = strategic_sequence
        
        self.memory.logger.info(
            f"Strategic plan updated: {[g.name for g in strategic_sequence[:3]]}..."
        )
    
    def _build_strategic_sequence(self) -> List[Goal]:
        """Build optimal sequence of strategic goals"""
        
        # Get all strategic goals (gyms, elite four, champion)
        strategic_ids = [
            'defeat_brock', 'defeat_misty', 'defeat_lt_surge',
            'defeat_erosa', 'defeat_koga', 'defeat_sabrina',
            'defeat_blaine', 'defeat_giovanni',
            'defeat_elite_four', 'defeat_champion'
        ]
        
        strategic_goals = [self.goals.goals[gid] for gid in strategic_ids if gid in self.goals.goals]
        
        # Filter achievable goals
        completed = {g.id for g in strategic_goals if g.status == 'completed'}
        achievable = [g for g in strategic_goals if g.can_activate(completed, self.goap.world_state)]
        
        # Sort by badge progression
        badge_order = [
            'defeat_brock', 'defeat_misty', 'defeat_lt_surge',
            'defeat_erosa', 'defeat_koga', 'defeat_sabrina',
            'defeat_blaine', 'defeat_giovanni'
        ]
        
        # First unachieved badge is priority
        for gid in badge_order:
            goal = self.goals.goals.get(gid)
            if goal and goal not in completed and goal in achievable:
                return [goal]  # Focus on next gym
        
        # Check Elite Four
        elite_goal = self.goals.goals.get('defeat_elite_four')
        if elite_goal and elite_goal.can_activate(completed, self.goap.world_state):
            return [elite_goal]
        
        # Check Champion
        champion_goal = self.goals.goals.get('defeat_champion')
        if champion_goal and champion_goal.can_activate(completed, self.goap.world_state):
            return [champion_goal]
        
        # Fallback: train for next challenge
        train_goal = self.goals.goals.get('train_party')
        if train_goal:
            return [train_goal]
        
        return []
```

### 4.2 Tactical Planner

```python
class TacticalPlanner:
    """Mid-term planning (30 cycles)"""
    
    def __init__(self, goap: GOAPPlanner, update_interval: int):
        self.goap = goap
        self.memory = goap.memory
        self.update_interval = update_interval
        self.last_update = 0
    
    async def update(self):
        """Update tactical plan"""
        current_cycle = self.memory.get_cycle_count()
        
        if current_cycle - self.last_update < self.update_interval:
            return
        
        self.last_update = current_cycle
        
        # Check for immediate needs
        immediate_goals = []
        
        # Party health check
        if not self.goal_is_satisfied('heal_party'):
            priority = self.goap._calculate_healing_priority()
            if priority > GoalPriority.MEDIUM.value:
                immediate_goals.append('heal_party')
        
        # Resource stock check
        if await self._needs_potions():
            immediate_goals.append('shop_potions')
        
        if await self._needs_pokeballs():
            immediate_goals.append('shop_pokeballs')
        
        # HM acquisition
        for hm_goal in ['obtain_cut', 'obtain_fly', 'obtain_surf', 'obtain_strength', 'obtain_flash']:
            if self.goals.goals[hm_goal].can_activate(set(), self.goap.world_state):
                immediate_goals.append(hm_goal)
        
        # Set tactical priorities
        for goal_id in immediate_goals:
            goal = self.goals.goals[goal_id]
            goal.priority_modifier += 0.2  # Boost priority
        
        self.memory.logger.debug(f"Tactical priorities: {immediate_goals}")
    
    def goal_is_satisfied(self, goal_id: str) -> bool:
        """Check if goal is satisfied"""
        goal = self.goals.goals.get(goal_id)
        if not goal:
            return True  # Goal doesn't exist = satisfied
        
        return goal.success_condition(self.goap.world_state)
    
    async def _needs_potions(self) -> bool:
        """Check if potions are needed"""
        item_count = self.goap.world_state.get('item_count', 0)
        
        if item_count >= 18:  # Bag nearly full
            return False
        
        # Check healing item count
        healing_manager = self.memory.inventory_manager
        potion_count = await healing_manager.get_healing_item_count()
        
        # Need potions if < 5 healing items
        return potion_count < 5
    
    async def _needs_pokeballs(self) -> bool:
        """Check if pokeballs are needed"""
        ball_count = self.goap.world_state.get('pokeball_count', 0)
        
        # Need balls if < 10
        return ball_count < 10
```

### 4.3 Reactive Planner

```python
class ReactivePlanner:
    """Immediate reaction (0 cycles)"""
    
    def __init__(self, goap: GOAPPlanner):
        self.goap = goap
        self.memory = goap.memory
    
    async def update(self):
        """Handle immediate reactions"""
        
        # Check for battle state
        battle_status = await self.memory.read_byte(0xD057)
        
        if battle_status == 0xFF:  # In battle
            await self._handle_battle_reaction()
        
        # Check for dialogue choice
        dialogue = await self.memory.text_extractor.get_current_text()
        if dialogue and '?' in ' '.join(dialogue['lines']):
            await self._handle_dialogue_choice_reaction(dialogue)
        
        # Check for menu stack overflow
        if await self._detect_menu_loop():
            await self._handle_menu_emergency()
    
    async def _handle_battle_reaction(self):
        """Immediate battle reactions"""
        # Delegate to combat system for menu navigation
        combat_system = self.memory.combat_system
        
        await combat_system.handle_battle_menus()
    
    async def _handle_dialogue_choice_reaction(self, dialogue):
        """Handle YES/NO or choice dialogues"""
        # Default to affirmative for most dialogues
        lines = ' '.join(dialogue['lines']).lower()
        
        # Check for heal dialogue
        if 'heal' in lines and 'pokemon' in lines:
            # Always accept heal
            await self.memory.input.press_key('A')
        
        # Check for shop dialogue
        elif 'buy' in lines or 'sell' in lines:
            # Default to buy
            await self.memory.input.press_key('A')
        
        # Check for dangerous actions
        elif 'release' in lines or 'toss' in lines:
            # Default to NO for dangerous actions
            await self.memory.input.press_key('Down')  # Move to NO
            await self.memory.input.press_key('A')
        
        else:
            # Default YES for others
            await self.memory.input.press_key('A')
    
    async def _detect_menu_loop(self) -> bool:
        """Detect if stuck in menu loop"""
        # Check menu history for repeating patterns
        menu_history = self.memory.menu_detector.menu_history[-10:]
        
        if len(menu_history) < 10:
            return False
        
        # Check if same menu repeated > 5 times
        menu_types = [m['type'] for m in menu_history]
        most_common = max(set(menu_types), key=menu_types.count)
        
        return menu_types.count(most_common) >= 5
    
    async def _handle_menu_emergency(self):
        """Emergency exit from menu loop"""
        self.memory.logger.warning("Menu loop detected - emergency exit")
        
        # Spam B button to exit all menus
        for _ in range(10):
            await self.memory.input.press_key('B')
            await asyncio.sleep(0.1)
        
        # Reset menu detector state
        self.memory.menu_detector.last_menu = MenuType.NONE
        self.memory.menu_detector.menu_history.clear()
```

---

## 5. Action Execution

### 5.1 Action System

```python
class Action:
    """Executable action with state tracking"""
    
    def __init__(self, goal: Goal, execute_func: Callable):
        self.goal = goal
        self.execute = execute_func
        self.start_time = None
        self.end_time = None
        self.interrupted = False
    
    def duration(self) -> int:
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return 0
    
    def __repr__(self):
        return f"Action({self.goal.id})"
```

### 5.2 Goal-Specific Action Implementations

```python
class GoalActions:
    """Action implementations for all goals"""
    
    def __init__(self, goap: GOAPPlanner):
        self.goap = goap
        self.memory = goap.memory
    
    # ==== GYM LEADER ACTIONS ====
    
    async def _battle_gym_leader_action(self) -> bool:
        """Navigate to and defeat gym leader"""
        goal = self.goap.current_action.goal
        
        # Navigate to gym
        gym_location = self._get_gym_location(goal.id)
        
        success = await self._navigate_to_location(gym_location)
        if not success:
            return False
        
        # Enter gym and navigate to leader
        await self._enter_building()
        
        # Follow gym puzzle (each gym has different layout)
        success = await self._solve_gym_puzzle(goal.id)
        if not success:
            return False
        
        # Battle leader
        success = await self._battle_trainer_sequence()
        
        return success
    
    async def _battle_elite_four_action(self) -> bool:
        """Defeat Elite Four in sequence"""
        elite_order = ['lorelei', 'bruno', 'agatha', 'lance']
        
        for elite_name in elite_order:
            success = await self._battle_trainer_sequence()
            if not success:
                return False
            
            # Heal between battles
            await self._heal_party_action()
        
        return True
    
    async def _battle_champion_action(self) -> bool:
        """Defeat final champion"""
        # Final battle
        return await self._battle_trainer_sequence()
    
    # ==== HM ACQUISITION ACTIONS ====
    
    async def _obtain_cut_action(self) -> bool:
        """Navigate to S.S. Anne and obtain Cut"""
        # Go to Vermillion City
        await self._navigate_to_location('vermillion_city')
        
        # Board S.S. Anne
        await self._navigate_to_location('ss_anne')
        
        # Navigate ship to captain
        await self._follow_ship_path()
        
        # Talk to captain
        await self._talk_to_npc('captain')
        
        # Get Cut HM
        dialogue = await self.memory.text_extractor.wait_for_text_change()
        
        return 'cut' in ' '.join(dialogue['lines']).lower()
    
    async def _obtain_fly_action(self) -> bool:
        """Navigate to Route 16 and obtain Fly"""
        # Navigate through Route 16
        await self._navigate_to_location('route_16_house')
        
        # Talk to NPC girl
        await self._talk_to_npc('girl')
        
        # Receive Fly
        dialogue = await self.memory.text_extractor.wait_for_text_change()
        
        return 'fly' in ' '.join(dialogue['lines']).lower()
    
    async def _obtain_surf_action(self) -> bool:
        """Navigate through Safari Zone to obtain Surf"""
        # Enter Safari Zone
        await self._navigate_to_location('safari_zone')
        
        # Navigate to Zone 4 (Surf location)
        success = await self._navigate_safari_zone_path()
        if not success:
            return False
        
        # Talk to NPC
        await self._talk_to_npc('man')
        
        # Get Surf
        dialogue = await self.memory.text_extractor.wait_for_text_change()
        
        return 'surf' in ' '.join(dialogue['lines']).lower()
    
    async def _obtain_strength_action(self) -> bool:
        """Get Gold Teeth and trade for Strength"""
        # Navigate Safari Zone
        await self._navigate_to_location('safari_zone')
        
        # Find Gold Teeth item
        success = await self._find_item_in_safari('gold_teeth')
        if not success:
            return False
        
        # Return to Warden
        await self._navigate_to_location('fuchsia_warden_house')
        await self._talk_to_npc('warden')
        
        # Receive Strength
        dialogue = await self.memory.text_extractor.wait_for_text_change()
        
        return 'strength' in ' '.join(dialogue['lines']).lower()
    
    async def _obtain_flash_action(self) -> bool:
        """Catch 10 Pokemon and receive Flash from Oak's aide"""
        # Check pokedex count
        caught_count = await self.memory.read_byte(0xD2CE)
        
        if caught_count < 10:
            # Need to catch more Pokemon
            catch_goal = self.goals.goals.get('catch_pokemon')
            if catch_goal:
                # Switch to catching goal
                self.goap.current_action = Action(catch_goal, self._catch_pokemon_action)
                return False  # Not yet complete
        
        # Return to Route 2 building
        await self._navigate_to_location('route_2_oak_lab')
        
        # Talk to Oak's aide
        await self._talk_to_npc('aide')
        
        # Receive Flash
        dialogue = await self.memory.text_extractor.wait_for_text_change()
        
        return 'flash' in ' '.join(dialogue['lines']).lower()
    
    # ==== UTILITY ACTIONS ====
    
    async def _train_party_action(self) -> bool:
        """Train party in optimal location"""
        # Find optimal training location
        location = await self._find_optimal_training_spot()
        
        # Navigate there
        await self._navigate_to_location(location)
        
        # Grind until target level reached
        success = await self._grind_until_target_level()
        
        return success
    
    async def _heal_party_action(self) -> bool:
        """Navigate to Pokemon Center and heal"""
        # Find nearest Pokemon Center
        location = self.goap.world_state.get('current_location')
        
        if not self._is_in_town(location):
            # Need to travel to town first
            await self._navigate_to_nearest_town()
        
        # Enter Pokemon Center
        await self._enter_building('pokemon_center')
        
        # Talk to nurse
        await self._navigate_to_nurse()
        await self._talk_to_npc('nurse')
        
        # Navigate heal menu
        success = await self.memory.menu_navigator.navigate_to(MenuType.HEAL_MENU, 'yes')
        
        # Exit building
        await self._exit_building()
        
        return success
    
    async def _optimize_party_action(self) -> bool:
        """Rearrange party for optimal performance"""
        party_manager = self.memory.party_manager
        
        # Calculate optimal order
        optimal_order = await party_manager.get_optimal_party_order()
        
        # Swap Pokemon to optimal positions
        for target_slot, (current_slot, pokemon, score) in enumerate(optimal_order):
            if current_slot != target_slot:
                await self._swap_party_pokemon(current_slot, target_slot)
        
        return True
    
    async def _use_rare_candy_action(self) -> bool:
        """Find optimal Rare Candy target and use"""
        # Find optimal target
        target = await self._find_optimal_candy_target()
        
        if not target:
            return False
        
        # Use candy
        inventory = self.memory.inventory_manager
        success = await inventory.use_item_on_pokemon(0x28, target)
        
        return success
    
    async def _shop_potions_action(self) -> bool:
        """Buy healing items from shop"""
        return await self._shop_buy_items(['Potion', 'Antidote', 'Parlyz Heal'], budget=500)
    
    async def _shop_pokeballs_action(self) -> bool:
        """Buy pokeballs from shop"""
        return await self._shop_buy_items(['Poke Ball'], budget=300)
    
    async def _clear_dungeon_action(self) -> bool:
        """Clear current dungeon of trainers and items"""
        # Navigate to dungeon entrance
        # Systematically explore all rooms
        # Battle all trainers
        # Collect all visible items
        # Reach exit
        pass
    
    async def _explore_action(self) -> bool:
        """Explore current area randomly"""
        # Simple random exploration for now
        directions = ['Up', 'Down', 'Left', 'Right']
        direction = random.choice(directions)
        
        await self.memory.input.press_key(direction)
        
        return True
    
    # Helper methods
    async def _navigate_to_location(self, location: str) -> bool:
        """Use navigation engine to reach location"""
        nav_engine = self.memory.navigation_engine
        return await nav_engine.navigate_to_location(location)
    
    async def _talk_to_npc(self, npc_type: str) -> bool:
        """Approach and talk to NPC"""
        # Face NPC
        await self.memory.input.press_key('A')
        
        # Wait for dialogue
        await self.memory.text_extractor.wait_for_text_change()
        
        return True
    
    async def _battle_trainer_sequence(self) -> bool:
        """Execute full trainer battle sequence"""
        # Delegate to combat system
        combat = self.memory.combat_system
        return await combat.execute_trainer_battle()
    
    async def _shop_buy_items(self, item_names: List[str], budget: int) -> bool:
        """Generic shopping action"""
        # Navigate to shop
        await self._navigate_to_location('pokemon_mart')
        
        # Enter and shop
        await self._enter_building()
        
        for item_name in item_names:
            await self.memory.interaction_optimizer.shop_buy_optimal(item_name, 5)
        
        # Exit
        await self._exit_building()
        
        return True
```

---

## 6. Performance Specifications

### 6.1 Planning Benchmarks

| Layer | Update Interval | Time Budget | Goals Evaluated |
|-------|----------------|-------------|-----------------|
| Strategic | 1000 cycles | 500ms | 10-15 goals |
| Tactical | 30 cycles | 50ms | 5-8 goals |
| Reactive | Continuous | 5ms | 1-3 immediate checks |
| Action Execution | Per action | Varies | Single action |

**Total AI overhead:** <8% CPU @ 60fps

---

## 7. Testing Requirements

```python
# Critical tests
test_goal_utility_calculation()
test_prerequisite_resolution()
test_plan_repair_on_failure()
test_strategic_sequence_generation()
test_tactical_priority_recalculation()
test_action_execution_success()
test_success_rate_learning()
test_temporal_discounting()
test_parallel_goal_handling()
```

**Coverage Target:** 90% critical path, 100% goal dependency resolution

---

## 8. Known Edge Cases

| Scenario | Handling Strategy |
|----------|------------------|
| Circular dependencies | Topological sort with cycle detection |
| Goal conflicts | Utility-based arbitration |
| Resource starvation | Temporal difference learning |
| Failure cascades | Local plan repair |
| Stuck in local optima | Random exploration boost |
| Overwhelming choice | Satisficing (first "good enough") |
| Dynamic environment | Incremental replanning |

---

**Document Version History:**
- v1.0: Complete hierarchical GOAP system with goal enablement graph