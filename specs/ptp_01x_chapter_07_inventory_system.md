# PTP-01X Chapter 7: Inventory & Item Logistics

**Version:** 1.0  
**Author:** AI Architect  
**Status:** Technical Specification (Implementable)  
**Dependencies:** Chapter 2 (Memory Layer), Chapter 6 (Entity Management)

---

## Executive Summary

The Inventory System manages the 20-slot bag with automatic partitioning, opportunity cost analysis, and tactical usage optimization. It solves three core problems:

1. **Hoarding Prevention**: Auto-use or toss items approaching bag capacity
2. **Opportunity Cost**: Every held item prevents an alternative; calculate implicit cost
3. **Shopping Heuristics**: Determine which items to buy based on upcoming challenges

This layer implements **ruthless item triage** where no item is sacred - everything is evaluated on utility-per-slot.

---

## 1. Bag Memory Structure (WRAM)

### 1.1 Inventory Layout

```
Bag starts at $D31D (20 slots, 2 bytes each)
Slot structure: [Item ID] [Quantity]
Empty slots: [0xFF] [0x00]

$D31D-$D34A: 20 item slots (2 bytes each)
$D34B: Item count (0-20)

Key addresses:
$31C8-$31CC: Money (3 bytes BCD)
$D31C: Item count
$D31D: Item slot 1 (ID)
$D31E: Item slot 1 (Quantity)
...
$D34A: Item slot 20 (Quantity)
```

### 1.2 Item Categories

```python
ITEM_CATEGORIES = {
    # Healing (auto-use when health < threshold)
    'healing': {
        0x11: {'name': 'Potion', 'hp': 20, 'priority': 1.0},
        0x12: {'name': 'Super Potion', 'hp': 50, 'priority': 1.2},
        0x13: {'name': 'Hyper Potion', 'hp': 200, 'priority': 1.5},
        0x14: {'name': 'Max Potion', 'hp': 999, 'priority': 1.8},
        0x15: {'name': 'Revive', 'hp': 50, 'priority': 2.0},  # Revive from fainted
        0x16: {'name': 'Max Revive', 'hp': 999, 'priority': 2.2},
        0x17: {'name': 'Fresh Water', 'hp': 50, 'priority': 1.1},
        0x18: {'name': 'Soda Pop', 'hp': 60, 'priority': 1.1},
        0x19: {'name': 'Lemonade', 'hp': 80, 'priority': 1.2},
        0x1A: {'name': 'Burn Heal', 'status': 'burn', 'priority': 0.8},
        0x1B: {'name': 'Antidote', 'status': 'poison', 'priority': 1.0},
        0x1C: {'name': 'Awakening', 'status': 'sleep', 'priority': 0.7},
        0x1D: {'name': 'Parlyz Heal', 'status': 'paralyze', 'priority': 0.9},
        0x1E: {'name': 'Full Restore', 'hp': 999, 'status': 'all', 'priority': 2.5},
        0x1F: {'name': 'Full Heal', 'status': 'all', 'priority': 1.4},
        0x20: {'name': 'Ice Heal', 'status': 'freeze', 'priority': 0.6},
    },
    
    # Poke Balls (shopping priority based on remaining encounters)
    'pokeballs': {
        0x04: {'name': 'Poke Ball', 'catch_rate': 1.0, 'priority': 1.0},
        0x05: {'name': 'Great Ball', 'catch_rate': 1.5, 'priority': 1.3},
        0x06: {'name': 'Ultra Ball', 'catch_rate': 2.0, 'priority': 1.6},
        0x07: {'name': 'Master Ball', 'catch_rate': 999, 'priority': 3.0},
    },
    
    # Battle Items (tactical use during combat)
    'battle_tactical': {
        0x2C: {'name': 'X Attack', 'stat': 'attack', 'stages': 1, 'priority': 0.9},
        0x2D: {'name': 'X Defend', 'stat': 'defense', 'stages': 1, 'priority': 0.8},
        0x2E: {'name': 'X Speed', 'stat': 'speed', 'stages': 1, 'priority': 1.0},
        0x2F: {'name': 'X Special', 'stat': 'special', 'stages': 1, 'priority': 1.1},
        0x30: {'name': 'X Accuracy', 'stat': 'accuracy', 'stages': 1, 'priority': 0.7},
        0x31: {'name': 'Guard Spec.', 'effect': 'mist', 'priority': 0.6},
        0x32: {'name': 'Dire Hit', 'effect': 'critical_rate', 'priority': 0.8},
        0x33: {'name': 'X Accuracy', 'stat': 'accuracy', 'stages': 2, 'priority': 0.9},
    },
    
    # Evolution Items (high value, never toss)
    'evolution': {
        0x19: {'name': 'Leaf Stone', 'value': 3.0, 'sell_price': 1050},
        0x1A: {'name': 'Water Stone', 'value': 3.0, 'sell_price': 1050},
        0x1B: {'name': 'Moon Stone', 'value': 3.5, 'sell_price': 0},  # Priceless
        0x1C: {'name': 'Fire Stone', 'value': 3.0, 'sell_price': 1050},
        0x1D: {'name': 'Thunder Stone', 'value': 3.0, 'sell_price': 1050},
    },
    
    # Rare Candies (strategic use, never waste)
    'rare_candy': {
        0x28: {'name': 'Rare Candy', 'value': 4.0, 'effect': 'level_up'},
    },
    
    # Key Items (cannot toss, permanent slots)
    'key_items': {
        0x08: {'name': 'Bicycle', 'required': True},
        0x09: {'name': 'S.S. Ticket', 'required': True},
        0x0A: {'name': 'Parcel', 'required': True},
        0x0B: {'name': 'Item Finder', 'required': False},
        0x0C: {'name': 'Silph Scope', 'required': True},
        0x0D: {'name': 'Coin Case', 'required': False},
        0x0E: {'name': 'Poke Flute', 'required': True},
        0x0F: {'name': 'Lift Key', 'required': True},
        0x10: {'name': 'Secret Key', 'required': True},
        0x2A: {'name': 'Old Rod', 'required': False},
        0x2B: {'name': 'Good Rod', 'required': False},
        0x2C: {'name': 'Super Rod', 'required': False},
        0x2D: {'name': 'PP Up', 'value': 2.5, 'sell_price': 0},
        0x2E: {'name': 'Ether', 'pp_restore': 10, 'priority': 1.8},
        0x2F: {'name': 'Max Ether', 'pp_restore': 999, 'priority': 2.0},
        0x30: {'name': 'Elixir', 'pp_restore': 10, 'priority': 2.2},
        0x31: {'name': 'Max Elixir', 'pp_restore': 999, 'priority': 2.5},
    },
    
    # Escape Items (emergency use)
    'escape': {
        0x27: {'name': 'Escape Rope', 'value': 1.2, 'priority': 1.0},
        0x24: {'name': 'Repel', 'steps': 100, 'priority': 0.8},
        0x25: {'name': 'Super Repel', 'steps': 200, 'priority': 1.0},
        0x26: {'name': 'Max Repel', 'steps': 250, 'priority': 1.1},
    },
    
    # Vendor Trash (sell when bag full)
    'vendor_trash': {
        0x21: {'name': 'Nugget', 'sell_price': 2500, 'priority': 0.1},
        0x22: {'name': 'PP Up', 'sell_price': 0, 'priority': 2.5},  # Actually valuable
        0x23: {'name': 'Rare Candy', 'sell_price': 0, 'priority': 4.0},  # Never sell
    }
}
```

