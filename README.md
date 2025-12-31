# AI Plays Pokemon - Orchestrated Intelligence Framework

🎮 An AI that learns to play Pokemon using hierarchical memory and strategic reasoning.

## ROM Selection

**Place your ROM in:** `data/rom/`

**Available Games:**
```
Gen 1 (Game Boy):
├── pokemon_red.gb       - Pokemon Red (English)
├── pokemon_blue.gb      - Pokemon Blue (English) ⭐ DEFAULT
├── pokemon_green.gb     - Pokemon Green (Japanese)
└── pokemon_yellow.gb    - Pokemon Yellow (Gen 1.5)

Gen 2 (Game Boy Color):
├── pokemon_gold.gbc     - Pokemon Gold
└── pokemon_silver.gbc   - Pokemon Silver
```

**To change games:** Edit `config/settings.yaml` and change `rom.path`

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set up API key
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY

# 3. Select your game
# Edit config/settings.yaml -> rom.path

# 4. Run!
python -m src.main
```

## Architecture

- **Observer** - Long-term journey memory
- **Strategist** - Mid-term lessons learned  
- **Tactician** - Immediate battle decisions
- **Reflection Engine** - Learns from victories and defeats

## Documentation

See [memory-bank/](memory-bank/) for full architecture docs.

## Requirements

- Python 3.10+
- OpenAI API key (for GPT-4V/GPT-4o-mini)
- 1GB storage for logs/memory
- Internet connection (API calls)
