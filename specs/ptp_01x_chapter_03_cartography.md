# PTP-01X Chapter 3: Cartographic Intelligence & Spatial Mapping

## Executive Summary

The **Cartographic Layer** provides the agent with a global, interconnected understanding of the Kanto region. This layer stitches together individual map data into a cohesive topological graph, enabling long-range pathfinding and strategic routing.

**Key Functions:**
- Global Map Stitching and Topology
- Collision Matrix Generation
- Dynamic Obstacle Layers (HM obstacles, NPCs)
- Warp Transition Logic

---

## 3.1 Global Map Stitching and Topology

### Global Adjacency Graph

```
Nodes: Individual Maps (identified by Map ID $D35E)
Edges: Warps connecting maps

Example Graph:
Pallet Town (0x00) ──► Route 1 (0x0C)
      │                    │
      ▼                    ▼
Viridian City (0x01) ◄── Route 2 (0x0D)
```

### Warp Transition Logic

```python
from typing import Dict, List, Tuple, Set
from dataclasses import dataclass
from collections import defaultdict
import heapq

@dataclass
class MapNode:
    map_id: int
    map_name: str
    warps: List[Dict]  # [{'target_map': int, 'target_pos': (x, y), 'local_pos': (x, y)}]
    collision_matrix: np.ndarray  # Binary walkability matrix

class GlobalAdjacencyGraph:
    """
    Maintains the global graph of Kanto region maps and their connections.
    """
    
    def __init__(self):
        self.nodes: Dict[int, MapNode] = {}
        self.edges: Dict[Tuple[int, int], Dict] = {}  # (from, to) -> edge_data
        self.map_names: Dict[int, str] = {
            0x00: "Pallet Town",
            0x01: "Viridian City",
            0x02: "Pewter City",
            0x03: "Cerulean City",
            0x04: "Lavender Town",
            0x05: "Vermilion City",
            0x06: "Celadon City",
            0x07: "Fuchsia City",
            0x08: "Cinnabar Island",
            0x09: "Indigo Plateau",
            # ... more maps
        }
    
    def add_map(self, map_id: int, map_name: str = None):
        """Add a new map node to the graph."""
        if map_id not in self.nodes:
            self.nodes[map_id] = MapNode(
                map_id=map_id,
                map_name=map_name or self.map_names.get(map_id, f"Map_{map_id:02x}"),
                warps=[],
                collision_matrix=None
            )
    
    def add_warp(self, from_map: int, from_pos: Tuple[int, int],
                 to_map: int, to_pos: Tuple[int, int]):
        """Add a warp edge between two maps."""
        # Add to source map
        if from_map in self.nodes:
            self.nodes[from_map].warps.append({
                'target_map': to_map,
                'target_pos': to_pos,
                'local_pos': from_pos
            })
        
        # Add to adjacency list
        edge_key = (from_map, to_map)
        self.edges[edge_key] = {
            'from_pos': from_pos,
            'to_pos': to_pos,
            'bidirectional': self._is_bidirectional_warp(from_map, to_map)
        }
    
    def _is_bidirectional_warp(self, map1: int, map2: int) -> bool:
        """Determine if warp between two maps is bidirectional."""
        # Most building entrances/exits are bidirectional
        # Some one-way areas (Safari Zone exit) are not
        return True  # Simplified - would check specific map pairs
    
    def get_path(self, start_map: int, end_map: int) -> List[Dict]:
        """
        Find shortest path between two maps using Dijkstra's algorithm.
        
        Returns:
            List of edges to traverse: [{'from': map1, 'to': map2, 'from_pos': (x,y), 'to_pos': (x,y)}]
        """
        # Dijkstra's algorithm for shortest path
        distances = {start_map: 0}
        previous = {start_map: None}
        pq = [(0, start_map)]
        visited = set()
        
        while pq:
            current_dist, current_map = heapq.heappop(pq)
            
            if current_map in visited:
                continue
            visited.add(current_map)
            
            if current_map == end_map:
                break
            
            # Find neighbors
            for map_id, node in self.nodes.items():
                if map_id == current_map:
                    continue
                
                edge_key = (current_map, map_id)
                if edge_key in self.edges:
                    new_dist = current_dist + 1  # Each warp = 1 step
                    
                    if map_id not in distances or new_dist < distances[map_id]:
                        distances[map_id] = new_dist
                        previous[map_id] = current_map
                        heapq.heappush(pq, (new_dist, map_id))
        
        # Reconstruct path
        if end_map not in previous:
            return []  # No path found
        
        path = []
        current = end_map
        while previous[current] is not None:
            from_map = previous[current]
            edge_key = (from_map, current)
            
            if edge_key in self.edges:
                path.append({
                    'from': from_map,
                    'to': current,
                    **self.edges[edge_key]
                })
            current = from_map
        
        return list(reversed(path))


class WarpTransitionDetector:
    """
    Detects and tracks warp transitions between maps.
    """
    
    def __init__(self, memory_interface):
        self.memory = memory_interface
        self.last_map_id = None
        self.last_position = None
        self.transition_in_progress = False
    
    def check_transition(self) -> Optional[Dict]:
        """
        Check if a warp transition has occurred.
        
        Returns:
            Transition info dict or None if no transition
        """
        current_map = self.memory.get_current_map()
        current_pos = self.memory.get_player_position()
        
        if self.last_map_id is None:
            # First call - just store initial state
            self.last_map_id = current_map
            self.last_position = current_pos
            return None
        
        if current_map != self.last_map_id:
            # Map changed - warp occurred!
            transition = {
                'from_map': self.last_map_id,
                'to_map': current_map,
                'from_pos': self.last_position,
                'to_pos': current_pos,
                'timestamp': self._get_timestamp()
            }
            
            self.last_map_id = current_map
            self.last_position = current_pos
            
            return transition
        
        return None
    
    def get_transition_warp_info(self, transition: Dict) -> Dict:
        """
        Determine which specific warp was used.
        """
        from_map = transition['from_map']
        from_pos = transition['from_pos']
        
        # Look for warp that matches exit position
        if from_map in self.nodes:
            for warp in self.nodes[from_map].warps:
                if warp['local_pos'] == from_pos:
                    return warp
        
        return {'unknown_warp': True}
```

