# Vision prompt — spatial blueprint

Give this to the vision model for every overworld frame. It implements
`docs/specs/SPEC_spatial_blueprint.md`, so the returned grid is directly comparable,
cell for cell, with the RAM reader's `overworld_grid`.

---

You are reading a single Game Boy screen (Pokémon, Generation I) and returning a spatial
map of it. Return ONLY a JSON object. No prose, no markdown fences.

## The geometry of the image — measured on real frames, not assumed

- The image is exactly **160 x 144 pixels**: the whole Game Boy screen, edge to edge.
- The game's own coordinate unit is **16 x 16 pixels** (this is the unit the game counts
  positions in). So the screen is **10 cells across by 9 cells down**.
- Below that, the artwork repeats every **8 x 8 pixels** — do not use 8 px as your cell,
  use the game's 16 px unit, or your grid will be twice as wide as it should be.
- The player's sprite is **16 x 16 pixels** — exactly one cell.
- **The map is often SMALLER than the screen.** When it is, the camera stops scrolling and
  the leftover screen area is filled with **black**. When the map is larger than the
  screen the camera keeps the player centred while it can.
- So: **never assume the player is centred.** Find the sprite and report where it actually
  is. On a small map it will be off-centre and there will be black around it.

Draw the grid over the whole screen: **10 columns by 9 rows**. Report it at that size every
time, so the same frame always produces the same shape of answer.


## How to draw each cell — one character per block

- `.` — **floor you can positively see**. Walkable ground: plain tiles, patterned tiles,
  carpet... **Different floor types are still floor and always `.`**. Only use `.` when
  you can actually see floor tiles there.
- `B` — **blocking structure**: wall, fence, counter, or furniture that stands in the way.
- `↑` `↓` `←` `→` — **the player**, in the player's own cell, pointing where they face.
  Exactly one cell has an arrow.
- `?` — **anything you cannot positively identify.** Black areas. Dark areas. Anything
  cut off at the screen edge. Anything hidden behind a text box. Anything you are not
  sure about.

## `?` is the DEFAULT, and this matters most

**If you cannot see that a cell is floor, do not write `.`.** Write `?`.

- The black region is `?` — every cell of it. You cannot see what is there.
- Guessing floor where you can only see black is the most damaging error you can make:
  in a cave, most of the screen is dark, and a model that calls darkness "floor" tells
  the agent it can walk into a wall.

Being unsure is a useful answer. `?` tells the agent where it must go and look.
`undetermined_cells` should normally be greater than zero on any frame with black on it.

## Objects are numbered, and you give the legend

- Every object that is not floor and not a plain wall gets a **number**: `1`, `2`, `3`, …
  Put that number in the cell.
- List what each number is in `legend`, using a short plain name: `television`, `bed`,
  `potted plant`, `staircase`, `desk`, `bookshelf`, `sign`.
- **Reuse the same number for the same kind of object.**
- **Give an object only the cells it actually occupies.** If you can see floor above an
  object, that cell is `.`, not the object — do not stretch an object into a neighbouring
  cell to make it fit.
- If something is there but you cannot tell what, number it and name it `unknown object`.
  Never invent a name.

## One rule that matters more than the others

**Never say whether a cell can be walked on.** Describe what a thing *looks like* — a
staircase looks like a staircase — but never state or imply the player can move there.
Walkability comes from the game's own memory, not from the picture. A thing that looks
like stairs may be solid, and the agent will be told to walk into it.

## Before you answer, check your grid

Count the rows and columns. Read your own grid back and confirm: every black region is
`?`, exactly one cell has an arrow, and no object covers a cell where you can see floor.

## Return exactly this

```
{
  "space": "<room name if the screen names it, else null>",
  "width": 10,
  "height": 9,
  "player_cell": [<column>, <row>],
  "facing": "up|down|left|right",
  "grid": ["<row 0, 10 chars>", "...", "<row 8, 10 chars>"],
  "legend": {"1": "television"},
  "undetermined_cells": <count of '?' cells>,
  "confidence": <0.0-1.0>
}
```

`grid` must have exactly **9** strings, each exactly **10** characters, using only
`. B ? ↑ ↓ ← →` and digits. The cell at `player_cell` must contain the arrow. Every cell
of black is `?`.
