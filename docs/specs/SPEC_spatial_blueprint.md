# SPEC — Spatial Blueprint (shared by RAM and Vision)

**Status:** draft, authored 2026-09-28
**Supersedes:** the `adjacent_tiles` word-vocabulary in `src/core/vision.py`

## Why this exists

The agent receives two descriptions of the same room and they cannot be compared:

| | RAM reader | Vision model |
|---|---|---|
| What it covers | a 5x5 window around the player | the 4 tiles touching the player |
| Vocabulary | symbols `. B S D ↑↓←→` | words `wall, stairs, path, grass, bed, pc, plant` |
| Dimensions | stated (`Map: X (4x4)`) | never stated |
| Floor | one symbol for every floor | `path` / `grass` / `empty` — several words |
| Objects | one catch-all `S` | free-form words, no ids |
| Unknown | `?` | not represented (silently omitted) |

Consequence, observed live: the reader called the block **north of the bedroom spawn**
`stairs` and told the agent `explore: exits at up`. That block is the television. The
vision model, looking at the *same frame*, correctly saw a TV and a staircase in the
north-east corner. Neither description could correct the other, because they share no
vocabulary and cover different areas.

**A blueprint fixes this by making both channels emit the same grid.**

## The blueprint

One observation of a space is a **grid of W x H cells**, always stating its dimensions.

```
Space: <name or "unidentified"> (<W>x<H>)
Origin: (<ox>,<oy>)        # cell (0,0) of this grid in world terms
Pos: (<px>,<py>) Facing: <direction> <arrow>

<H rows, each W characters>

Legend:
  .  = floor (any floor)
  B  = blocking structure
  ?  = not determinable
  ←↑↓→ = the player (position and facing)
Objects:
  1 = <name>
  2 = <name>
```

### Symbol rules

1. **`.` = floor, without exception.** Every walkable ground surface renders as `.` —
   plain tile, patterned tile, carpet, grass, sand, doorway threshold, the mat inside a
   door. The agent must never need to learn a new symbol because a room has new carpet.
   *Different floor types are still floor.*
2. **`B` = blocking structure.** Walls, fences, counters, and furniture that stops
   movement. Appearance only — see rule 6.
3. **`←↑↓→` = the player**, drawn at the player's own cell. The arrow carries both
   position and facing in one glyph, and the cell is **not** overwritten by whatever the
   player stands on, so nothing is hidden. (This replaces the older `@` marker, which
   needed a second character to show facing and masked the tile in front.)
4. **Objects are numbered.** `1`-`9`, then `A`-`Z` if a space is crowded. The number is a
   *placeholder id*; the **legend is the authority** on what it means, and the legend is
   emitted with every grid. Never assume `1` is the same thing in two observations.
5. **`?` = not determinable.** Occluded, off-screen, or unreadable. A channel that cannot
   see a cell says `?`; it never guesses and never omits the cell. `?` is information:
   it marks exactly where the description is blind, which is what tells the agent where
   to spend an exploratory move.
6. **Walkability is never inferred from appearance.** By either channel. That an object
   looks like stairs, or looks like an open path, says nothing about whether the game
   will let the player step there. Walkability comes only from the game's own collision
   data (RAM: `adjacent_walkability`, backed by the ROM metatile collision table).
   *See the defect this rule exists to prevent, below.*
7. **Parity.** When both channels render the same space they must use the same
   dimensions and the same origin, so cell `(i,j)` in one can be compared directly with
   cell `(i,j)` in the other. Any disagreement is then a **finding**, not a formatting
   difference.

### Object naming

Objects get a number and, if the channel can name it, a name:

- RAM's block table currently classifies furniture as the generic `object` — it can assign
  the number but often cannot name it, and must then write `object (unnamed)` rather than
  invent a name.
- Vision can usually name it (`television`, `bed`, `potted plant`, `staircase`).
- The union of the two legends is what the agent learns from. A number named by vision and
  left unnamed by RAM is exactly the gap worth closing in RAM's block table.

### The defect these rules prevent

`ram_reader.py` derived `visible_exits` from the **terrain label alone**:

```python
exits = [d for d, t in adj.items() if t in ("stairs", "door", "warp")]
```

A hand-written table maps block `0x0D` (tileset 4) to `"stairs"`; the block north of the
bedroom spawn holds the television and is `0x0D`. So the reader announced
`visible_exits: ["up"]` and `explore: exits at up` while its own next field,
`adjacent_walkability`, reported the same cell `blocked` — and pressing into it does
nothing. The agent was advised to walk into a television.

An exit must satisfy **both**: labelled like a passage *and* reported walkable by
collision data. Rule 6 is the general form; this was the specific case.

## Where it lives

| Piece | Path |
|---|---|
| This spec | `docs/specs/SPEC_spatial_blueprint.md` |
| Vision prompt implementing it | `prompts/exploration/vision_map_blueprint.md` |
| RAM renderer (already conforms) | `src/core/ram_reader.py::render_overworld` |
