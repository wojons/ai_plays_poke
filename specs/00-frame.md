# 00 — Frame

**System.** AI-Plays-Poke (PTP-01X): an autonomous agent that plays Pokémon Blue (Gen 1) on a
headless PyBoy-family emulator, for the operator (Bane), inside the Coding Hermes fleet on the
karaHermes workstation.

**One idea.** The agent perceives the game through two independent channels — RAM and a vision
model — that must describe the same room in **one grid, one symbol set, one legend**, so they can be
diffed every frame; JEV decides most cycles and hands back to a reasoning LLM only when it cannot.

**Readers.** The worker (implements against this spec), the judge (grades claims against evidence),
the operator (drives the game and reads the console). After reading: a worker knows what each module
owns and must never touch; a judge knows which fact backs which claim; the operator knows what each
console control does and what a reading costs.

**If the spec is wrong.** A wrong grid geometry makes every RAM-vs-vision verdict a false alarm; a
wrong default decision mode sends the agent into a loop that cannot leave Pallet Town; a wrong bridge
contract lets two drivers fight over one emulator.

**Out of scope.** The Coding Hermes scheduler internals (documented in its own repo), DuckBrain
internals, anything a run cannot reach, and the Trading/messaging surface of the fleet.
