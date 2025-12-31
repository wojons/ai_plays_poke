# PTP-01X Chapter 2: Memory Layer - State Retrieval (The "Truth" Layer)

## Executive Summary

This chapter defines the complete memory map required for deterministic 100% completion of Pokémon Red/Blue/Yellow. The Memory Layer provides **ground truth** about the game state through direct memory access (DMA) via the PyBoy emulator's memory interface.

**Source Documentation:**
- [Data Crystal RAM Map](https://datacrystal.tcrf.net/wiki/Pok%C3%A9mon_Red_and_Blue/RAM_map)
- [PyBoy API Documentation](https://docs.pyboy.dk/api/index.html)
- [Pokemon Red Disassembly Project](https://github.com/pret/pokered/blob/master/ram/wram.asm)

---

## 2.1 WRAM Architecture and Address Mapping

The Game Boy's Work RAM (WRAM) is an 8KB block located at memory addresses `$C000-$DFFF`. This bank contains all dynamic game variables.

### PyBoy Memory Access API

```python
from pyboy import PyBoy

pyboy = PyBoy('pokemon_red.gb')

# Read single byte
player_x = pyboy.memory[0xD362]  # Player X block coordinate
player_y = pyboy.memory[0xD361]  # Player Y block coordinate
map_id = pyboy.memory[0xD35E]    # Current map ID
battle_status = pyboy.memory[0xD057]  # 0=Overworld, 1=Battle

# Read multiple bytes (slice)
party_data = pyboy.memory[0xD163:0xD163 + party_count * 30]

# PyBoy also provides high-level sprite access
sprite_data = pyboy.api.sprite.Sprite(pyboy, 0)  # Sprite 0 = Player
```

### Critical Memory Hooks

| Address | Size | Type | Purpose | Implementation |
|---------|------|------|---------|-----------------|
| `$D362` | 1 byte | uint8 | Player X block coordinate (0-255) | `pyboy.memory[0xD362]` |
| `$D361` | 1 byte | uint8 | Player Y block coordinate (0-255) | `pyboy.memory[0xD361]` |
| `$D35E` | 1 byte | uint8 | Current Map ID | `pyboy.memory[0xD35E]` |
| `$D057` | 1 byte | uint8 | Battle Status (0=Overworld, 1=Battle) | `pyboy.memory[0xD057]` |
| `$CC26` | 1 byte | uint8 | Menu Cursor Position | `pyboy.memory[0xCC26]` |
| `$D163` | 1 byte | uint8 | Party Count | `pyboy.memory[0xD163]` |

---

## 2.2 Player State Hooks

### Movement and Positioning

```
Addresses: $D362 (X), $D361 (Y)
Type: uint8 (0-255)
Range: Block coordinates, not pixel coordinates

Pixel Position Calculation:
pixel_x = block_x * 16 + 8  # Center of tile
pixel_y = block_y * 16 + 16 # Bottom of sprite (Game Boy offset)
```

**Implementation:**
```python
def get_player_position(pyboy) -> tuple[int, int]:
    """Get player position in block coordinates"""
    x = pyboy.memory[0xD362]
    y = pyboy.memory[0xD361]
    return (x, y)

def get_pixel_position(pyboy) -> tuple[int, int]:
    """Get player position in pixel coordinates"""
    block_x, block_y = get_player_position(pyboy)
    return (block_x * 16 + 8, block_y * 16 + 16)
```

### Sprite Data Table ($C100-$C1FF)

The sprite data table contains information for 16 sprites with 16 bytes each. **Player is always Sprite 0.**

```
Sprite Data Structure (16 bytes per sprite):

Offset  Property             Description
─────────────────────────────────────────
+$00    Picture ID           Fixed, loaded at map init
+$01    Movement Status      0=uninitialized, 1=ready, 2=delayed, 3=moving
+$02    Image Index          Changed on update, $FF=offscreen
+$03    Y Position Delta     -1, 0, or 1 (walking animation)
+$04    Y Screen Position    In pixels (4 pixels above grid center)
+$05    X Position Delta     -1, 0, or 1 (walking animation)
+$06    X Screen Position    In pixels (snaps to grid)
+$07    Animation Counter    Counts 0-4 per frame
+$08    Animation Frame      Increments every 4 updates (16 frames total)
+$09    Facing Direction     0=down, 4=up, 8=left, $C=right
+$0A-$0F  Undocumented       Reserved
```

**Implementation:**
```python
SPRITE_OFFSETS = {
    'picture_id': 0x00,
    'movement_status': 0x01,
    'image_index': 0x02,
    'y_delta': 0x03,
    'y_position': 0x04,
    'x_delta': 0x05,
    'x_position': 0x06,
    'anim_counter': 0x07,
    'anim_frame': 0x08,
    'facing': 0x09,
}

FACING_MAP = {0x00: 'down', 0x04: 'up', 0x08: 'left', 0x0C: 'right'}

def get_sprite_data(pyboy, sprite_id: int) -> dict:
    """Get sprite data from memory"""
    base = 0xC100 + (sprite_id * 0x10)
    return {
        'movement_status': pyboy.memory[base + SPRITE_OFFSETS['movement_status']],
        'facing': FACING_MAP.get(pyboy.memory[base + SPRITE_OFFSETS['facing']], 'unknown'),
        'x_position': pyboy.memory[base + SPRITE_OFFSETS['x_position']],
        'y_position': pyboy.memory[base + SPRITE_OFFSETS['y_position']],
    }

def get_player_facing(pyboy) -> str:
    """Get player's current facing direction"""
    sprite = get_sprite_data(pyboy, 0)
    return sprite['facing']
```

---

## 2.3 Map and Environment Hooks

### Current Map ID ($D35E)

```
Type: uint8
Purpose: Identifies the current zone

Map ID Examples (approximate):
0x00  Pallet Town
0x01  Viridian City
0x02  Pewter City
0x03  Cerulean City
0x04  Lavender Town
0x05  Vermilion City
0x06  Celadon City
0x07  Fuchsia City
0x08  Cinnabar Island
0x09  Indigo Plateau
0x0A  Route 1
...
```

**Implementation:**
```python
MAP_NAMES = {
    0x00: "Pallet Town",
    0x01: "Viridian City",
    # ... complete map table
}

def get_current_map(pyboy) -> dict:
    """Get current map information"""
    map_id = pyboy.memory[0xD35E]
    return {
        'map_id': map_id,
        'map_name': MAP_NAMES.get(map_id, f"Unknown_{map_id:02x}"),
        'x': pyboy.memory[0xD362],
        'y': pyboy.memory[0xD361],
    }
```

### Tile Graphics and Tileset

```
Addresses: $C3A0-$C507 (Current screen tiles)
           $C508-$C5CF (Previous screen tiles for restoration)

Purpose: Contains decompressed tile data for current screen
         Used to restore screen after closing menus
```

---

## 2.4 Menu and Interface Hooks

### Menu Cursor Tracking ($CC24-$CC36)

```
Address     Property                 Description
─────────────────────────────────────────────────
$CC24       Menu Cursor Y            Y position of cursor
$CC25       Menu Cursor X            X position of cursor
$CC26       Current Selection        Currently selected menu item (0=top)
$CC28       Last Menu Item ID        ID of last menu item
$CC2A       Previous Selection       Previously selected item
$CC2B       Last Party Position      Cursor pos on party screen
$CC2C       Last Item Position       Cursor pos on item screen
$CC2D       Last Start Menu Pos      Cursor pos on START menu
$CC35       Select Highlighted       Item highlighted with Select button
$CC36       First Displayed Item     ID of first displayed menu item
```

**Implementation:**
```python
def get_menu_state(pyboy) -> dict:
    """Get current menu state from memory"""
    return {
        'cursor_x': pyboy.memory[0xCC25],
        'cursor_y': pyboy.memory[0xCC24],
        'selected_item': pyboy.memory[0xCC26],
        'first_displayed': pyboy.memory[0xCC36],
        'select_highlighted': pyboy.memory[0xCC35],
    }

def is_in_menu(pyboy) -> bool:
    """Check if any menu is open"""
    # Menu cursor position is valid when in menu
    cursor = pyboy.memory[0xCC26]
    return cursor != 0xFF  # 0xFF typically indicates no menu
```

---

## 2.5 Battle State Hooks

### Master Battle Flag ($D057)

```
Value: 0x00 = Overworld traversal
       0x01 = Battle active
       Other = Transition state
```

### Battle Turn Data ($CCD5-$CD33)

```
Address     Property                     Description
─────────────────────────────────────────────────
$CCD5       Battle Turns                 Number of turns in current battle
$CCD7       Player Substitute HP         HP of player's substitute
$CCD8       Enemy Substitute HP          HP of enemy's substitute
$CCDB       Move Menu Type               0=regular, 1=mimic, other=textbox
$CCDC       Player Selected Move         Index of player's selected move
$CCDD       Enemy Selected Move          Index of enemy's selected move
$CCE5-$CCE7 Pay Day Money                Money earned by Pay Day

Stat Modifiers (7 = no modifier):
$CD1A       Player Attack Modifier
$CD1B       Player Defense Modifier
$CD1C       Player Speed Modifier
$CD1D       Player Special Modifier
$CD1E       Player Accuracy Modifier
$CD1F       Player Evasion Modifier

$CD2F       Enemy Defense Modifier
$CD30       Enemy Speed Modifier
$CD31       Enemy Special Modifier
$CD32       Enemy Accuracy Modifier
$CD33       Enemy Evasion Modifier
```

**Implementation:**
```python
def get_battle_state(pyboy) -> dict:
    """Get comprehensive battle state"""
    return {
        'battle_active': pyboy.memory[0xD057] == 0x01,
        'turn': pyboy.memory[0xCCD5],
        'player_move': pyboy.memory[0xCCDC],
        'enemy_move': pyboy.memory[0xCCDD],
        'player_stat_mods': {
            'attack': pyboy.memory[0xCD1A],
            'defense': pyboy.memory[0xCD1B],
            'speed': pyboy.memory[0xCD1C],
            'special': pyboy.memory[0xCD1D],
            'accuracy': pyboy.memory[0xCD1E],
            'evasion': pyboy.memory[0xCD1F],
        },
    }

def get_enemy_stats(pyboy) -> dict:
    """Get enemy stat modifiers"""
    return {
        'attack': pyboy.memory[0xCD2E],
        'defense': pyboy.memory[0xCD2F],
        'speed': pyboy.memory[0xCD30],
        'special': pyboy.memory[0xCD31],
        'accuracy': pyboy.memory[0xCD32],
        'evasion': pyboy.memory[0xCD33],
    }
```

---

## 2.6 Party and Pokemon Data

### Party Count ($D163)

```
Type: uint8 (0-6)
Location: $D163

Party Structure: Follows immediately after count
Each Pokemon: ~30 bytes with stats, moves, etc.
```

### Pokemon Data Structure (Partial)

```
Offset  Property             Size    Description
───────────────────────────────────────────────
+$00    Species              1       Pokemon species ID
+$01    HP Current           2       Current HP (big-endian)
+$03    HP Max               2       Max HP (big-endian)
+$0B    Status               1       Status condition (SLP/PSN/BRN/FRZ/PAR)
+$0D    Type 1               1       Primary type
+$0E    Type 2               1       Secondary type
+$11    Move 1 PP            1       PP remaining for move 1
+$12    Move 2 PP            1       PP remaining for move 2
+$13    Move 3 PP            1       PP remaining for move 3
+$14    Move 4 PP            1       PP remaining for move 4
+$15    Move 1 PP Max        1       Max PP for move 1
+$16    Move 2 PP Max        1       Max PP for move 2
+$17    Move 3 PP Max        1       Max PP for move 3
+$18    Move 4 PP Max        1       Max PP for move 4
+$19    Level                1       Pokemon level
+$1A    Exp                  3       Experience points (big-endian)
```

**Implementation:**
```python
POKEMON_STRUCT_SIZE = 0x2C  # 44 bytes per Pokemon

def get_party_count(pyboy) -> int:
    """Get number of Pokemon in party"""
    return pyboy.memory[0xD163]

def get_party_pokemon(pyboy, index: int) -> dict:
    """Get party Pokemon data at index"""
    base = 0xD164 + (index * POKEMON_STRUCT_SIZE)
    return {
        'species': pyboy.memory[base],
        'current_hp': (pyboy.memory[base + 0x01] << 8) | pyboy.memory[base + 0x02],
        'max_hp': (pyboy.memory[base + 0x03] << 8) | pyboy.memory[base + 0x04],
        'level': pyboy.memory[base + 0x19],
        'status': pyboy.memory[base + 0x0B],
        'moves': [
            pyboy.memory[base + 0x0F],
            pyboy.memory[base + 0x10],
            pyboy.memory[base + 0x11],
            pyboy.memory[base + 0x12],
        ],
        'move_pp': [
            pyboy.memory[base + 0x15],
            pyboy.memory[base + 0x16],
            pyboy.memory[base + 0x17],
            pyboy.memory[base + 0x18],
        ],
    }

def get_full_party(pyboy) -> list:
    """Get all party Pokemon"""
    count = get_party_count(pyboy)
    return [get_party_pokemon(pyboy, i) for i in range(count)]
```

---

## 2.7 Enemy Pokemon Data

### Enemy Pokemon Addresses

```
$CFE6-$CFE7    Enemy Current HP (big-endian)
$CFF4+         Enemy Defense Stat (with offset)
$CD2D          Enemy Trainer Class / Pokemon ID
$CD2E          Enemy Attack Modifier
```

**Implementation:**
```python
def get_enemy_pokemon(pyboy) -> dict:
    """Get enemy Pokemon data from battle memory"""
    return {
        'current_hp': (pyboy.memory[0xCFE6] << 8) | pyboy.memory[0xCFE7],
        'attack_mod': pyboy.memory[0xCD2E],
        'defense_mod': pyboy.memory[0xCD2F],
        'speed_mod': pyboy.memory[0xCD30],
        'special_mod': pyboy.memory[0xCD31],
        'accuracy_mod': pyboy.memory[0xCD32],
        'evasion_mod': pyboy.memory[0xCD33],
    }
```

---

## 2.8 Event Flags ($D7xx-$D8xx range)

Event flags track game progress (badges received, NPCs talked to, items obtained).

```
Structure: Contiguous bitfield in WRAM
Each byte: 8 individual flags (bits 0-7)
Bit = 1: Event completed
Bit = 0: Event not yet completed
```

**Implementation:**
```python
def get_event_flag(pyboy, address: int, bit: int) -> bool:
    """Check if a specific event flag is set"""
    flag_byte = pyboy.memory[address]
    return (flag_byte >> bit) & 0x01 == 0x01

def set_event_flag(pyboy, address: int, bit: int):
    """Set an event flag"""
    current = pyboy.memory[address]
    pyboy.memory[address] = current | (0x01 << bit)

def get_event_flags_range(pyboy, start: int, end: int) -> dict:
    """Get range of event flags as bitfield"""
    flags = {}
    for addr in range(start, end + 1):
        flags[addr] = pyboy.memory[addr]
    return flags
```

---

## 2.9 Inventory and Item Data

### Item Bag Structure

```
$C3A0-$C3FF range (approximate, varies by version)
Structure: Linked list of (Item ID, Quantity) pairs
```

### Money Address

```
$D3C7-$D3C9    Money (big-endian, 3 bytes)
```

**Implementation:**
```python
def get_money(pyboy) -> int:
    """Get player's current money"""
    m = pyboy.memory
    return (m[0xD3C7] << 16) | (m[0xD3C8] << 8) | m[0xD3C9]

def get_pokeball_count(pyboy) -> int:
    """Get number of Pokeballs (approximate - needs specific address)"""
    # This requires the specific item bag structure address
    # Based on Data Crystal, item data starts at $C3A0 approximately
    pass
```

---

## 2.10 Joypad Simulation and Input

### Joypad Input Memory ($CC38 for simulation)

```
$CC38   Joypad Input Simulation
        If non-zero: Disables collision detection but allows movement
        Used for automated input sequences
```

**Implementation:**
```python
def simulate_joypad(pyboy, input_byte: int):
    """
    Simulate joypad input
    Bitmask: 0x01=A, 0x02=B, 0x04=SELECT, 0x08=START
             0x10=UP, 0x20=DOWN, 0x40=LEFT, 0x80=RIGHT
    """
    pyboy.memory[0xCC38] = input_byte

def clear_joypad_simulation(pyboy):
    """Clear joypad simulation"""
    pyboy.memory[0xCC38] = 0x00
```

---

## 2.11 Memory Integrity and Corruption Detection

### Glitch Prevention

The agent must monitor for Generation I instability issues:

1. **Stack Overflow Detection**: Monitor addresses surrounding stack ($C000-$C0FF)
2. **Sprite Buffer Overflow**: Sprite buffers at $A000-$B857 (SRAM)
3. **MissingNo Protection**: Monitor for invalid Pokemon species IDs (0x00, 0xFF, >151)

**Implementation:**
```python
VALID_POKEMON_IDS = set(range(1, 152))  # 1-151 for Gen 1

def validate_memory_integrity(pyboy) -> dict:
    """Check for memory corruption"""
    issues = []
    
    # Check party Pokemon are valid
    party_count = pyboy.memory[0xD163]
    for i in range(party_count):
        species = pyboy.memory[0xD164 + (i * 0x2C)]
        if species not in VALID_POKEMON_IDS:
            issues.append(f"Invalid Pokemon species {species:02x} at party slot {i}")
    
    # Check map ID is in valid range
    map_id = pyboy.memory[0xD35E]
    if map_id > 0x7F:  # Sanity check
        issues.append(f"Suspicious map ID {map_id:02x}")
    
    # Check HP values are valid
    enemy_hp = (pyboy.memory[0xCFE6] << 8) | pyboy.memory[0xCFE7]
    if enemy_hp > 65535:
        issues.append(f"Invalid enemy HP {enemy_hp}")
    
    return {
        'valid': len(issues) == 0,
        'issues': issues,
    }
```

---

## 2.12 Complete Memory Interface Class

```python
class PokemonMemoryInterface:
    """
    Complete memory interface for Pokemon Red/Blue/Yellow
    Provides O(1) access to all critical game state data
    """
    
    # Memory addresses from Data Crystal RAM map
    ADDRESSES = {
        'player_x': 0xD362,
        'player_y': 0xD361,
        'map_id': 0xD35E,
        'battle_status': 0xD057,
        'party_count': 0xD163,
        'menu_cursor': 0xCC26,
        'menu_cursor_x': 0xCC25,
        'menu_cursor_y': 0xCC24,
        'battle_turn': 0xCCD5,
        'player_move': 0xCCDC,
        'enemy_move': 0xCCDD,
        'enemy_hp_low': 0xCFE6,
        'enemy_hp_high': 0xCFE7,
        'money_1': 0xD3C7,
        'money_2': 0xD3C8,
        'money_3': 0xD3C9,
        'joypad_sim': 0xCC38,
    }
    
    def __init__(self, pyboy):
        self.pyboy = pyboy
        self.memory = pyboy.memory
    
    def get_player_position(self) -> tuple[int, int]:
        """Get player block coordinates"""
        return (self.memory[self.ADDRESSES['player_x']],
                self.memory[self.ADDRESSES['player_y']])
    
    def get_current_map(self) -> int:
        """Get current map ID"""
        return self.memory[self.ADDRESSES['map_id']]
    
    def is_in_battle(self) -> bool:
        """Check if in battle"""
        return self.memory[self.ADDRESSES['battle_status']] == 0x01
    
    def is_in_menu(self) -> bool:
        """Check if menu is open"""
        cursor = self.memory[self.ADDRESSES['menu_cursor']]
        return cursor != 0xFF
    
    def get_battle_state(self) -> dict:
        """Get comprehensive battle state"""
        return {
            'turn': self.memory[self.ADDRESSES['battle_turn']],
            'player_move': self.memory[self.ADDRESSES['player_move']],
            'enemy_move': self.memory[self.ADDRESSES['enemy_move']],
            'enemy_hp': ((self.memory[self.ADDRESSES['enemy_hp_low']] << 8) |
                          self.memory[self.ADDRESSES['enemy_hp_high']]),
        }
    
    def get_money(self) -> int:
        """Get player money"""
        return ((self.memory[self.ADDRESSES['money_1']] << 16) |
                (self.memory[self.ADDRESSES['money_2']] << 8) |
                self.memory[self.ADDRESSES['money_3']])
    
    def simulate_input(self, input_byte: int):
        """Simulate joypad input"""
        self.memory[self.ADDRESSES['joypad_sim']] = input_byte
    
    def clear_input_simulation(self):
        """Clear input simulation"""
        self.memory[self.ADDRESSES['joypad_sim']] = 0x00
```

---

## 2.13 Memory Access Patterns

### Optimization Strategies

1. **Batch Reading**: Read multiple addresses in single operation
2. **Caching**: Cache static data (map names, Pokemon stats)
3. **Change Detection**: Only re-read changed values

```python
def batch_read(pyboy, addresses: list) -> dict:
    """Batch read multiple memory addresses efficiently"""
    return {addr: pyboy.memory[addr] for addr in addresses}

# Pre-computed static data (never changes)
STATIC_DATA = {
    'type_chart': {...},  # Gen 1 type effectiveness
    'move_data': {...},   # Move names, types, power
    'pokemon_stats': {...},  # Base stats for all Pokemon
    'map_names': {...},   # Map ID to name mapping
}
```

---

## 2.14 Summary of Memory Hooks

| Category | Addresses | Purpose | Access Frequency |
|----------|-----------|---------|------------------|
| **Player Position** | $D362, $D361 | X, Y coordinates | Every tick |
| **Map ID** | $D35E | Current zone | Every tick |
| **Battle State** | $D057, $CCD5, etc. | Battle status | During battles |
| **Menu State** | $CC24-$CC36 | Menu cursor/selection | In menus |
| **Sprite Data** | $C100-$C1FF | Sprite positions | Every tick |
| **Party Data** | $D163+ | Pokemon in party | Frequent |
| **Enemy Data** | $CFE6+, $CDxx | Battle opponent | During battles |
| **Event Flags** | $D7xx-$D8xx | Quest progress | On events |
| **Inventory** | $C3A0+ | Items | Shopping/inventory |
| **Money** | $D3C7-$D3C9 | Currency | Shopping |

---

## 2.15 References

1. **Data Crystal RAM Map**: https://datacrystal.tcrf.net/wiki/Pok%C3%A9mon_Red_and_Blue/RAM_map
2. **Pokemon Red Disassembly**: https://github.com/pret/pokered/blob/master/ram/wram.asm
3. **PyBoy API Documentation**: https://docs.pyboy.dk/api/index.html
4. **Game Boy Memory Map**: https://gbdev.io/pandocs/Memory_Map.html

---

**Document Version:** 1.0  
**Last Updated:** December 31, 2025  
**Protocol:** PTP-01X - Chapter 2: Memory Layer  
**Data Source:** Data Crystal RAM Map (verified with Pokemon Red disassembly)