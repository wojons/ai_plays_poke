# PTP-01X Chapter 4: Navigation Engine & Pathfinding Algorithms

## Executive Summary

The **Navigation Engine** translates high-level strategic goals ("Go to Viridian City") into low-level controller inputs ("Hold Down for 500ms"). It uses Hierarchical Pathfinding (HPA*) to efficiently navigate the Kanto region.

---

## 4.1 Hierarchical Pathfinding (HPA*)

```python
import heapq
from typing import List, Tuple, Dict, Set, Optional
from dataclasses import dataclass
import numpy as np

@dataclass
class PathStep:
    x: int
    y: int
    direction: str
    cost: float

class HierarchicalPathfinder:
    """
    Implements HPA* for efficient navigation across Kanto.
    
    Two-level search:
    1. Macro: Find sequence of maps
    2. Micro: Find path within current map
    """
    
    def __init__(self, adjacency_graph, collision_manager):
        self.graph = adjacency_graph
        self.collision = collision_manager
    
    def find_path(self, start_pos: Tuple[int, int], 
                  goal_pos: Tuple[int, int],
                  start_map: int = None,
                  goal_map: int = None) -> List[PathStep]:
        """
        Find optimal path from start to goal.
        
        Uses HPA*:
        1. If same map: micro-pathfinding only
        2. If different maps: macro + micro
        """
        if start_map is None:
            start_map = self.graph.get_current_map()
        if goal_map is None:
            goal_map = self.graph.get_current_map()
        
        # Case 1: Same map - simple A*
        if start_map == goal_map:
            return self._micro_pathfinding(
                start_pos, goal_pos, start_map
            )
        
        # Case 2: Different maps - HPA*
        # Find macro path (sequence of maps)
        macro_path = self.graph.get_path(start_map, goal_map)
        
        # Find micro paths within each map
        full_path = []
        current_pos = start_pos
        
        for edge in macro_path:
            # Find path to warp
            warp_pos = edge['from_pos']
            path_to_warp = self._micro_pathfinding(
                current_pos, warp_pos, edge['from']
            )
            full_path.extend(path_to_warp)
            
            # Update position
            current_pos = edge['to_pos']
        
        # Add final segment to goal
        final_path = self._micro_pathfinding(
            current_pos, goal_pos, goal_map
        )
        full_path.extend(final_path)
        
        return full_path
    
    def _micro_pathfinding(self, start: Tuple[int, int],
                           goal: Tuple[int, int],
                           map_id: int) -> List[PathStep]:
        """
        Standard A* within a single map.
        """
        # Get collision matrix with dynamic obstacles
        collision = self.collision.get_dynamic_collision_matrix(map_id)
        
        # A* implementation
        open_set = [(0, start)]
        came_from = {start: None}
        g_score = {start: 0}
        f_score = {start: self._heuristic(start, goal)}
        
        while open_set:
            _, current = heapq.heappop(open_set)
            
            if current == goal:
                return self._reconstruct_path(came_from, current)
            
            for neighbor in self._get_neighbors(current, collision):
                tentative_g = g_score[current] + 1
                
                if tentative_g < g_score.get(neighbor, float('inf')):
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f_score[neighbor] = tentative_g + self._heuristic(neighbor, goal)
                    heapq.heappush(open_set, (f_score[neighbor], neighbor))
        
        return []  # No path found
    
    def _heuristic(self, a: Tuple[int, int], 
                   b: Tuple[int, int]) -> float:
        """Manhattan distance heuristic."""
        return abs(a[0] - b[0]) + abs(a[1] - b[1])
    
    def _get_neighbors(self, pos: Tuple[int, int],
                       collision: np.ndarray) -> List[Tuple[int, int]]:
        """Get valid neighbors (up, down, left, right)."""
        neighbors = []
        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            nx, ny = pos[0] + dx, pos[1] + dy
            if (0 <= ny < collision.shape[0] and 
                0 <= nx < collision.shape[1] and
                collision[ny, nx] == 1):
                neighbors.append((nx, ny))
        return neighbors
    
    def _reconstruct_path(self, came_from: Dict, 
                          current: Tuple[int, int]) -> List[PathStep]:
        """Reconstruct path from A* results."""
        path = []
        while current in came_from:
            prev = came_from[current]
            if prev is None:
                break
                
            direction = self._get_direction(prev, current)
            path.append(PathStep(
                x=current[0],
                y=current[1],
                direction=direction,
                cost=1.0
            ))
            current = prev
        
        return list(reversed(path))
    
    def _get_direction(self, from_pos: Tuple[int, int],
                       to_pos: Tuple[int, int]) -> str:
        """Determine movement direction."""
        dx = to_pos[0] - from_pos[0]
        dy = to_pos[1] - from_pos[1]
        
        if dx > 0: return 'right'
        if dx < 0: return 'left'
        if dy > 0: return 'down'
        if dy < 0: return 'up'
        return 'none'
```

---

## 4.2 Ledge and One-Way Logic (Diode Nodes)