---

## 2. Item Value Function

### 2.1 Dynamic Value Calculation

```python
class ItemValueCalculator:
    """
    Calculate utility-per-slot for each item
    Dynamic based on game state, upcoming challenges, and current party
    """
    
    def __init__(self, memory_interface, party_manager):
        self.memory = memory_interface
        self.party = party_manager
        self.logger = memory_interface.logger
        
        # Cache item priorities for this cycle
        self._value_cache = {}
        self._cache_cycle = -1
    
    async def calculate_item_value(self, item_id, quantity):
        """
        Calculate value (0.0-5.0) of holding this item
        Factors: immediate utility, future utility, opportunity cost
        """
        # Check cache
        if self.memory.get_cycle_count() == self._cache_cycle:
            if item_id in self._value_cache:
                return self._value_cache[item_id]
        
        # Get base priority from category
        category = self._get_item_category(item_id)
        base_priority = self._get_base_priority(item_id, category)
        
        # Apply game state modifiers
        situation_modifier = 1.0
        
        if category == 'healing':
            situation_modifier = await self._healing_modifier(item_id)
        elif category == 'pokeballs':
            situation_modifier = await self._pokeball_modifier(item_id)
        elif category == 'battle_tactical':
            situation_modifier = await self._battle_modifier(item_id)
        elif category == 'rare_candy':
            situation_modifier = await self._rare_candy_modifier(item_id)
        
        # Calculate opportunity cost
        opportunity_cost = await self._calculate_opportunity_cost(item_id)
        
        # Final value
        value = base_priority * situation_modifier * (1.0 - opportunity_cost)
        
        # Cache result
        if self.memory.get_cycle_count() != self._cache_cycle:
            self._value_cache.clear()
            self._cache_cycle = self.memory.get_cycle_count()
        
        self._value_cache[item_id] = value
        
        self.logger.debug(
            f"Item value: {ITEM_DATA[item_id]['name']} → {value:.2f} "
            f"(base: {base_priority}, mod: {situation_modifier:.2f}, "
            f"opportunity: {opportunity_cost:.2f})"
        )
        
        return value
    
    def _get_item_category(self, item_id):
        """Determine which category an item belongs to"""
        for category, items in ITEM_CATEGORIES.items():
            if item_id in items:
                return category
        return 'miscellaneous'
    
    def _get_base_priority(self, item_id, category):
        """Get static priority from category table"""
        if category in ITEM_CATEGORIES and item_id in ITEM_CATEGORIES[category]:
            return ITEM_CATEGORIES[category][item_id].get('priority', 1.0)
        
        # Default priority for uncategorized items
        return 0.5
    
    async def _healing_modifier(self, item_id):
        """Modifier based on party health status"""
        party_health = await self._get_party_health_status()
        
        modifiers = {
            'critical': 2.0,   # Multiple Pokemon < 30% HP
            'low': 1.5,        # Some Pokemon < 50% HP
            'healthy': 0.7,    # All Pokemon > 70% HP
            'full': 0.3        # All Pokemon > 90% HP
        }
        
        return modifiers.get(party_health, 1.0)
    
    async def _pokeball_modifier(self, item_id):
        """Modifier based on remaining encounters"""
        # Check if near legendary or rare Pokemon
        if await self._is_near_rare_encounter():
            # Prioritize better balls
            ball_ranking = {0x04: 0.5, 0x05: 1.0, 0x06: 2.0, 0x07: 3.0}
            return ball_ranking.get(item_id, 0.3)
        
        # Regular catching: prioritize quantity over quality
        return 1.0
    
    async def _battle_modifier(self, item_id):
        """Modifier based on upcoming boss battles"""
        upcoming_battle = await self._get_upcoming_battle_type()
        
        if upcoming_battle in ['gym', 'elite4']:
            # High value for stat boosters
            if item_id in [0x2C, 0x2D, 0x2E, 0x2F]:  # X Items
                return 1.5
        
        return 0.8  # Lower value for regular battles
    
    async def _rare_candy_modifier(self, item_id):
        """Rare Candy: calculate optimal usage target"""
        if item_id != 0x28:
            return 1.0
        
        # Find Pokemon closest to evolution or important move
        optimal_target = await self._find_optimal_rare_candy_target()
        
        if optimal_target:
            levels_to_target = optimal_target['target_level'] - optimal_target['pokemon'].level
            
            if levels_to_target <= 1:
                return 2.0  # Very high value: immediate evolution
            elif levels_to_target <= 3:
                return 1.5
            else:
                return 1.0  # Hold for future
        
        return 0.7  # No good target currently
    
    async def _calculate_opportunity_cost(self, item_id):
        """
        Calculate cost of holding this item (0.0-1.0)
        Higher = should use/sell/toss to free up slot
        """
        # Check bag capacity
        current_items = await self.memory.get_item_count()
        max_capacity = 20
        
        if current_items < max_capacity * 0.7:
            return 0.1  # Plenty of space
        elif current_items < max_capacity * 0.9:
            return 0.3  # Getting full
        else:
            # Bag nearly full: high opportunity cost for low-value items
            item_value = await self.calculate_item_value(item_id, 1)  # Base value
            if item_value < 1.0:
                return 0.8  # High cost: occupying valuable slot
            else:
                return 0.4
    
    async def _get_party_health_status(self):
        """Assess party overall health"""
        party = [p for p in self.party.party if p]
        
        if not party:
            return 'healthy'
        
        low_health = sum(1 for p in party if p.health_percentage < 30)
        medium_health = sum(1 for p in party if p.health_percentage < 50)
        
        if low_health >= 2:
            return 'critical'
        elif medium_health >= 3 or low_health >= 1:
            return 'low'
        elif all(p.health_percentage > 90 for p in party):
            return 'full'
        else:
            return 'healthy'
    
    async def _find_optimal_rare_candy_target(self):
        """Find Pokemon who would benefit most from Rare Candy"""
        candidates = []
        
        for pokemon in self.party.party:
            if not pokemon or pokemon.level >= 100:
                continue
            
            # Check for evolution
            species_data = SPECIES_DATA.get(pokemon.species_id, {})
            if 'evolution_level' in species_data:
                levels_to_evo = species_data['evolution_level'] - pokemon.level
                
                if 0 < levels_to_evo <= 3:  # Close to evolution
                    candidates.append({
                        'pokemon': pokemon,
                        'target_level': species_data['evolution_level'],
                        'reason': 'evolution',
                        'urgency': 1.0 / levels_to_evo
                    })
            
            # Check for important move
            next_move = self._get_next_important_move(pokemon)
            if next_move:
                levels_to_move = next_move['level'] - pokemon.level
                
                if 0 < levels_to_move <= 2:  # About to learn crucial move
                    candidates.append({
                        'pokemon': pokemon,
                        'target_level': next_move['level'],
                        'reason': 'move',
                        'urgency': 0.8 / levels_to_move
                    })
        
        if not candidates:
            return None
        
        # Choose highest urgency
        return max(candidates, key=lambda x: x['urgency'])
    
    def _get_next_important_move(self, pokemon):
        """Get next strategically important move for this Pokemon"""
        learnset = POKEMON_LEARNSETS.get(pokemon.species_id, [])
        
        # Moves worth prioritizing
        important_moves = {
            0x3C,  # Psychic
            0x46,  # Razor Leaf
            0x56,  # Thunderbolt
            0x55,  # Thunder
            0x53,  # Fire Blast
            0x5A,  # Solar Beam
            0x28,  # Earthquake
        }
        
        for move in learnset:
            if move['level'] > pokemon.level and move['id'] in important_moves:
                return move
        
        return None