---

## 3.2 The Collision Matrix

### Binary Collision Matrix

For every Map ID, the agent generates a binary collision matrix where:
- `0` = Wall/Blocked
- `1` = Walkable

### Implementation

```python
import numpy as np

class CollisionMatrixGenerator:
    """
    Generates binary collision matrices for each map.
    Data is extracted deterministically from ROM, not learned.
    """
    
    MAP_WIDTH = 20  # tiles
    MAP_HEIGHT = 15  # tiles
    
    # Map header address for collision data
    MAP_HEADER_PTR = 0xD36E
    
    TILE_TYPES = {
        0x00: 'walkable',    # Grass
        0x01: 'wall',        # Building wall
        0x02: 'water',       # Water (needs Surf)
        0x03: 'ledge',       # Ledge (one-way)
        0x04: 'tree',        # Cut tree (needs HM01)
        0x05: 'rock',        # Strength boulder (needs HM04)
        0x06: 'warp',        # Warp tile
        0x07: 'npc',         # NPC blocking
        0x08: 'sign',        # Signpost
    }
    
    def __init__(self, memory_interface):
        self.memory = memory_interface
        self.collision_matrices: Dict[int, np.ndarray] = {}
    
    def get_collision_matrix(self, map_id: int = None) -> np.ndarray:
        """
        Get collision matrix for current or specified map.
        
        Returns:
            Binary numpy array (15x20) where 1 = walkable
        """
        if map_id is None:
            map_id = self.memory.get_current_map()
        
        # Check cache
        if map_id in self.collision_matrices:
            return self.collision_matrices[map_id]
        
        # Generate from ROM data
        matrix = self._generate_from_rom(map_id)
        
        # Cache it
        self.collision_matrices[map_id] = matrix
        
        return matrix
    
    def _generate_from_rom(self, map_id: int) -> np.ndarray:
        """
        Extract collision data from ROM deterministically.
        
        The ROM contains pre-computed collision data for each map.
        We read the pointer from the map header and extract the data.
        """
        # Read map header pointer
        header_ptr = self.memory.read_word(self.MAP_HEADER_PTR)
        
        # Navigate to collision data
        collision_ptr = self.memory.read_word(header_ptr + 0x0A)
        
        # Read collision data bytes
        matrix = np.zeros((self.MAP_HEIGHT, self.MAP_WIDTH), dtype=int)
        
        for row in range(self.MAP_HEIGHT):
            for col in range(self.MAP_WIDTH):
                tile_type_id = self.memory.read_byte(
                    collision_ptr + (row * self.MAP_WIDTH) + col
                )
                
                # Convert to walkability
                tile_type = self.TILE_TYPES.get(tile_type_id, 'wall')
                
                if tile_type in ['walkable', 'grass']:
                    matrix[row, col] = 1  # Walkable
                else:
                    matrix[row, col] = 0  # Blocked
        
        return matrix
    
    def is_walkable(self, x: int, y: int, map_id: int = None) -> bool:
        """
        Check if a specific tile is walkable.
        """
        matrix = self.get_collision_matrix(map_id)
        
        if not (0 <= x < self.MAP_WIDTH and 0 <= y < self.MAP_HEIGHT):
            return False
        
        return matrix[y, x] == 1
    
    def get_tile_type(self, x: int, y: int, map_id: int = None) -> str:
        """
        Get the semantic type of a tile.
        """
        # Would return specific tile type (grass, water, etc.)
        pass
```

