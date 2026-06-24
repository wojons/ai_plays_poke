"""
Rich symbol system for the AI Plays Pokémon world state.

Two symbol sets:
- EMOJI: used in file storage and vision model output (rich, unambiguous)
- ASCII_COMPOSED: compact grid chars for the non-vision controller (LLM-friendly)

The vision model maps screenshots → emoji tiles.
The map integrator stores emoji tiles, renders ASCII for the controller.
"""

# ── Terrain symbols ────────────────────────────────────────────────────────

TERRAIN_EMOJI: dict[str, str] = {
    "?": "❓",   # unknown / never seen
    ".": "⬜",   # normal walkable floor/path/road (interior)
    "g": "🌿",   # tall grass
    "G": "🌾",   # tall grass (dark grass / gen3 variant)
    "T": "🌲",   # tree
    "#": "🧱",   # wall / building / cliff / solid
    "~": "🌊",   # water
    "=": "🌉",   # bridge / plank road
    "^": "⬆️",    # north ledge (one-way down from north)
    "v": "⬇️",    # south ledge (one-way down from south)
    "<": "⬅️",    # west ledge (one-way)
    ">": "➡️",    # east ledge (one-way)
    ":": "🪨",   # cave / rocky floor
    "s": "🏖️",    # sand
    "i": "🧊",   # ice
    "f": "🔥",   # fire / lava / dangerous floor
    "d": "🚪",   # door tile (walkable, triggers warp)
    "S": "🪜",   # stairs / ladder
    "p": "🟫",   # path / cobblestone
}

TERRAIN_ASCII: dict[str, str] = {
    "?": "?",
    ".": ".",
    "g": "g",
    "G": "G",
    "T": "T",
    "#": "#",
    "~": "~",
    "=": "=",
    "^": "^",
    "v": "v",
    "<": "<",
    ">": ">",
    ":": ":",
    "s": "s",
    "i": "i",
    "f": "f",
    "d": "D",
    "S": "S",
    "p": ".",
}

# ── Object symbols ─────────────────────────────────────────────────────────

OBJECT_EMOJI: dict[str, str] = {
    "D": "🚪",   # door / warp point
    "S": "🪧",   # sign / readable
    "C": "🪑",   # counter / desk
    "I": "💎",   # item ball / pickup
    "B": "🪨",   # boulder / rock (strength)
    "M": "🖥️",    # machine / computer
    "H": "🏥",   # healing machine
    "F": "🚧",   # fence / rail / barrier
    "N": "📺",   # TV / screen
    "P": "🪴",   # plant / decoration
    "B": "📚",   # bookshelf
    "R": "🪑",   # chair
    "T": "🪜",   # table
    "X": "❌",   # cut tree (HM01)
    "Y": "🧱",   # breakable rock (HM06)
}

OBJECT_ASCII: dict[str, str] = {
    "D": "D",
    "S": "S",
    "C": "C",
    "I": "I",
    "B": "B",
    "M": "M",
    "H": "H",
    "F": "F",
    "N": "N",
    "P": "P",
    "B": "B",
    "R": "R",
    "T": "T",
    "X": "X",
    "Y": "Y",
}

# ── Actor symbols ───────────────────────────────────────────────────────────

ACTOR_EMOJI: dict[str, str] = {
    "u": "👤",          # unknown person
    "n": "👩‍⚕️",         # nurse Joy
    "o": "👮",          # officer Jenny
    "m": "🏪",          # mart clerk
    "p": "👨‍🔬",          # professor
    "r": "🧑‍🔬",          # rival
    "t": "🧒",          # trainer / youngster
    "T": "🧑",          # trainer (generic)
    "b": "🚴",          # biker
    "l": "🧑‍🎤",          # lass
    "h": "🧗",          # hiker
    "g": "🧓",          # gentleman / old man
    "s": "🏊",          # swimmer
    "f": "🎣",          # fisherman
    "c": "🧑‍💻",          # cooltrainer
    "e": "🧑‍🔧",          # engineer / worker
    "k": "🦹",          # team rocket grunt
    "K": "🦹‍♂️",          # team rocket boss
    "P": "🧬",          # Pokémon (wild / overworld)
    "R": "🧬",          # rare / legendary Pokémon
    "x": "❓",          # unknown entity (could be anything)
}

ACTOR_ASCII: dict[str, str] = {
    "u": "u",
    "n": "N",
    "o": "O",
    "m": "M",
    "p": "P",
    "r": "R",
    "t": "t",
    "T": "T",
    "b": "b",
    "l": "l",
    "h": "h",
    "g": "g",
    "s": "s",
    "f": "f",
    "c": "c",
    "e": "e",
    "k": "k",
    "K": "K",
    "P": "P",
    "R": "R",
    "x": "x",
}

# ── Player / mode symbols ──────────────────────────────────────────────────

PLAYER_FACING_EMOJI: dict[str, str] = {
    "N": "⬆️",
    "S": "⬇️",
    "E": "➡️",
    "W": "⬅️",
}

PLAYER_FACING_ASCII: dict[str, str] = {
    "N": "^",
    "S": "v",
    "E": ">",
    "W": "<",
}

MODE_EMOJI: dict[str, str] = {
    "walk": "🚶",
    "bike": "🚲",
    "surf": "🏄",
    "menu": "📋",
    "battle": "⚔️",
    "dialog": "💬",
    "cutscene": "🎬",
    "unknown": "❓",
}

# ── Lighting / visibility ──────────────────────────────────────────────────

