"""
RAM Reader for Pokémon Gen 1 (Red/Blue).

Reads the Game Boy's working RAM via pygba's memory API and the ROM file
on disk to extract the same structured observation that the cartographer
(vision model) currently produces. No hallucinations, <1ms per call, zero API cost.

Architecture:
  - ROM parsing (ROM file on disk) → map block data, dimensions, tileset
  - Emulator RAM (via Emulator.read_u8) → player position, facing, screen type
  - Combined output → minimap text + structured JSON observation

Addresses from:
  - pret/pokered disassembly: https://github.com/pret/pokered
  - Data Crystal: https://datacrystal.tcrf.net/wiki/Pokémon_Red_and_Blue
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# ── WRAM addresses (Pokémon Red/Blue) ────────────────────────────────────

# Player state
ADDR_Y_COORD = 0xD361          # wYCoord — player Y on map (in blocks)
ADDR_X_COORD = 0xD362          # wXCoord — player X on map (in blocks)
ADDR_CUR_MAP = 0xD35E          # wCurMap — current map ID
ADDR_WALK_COUNTER = 0xCFC5     # wWalkCounter — non-zero → moving

# Screen tile buffer: 20×18 tiles at $C3A0 (wTileMap)
ADDR_TILE_MAP = 0xC3A0
TILE_MAP_WIDTH = 20
TILE_MAP_HEIGHT = 18

# Text box state
ADDR_TEXT_BOX_FRAME = 0xCF2B   # nonzero → text box rendering
ADDR_TEXT_PROMPT = 0xCF4C      # wTextScrollPrompt — text box scroll indicator

# Battle state
ADDR_IS_IN_BATTLE = 0xD057     # wIsInBattle — 0=none, 1=wild, 2=trainer
ADDR_BATTLE_TYPE = 0xD05A      # wBattleType — 1=wild, 2=trainer
ADDR_CUR_OPPONENT = 0xD058     # wCurOpponent — species (wild) or trainer class+offset

# Battle — Player mon (wBattleMon, 0xD016–0xD032)
ADDR_BATTLE_MON_SPECIES  = 0xD016
ADDR_BATTLE_MON_HP       = 0xD017  # u16
ADDR_BATTLE_MON_STATUS   = 0xD01A
ADDR_BATTLE_MON_TYPE1    = 0xD01B
ADDR_BATTLE_MON_TYPE2    = 0xD01C
ADDR_BATTLE_MON_MOVES    = 0xD01E  # 4 bytes
ADDR_BATTLE_MON_DVS      = 0xD022  # u16
ADDR_BATTLE_MON_LEVEL    = 0xD024
ADDR_BATTLE_MON_MAX_HP   = 0xD025  # u16
ADDR_BATTLE_MON_ATTACK   = 0xD027  # u16
ADDR_BATTLE_MON_DEFENSE  = 0xD029  # u16
ADDR_BATTLE_MON_SPEED    = 0xD02B  # u16
ADDR_BATTLE_MON_SPECIAL  = 0xD02D  # u16
ADDR_BATTLE_MON_PP       = 0xD02F  # 4 bytes

# Battle — Enemy mon (wEnemyMon, 0xCFE7–0xD003)
ADDR_ENEMY_MON_SPECIES   = 0xCFE7
ADDR_ENEMY_MON_HP        = 0xCFE8  # u16
ADDR_ENEMY_MON_STATUS    = 0xCFEB
ADDR_ENEMY_MON_TYPE1     = 0xCFEC
ADDR_ENEMY_MON_TYPE2     = 0xCFED
ADDR_ENEMY_MON_MOVES     = 0xCFEF  # 4 bytes
ADDR_ENEMY_MON_CATCH     = 0xCFEE
ADDR_ENEMY_MON_DVS       = 0xCFF3  # u16
ADDR_ENEMY_MON_LEVEL     = 0xCFF5
ADDR_ENEMY_MON_MAX_HP    = 0xCFF6  # u16
ADDR_ENEMY_MON_ATTACK    = 0xCFF8  # u16
ADDR_ENEMY_MON_DEFENSE   = 0xCFFA  # u16
ADDR_ENEMY_MON_SPEED     = 0xCFFC  # u16
ADDR_ENEMY_MON_SPECIAL   = 0xCFFE  # u16
ADDR_ENEMY_MON_PP        = 0xD000  # 4 bytes

# Battle — Move selection
ADDR_PLAYER_MOVE_NUM     = 0xCF95  # wPlayerMoveNum
ADDR_MOVE_NUM            = 0xCC85  # wMoveNum

# NPC / interaction state
ADDR_SPRITE_STATE_DATA = 0xC100  # wSpriteStateData1 (16 sprites × 16 bytes)

# Menu state
ADDR_TOP_MENU_ITEM_Y     = 0xCC24  # wTopMenuItemY
ADDR_TOP_MENU_ITEM_X     = 0xCC25  # wTopMenuItemX
ADDR_CURRENT_MENU_ITEM   = 0xCC26  # wCurrentMenuItem
ADDR_MAX_MENU_ITEM       = 0xCC28  # wMaxMenuItem
ADDR_LAST_MENU_ITEM      = 0xCC2A  # wLastMenuItem

# List/context menu
ADDR_LIST_MENU_ID        = 0xCF88  # wListMenuID

# Text buffer
ADDR_STRING_BUFFER       = 0xCE00  # wStringBuffer (11 bytes)

# Name entry
ADDR_NAMING_SCREEN       = 0xCC47    # wNamingScreenType
ADDR_NAMING_NAME_LENGTH  = 0xCC48    # wNamingScreenNameLength
ADDR_NAMING_SUBMIT       = 0xCC4A    # wNamingScreenSubmitName
ADDR_ALPHABET_CASE       = 0xCC4D    # wAlphabetCase
ADDR_NAMING_LETTER       = 0xCC4F    # wNamingScreenLetter

# Map block data in WRAM — $C6E8 + width + (width+6)*Y + X
# (from Data Crystal notes)
ADDR_OVERWORLD_MAP_BASE = 0xC6E8

# ── Facing direction decode ──────────────────────────────────────────────

FACING_DIRECTIONS: dict[int, str] = {
    0x00: "down",
    0x04: "up",
    0x08: "left",
    0x0C: "right",
}

FACING_ARROWS: dict[str, str] = {
    "down": "↓",
    "up": "↑",
    "left": "←",
    "right": "→",
}

# Classification → single-letter symbol for the 5×5 overworld grid
CLASS_SYMBOLS: dict[str, str] = {
    "floor": ".",
    "wall": "B",
    "stairs": "D",
    "door": "D",
    "warp": "D",
    "water": "W",
    "grass": "G",
    "ledge": "B",
    "object": "S",
    "tree": "T",
    "unknown": "?",
    "void": "?",
}

# ── Screen type constants ────────────────────────────────────────────────

SCREEN_OVERWORLD = "overworld"
SCREEN_DIALOG = "dialog"
SCREEN_BATTLE = "battle"
SCREEN_MENU = "menu"
SCREEN_TITLE = "title"
SCREEN_NAME_ENTRY = "name_entry"
SCREEN_UNKNOWN = "unknown"

# ── Block classification (symbols for the minimap) ───────────────────────

# These are guesses based on observation; refined as the AI explores.
# Known block types per tileset will be learned over time.
BLOCK_SYMBOLS: dict[str, str] = {
    "floor": "··",
    "wall": "██",
    "stairs": "⇩⇩",
    "door": "DD",
    "warp": "WW",
    "water": "~~",
    "grass": "░░",
    "ledge": "^^",
    "object": "◈◈",
    "unknown": "??",
    "void": "  ",
    "player": "PP",
    "out_of_bounds": "░░",
}


# ── ROM map database ─────────────────────────────────────────────────────

# Pokémon Red/Blue ROM layout (from Data Crystal)
_MAP_COUNT = 248
_PTR_TABLE = 0x01AE         # Map header pointer table (ROM offset)
_BANK_TABLE = 0xC23D        # Map header bank table (ROM offset)


class _MapDB:
    """Parse Pokémon Red/Blue ROM to provide map block data on demand."""

    def __init__(self, rom_path: str | Path) -> None:
        self._rom = Path(rom_path).read_bytes()
        self._cache: dict[int, dict[str, Any]] = {}

    @classmethod
    def from_bytes(cls, rom_bytes: bytes) -> _MapDB:
        """Construct _MapDB from pre-loaded ROM bytes (for testing)."""
        self = cls.__new__(cls)
        self._rom = rom_bytes
        self._cache = {}
        return self

    # ── ROM helpers ──────────────────────────────────────────────────

    @staticmethod
    def _read_u16(data: bytes, offset: int) -> int:
        return data[offset] | (data[offset + 1] << 8)

    @staticmethod
    def _read_u8(data: bytes, offset: int) -> int:
        return data[offset]

    def _rom_offset(self, ptr: int, bank: int) -> int:
        """Convert (pointer, bank) → ROM file byte offset."""
        if bank == 0:
            return ptr
        return bank * 0x4000 + (ptr - 0x4000)

    # ── Map header parsing ───────────────────────────────────────────

    def _parse_header(self, map_id: int) -> dict[str, Any] | None:
        """Parse the map header for *map_id* and return block data + metadata."""
        if map_id in self._cache:
            return self._cache[map_id]

        if map_id >= _MAP_COUNT:
            return None

        ptr = self._read_u16(self._rom, _PTR_TABLE + map_id * 2)
        bank = self._read_u8(self._rom, _BANK_TABLE + map_id)
        roff = self._rom_offset(ptr, bank)

        if roff + 12 > len(self._rom):
            return None

        tileset = self._rom[roff]
        height = self._rom[roff + 1]
        width = self._rom[roff + 2]
        block_ptr = self._read_u16(self._rom, roff + 3)
        # text_ptr = self._read_u16(self._rom, roff + 5)
        # script_ptr = self._read_u16(self._rom, roff + 7)
        # connection = self._rom[roff + 9]

        # Read block data (width × height bytes)
        block_roff = self._rom_offset(block_ptr, bank)
        block_data: list[int] = []
        for y in range(height):
            for x in range(width):
                idx = y * width + x
                block_data.append(self._rom[block_roff + idx])

        result: dict[str, Any] = {
            "tileset": tileset,
            "width": width,
            "height": height,
            "block_data": block_data,  # flat list, row-major
        }
        self._cache[map_id] = result
        return result

    def get_map(self, map_id: int) -> dict[str, Any] | None:
        """Return parsed map data for *map_id*."""
        return self._parse_header(map_id)

    def block_at(self, map_id: int, x: int, y: int) -> int | None:
        """Return the block index at map position (x, y), or None."""
        info = self.get_map(map_id)
        if info is None:
            return None
        w, h = info["width"], info["height"]
        if not (0 <= x < w and 0 <= y < h):
            return None
        return info["block_data"][y * w + x]  # type: ignore[no-any-return]

    # ── Block classification ─────────────────────────────────────────

    # Known block → classification for tileset 4 (indoor: Red's House, etc.)
    # These are empirically determined; expanded as the AI explores.
    _TILESET4_CLASSES: dict[int, str] = {
        0x0F: "floor",
        0x0D: "stairs",
        0x10: "wall",
        0x11: "wall",
        0x05: "wall",
        0x08: "wall",
        0x0C: "wall",   # bottom-left corner / wall piece
        0x12: "object",  # bottom-right object
    }

    # Known block → classification for tileset 0 (outdoor: towns, routes)
    # Source: pret/pokered disassembly block sets
    _TILESET0_CLASSES: dict[int, str] = {
        # Tall grass
        0x00: "grass", 0x01: "grass", 0x02: "grass", 0x03: "grass",
        # Path / floor (plain ground)
        0x0C: "floor", 0x0D: "floor", 0x0E: "floor", 0x0F: "floor",
        0x10: "floor", 0x11: "floor",
        # Building walls / roof pieces
        0x14: "wall", 0x15: "wall", 0x16: "wall", 0x17: "wall",
        0x18: "wall", 0x19: "wall", 0x1A: "wall", 0x1B: "wall",
        0x1C: "wall", 0x1D: "wall", 0x1E: "wall", 0x1F: "wall",
        # Water
        0x2B: "water", 0x2C: "water",
        0x48: "water", 0x49: "water",
        # Trees
        0x32: "tree", 0x33: "tree", 0x34: "tree", 0x35: "tree",
        0x3E: "tree", 0x3F: "tree",
        # Ledge
        0x4A: "ledge", 0x4B: "ledge", 0x4C: "ledge",
        0x4D: "ledge", 0x4E: "ledge", 0x4F: "ledge",
        # Signposts / objects
        0x60: "object", 0x61: "object",
        # Doors / entrances
        0x5C: "door", 0x5D: "door",
        # Fences / hedges
        0x50: "wall", 0x51: "wall", 0x52: "wall", 0x53: "wall",
    }

    def classify_block(self, block_id: int, tileset: int) -> str:
        """Classify a block ID as floor/wall/stairs/etc. for the given tileset."""
        if tileset == 4:
            return self._TILESET4_CLASSES.get(block_id, "unknown")
        if tileset == 0:
            return self._TILESET0_CLASSES.get(block_id, "unknown")
        # Generic heuristic: if block_id is 0x0F, assume floor
        if block_id == 0x0F:
            return "floor"
        return "unknown"


# ── Pokémon species names (index → name, Gen 1 1-indexed) ────────────────

POKEMON_NAMES: dict[int, str] = {
    1: "Rhydon", 2: "Kangaskhan", 3: "Nidoran♂", 4: "Clefairy",
    5: "Spearow", 6: "Voltorb", 7: "Nidoking", 8: "Slowbro",
    9: "Ivysaur", 10: "Exeggutor", 11: "Lickitung", 12: "Exeggcute",
    13: "Grimer", 14: "Gengar", 15: "Nidoran♀", 16: "Nidoqueen",
    17: "Cubone", 18: "Rhyhorn", 19: "Lapras", 20: "Arcanine",
    21: "Mew", 22: "Gyarados", 23: "Shellder", 24: "Tentacool",
    25: "Gastly", 26: "Scyther", 27: "Staryu", 28: "Blastoise",
    29: "Pinsir", 30: "Tangela",
    33: "Growlithe", 34: "Onix", 35: "Fearow", 36: "Pidgey",
    37: "Slowpoke", 38: "Kadabra", 39: "Graveler", 40: "Chansey",
    41: "Machoke", 42: "Mr. Mime", 43: "Hitmonlee", 44: "Hitmonchan",
    45: "Arbok", 46: "Parasect", 47: "Psyduck", 48: "Drowzee",
    49: "Golem", 51: "Magmar",
    53: "Electabuzz", 54: "Magneton", 55: "Koffing",
    57: "Mankey", 58: "Seel", 59: "Diglett", 60: "Tauros",
    63: "Farfetch'd", 64: "Venonat", 65: "Dragonite",
    67: "Doduo", 68: "Poliwag", 69: "Jynx", 70: "Moltres",
    71: "Articuno", 72: "Zapdos", 73: "Ditto", 74: "Meowth",
    75: "Krabby",
    77: "Vulpix", 78: "Ninetales", 79: "Pikachu", 80: "Raichu",
    83: "Dratini", 84: "Dragonair", 85: "Kabuto", 86: "Kabutops",
    87: "Horsea", 88: "Seadra",
    90: "Sandshrew", 91: "Sandslash", 92: "Omanyte", 93: "Omastar",
    94: "Jigglypuff", 95: "Wigglytuff", 96: "Eevee", 97: "Flareon",
    98: "Jolteon", 99: "Vaporeon", 100: "Machop",
    101: "Zubat", 102: "Ekans", 103: "Paras", 104: "Poliwhirl",
    105: "Poliwrath", 106: "Weedle", 107: "Kakuna", 108: "Beedrill",
    110: "Dodrio", 111: "Primeape", 112: "Dugtrio", 113: "Venomoth",
    114: "Dewgong",
    117: "Caterpie", 118: "Metapod", 119: "Butterfree",
    120: "Machamp",
    123: "Golduck", 124: "Hypno", 125: "Golbat", 126: "Mewtwo",
    127: "Snorlax", 128: "Magikarp",
    131: "Muk",
    133: "Kingler", 134: "Cloyster",
    136: "Electrode", 137: "Clefable", 138: "Weezing",
    139: "Persian", 140: "Marowak",
    142: "Haunter", 143: "Abra", 144: "Alakazam",
    145: "Pidgeotto", 146: "Pidgeot", 147: "Starmie",
    148: "Bulbasaur", 149: "Venusaur", 150: "Tentacruel",
    152: "Goldeen", 153: "Seaking",
    157: "Ponyta", 158: "Rapidash", 159: "Rattata", 160: "Raticate",
    161: "Nidorino", 162: "Nidorina", 163: "Geodude", 164: "Porygon",
    165: "Aerodactyl",
    167: "Magnemite",
    170: "Charmander", 171: "Charmeleon", 172: "Charizard",
    174: "Oddish", 175: "Gloom", 176: "Vileplume", 177: "Bellsprout",
    178: "Weepinbell", 179: "Victreebel",
    185: "MissingNo.",
}

# ── Move names (index → name, Gen 1) ───────────────────────────────────

MOVE_NAMES: dict[int, str] = {
    1: "Pound", 2: "Karate Chop", 3: "Double Slap", 4: "Comet Punch",
    5: "Mega Punch", 6: "Pay Day", 7: "Fire Punch", 8: "Ice Punch",
    9: "Thunder Punch", 10: "Scratch", 11: "Vice Grip", 12: "Guillotine",
    13: "Razor Wind", 14: "Swords Dance", 15: "Cut", 16: "Gust",
    17: "Wing Attack", 18: "Whirlwind", 19: "Fly", 20: "Bind",
    21: "Slam", 22: "Vine Whip", 23: "Stomp", 24: "Double Kick",
    25: "Mega Kick", 26: "Jump Kick", 27: "Rolling Kick", 28: "Sand Attack",
    29: "Headbutt", 30: "Horn Attack", 31: "Fury Attack", 32: "Horn Drill",
    33: "Tackle", 34: "Body Slam", 35: "Wrap", 36: "Take Down",
    37: "Thrash", 38: "Double-Edge", 39: "Tail Whip", 40: "Poison Sting",
    41: "Twineedle", 42: "Pin Missile", 43: "Leer", 44: "Bite",
    45: "Growl", 46: "Roar", 47: "Sing", 48: "Supersonic",
    49: "Sonic Boom", 50: "Disable", 51: "Acid", 52: "Ember",
    53: "Flamethrower", 54: "Mist", 55: "Water Gun", 56: "Hydro Pump",
    57: "Surf", 58: "Ice Beam", 59: "Blizzard", 60: "Psybeam",
    61: "Bubble Beam", 62: "Aurora Beam", 63: "Hyper Beam", 64: "Peck",
    65: "Drill Peck", 66: "Submission", 67: "Low Kick", 68: "Counter",
    69: "Seismic Toss", 70: "Strength", 71: "Absorb", 72: "Mega Drain",
    73: "Leech Seed", 74: "Growth", 75: "Razor Leaf", 76: "Solar Beam",
    77: "Poison Powder", 78: "Stun Spore", 79: "Sleep Powder", 80: "Petal Dance",
    81: "String Shot", 82: "Dragon Rage", 83: "Fire Spin", 84: "Thunder Shock",
    85: "Thunderbolt", 86: "Thunder Wave", 87: "Thunder", 88: "Rock Throw",
    89: "Earthquake", 90: "Fissure", 91: "Dig", 92: "Toxic",
    93: "Confusion", 94: "Psychic", 95: "Hypnosis", 96: "Meditate",
    97: "Agility", 98: "Quick Attack", 99: "Rage", 100: "Teleport",
    101: "Night Shade", 102: "Mimic", 103: "Screech", 104: "Double Team",
    105: "Recover", 106: "Harden", 107: "Minimize", 108: "Smokescreen",
    109: "Confuse Ray", 110: "Withdraw", 111: "Defense Curl", 112: "Barrier",
    113: "Light Screen", 114: "Haze", 115: "Reflect", 116: "Focus Energy",
    117: "Bide", 118: "Metronome", 119: "Mirror Move", 120: "Self-Destruct",
    121: "Egg Bomb", 122: "Lick", 123: "Smog", 124: "Sludge",
    125: "Bone Club", 126: "Fire Blast", 127: "Waterfall", 128: "Clamp",
    129: "Swift", 130: "Skull Bash", 131: "Spike Cannon", 132: "Constrict",
    133: "Amnesia", 134: "Kinesis", 135: "Soft-Boiled", 136: "Hi Jump Kick",
    137: "Glare", 138: "Dream Eater", 139: "Poison Gas", 140: "Barrage",
    141: "Leech Life", 142: "Lovely Kiss", 143: "Sky Attack", 144: "Transform",
    145: "Bubble", 146: "Dizzy Punch", 147: "Spore", 148: "Flash",
    149: "Psywave", 150: "Splash", 151: "Acid Armor", 152: "Crabhammer",
    153: "Explosion", 154: "Fury Swipes", 155: "Bonemerang", 156: "Rest",
    157: "Rock Slide", 158: "Hyper Fang", 159: "Sharpen", 160: "Conversion",
    161: "Tri Attack", 162: "Super Fang", 163: "Slash", 164: "Substitute",
    165: "Struggle",
}

# ── Type names (index → name, Gen 1) ───────────────────────────────────

TYPE_NAMES: dict[int, str] = {
    0: "Normal", 1: "Fighting", 2: "Flying", 3: "Poison",
    4: "Ground", 5: "Rock", 7: "Bug", 8: "Ghost",
    20: "Fire", 21: "Water", 22: "Grass", 23: "Electric",
    24: "Psychic", 25: "Ice", 26: "Dragon",
}

# ── Text decode ────────────────────────────────────────────────────────

def _decode_text(data: bytes, offset: int, max_len: int = 20) -> str:
    """Decode Pokémon Gen 1 text encoding from RAM bytes."""
    chars: list[str] = []
    for i in range(max_len):
        b = data[offset + i] if offset + i < len(data) else 0x50
        if b == 0x50:  # terminator
            break
        if 0x80 <= b <= 0x99:
            chars.append(chr(ord("A") + (b - 0x80)))
        elif 0xA0 <= b <= 0xB9:
            chars.append(chr(ord("a") + (b - 0xA0)))
        elif 0x00 <= b <= 0x09:
            chars.append(str(b))
        elif b == 0x4E:  # PK
            chars.append("PK")
        elif b == 0x54:  # POKé
            chars.append("POKé")
        elif b == 0x5E:  # ™
            chars.append("™")
        elif b == 0x6D:  # /
            chars.append("/")
        elif b == 0x6E:  # .
            chars.append(".")
        elif b == 0x7F:  # space
            chars.append(" ")
        elif 32 <= b < 127:
            chars.append(chr(b))
        else:
            chars.append(f"\\x{b:02x}")
    return "".join(chars)

MAP_NAMES: dict[int, str] = {
    0x00: "Pallet Town",
    0x01: "Viridian City",
    0x02: "Pewter City",
    0x03: "Cerulean City",
    0x04: "Lavender Town",
    0x05: "Vermilion City",
    0x06: "Celadon City",
    0x07: "Fuchsia City",
    0x08: "Cinnabar Island",
    0x09: "Indigo Plateau",
    0x0A: "Saffron City",
    0x0C: "Route 1",
    0x0D: "Route 2",
    0x0E: "Route 3",
    0x0F: "Route 4",
    0x10: "Route 5",
    0x11: "Route 6",
    0x12: "Route 7",
    0x13: "Route 8",
    0x14: "Route 9",
    0x15: "Route 10",
    0x16: "Route 11",
    0x17: "Route 12",
    0x18: "Route 13",
    0x19: "Route 14",
    0x1A: "Route 15",
    0x1B: "Route 16",
    0x1C: "Route 17",
    0x1D: "Route 18",
    0x1E: "Route 19",
    0x1F: "Route 20",
    0x20: "Route 21",
    0x21: "Route 22",
    0x22: "Route 23",
    0x23: "Route 24",
    0x24: "Route 25",
    # Interior maps
    0x25: "Red's House 1F",
    0x26: "Red's House 2F",
    0x27: "Blue's House",
    0x28: "Oak's Lab",
    0x29: "Viridian Pokémon Center",
    0x2A: "Viridian Mart",
    0x2B: "Viridian School",
    0x2C: "Viridian House",
    0x2D: "Pewter Pokémon Center",
    0x2E: "Pewter Mart",
    0x2F: "Pewter House 1",
    0x30: "Pewter House 2",
    0x31: "Cerulean Pokémon Center",
    0x32: "Cerulean Mart",
    0x33: "Cerulean House 1",
    0x34: "Cerulean House 2",
    0x35: "Lavender Pokémon Center",
    0x36: "Lavender Mart",
}


# ── RAMReader ─────────────────────────────────────────────────────────────


class RAMReader:
    """Read Pokémon Red/Blue game state from emulator RAM + ROM map data."""

    def __init__(self, emulator: Any, rom_path: str | Path) -> None:
        """*emulator* is the Emulator instance (has working read_u8/read_u16).
        *rom_path* is the path to the .gb ROM file on disk.
        """
        self._emu = emulator
        self._mapdb = _MapDB(rom_path)

    # ── Low-level memory reads ───────────────────────────────────────

    def read_u8(self, addr: int) -> int:
        return self._emu.read_u8(addr)  # type: ignore[no-any-return]

    def read_u16(self, addr: int) -> int:
        return self._emu.read_u16(addr)  # type: ignore[no-any-return]

    # ── Player state ────────────────────────────────────────────────

    def player_x(self) -> int:
        """Player X in map block coordinates (0-indexed, border offset removed)."""
        return self.read_u8(ADDR_X_COORD) - 4

    def player_y(self) -> int:
        """Player Y in map block coordinates (0-indexed, border offset removed)."""
        return self.read_u8(ADDR_Y_COORD) - 4

    def player_facing(self) -> str:
        facing = self.read_u8(ADDR_SPRITE_STATE_DATA + 9) & 0x0C
        return FACING_DIRECTIONS.get(facing, "down")

    def is_moving(self) -> bool:
        return self.read_u8(ADDR_WALK_COUNTER) != 0

    def current_map_id(self) -> int:
        return self.read_u8(ADDR_CUR_MAP)

    def current_map_name(self) -> str:
        mid = self.current_map_id()
        return MAP_NAMES.get(mid, f"Map_{mid:02X}")

    # ── Screen type ──────────────────────────────────────────────────

    def screen_type(self) -> str:
        battle = self.read_u8(ADDR_IS_IN_BATTLE)
        if battle != 0:
            return SCREEN_BATTLE

        text_frame = self.read_u8(ADDR_TEXT_BOX_FRAME)
        if text_frame != 0:
            return SCREEN_DIALOG

        naming_state = self.read_u8(ADDR_NAMING_SCREEN)
        if naming_state != 0:
            return SCREEN_NAME_ENTRY

        return SCREEN_OVERWORLD

    # ── Map / minimap ────────────────────────────────────────────────

    def _get_map_info(self) -> dict[str, Any] | None:
        """Get parsed map data for the current map."""
        mid = self.current_map_id()
        return self._mapdb.get_map(mid)

    def overworld_grid(self) -> str:
        """Alias for :meth:`render_overworld`."""
        return self.render_overworld()

    def build_minimap(self, radius: int = 3) -> str:
        """Build an ASCII minimap centred on the player using ROM block data.

        Returns a compact text grid where each cell represents a 2×2 tile
        metatile block, classified as floor, wall, stairs, etc.

        Example output for Red's House 2F (4×4 room)::

            ██  ██  ██  ██
            ··  ··  ··  ··
            ··  ⇩⇩  ··  ··
            ██  ··  ··  ◈◈
        """
        mid = self.current_map_id()
        info = self._mapdb.get_map(mid)
        if info is None:
            return f"[No map data for map {mid:#04x}]"

        w, h = info["width"], info["height"]
        tileset = info["tileset"]
        block_data = info["block_data"]
        px, py = self.player_x(), self.player_y()

        # Clamp player position to map bounds for display
        # (during transitions coords may be out of bounds)
        cpx = max(0, min(px, w - 1))
        cpy = max(0, min(py, h - 1))

        # Build minimap rows
        lines: list[str] = []
        r_start = max(0, cpy - radius)
        r_end = min(h, cpy + radius + 1)
        c_start = max(0, cpx - radius)
        c_end = min(w, cpx + radius + 1)

        # If player is outside map bounds, add a header note
        if px < 0 or px >= w or py < 0 or py >= h:
            lines.append(f"[Player at ({px},{py}) is outside {w}×{h} map]")

        for y in range(r_start, r_end):
            row_parts: list[str] = []
            for x in range(c_start, c_end):
                if x == px and y == py:
                    row_parts.append(BLOCK_SYMBOLS["player"])
                else:
                    block_id = block_data[y * w + x]
                    classification = self._mapdb.classify_block(block_id, tileset)
                    row_parts.append(BLOCK_SYMBOLS.get(classification, "??"))
            lines.append("".join(row_parts))

        return "\n".join(lines)

    def render_overworld(self) -> str:
        """Render a compact 5×5 text grid using single-letter symbols.

        Centres the grid on the player's block position (wXCoord-4, wYCoord-4).
        The player is shown as ``@`` and the block the player faces is an arrow
        (``↑↓←→``). Out-of-bounds cells are ``?``.

        Example output::

            Map: Pallet Town (10×9)
            Pos: (5,4) Facing: South ↓

             .  .  .  G  G
             .  .  @  G  G
             .  .  ↓  .  .
             B  B  .  S  .
             .  .  .  .  .
        """
        mid = self.current_map_id()
        info = self._mapdb.get_map(mid)
        if info is None:
            return f"[No map data for map {mid:#04x}]"

        w, h = info["width"], info["height"]
        tileset = info["tileset"]
        block_data = info["block_data"]
        px, py = self.player_x(), self.player_y()
        facing = self.player_facing()
        mname = self.current_map_name()
        arrow = FACING_ARROWS.get(facing, "?")

        lines = [
            f"Map: {mname} ({w}×{h})",
            f"Pos: ({px},{py}) Facing: {facing.capitalize()} {arrow}",
            "",
        ]

        # Build 5×5 grid rows (dy=-2..2, dx=-2..2)
        for dy in range(-2, 3):
            row_parts: list[str] = []
            for dx in range(-2, 3):
                gx, gy = px + dx, py + dy

                # Player's own cell
                if dx == 0 and dy == 0:
                    row_parts.append("@")
                    continue

                # Cell the player is facing
                if (
                    (dx == 0 and dy == -1 and facing == "up")
                    or (dx == 0 and dy == 1 and facing == "down")
                    or (dx == -1 and dy == 0 and facing == "left")
                    or (dx == 1 and dy == 0 and facing == "right")
                ):
                    row_parts.append(arrow)
                    continue

                # Out of bounds
                if not (0 <= gx < w and 0 <= gy < h):
                    row_parts.append("?")
                    continue

                # Classify the block and map to a single letter
                block_id = block_data[gy * w + gx]
                classification = self._mapdb.classify_block(block_id, tileset)
                row_parts.append(CLASS_SYMBOLS.get(classification, "?"))

            lines.append(" ".join(row_parts))

        lines.append("")
        legend_parts = [
            "Legend: ",
            ".=floor ", "G=grass ", "T=tree ", "W=water ",
            "B=wall ", "S=sign/object ", "D=door ", "@=you",
        ]
        lines.append("".join(legend_parts))
        return "\n".join(lines)

    def adjacent_blocks(self) -> dict[str, str]:
        """What's adjacent to the player in each cardinal direction.

        Reads ROM block data (not screen tiles) for 100% accuracy.
        """
        mid = self.current_map_id()
        info = self._mapdb.get_map(mid)
        if info is None:
            return {"up": "unknown", "down": "unknown",
                    "left": "unknown", "right": "unknown"}

        w, h = info["width"], info["height"]
        tileset = info["tileset"]
        px, py = self.player_x(), self.player_y()

        offsets = {"up": (0, -1), "down": (0, 1),
                    "left": (-1, 0), "right": (1, 0)}

        result: dict[str, str] = {}
        for direction, (dx, dy) in offsets.items():
            nx, ny = px + dx, py + dy
            if 0 <= nx < w and 0 <= ny < h:
                block_id = info["block_data"][ny * w + nx]
                result[direction] = self._mapdb.classify_block(block_id, tileset)
            else:
                result[direction] = "void"  # map edge / connection

        return result

    def _pokemon_name(self, species_id: int) -> str:
        """Look up a Pokémon species name by internal ID."""
        return POKEMON_NAMES.get(species_id, f"#{species_id}")

    def _move_name(self, move_id: int) -> str:
        """Look up a move name by internal ID."""
        return MOVE_NAMES.get(move_id, f"Move#{move_id}")

    def _type_name(self, type_id: int) -> str:
        """Look up a type name by internal ID."""
        return TYPE_NAMES.get(type_id, f"Type#{type_id}")

    # ── Battle state ──────────────────────────────────────────────────

    def read_battle_state(self) -> dict[str, Any]:
        """Read full battle state from RAM. Returns structured dict for LLM consumption."""
        bt = self.read_u8(ADDR_BATTLE_TYPE)
        is_trainer = bt == 2

        # Player mon
        pspecies = self.read_u8(ADDR_BATTLE_MON_SPECIES)
        php = self.read_u16(ADDR_BATTLE_MON_HP)
        pmaxhp = self.read_u16(ADDR_BATTLE_MON_MAX_HP)
        plevel = self.read_u8(ADDR_BATTLE_MON_LEVEL)
        patk = self.read_u16(ADDR_BATTLE_MON_ATTACK)
        pdef = self.read_u16(ADDR_BATTLE_MON_DEFENSE)
        pspd = self.read_u16(ADDR_BATTLE_MON_SPEED)
        pspc = self.read_u16(ADDR_BATTLE_MON_SPECIAL)
        pstatus = self.read_u8(ADDR_BATTLE_MON_STATUS)
        ptype1 = self.read_u8(ADDR_BATTLE_MON_TYPE1)
        ptype2 = self.read_u8(ADDR_BATTLE_MON_TYPE2)

        pmoves: list[dict[str, Any]] = []
        for i in range(4):
            mid = self.read_u8(ADDR_BATTLE_MON_MOVES + i)
            pp = self.read_u8(ADDR_BATTLE_MON_PP + i)
            if mid != 0:
                pmoves.append({"name": self._move_name(mid),
                               "pp": pp, "slot": i + 1})

        # Enemy mon
        espec = self.read_u8(ADDR_ENEMY_MON_SPECIES)
        ehp = self.read_u16(ADDR_ENEMY_MON_HP)
        emaxhp = self.read_u16(ADDR_ENEMY_MON_MAX_HP)
        elevel = self.read_u8(ADDR_ENEMY_MON_LEVEL)
        eatk = self.read_u16(ADDR_ENEMY_MON_ATTACK)
        edef = self.read_u16(ADDR_ENEMY_MON_DEFENSE)
        espd = self.read_u16(ADDR_ENEMY_MON_SPEED)
        espc = self.read_u16(ADDR_ENEMY_MON_SPECIAL)
        etype1 = self.read_u8(ADDR_ENEMY_MON_TYPE1)
        etype2 = self.read_u8(ADDR_ENEMY_MON_TYPE2)

        phpct = round(php / max(pmaxhp, 1) * 100)
        ehpct = round(ehp / max(emaxhp, 1) * 100)

        return {
            "battle_type": "trainer" if is_trainer else "wild",
            "player": {
                "name": self._pokemon_name(pspecies),
                "hp": php,
                "max_hp": pmaxhp,
                "hp_pct": phpct,
                "level": plevel,
                "attack": patk,
                "defense": pdef,
                "speed": pspd,
                "special": pspc,
                "status": pstatus,
                "type": f"{self._type_name(ptype1)}/{self._type_name(ptype2)}" if ptype2 != ptype1 else self._type_name(ptype1),
                "moves": pmoves,
            },
            "enemy": {
                "name": self._pokemon_name(espec),
                "hp": ehp,
                "max_hp": emaxhp,
                "hp_pct": ehpct,
                "level": elevel,
                "attack": eatk,
                "defense": edef,
                "speed": espd,
                "special": espc,
                "type": f"{self._type_name(etype1)}/{self._type_name(etype2)}" if etype2 != etype1 else self._type_name(etype1),
            },
        }

    def render_battle(self) -> str:
        """Render a compact text battle state for the LLM."""
        bs = self.read_battle_state()
        p = bs["player"]
        e = bs["enemy"]
        moves_str = " | ".join(f"{i+1}:{m['name']}({m['pp']}PP)" for i, m in enumerate(p["moves"]))

        return (
            f"⚔ BATTLE: {'Trainer' if bs['battle_type']=='trainer' else 'Wild'} {e['name']}\n"
            f"  Your {p['name']} Lv{p['level']} | HP:{p['hp_pct']}% ({p['hp']}/{p['max_hp']}) | {p['type']}\n"
            f"  Enemy {e['name']} Lv{e['level']} | HP:{e['hp_pct']}% ({e['hp']}/{e['max_hp']}) | {e['type']}\n"
            f"  Moves: {moves_str or 'None'}\n"
            f"  Options: FIGHT BAG PKMN RUN"
        )

    # ── Dialog / text ─────────────────────────────────────────────────

    def read_dialog_text(self) -> str:
        """Read the current text box content from RAM (wStringBuffer + surrounding area)."""
        # Build a buffer from consecutive u8 reads at the text region
        buf = bytes(self.read_u8(ADDR_STRING_BUFFER + i) for i in range(60))
        text = _decode_text(buf, 0, 20)
        # If wStringBuffer is empty, try wTextScrollPrompt region
        if len(text) < 3:
            buf2 = bytes(self.read_u8(ADDR_TEXT_PROMPT + i) for i in range(60))
            text = _decode_text(buf2, 0, 40)
        return text

    def render_dialog(self) -> str:
        """Render dialog text for the LLM."""
        text = self.read_dialog_text()
        # Check if it's a yes/no prompt
        yn_detected = any(phrase in text.upper() for phrase in ["YES", "NO", "YES/NO"])
        hint = " (Yes/No choice expected)" if yn_detected else " (Press A to continue)"
        return f"💬 DIALOG{hint}:\n  \"{text}\""

    # ── Menu state ─────────────────────────────────────────────────────

    def read_menu_state(self) -> dict[str, Any]:
        """Read current menu state from RAM. Returns empty menu if none active."""
        cur = self.read_u8(ADDR_CURRENT_MENU_ITEM)
        max_item = self.read_u8(ADDR_MAX_MENU_ITEM)
        menu_id = self.read_u8(ADDR_LIST_MENU_ID)
        y = self.read_u8(ADDR_TOP_MENU_ITEM_Y)
        x = self.read_u8(ADDR_TOP_MENU_ITEM_X)

        # Guard: only report menu when one is actually active.
        # wListMenuID is zeroed when no menu is on screen.
        if menu_id == 0:
            return {"menu_id": 0, "current_item": 0, "num_items": 0, "cursor_pos": (0, 0)}

        return {
            "menu_id": menu_id,
            "current_item": cur,
            "num_items": max_item + 1 if max_item > 0 else 0,
            "cursor_pos": (x, y),
            "active": True,
        }

    def render_menu(self) -> str:
        """Render menu state for the LLM."""
        ms = self.read_menu_state()
        items = ms["num_items"]
        cur = ms["current_item"]

        # Build a simple numbered list
        lines = ["📋 MENU:"]
        for i in range(items):
            marker = "→" if i == cur else " "
            lines.append(f"  {marker} [{i+1}]")
        lines.append("  Use UP/DOWN to navigate, A to select, B to cancel")
        return "\n".join(lines)

    # ── Name entry ─────────────────────────────────────────────────────

    def read_name_entry(self) -> dict[str, Any]:
        """Read name entry screen state from RAM."""
        name_len = self.read_u8(ADDR_NAMING_NAME_LENGTH)
        submit = self.read_u8(ADDR_NAMING_SUBMIT)
        case = self.read_u8(ADDR_ALPHABET_CASE)  # 0=upper, 1=lower
        letter = self.read_u8(ADDR_NAMING_LETTER)

        # Read current name from string buffer
        name_buf = bytes(self.read_u8(ADDR_STRING_BUFFER + i) for i in range(20))
        name = _decode_text(name_buf, 0, 11)

        # Keyboard grid: the naming screen has a 9-wide grid.
        # Rows from top: uppercase, lowercase, numerals, symbols/misc
        # These are embedded in VRAM tile map, but we can approximate.
        grid_rows = [
            ["A", "B", "C", "D", "E", "F", "G", "H", "I"],
            ["J", "K", "L", "M", "N", "O", "P", "Q", "R"],
            ["S", "T", "U", "V", "W", "X", "Y", "Z", " "],
            ["a", "b", "c", "d", "e", "f", "g", "h", "i"],
            ["j", "k", "l", "m", "n", "o", "p", "q", "r"],
            ["s", "t", "u", "v", "w", "x", "y", "z", " "],
            ["0", "1", "2", "3", "4", "5", "6", "7", "8"],
            ["9", "!", "?", "♂", "♀", "/", "-", ".", ","],
            ["(", ")", "ED", "PK", "MN", "×", ";", ":", "["],
            ["]", "…", "up", "lo", "DEL", "END", " ", " ", " "],
        ]
        # Determine which row set we're in based on case + section
        row_offset = 0 if case == 0 else 3  # uppercase vs lowercase rows
        if letter == 2:  # numerals
            row_offset = 6
        elif letter == 3:  # symbols
            row_offset = 8

        return {
            "screen": "name_entry",
            "name_so_far": name,
            "length": name_len,
            "case": "UPPER" if case == 0 else "lower",
            "ready_to_submit": submit != 0,
            "grid_rows": grid_rows[row_offset:row_offset + 2],
        }

    def render_name_entry(self) -> str:
        """Render name entry state for the LLM."""
        ne = self.read_name_entry()
        rows = ne["grid_rows"]
        grid_str = "\n".join(f"    {' '.join(r)}" for r in rows)

        return (
            f"⌨ NAME ENTRY: \"{ne['name_so_far']}\" ({ne['length']} chars)\n"
            f"  Case: {ne['case']} | {'READY to submit' if ne['ready_to_submit'] else 'still editing'}\n"
            f"  Keyboard:\n{grid_str}\n"
            f"  Use D-pad to move cursor, A to select letter, START to confirm"
        )

    # ── Full observation ─────────────────────────────────────────────

    def observe(self) -> dict[str, Any]:
        """Produce a structured observation matching the cartographer's JSON schema.

        Drop-in replacement for the vision model's output.
        """
        st = self.screen_type()
        mid = self.current_map_id()
        mname = self.current_map_name()
        px, py = self.player_x(), self.player_y()
        facing = self.player_facing()

        obs: dict[str, Any] = {
            "result": st,
            "player_facing": facing,
            "player_x": px,
            "player_y": py,
            "map_id": mid,
            "map_name": mname,
            "adjacent": {},
            "minimap": "",
            "overworld_grid": "",
            "visible_exits": [],
            "text_content": [],
            "menu_items": [],
            "keyboard_grid": {},
            "name_field": "",
            "suggested_action": "",
            # New structured fields for LLM-friendly rendering
            "render": "",             # pre-formatted text for the LLM
            "battle_state": {},       # populated when in battle
            "menu_state": {},         # populated when in menu
        }

        info = self._get_map_info()
        if info:
            obs["map_dimensions"] = f"{info['width']}×{info['height']}"
            obs["map_tileset"] = info["tileset"]

        if st == SCREEN_BATTLE:
            obs["suggested_action"] = "choose a battle action"
            obs["battle_state"] = self.read_battle_state()
            obs["render"] = self.render_battle()
        elif st == SCREEN_DIALOG:
            obs["suggested_action"] = "advance the dialogue"
            obs["text_content"] = [self.read_dialog_text()]
            obs["render"] = self.render_dialog()
        elif st == SCREEN_NAME_ENTRY:
            ne = self.read_name_entry()
            obs["name_field"] = ne["name_so_far"]
            obs["keyboard_grid"] = {"rows": ne["grid_rows"]}
            obs["render"] = self.render_name_entry()
            obs["suggested_action"] = "enter a name and press START"
        elif st == SCREEN_OVERWORLD:
            obs["adjacent"] = self.adjacent_blocks()
            obs["minimap"] = self.build_minimap(radius=2)
            obs["overworld_grid"] = self.render_overworld()
            obs["render"] = self.render_overworld()
            obs["suggested_action"] = "explore the area"
            # Highlight non-floor adjacent tiles as potential exits
            adj = obs["adjacent"]
            exits = [d for d, t in adj.items()
                      if t in ("stairs", "door", "warp")]
            if exits:
                obs["visible_exits"] = exits
                obs["suggested_action"] = f"explore: exits at {', '.join(exits)}"
        # Also check menu-like overlay states
        menu_data = self.read_menu_state()
        if menu_data["num_items"] > 0:
            obs["menu_state"] = menu_data
            obs["menu_items"] = [f"Item {i}" for i in range(menu_data["num_items"])]
            # If we're in menu mode but screen_type says overworld, we're in start/menu overlay
            if st == SCREEN_OVERWORLD and menu_data["num_items"] >= 2:
                obs["render"] = obs.get("render", "") + "\n" + self.render_menu()

        return obs
