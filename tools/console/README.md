# Console tools

Quality tooling for the local console app (which lives at ~/aipp-console and is run by the
aipp-console / aipp-bridge systemd user units). The console itself is NOT moved in here: it has its
own git history and two live systemd units pointing at its path, so moving it is a separate
decision, not a side effect of adding tests. Bane asked for the extra tools to live in the project
directory and for the work to be on the board; both are done.

- `test_controls.py` - exercises every control on the console against the running server, including
  malformed input. Skips the movement buttons on purpose: a press moves the player, and that needs
  explicit approval.
- `test_pass.py` - panel-level smoke test (checks panels render, not that controls work).
- `test_auto_vision.py` - proves the vision panel refreshes on its own.
- `bench_vision_accuracy.py` - scores a vision model against the reader grid, cell by cell.
- `bench_equipped.py` - grid reading AND people identification, per model.
- `vision_10x9.md` - the prompt that measured best. A vague prompt makes a small model answer all
  floor, which scores well on a mostly-open screen and finds nothing; wording matters more than the
  model choice here.

Run them with the project venv: /home/kara/ai_plays_poke/.venv/bin/python <tool>.py