LIGHTING_EMOJI: dict[str, str] = {
    "normal": "☀️",
    "dark": "🌑",
    "flash": "🔦",
    "indoor": "💡",
    "cave": "🕯️",
    "unknown": "❓",
}

# ── Movement edge symbols ──────────────────────────────────────────────────

EDGE_OUTCOME_EMOJI: dict[str, str] = {
    "open": "✅",
    "blocked": "🚫",
    "one_way_ledge": "⏬",
    "warp": "🚪",
    "npc_block": "👤",
    "water_edge": "🌊",
    "unknown": "❓",
}

# ── Visited symbols ─────────────────────────────────────────────────────────

VISITED_EMOJI: dict[str, str] = {
    "?": "⬛",    # never seen
    ".": "⬜",    # seen but never stood on
    "+": "👣",    # player has stood here
    "@": "🎯",    # current position
}

VISITED_ASCII: dict[str, str] = {
    "?": "?",
    ".": ".",
    "+": "+",
    "@": "@",
}

# ── Composers ───────────────────────────────────────────────────────────────

def terrain_to_emoji(char: str) -> str:
    """Convert single terrain char to emoji."""
    return TERRAIN_EMOJI.get(char, "❓")

def terrain_to_ascii(char: str) -> str:
    """Convert single terrain char to ASCII (identity for grid rendering)."""
    return TERRAIN_ASCII.get(char, char)

def object_to_emoji(char: str) -> str:
    """Convert single object char to emoji."""
    if char == " ":
        return "  "  # double-width spacer so emoji grids align
    return OBJECT_EMOJI.get(char, "❓")

def object_to_ascii(char: str) -> str:
    """Convert single object char to ASCII."""
    if char == " ":
        return " "
    return OBJECT_ASCII.get(char, char)

def actor_to_emoji(kind: str) -> str:
    """Convert actor kind string to emoji."""
    return ACTOR_EMOJI.get(kind, "👤")

def actor_to_ascii(kind: str) -> str:
    """Convert actor kind string to compact ASCII."""
    return ACTOR_ASCII.get(kind, kind[:1] if kind else "?")

def facing_emoji(direction: str) -> str:
    """Player facing direction → emoji arrow."""
    return PLAYER_FACING_EMOJI.get(direction, "❓")

def facing_ascii(direction: str) -> str:
    """Player facing direction → ASCII arrow."""
    return PLAYER_FACING_ASCII.get(direction, "?")

def mode_emoji(mode: str) -> str:
    """Game mode → emoji."""
    return MODE_EMOJI.get(mode, "❓")

def edge_emoji(outcome: str) -> str:
    """Movement edge outcome → emoji."""
    return EDGE_OUTCOME_EMOJI.get(outcome, "❓")

def visited_emoji(state: str) -> str:
    """Visited state → emoji."""
    return VISITED_EMOJI.get(state, "⬛")

def visited_ascii(state: str) -> str:
    """Visited state → ASCII."""
    return VISITED_ASCII.get(state, "?")

# ── Rich tile description ───────────────────────────────────────────────────

def describe_tile(terrain: str, obj: str = " ", actor_kind: str = "") -> str:
    """Build a rich textual description of a tile for the vision model."""
    parts = [terrain_to_emoji(terrain)]
    if obj and obj != " ":
        parts.append(object_to_emoji(obj))
    if actor_kind:
        parts.append(actor_to_emoji(actor_kind))
    return " ".join(parts)

# ── Symbol table for prompts ────────────────────────────────────────────────

SYMBOL_REFERENCE = """
TERRAIN SYMBOLS (use these in terrain.map patches):
  ? = ❓ unknown/never seen
  . = ⬜ walkable floor/path
  g = 🌿 tall grass
  G = 🌾 dark grass
  T = 🌲 tree
  # = 🧱 wall/building/cliff
  ~ = 🌊 water
  = = 🌉 bridge
  ^ = ⬆️ north ledge (one-way)
  v = ⬇️ south ledge (one-way)
  < = ⬅️ west ledge (one-way)
  > = ➡️ east ledge (one-way)
  : = 🪨 cave floor
  s = 🏖️ sand
  i = 🧊 ice
  f = 🔥 fire/lava
  d = 🚪 door/warp tile
  S = 🪜 stairs/ladder
  p = 🟫 path/cobblestone

OBJECT SYMBOLS (use in objects.map patches):
  (space) = no object
  D = 🚪 door/warp
  S = 🪧 sign
  C = 🪑 counter
  I = 💎 item ball
  B = 🪨 boulder
  M = 🖥️ machine
  H = 🏥 heal machine
  F = 🚧 fence
  N = 📺 TV/screen

ACTOR KINDS (use in actor_updates):
  u = 👤 unknown person
  n = 👩‍⚕️ nurse
  o = 👮 officer
  m = 🏪 mart clerk
  p = 👨‍🔬 professor
  r = 🧑‍🔬 rival
  t = 🧒 trainer
  T = 🧑 trainer (generic)
  b = 🚴 biker
  l = 🧑‍🎤 lass
  h = 🧗 hiker
  g = 🧓 gentleman
  s = 🏊 swimmer
  f = 🎣 fisherman
  c = 🧑‍💻 cooltrainer
  e = 🧑‍🔧 engineer
  k = 🦹 rocket grunt
  K = 🦹‍♂️ rocket boss
  P = 🧬 wild Pokémon
  x = ❓ unknown entity
"""