```python
class LedgeNavigator:
    """
    Handles ledge tiles as "diode nodes" - one-way traversal.
    """
    
    def __init__(self, collision_manager):
        self.collision = collision_manager
    
    def get_ledge_constraints(self, semantic_grid: np.ndarray) -> Dict:
        """
        Identify ledges and their allowed directions.
        
        Returns:
            Dict mapping (x, y) to allowed direction
        """
        ledges = {}
        
        for y in range(semantic_grid.shape[0]):
            for x in range(semantic_grid.shape[1]):
                if semantic_grid[y, x] == SemanticType.LEDGE:
                    ledges[(x, y)] = self._determine_ledge_direction(
                        semantic_grid, x, y
                    )
        
        return ledges
    
    def _determine_ledge_direction(self, grid: np.ndarray,
                                    x: int, y: int) -> str:
        """Determine which directions are allowed through a ledge."""
        allowed = []
        
        # Check each direction
        directions = {
            'up': (x, y - 1),
            'down': (x, y + 1),
            'left': (x - 1, y),
            'right': (x + 1, y)
        }
        
        for direction, (nx, ny) in directions.items():
            if not (0 <= ny < grid.shape[0] and 0 <= nx < grid.shape[1]):
                continue
            
            target_tile = grid[ny, nx]
            
            # Ledges typically allow movement TO lower elevation (down)
            # But not back UP
            if direction == 'down' and target_tile != SemanticType.WALL:
                allowed.append(direction)
            elif direction == 'right' and target_tile != SemanticType.WALL:
                allowed.append(direction)
        
        return allowed[0] if allowed else 'down'  # Default
    
    def apply_ledge_constraints(self, path: List[PathStep],
                                 ledges: Dict) -> List[PathStep]:
        """
        Filter path to respect ledge constraints.
        Removes invalid movements through ledges.
        """
        constrained_path = []
        
        for i, step in enumerate(path):
            ledge_key = (step.x, step.y)
            
            if ledge_key in ledges:
                # Check if movement direction is allowed
                allowed = ledges[ledge_key]
                
                # If trying to go wrong direction through ledge, skip
                if step.direction not in allowed:
                    # Need to recalculate - path is invalid
                    return []  # Signal recalculation needed
            
            constrained_path.append(step)
        
        return constrained_path
```

---

## 4.3 Bonk Recovery Protocol

```python
class BonkRecoverySystem:
    """
    Handles collision recovery when movement doesn't register.
    """
    
    def __init__(self, memory_interface):
        self.memory = memory_interface
        self.bonk_count = 0
        self.max_bonks = 3
        self.stabilization_delay = 200  # ms
    
    def check_and_recover(self, action: str, 
                         expected_pos: Tuple[int, int]) -> Dict:
        """
        Check for bonk and recover if needed.
        
        Returns:
            Recovery action or None if no bonk
        """
        actual_pos = self.memory.get_player_position()
        
        if actual_pos != expected_pos:
            # Bonk detected!
            self.bonk_count += 1
            
            return {
                'action': 'bonk',
                'recovery': self._execute_recovery(),
                'bonk_number': self.bonk_count
            }
        
        self.bonk_count = 0
        return None
    
    def _execute_recovery(self) -> Dict:
        """
        Execute bonk recovery protocol.
        """
        return {
            'action': 'wait',
            'duration_ms': self.stabilization_delay,
            'next_action': 'realign'
        }
```

---

## 4.4 Warp Handling

```python
class WarpHandler:
    """
    Handles warp transitions and state changes.
    """
    
    def __init__(self, memory_interface, anomaly_detector):
        self.memory = memory_interface
        self.anomaly = anomaly_detector
        self.in_transition = False
        self.transition_start_time = None
    
    def initiate_warp(self) -> bool:
        """
        Check if warp transition should begin.
        
        Returns:
            True if warp started successfully
        """
        current_map = self.memory.get_current_map()
        
        # Transition state
        self.in_transition = True
        self.transition_start_time = self._get_time_ms()
        
        return True
    
    def check_transition_complete(self) -> bool:
        """
        Check if warp transition is complete.
        
        Returns:
            True if transition complete, False if still transitioning
        """
        if not self.in_transition:
            return True
        
        # Check for Map ID change
        current_map = self.memory.get_current_map()
        
        # Check visual stability (no anomaly)
        anomaly = self.anomaly.analyze_frame(
            self.memory.get_current_frame()
        )
        
        if anomaly['is_shake'] or anomaly['is_flash']:
            # Still in animation
            return False
        
        # Check if enough time has passed
        elapsed = self._get_time_ms() - self.transition_start_time
        if elapsed < 1000:  # 1 second minimum
            return False
        
        # Transition complete
        self.in_transition = False
        return True
    
    def should_suppress_input(self) -> bool:
        """
        Check if movement inputs should be suppressed.
        During transitions, game ignores input.
        """
        return self.in_transition
```

---

## Summary

| Section | Purpose | Key Components |
|---------|---------|----------------|
| **4.1 HPA*** | Hierarchical pathfinding | Macro/micro pathfinding |
| **4.2 Ledge Logic** | One-way tile handling | Diode nodes, constraints |
| **4.3 Bonk Recovery** | Collision recovery | Stabilization, realignment |
| **4.4 Warp Handling** | Transition logic | Animation wait, state change |

---

**Document Version:** 1.0  
**Last Updated:** December 31, 2025  
**Protocol:** PTP-01X - Chapter 4: Navigation Engine