# Place your Pokemon ROM here

## Available Games:

**Gen 1 (Game Boy):**
- pokemon_red.gb
- pokemon_blue.gb ⭐ DEFAULT
- pokemon_green.gb
- pokemon_yellow.gb

**Gen 2 (Game Boy Color):**
- pokemon_gold.gbc
- pokemon_silver.gbc

## How to Select a Game:

Edit `config/settings.yaml` and change:
```yaml
rom:
  path: "data/rom/pokemon_blue.gb"  # Change this line
```

## Notes:
- .gbc = Game Boy Color games (larger, 2MB)
- .gb = Original Game Boy games (1MB)
- All files are ignored by git
