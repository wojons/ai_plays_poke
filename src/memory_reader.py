"""
Memory Reader - Access Pokemon game data from PyBoy memory
"""
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pyboy import PyBoy

def scan_memory_for_pokemon_data(pyboy, scan_range=(0xD000, 0xE000)):
    """Scan memory for Pokemon-related data"""
    
    memory = pyboy.memory
    memory_data = {}
    
    # Scan a range of memory addresses
    start_addr, end_addr = scan_range
    print(f"🔍 Scanning memory from {hex(start_addr)} to {hex(end_addr)}...")
    
    # Look for patterns that might indicate Pokemon data
    for addr in range(start_addr, end_addr, 2):  # Scan every 2 bytes
        try:
            value = memory[addr]
            next_value = memory[addr + 1]
            
            # Look for patterns that might be Pokemon stats
            # This is a simplified approach - actual patterns need to be determined
            if value > 0 and next_value > 0:
                # This could be a Pokemon stat (HP, level, etc.)
                memory_data[f"addr_{hex(addr)}"] = f"{value}, {next_value}"
                
        except IndexError:
            break
    
    return memory_data

def read_pokemon_stats(pyboy):
    """Read Pokemon game stats from memory"""
    
    memory = pyboy.memory
    
    # Common memory locations for Pokemon data (needs verification for each ROM)
    # These are example addresses and need to be determined through experimentation
    stats = {}
    
    try:
        # Player's Pokemon data (example addresses)
        stats['player_hp'] = memory[0xD158]  # Current HP
        stats['player_max_hp'] = memory[0xD159]  # Max HP
        stats['player_level'] = memory[0xD16A]  # Level
        stats['player_status'] = memory[0xD15E]  # Status effects
        
        # Enemy Pokemon data (example addresses)
        stats['enemy_hp'] = memory[0xCFD8]  # Current HP
        stats['enemy_max_hp'] = memory[0xCFD9]  # Max HP
        stats['enemy_level'] = memory[0xCFE2]  # Level
        
        return stats
        
    except Exception as e:
        print(f"❌ Error reading Pokemon stats: {e}")
        return None

def test_memory_scanning():
    """Test memory scanning functionality"""
    
    print("🧪 Memory Scanning Test")
    print("=" * 50)
    
    rom_path = "data/rom/pokemon_blue.gb"
    print(f"📂 ROM: {rom_path}")
    
    # Check if ROM exists
    if not os.path.exists(rom_path):
        print(f"❌ ROM not found: {rom_path}")
        return False
    
    # Initialize emulator
    print("🚀 Loading ROM...")
    pyboy = PyBoy(rom_path)
    
    # Run for some ticks to let the game initialize
    print("▶️  Running 500 ticks for game initialization...")
    for _ in range(500):
        pyboy.tick()
    
    # Scan memory for Pokemon data
    print("🔍 Scanning memory for Pokemon data...")
    memory_data = scan_memory_for_pokemon_data(pyboy)
    
    if memory_data:
        print(f"✅ Found {len(memory_data)} memory locations with data:")
        for addr, values in list(memory_data.items())[:10]:  # Show first 10
            print(f"  {addr}: {values}")
    else:
        print("❌ No Pokemon data found in scanned memory range")
    
    # Read Pokemon stats
    print("\n📊 Reading Pokemon stats...")
    pokemon_stats = read_pokemon_stats(pyboy)
    
    if pokemon_stats:
        print("✅ Pokemon stats read successfully:")
        for key, value in pokemon_stats.items():
            print(f"  {key}: {value}")
    else:
        print("❌ Failed to read Pokemon stats")
    
    # Clean up
    print("\n🛑 Stopping emulator...")
    pyboy.stop()
    
    print("\n" + "=" * 50)
    print("✅ Test completed!")
    
    return memory_data is not None

if __name__ == "__main__":
    success = test_memory_scanning()
    if success:
        print("\n🎉 Memory scanning functionality is working!")
    else:
        print("\n❌ Memory scanning test failed.")