# People vision measurement (VIS-PEOPLE-1)

## Method

The probe used three fresh frames captured through the live bridge from the `start`,
`pallet_outside_house_20260929`, and `slot1` save positions. It restored the bridge's
original state after the run; static screenshots were not used.

Each frame was paired with a bridge save made at the same instant. Ground truth came
from `wSpriteStateData1` (`0xC100`, 16 records × 16 bytes). The player is slot 0 and is
excluded. Active non-player human sprites are placed in the 9×9 window relative to the
RAM player's measured screen position, with the player fixed at cell `(4,3)`. Still
objects and non-human sprite archetypes are excluded.

The model was `openai/gpt-4o-mini` through OpenRouter. The frame was enlarged 6× in the
same way as the existing vision probes. Scoring is exact sprite-cell presence only:
there is no whole-grid score. RAM exposes a sprite archetype and facing, not a person's
true story identity or hair/clothing colours, so names and features are retained in the
output but do not replace the cell oracle. A facing contradiction is reported as a
non-scoring diagnostic.

## Real probe output

Command:

```text
set -a; source /home/kara/ai_plays_poke/.env; set +a
PYTHONPATH=. /home/kara/ai_plays_poke/venv/bin/python scripts/vision_people_probe.py \
  --slot start --slot pallet_outside_house_20260929 --slot slot1
```

Output:

```text
PER-FRAME PEOPLE MEASUREMENT
frame | RAM sprite people | model people | result
--- | --- | --- | ---
start | girl@(6, 5)/up | girl@(1, 4)/facing up | MISS
  failure: wrong cell for girl: model (1, 4), RAM (6, 5) (girl)
pallet_outside_house_20260929 | girl@(1, 4)/up | girl@(1, 4)/facing up | CORRECT
slot1 | blue@(4, 5)/down, oak@(3, 3)/down, oak@(3, 8)/up | girl@(1, 4)/facing up, boy@(2, 4)/hat | MISS
  failure: wrong cell for boy: model (2, 4), RAM (3, 3) (oak)
  failure: wrong cell for girl: model (1, 4), RAM (4, 5) (blue)
  failure: missed person at (3, 8) (oak)

SUMMARY
model: openai/gpt-4o-mini
frames correct: 1/3
frames failed: 2/3 (66.7% failure rate)
RAM person cells matched: 1/5
score basis: exact RAM sprite cells only; no whole-grid percentage
```

## Verdict

The measured failure rate is **66.7% (2/3 frames failed)**. Only **1/5 RAM person
cells** was matched. The terse prompt correctly located the Pallet Town person in one
position, placed the same sprite at the wrong cell in another position, and failed the
Oak's Lab scene badly (two wrong cells plus one missed person). On this sample,
`openai/gpt-4o-mini` is not reliable enough to supply people locations without the RAM
sprite-cell check.