---

## 3.3 Dynamic Obstacle Layers

### Conditional Obstacles

The static collision matrix is modified by dynamic obstacles:

```python
class DynamicObstacleManager:
    """
    Manages dynamic obstacles that modify the collision matrix.
    """
    
    def __init__(self, memory_interface, collision_gen):
        self.memory = memory_interface
        self.collision_gen = collision_gen
        self.hm_items = set()
        self.badges = set()
        self.npc_positions = {}
    
    def has_hm(self, hm_name: str) -> bool:
        """Check if player has a specific HM."""
        return hm_name in self.hm_items
    
    def has_badge(self, badge_name: str) -> bool:
        """Check if player has a specific badge (enables HM)."""
        return badge_name in self.badges
    
    def get_dynamic_collision_matrix(self, map_id: int = None) -> np.ndarray:
        """
        Get collision matrix with dynamic obstacles applied.
        
        Modifications:
        - Cut trees become walkable if has HM01 + Cascade Badge
        - Strength boulders become pushable if has HM04 + Soul Badge
        - Warps open when events are triggered
        - NPCs are dynamically positioned
        """
        # Start with base matrix
        base_matrix = self.collision_gen.get_collision_matrix(map_id)
        dynamic_matrix = base_matrix.copy()
        
        # Apply HM modifications
        dynamic_matrix = self._apply_hm_modifications(dynamic_matrix, map_id)
        
        # Apply NPC positions
        dynamic_matrix = self._apply_npc_positions(dynamic_matrix, map_id)
        
        return dynamic_matrix
    
    def _apply_hm_modifications(self, matrix: np.ndarray, 
                                 map_id: int) -> np.ndarray:
        """Apply HM-related obstacle modifications."""
        # Cut trees
        if self.has_hm('HM01') and self.has_badge('Cascade Badge'):
            for (x, y), tile_type in self._get_hm_obstacles(map_id).items():
                if tile_type == 'cut_tree':
                    matrix[y, x] = 1  # Now walkable (with penalty)
        
        # Strength boulders
        if self.has_hm('HM04') and self.has_badge('Soul Badge'):
            for (x, y), tile_type in self._get_hm_obstacles(map_id).items():
                if tile_type == 'boulder':
                    matrix[y, x] = 1  # Pushable
        
        return matrix
    
    def _apply_npc_positions(self, matrix: np.ndarray,
                              map_id: int) -> np.ndarray:
        """Apply current NPC positions to collision matrix."""
        # Get NPC positions from sprite data
        npc_positions = self.memory.get_npc_positions()
        
        for npc_id, (x, y) in npc_positions.items():
            if 0 <= x < 20 and 0 <= y < 15:
                matrix[y, x] = 0  # NPC blocks tile
        
        return matrix
    
    def _get_hm_obstacles(self, map_id: int) -> Dict[Tuple[int, int], str]:
        """
        Get HM obstacles for a specific map.
        This data is pre-computed from the ROM.
        """
        # Would load from pre-computed database
        return {}
```

---

## Summary

| Section | Purpose | Key Components |
|---------|---------|----------------|
| **3.1 Map Stitching** | Global topology graph | GlobalAdjacencyGraph, WarpTransitionDetector |
| **3.2 Collision Matrix** | Binary walkability | CollisionMatrixGenerator, ROM extraction |
| **3.3 Dynamic Obstacles** | HM/NPC modifications | DynamicObstacleManager, HM requirements |

---

**Document Version:** 1.0  
**Last Updated:** December 31, 2025  
**Protocol:** PTP-01X - Chapter 3: Cartographic Intelligence