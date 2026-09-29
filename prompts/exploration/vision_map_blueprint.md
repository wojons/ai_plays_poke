# Vision prompt — spatial blueprint

Give this to the vision model for every overworld frame. It implements
`docs/specs/SPEC_spatial_blueprint.md`, so the returned grid is directly comparable,
cell for cell, with the RAM reader's `overworld_grid`.

---

You are reading a single Game Boy screen (Pokémon, Generation I) and returning a spatial
map of it. Return ONLY a JSON object. No prose, no markdown fences.

## The geometry of the image — measured on real frames, not assumed

- The screen is **160 x 144 pixels**, and the game's own coordinate unit is **16 x 16
  pixels**, so the screen shows exactly **10 cells across by 9 down**.
- **Report a 10 x 9 window — the whole screen.** That is what you are looking at, and the
  RAM channel describes the same window, so the two can be compared cell for cell. Do NOT
  drop the tenth column: on a frame with four wall cells to the left of the player and
  four to the right, a 9-wide grid reports two on one side and three on the other, which
  is worse than useless because it looks plausible.
- The screen is **even** (10) wide, so its centre falls *between* two columns. The player
  is the **5th cell from the left** (column index 4): four cells to the left, five to the
  right. Count from the left edge of the screen and keep that position fixed.
- Do **not** assume the map is centred on the player. Where the player sits on screen
  depends on how close the map's edge is, not on a camera rule — a "the player is always
  centred" assumption was measured once in one room and is wrong; it only appeared true
  because repeating floor art aligns with itself when the map shifts by exactly one tile.
  Read the cells that are actually on screen.


## How to draw each cell — one character per block

- `.` — **plain floor with no special behaviour.** Carpet, tile, a doorway threshold: all
  `.`, because stepping there does nothing. Only use `.` when you can actually see floor
  there.
- `B` — **blocking structure**: wall, fence, counter, or furniture that stands in the way.
- `G` — **tall grass.** It is WALKABLE, but it is not plain floor, so it is never `.`:
  stepping into it can trigger a wild encounter. It is a hazard, not an obstacle.
- `W` — **water.** Impassable on foot. Never `.`, even when it looks easy to cross.
- `T` — **tree / foliage** (blocks movement, not walkable).
- `M` — **message, dialogue or menu panel.** This is UI on top of the map, not terrain.
  Use `M` for the whole panel, whatever text it shows — it is NOT `?`, because you can see
  it perfectly well, and it is not `.`, because it is not ground.
- `N` — **another person.** An NPC is a sprite, not terrain. Give the person their own
  cell(s). If a person is visible anywhere on the map, at least one cell must be `N`.
- `$` — **something real that you cannot name yet.** Use `$` when you can see there is a
  thing with meaning but you cannot tell what it is. `$` says "there is something here we
  have not identified"; `?` says "we cannot see this cell at all". Do not confuse them.
- `↑` `↓` `←` `→` — **the player**, in the player's own cell, pointing where they face.
  Exactly one cell has an arrow.
- `?` — **anything you cannot positively identify.** Black areas. Anything cut off at the
  screen edge. Anything you are not sure about.

### Grass and water are drawn alike in monochrome — decide by these cues, not by "it looks wavy"

Both use repeating wavy marks, which is exactly why this gets confused. Asked for a whole grid,
the model has called **tall grass "W" (water)** on the route out of Pallet Town. Split them like
this:

- **Tall grass (`G`)** — many **separate upright tufts**: little scallop / check-mark / clump
  shapes standing on their own, with gaps and ground showing between them. **No shoreline.** It
  usually sits **inside walkable land**, often fenced or hedged around (bushes, trees, a rail),
  and the ground around it is ordinary turf.
- **Water (`W`)** — a **broad, continuous field of flat ripple marks**, not upright tufts. Look
  for a **shore or bank edge**: a light strip, a rim, a transition tile, a cliff, or the map's
  border. Water is generally a large connected body, not a small fenced patch.

Rule of thumb: **bounded by hedge or fence, sitting in land → `G`. Bordered by a shore/bank, or
a big open expanse → `W`.**

This matters more than a naming slip: `W` means "impassable", `G` means "walkable but risky". Call
grass water and you tell the agent it cannot use the one safe place to train; call water grass and
you walk it into a wall.

### Use the game's own tile size — the artwork lies to you

The artwork **repeats every 8 pixels**, but the game counts positions in **16-pixel tiles**.
If you use 8 px as your cell, your grid comes out **twice as wide as it should be**: a path
two tiles wide becomes a one-tile gap, and every distance is wrong. This has already
happened — on a tall-grass frame the walkable path was drawn one cell wide when it is
measurably two. **The player sprite is exactly one tile wide: use it as your ruler.** A gap
the same width as the player is ONE cell. A gap twice the player's width is TWO cells.

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

`grid` must have exactly **9** strings, each exactly **9** characters, using only
`. B G W T M N $ ? ↑ ↓ ← →` and digits. The player is the **middle cell, (4,4)** — that is
the whole point of the odd size. Every cell of black is `?`.
