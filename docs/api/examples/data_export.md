# Data Export Example

This example demonstrates how to export and analyze session data.

## Export Session Data

Export all session data to JSON for analysis:

```python
from src.db.database import GameDatabase

# Connect to database
db = GameDatabase("./game_data.db")

# Export session
export_path = db.export_session_data(session_id=1)
print(f"Exported to: {export_path}")

# The exported JSON contains:
# {
#     "session": {...},
#     "commands": [...],
#     "thoughts": [...],
#     "battles": [...],
#     "screenshots": [...]
# }
```

## Analyze Command History

Parse and analyze command history:

```python
import json
from collections import Counter
from src.db.database import GameDatabase


def analyze_commands(db_path: str, session_id: int):
    """Analyze command patterns from a session"""
    db = GameDatabase(db_path)

    # Get commands (simplified - would need actual query)
    with open(f"session_{session_id}_export.json") as f:
        data = json.load(f)

    commands = data.get("commands", [])

    # Count button presses
    button_counts = Counter()
    for cmd in commands:
        if cmd["command_type"] == "press":
            button_counts[cmd["command_value"]] += 1

    print("Button press frequencies:")
    for button, count in button_counts.most_common():
        print(f"  {button}: {count}")

    # Calculate success rate
    successful = sum(1 for cmd in commands if cmd["success"])
    total = len(commands)
    print(f"\nSuccess rate: {successful}/{total} ({successful/total*100:.1f}%)")

    # Average confidence
    confidences = [cmd["confidence"] for cmd in commands]
    if confidences:
        avg_confidence = sum(confidences) / len(confidences)
        print(f"Average confidence: {avg_confidence:.2f}")


analyze_commands("./game_data.db", session_id=1)
```

## Analyze Battle Performance

Extract and analyze battle statistics:

```python
import json
from src.db.database import GameDatabase


def battle_analysis(db_path: str, session_id: int):
    """Analyze battle performance"""
    db = GameDatabase(db_path)

    # Export session data
    export_path = db.export_session_data(session_id)
    with open(export_path) as f:
        data = json.load(f)

    battles = data.get("battles", [])

    if not battles:
        print("No battles recorded")
        return

    # Battle outcomes
    outcomes = Counter(b["outcome"] for b in battles)
    print("Battle outcomes:")
    for outcome, count in outcomes.items():
        print(f"  {outcome}: {count}")

    # Win rate
    victories = outcomes.get("victory", 0)
    total = sum(outcomes.values())
    print(f"\nWin rate: {victories}/{total} ({victories/total*100:.1f}%)")

    # Average turns per battle
    turn_counts = [b["turns_taken"] for b in battles if b.get("turns_taken")]
    if turn_counts:
        avg_turns = sum(turn_counts) / len(turn_counts)
        print(f"Average turns per battle: {avg_turns:.1f}")

    # Most common enemies
    enemies = Counter(b["enemy_pokemon"] for b in battles)
    print("\nMost common encounters:")
    for enemy, count in enemies.most_common(5):
        print(f"  {enemy}: {count}")


battle_analysis("./game_data.db", session_id=1)
```

## Track AI Performance Over Time

Monitor AI performance metrics:

```python
import json
from datetime import datetime
from src.db.database import GameDatabase


def track_performance(db_path: str):
    """Track AI performance across sessions"""
    db = GameDatabase(db_path)

    sessions = db.get_all_sessions()  # Hypothetical method

    performance_data = []
    for session in sessions:
        summary = db.get_session_summary(session["session_id"])

        performance_data.append({
            "session_id": session["session_id"],
            "date": session["start_time"],
            "battles": summary.get("total_battles", 0),
            "win_rate": summary.get("win_rate", 0),
            "ticks": summary.get("total_ticks", 0)
        })

    # Print performance over time
    print("Session Performance:")
    print("-" * 60)
    for session in performance_data:
        date = datetime.fromisoformat(session["date"])
        print(f"Session {session['session_id']}: "
              f"{date.strftime('%Y-%m-%d %H:%M')} | "
              f"Battles: {session['battles']:3d} | "
              f"Win Rate: {session['win_rate']*100:5.1f}% | "
              f"Ticks: {session['ticks']}")


track_performance("./game_data.db")
```

## Export to CSV

Convert data to CSV for external analysis:

```python
import csv
import json
from src.db.database import GameDatabase


def export_commands_to_csv(db_path: str, session_id: int, output_path: str):
    """Export command history to CSV"""
    db = GameDatabase(db_path)
    export_path = db.export_session_data(session_id)

    with open(export_path) as f:
        data = json.load(f)

    commands = data.get("commands", [])

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "tick", "timestamp", "command_type", "command_value",
            "reasoning", "confidence", "success", "execution_time_ms"
        ])
        writer.writeheader()
        writer.writerows(commands)

    print(f"Exported {len(commands)} commands to {output_path}")


def export_battles_to_csv(db_path: str, session_id: int, output_path: str):
    """Export battle history to CSV"""
    db = GameDatabase(db_path)
    export_path = db.export_session_data(session_id)

    with open(export_path) as f:
        data = json.load(f)

    battles = data.get("battles", [])

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "battle_id", "start_tick", "end_tick", "enemy_pokemon",
            "enemy_level", "player_pokemon", "player_level",
            "outcome", "turns_taken"
        ])
        writer.writeheader()
        writer.writerows(battles)

    print(f"Exported {len(battles)} battles to {output_path}")


# Usage
export_commands_to_csv("./game_data.db", 1, "commands.csv")
export_battles_to_csv("./game_data.db", 1, "battles.csv")
```

## Visualize with Matplotlib

Create visualizations of session data:

```python
import json
import matplotlib.pyplot as plt
from src.db.database import GameDatabase


def visualize_session(db_path: str, session_id: int):
    """Create visualizations of session data"""
    db = GameDatabase(db_path)
    export_path = db.export_session_data(session_id)

    with open(export_path) as f:
        data = json.load(f)

    commands = data.get("commands", [])

    # Extract confidence over time
    ticks = [c["tick"] for c in commands]
    confidences = [c["confidence"] for c in commands]

    # Plot confidence over time
    plt.figure(figsize=(12, 4))
    plt.plot(ticks, confidences, alpha=0.7)
    plt.xlabel("Tick")
    plt.ylabel("Confidence")
    plt.title(f"AI Confidence Over Time (Session {session_id})")
    plt.grid(True, alpha=0.3)
    plt.savefig(f"confidence_session_{session_id}.png")
    plt.close()

    # Button press distribution
    from collections import Counter
    buttons = [c["command_value"] for c in commands if c["command_type"] == "press"]
    button_counts = Counter(buttons)

    plt.figure(figsize=(8, 4))
    plt.bar(button_counts.keys(), button_counts.values())
    plt.xlabel("Button")
    plt.ylabel("Press Count")
    plt.title(f"Button Press Distribution (Session {session_id})")
    plt.savefig(f"buttons_session_{session_id}.png")
    plt.close()

    print("Visualizations saved")


visualize_session("./game_data.db", session_id=1)
```

## Next Steps

- [Basic Usage](basic_usage.md) - Getting started
- [Custom AI Integration](custom_ai.md) - Custom AI models
- [API Reference](../index.md) - Full API documentation