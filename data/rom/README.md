# Supply your own Pokemon ROM

ROM files are not included in this repository. You must own the game and supply your
own dump.

For the default configuration, place the dump at this exact path and filename:

`data/rom/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).gb`

This path matches `rom.path` in `config/settings.yaml`. If you configure another game,
update `rom.path` to the path of your own dump.

The included `data/boot.state` checkpoint was captured from the exact default Pokemon
Blue ROM above. Save states depend on their matching ROM; using the checkpoint with a
different ROM can produce invalid game state. Use `--boot-state skip` when intentionally
running another owned game without a matching checkpoint.

All `.gb` and `.gbc` files in this directory are ignored by git.
