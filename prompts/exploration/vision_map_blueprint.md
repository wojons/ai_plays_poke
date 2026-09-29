# Vision prompt — spatial blueprint

Give this to the vision model for every overworld frame. It implements
`docs/specs/SPEC_spatial_blueprint.md`, so the returned grid is directly comparable,
cell for cell, with the RAM reader's `overworld_grid`.

---

You are reading a single Game Boy screen (Pokémon, Generation I) and returning a spatial
map of it. Return ONLY a JSON object. No prose, no markdown fences.

## The geometry of the image — measured on real frames, not assumed

- The screen is **160 x 144 pixels**, and the game's own coordinate unit is **16 x 16
  pixels**, so the screen shows about 10 cells across by 9 down.
- **The camera keeps the player centred on the pixel** (measured: moving the player one
  tile moves the map exactly one tile and the sprite does not move at all). So the player
  is always at the centre of the screen, and the black areas are where the map *ends*,
  not a camera clamp.
- **Report a 9 x 9 window centred on the player.** Not 10 wide. 9 is odd, so the player
  is the *middle cell* and every cell has an unambiguous position; a 10-wide grid puts
  the player on the boundary between two columns and there is no right answer for where
  the grid starts. Use an odd count on both axes.


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
  "width": 9,
  "height": 9,
  "player_cell": [4, 4],
  "facing": "up|down|left|right",
  "grid": ["<row 0, 9 chars>", "...", "<row 8, 9 chars>"],
  "legend": {"1": "television"},
  "undetermined_cells": <count of '?' cells>,
  "confidence": <0.0-1.0>
}
```

`grid` must have exactly **9** strings, each exactly **9** characters**, using only
`. B ? ↑ ↓ ← →` and digits. The player is the **middle cell, (4,4)** — that is the whole
point of the odd size. Every cell of black is `?`.
