"""
World Navigation & Pathfinding System for PTP-01X Pokemon AI

Implements comprehensive navigation including:
- WorldGraph: Tile-based navigation graph with HM dependencies
- AStarPathfinder: A* pathfinding algorithm with heuristics
- RouteOptimizer: Multi-target TSP optimization
- AreaManager: Route mapping and location databases
- PuzzleSolver: Special area puzzle solutions (Safari Zone, Rock Tunnel, Cycling Road)
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set, Tuple, Callable
from heapq import heappush, heappop
from collections import deque
import json
import logging


logger = logging.getLogger(__name__)


class TileType(Enum):
    """Tile classification types for navigation"""
    PASSABLE = auto()
    BLOCKING = auto()
    LEDGE = auto()
    WATER = auto()
    HM_BLOCK = auto()
    WARP = auto()
    TALL_GRASS = auto()
    TRAINER_VISION = auto()
    DOOR = auto()
    STAIRS = auto()
    ITEM_BALL = auto()
    ROCK_SMASH = auto()
    BOULDER = auto()
    ICE = auto()
    TELEPORT_PAD = auto()
    DANGER = auto()


class HMMove(Enum):
    """Hidden Machine moves that affect navigation"""
    CUT = "HM01"
    FLY = "HM02"
    SURF = "HM03"
    STRENGTH = "HM04"
    FLASH = "HM05"
    ROCK_SMASH = "HM06"
    WATERFALL = "HM07"


class LocationType(Enum):
    """Types of points of interest"""
    POKEMON_CENTER = auto()
    POKEMART = auto()
    GYM = auto()
    TOWN = auto()
    ROUTE = auto()
    LANDMARK = auto()
    BUILDING = auto()
    CAVE = auto()


@dataclass
class Position:
    """2D position representation"""
    x: int
    y: int
    map_id: str = ""

    def __hash__(self) -> int:
        return hash((self.x, self.y, self.map_id))

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Position):
            return False
        return (self.x, self.y, self.map_id) == (other.x, other.y, other.map_id)

    def __lt__(self, other: "Position") -> bool:
        if not isinstance(other, Position):
            return NotImplemented
        return (self.x, self.y) < (other.x, other.y)

    def distance_to(self, other: "Position") -> int:
        return abs(self.x - other.x) + abs(self.y - other.y)

    def manhattan_heuristic(self, other: "Position") -> int:
        return abs(self.x - other.x) + abs(self.y - other.y)


@dataclass
class GraphNode:
    """Node in the navigation graph"""
    position: Position
    tile_type: TileType
    hm_requirement: Optional[HMMove] = None
    warp_destination: Optional[Position] = None
    location_type: Optional[LocationType] = None
    is_poi: bool = False
    encounter_rate: float = 0.0
    danger_level: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphEdge:
    """Edge between graph nodes"""
    from_node: Position
    to_node: Position
    cost: float = 1.0
    is_warp: bool = False
    is_ledge: bool = False
    requires_hm: Optional[HMMove] = None
    direction: str = ""


@dataclass
class PathResult:
    """Result of a pathfinding operation"""
    success: bool
    path: List[Position] = field(default_factory=list)
    total_cost: float = 0.0
    hm_requirements: List[HMMove] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    encounters_expected: int = 0
    danger_exposure: int = 0


@dataclass
class RouteSegment:
    """Segment of a multi-target route"""
    from_pos: Position
    to_pos: Position
    path: List[Position]
    estimated_cost: float
    hm_needed: Optional[HMMove] = None


@dataclass
class PointOfInterest:
    """Point of interest in the game world"""
    name: str
    position: Position
    location_type: LocationType
    map_id: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PathfindingContext:
    """Context for pathfinding decisions"""
    avoid_encounters: bool = False
    avoid_trainers: bool = False
    prefer_shortest: bool = True
    allow_hm_usage: bool = True
    current_party_hp: int = 100
    max_party_hp: int = 100
    repel_active: bool = False
    has_flash: bool = False
    grind_mode: bool = False
    time_of_day: Optional[str] = None


class WorldGraph:
    """
    Tile-based navigation graph representing the game world
    """

    def __init__(self):
        self.nodes: Dict[Position, GraphNode] = {}
        self.edges: Dict[Position, List[GraphEdge]] = {}
        self.map_dimensions: Dict[str, Tuple[int, int]] = {}
        self.warps: Dict[Position, Position] = {}
        self.hm_obstacles: Dict[Position, HMMove] = {}
        self.ledges: Dict[Position, Tuple[str, int]] = {}
        self.pois: Dict[str, PointOfInterest] = {}

    def add_node(self, node: GraphNode) -> None:
        self.nodes[node.position] = node
        if node.position not in self.edges:
            self.edges[node.position] = []

    def add_edge(self, edge: GraphEdge) -> None:
        if edge.from_node not in self.edges:
            self.edges[edge.from_node] = []
        self.edges[edge.from_node].append(edge)

        if edge.is_warp:
            self.warps[edge.from_node] = edge.to_node

        if edge.requires_hm:
            self.hm_obstacles[edge.from_node] = edge.requires_hm

    def set_map_dimensions(self, map_id: str, width: int, height: int) -> None:
        self.map_dimensions[map_id] = (width, height)

    def get_neighbors(
        self,
        position: Position,
        context: PathfindingContext
    ) -> List[GraphEdge]:
        """Get all accessible neighboring positions"""
        neighbors = self.edges.get(position, [])
        valid_neighbors = []

        for edge in neighbors:
            to_pos = edge.to_node

            if edge.requires_hm:
                if not context.allow_hm_usage:
                    continue
                hm_move = edge.requires_hm
                if hm_move == HMMove.CUT and not context.has_flash:
                    pass
                elif hm_move not in [HMMove.FLY]:
                    continue

            if edge.is_ledge:
                if context.avoid_encounters:
                    continue
                ledge_info = self.ledges.get(edge.from_node)
                if ledge_info:
                    direction = ledge_info[0]
                    if direction != edge.direction:
                        continue

            node = self.nodes.get(to_pos)
            if node and node.tile_type == TileType.BLOCKING:
                continue

            if node and node.tile_type == TileType.TRAINER_VISION:
                if context.avoid_trainers:
                    continue

            valid_neighbors.append(edge)

        return valid_neighbors

    def is_accessible(
        self,
        position: Position,
        context: PathfindingContext
    ) -> bool:
        """Check if a position is accessible"""
        node = self.nodes.get(position)
        if node is None:
            return False

        if node.tile_type == TileType.BLOCKING:
            return False

        if node.hm_requirement:
            hm = node.hm_requirement
            if context.allow_hm_usage:
                if hm == HMMove.FLASH and not context.has_flash:
                    return False

        return True

    def add_poi(self, poi: PointOfInterest) -> None:
        self.pois[poi.name] = poi
        if poi.position not in self.nodes:
            node = GraphNode(
                position=poi.position,
                tile_type=TileType.PASSABLE,
                is_poi=True,
                location_type=poi.location_type
            )
            self.nodes[poi.position] = node

    def get_poi_by_type(self, location_type: LocationType) -> List[PointOfInterest]:
        return [poi for poi in self.pois.values() if poi.location_type == location_type]

    def get_poi_by_name(self, name: str) -> Optional[PointOfInterest]:
        return self.pois.get(name)

    def get_all_pois(self) -> List[PointOfInterest]:
        return list(self.pois.values())


class AStarPathfinder:
    """
    A* pathfinding implementation with HM integration
    """

    def __init__(self, graph: WorldGraph):
        self.graph = graph
        self._cache: Dict[Tuple[Position, Position], PathResult] = {}

    def find_path(
        self,
        start: Position,
        goal: Position,
        context: PathfindingContext
    ) -> PathResult:
        cache_key = (start, goal)
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if self._is_cache_valid(cached, context):
                return cached

        result = self._astar_search(start, goal, context)
        self._cache[cache_key] = result
        return result

    def _is_cache_valid(
        self,
        cached: PathResult,
        context: PathfindingContext
    ) -> bool:
        if not cached.success:
            return False
        if context.avoid_encounters and cached.encounters_expected > 0:
            return False
        return True

    def _astar_search(
        self,
        start: Position,
        goal: Position,
        context: PathfindingContext
    ) -> PathResult:
        open_set: List[Tuple[float, Position]] = []
        came_from: Dict[Position, Position] = {}
        g_score: Dict[Position, float] = {start: 0.0}
        f_score: Dict[Position, float] = {
            start: start.manhattan_heuristic(goal)
        }

        heappush(open_set, (f_score[start], start))

        closed_set: Set[Position] = set()
        warnings: List[str] = []
        hm_requirements: Set[HMMove] = set()
        total_encounters = 0
        total_danger = 0

        while open_set:
            _, current = heappop(open_set)

            if current in closed_set:
                continue

            if current == goal:
                return self._reconstruct_path(
                    start, goal, came_from, g_score,
                    hm_requirements, warnings, total_encounters, total_danger
                )

            closed_set.add(current)

            neighbors = self.graph.get_neighbors(current, context)

            for edge in neighbors:
                neighbor = edge.to_node
                if neighbor in closed_set:
                    continue

                node = self.graph.nodes.get(neighbor)

                movement_cost = self._calculate_movement_cost(
                    current, neighbor, edge, context, node
                )

                tentative_g = g_score[current] + movement_cost

                if neighbor not in g_score or tentative_g < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f_score[neighbor] = tentative_g + neighbor.manhattan_heuristic(goal)

                    if node:
                        if edge.requires_hm:
                            hm_requirements.add(edge.requires_hm)
                        if node.tile_type == TileType.TALL_GRASS:
                            total_encounters += int(node.encounter_rate * 10)
                        if node.danger_level > 0:
                            total_danger += node.danger_level

                    heappush(open_set, (f_score[neighbor], neighbor))

        return PathResult(
            success=False,
            warnings=["No path found from {start} to {goal}"]
        )

    def _calculate_movement_cost(
        self,
        current: Position,
        neighbor: Position,
        edge: GraphEdge,
        context: PathfindingContext,
        node: Optional[GraphNode]
    ) -> float:
        base_cost = edge.cost

        if node is None:
            return base_cost

        if node.tile_type == TileType.TALL_GRASS:
            if context.avoid_encounters:
                base_cost *= 5.0
            elif context.grind_mode:
                base_cost *= 0.8
            else:
                base_cost *= 2.0

        if node.tile_type == TileType.WATER:
            if context.has_flash:
                base_cost *= 1.1
            else:
                return float('inf')

        if node.tile_type == TileType.LEDGE:
            if edge.direction == "down":
                base_cost *= 0.9
            else:
                base_cost *= 2.0

        if node.danger_level > 0:
            hp_ratio = context.current_party_hp / context.max_party_hp
            if hp_ratio < 0.3:
                base_cost *= (1 + node.danger_level * 0.5)

        return base_cost

    def _reconstruct_path(
        self,
        start: Position,
        goal: Position,
        came_from: Dict[Position, Position],
        g_score: Dict[Position, float],
        hm_requirements: Set[HMMove],
        warnings: List[str],
        encounters: int,
        danger: int
    ) -> PathResult:
        path: List[Position] = [goal]
        current = goal

        while current in came_from:
            current = came_from[current]
            path.append(current)

        path.reverse()

        if hm_requirements:
            hm_names = [hm.value for hm in hm_requirements]
            warnings.append(f"Path requires HM moves: {', '.join(hm_names)}")

        if encounters > 5:
            warnings.append(f"Expected ~{encounters} wild encounters along path")

        return PathResult(
            success=True,
            path=path,
            total_cost=g_score.get(goal, 0.0),
            hm_requirements=list(hm_requirements),
            warnings=warnings,
            encounters_expected=encounters,
            danger_exposure=danger
        )

    def find_path_with_warps(
        self,
        start: Position,
        goal: Position,
        context: PathfindingContext
    ) -> PathResult:
        if start.map_id == goal.map_id:
            return self.find_path(start, goal, context)

        result = self.find_path(start, goal, context)
        if result.success:
            return result

        warp_path = self._find_warp_sequence(start.map_id, goal.map_id, context)
        if not warp_path:
            return PathResult(
                success=False,
                warnings=["No multi-map path found"]
            )

        full_path: List[Position] = []
        total_cost = 0.0
        all_hm: Set[HMMove] = set()

        for i in range(len(warp_path) - 1):
            from_pos = warp_path[i]
            to_pos = warp_path[i + 1]

            segment = self.find_path(from_pos, to_pos, context)

            if not segment.success:
                return PathResult(
                    success=False,
                    warnings=[f"Cannot reach {to_pos} from {from_pos}"]
                )

            if i == 0:
                full_path.extend(segment.path[:-1])
            else:
                full_path.extend(segment.path)

            total_cost += segment.total_cost
            all_hm.update(segment.hm_requirements)

        full_path.append(goal)

        return PathResult(
            success=True,
            path=full_path,
            total_cost=total_cost,
            hm_requirements=list(all_hm),
            warnings=["Multi-map path using warps"]
        )

    def _find_warp_sequence(
        self,
        start_map: str,
        goal_map: str,
        context: PathfindingContext
    ) -> List[Position]:
        if start_map == goal_map:
            return []

        visited: Set[str] = set()
        queue: deque = deque()
        queue.append((start_map, []))

        while queue:
            current_map, path = queue.popleft()

            if current_map in visited:
                continue
            visited.add(current_map)

            if current_map == goal_map:
                return path

            for warp_source, warp_dest in self.graph.warps.items():
                if warp_source.map_id == current_map:
                    if warp_dest.map_id not in visited:
                        new_path = path + [warp_source]
                        queue.append((warp_dest.map_id, new_path))

        return []


class RouteOptimizer:
    """
    Multi-target route optimization using TSP-like algorithms
    """

    def __init__(self, graph: WorldGraph, pathfinder: AStarPathfinder):
        self.graph = graph
        self.pathfinder = pathfinder

    def optimize_route(
        self,
        start: Position,
        objectives: List[PointOfInterest],
        context: PathfindingContext
    ) -> Tuple[List[RouteSegment], float]:
        if not objectives:
            return [], 0.0

        objectives_with_priority = [
            (poi, poi.metadata.get("priority", 1)) for poi in objectives
        ]
        objectives_with_priority.sort(key=lambda x: -x[1])

        visited = set()
        current_pos = start
        route_segments: List[RouteSegment] = []
        total_cost = 0.0

        objectives_sorted = [obj for obj, _ in objectives_with_priority]

        while objectives_sorted:
            nearest = None
            nearest_idx = 0
            nearest_cost = float('inf')
            nearest_path: List[Position] = []
            nearest_result: Optional[PathResult] = None

            for i, objective in enumerate(objectives_sorted):
                if objective.name in visited:
                    continue

                result = self.pathfinder.find_path(
                    current_pos, objective.position, context
                )

                if result.success and result.total_cost < nearest_cost:
                    nearest = objective
                    nearest_idx = i
                    nearest_cost = result.total_cost
                    nearest_path = result.path
                    nearest_result = result

            if nearest is None:
                break

            hm_needed = None
            if nearest_result and nearest_result.hm_requirements:
                hm_needed = nearest_result.hm_requirements[0]

            route_segments.append(RouteSegment(
                from_pos=current_pos,
                to_pos=nearest.position,
                path=nearest_path,
                estimated_cost=nearest_cost,
                hm_needed=hm_needed
            ))

            total_cost += nearest_cost
            current_pos = nearest.position
            visited.add(nearest.name)
            objectives_sorted.pop(nearest_idx)

        return route_segments, total_cost

    def cluster_objectives(
        self,
        objectives: List[PointOfInterest],
        cluster_radius: int = 50
    ) -> List[List[PointOfInterest]]:
        if not objectives:
            return []

        unassigned = set(range(len(objectives)))
        clusters: List[List[PointOfInterest]] = []

        while unassigned:
            idx = unassigned.pop()
            current = objectives[idx]
            current_cluster = [current]

            to_check = list(unassigned)
            for other_idx in to_check:
                other = objectives[other_idx]
                if current.position.distance_to(other.position) <= cluster_radius:
                    current_cluster.append(other)
                    unassigned.discard(other_idx)

            clusters.append(current_cluster)

        return clusters

    def calculate_route_safety(
        self,
        route: List[RouteSegment],
        context: PathfindingContext
    ) -> float:
        if not route:
            return 0.0

        total_safety = 0.0

        for segment in route:
            segment_safety = 10.0

            for pos in segment.path:
                node = self.graph.nodes.get(pos)
                if node:
                    if node.tile_type == TileType.TALL_GRASS:
                        if not context.repel_active:
                            segment_safety -= 2.0

                    if node.danger_level > 0:
                        hp_ratio = context.current_party_hp / context.max_party_hp
                        if hp_ratio < 0.5:
                            segment_safety -= node.danger_level

            total_safety += segment_safety

        return total_safety / len(route)


class AreaManager:
    """
    Manages route mapping, gym locations, Pokemon Centers, and shops
    """

    def __init__(self, graph: WorldGraph):
        self.graph = graph
        self.routes: Dict[str, Dict] = {}
        self.gyms: Dict[str, PointOfInterest] = {}
        self.pokemon_centers: Dict[str, PointOfInterest] = {}
        self.shops: Dict[str, PointOfInterest] = {}
        self._load_area_data()

    def _load_area_data(self) -> None:
        data_path = "src/core/data/routes.json"
        try:
            with open(data_path, 'r') as f:
                data = json.load(f)
                self._import_routes(data)
        except FileNotFoundError:
            logger.warning(f"Routes data not found at {data_path}, using default data")
            self._load_default_areas()

    def _import_routes(self, data: Dict) -> None:
        for route_data in data.get("routes", []):
            self.routes[route_data["id"]] = route_data

        for gym_data in data.get("gyms", []):
            pos = Position(
                gym_data["x"], gym_data["y"],
                map_id=gym_data["map_id"]
            )
            poi = PointOfInterest(
                name=gym_data["name"],
                position=pos,
                location_type=LocationType.GYM,
                map_id=gym_data["map_id"],
                metadata={
                    "badge": gym_data.get("badge"),
                    "leader": gym_data.get("leader"),
                    "required_hm": gym_data.get("required_hm")
                }
            )
            self.gyms[gym_data["name"]] = poi
            self.graph.add_poi(poi)

        for center_data in data.get("pokemon_centers", []):
            pos = Position(
                center_data["x"], center_data["y"],
                map_id=center_data["map_id"]
            )
            poi = PointOfInterest(
                name=center_data["name"],
                position=pos,
                location_type=LocationType.POKEMON_CENTER,
                map_id=center_data["map_id"],
                metadata={}
            )
            self.pokemon_centers[center_data["name"]] = poi
            self.graph.add_poi(poi)

        for shop_data in data.get("shops", []):
            pos = Position(
                shop_data["x"], shop_data["y"],
                map_id=shop_data["map_id"]
            )
            poi = PointOfInterest(
                name=shop_data["name"],
                position=pos,
                location_type=LocationType.POKEMART,
                map_id=shop_data["map_id"],
                metadata={
                    "inventory": shop_data.get("inventory", [])
                }
            )
            self.shops[shop_data["name"]] = poi
            self.graph.add_poi(poi)

    def _load_default_areas(self) -> None:
        default_routes = [
            {"id": "route1", "name": "Route 1", "connections": ["pallet_town", "viridian_city"]},
            {"id": "route2", "name": "Route 2", "connections": ["viridian_city", "pewter_city"]},
            {"id": "route3", "name": "Route 3", "connections": ["pewter_city", "cerulean_city"]},
        ]
        self.routes.update({r["id"]: r for r in default_routes})

        default_centers = [
            {"name": "Pallet Town Center", "x": 6, "y": 10, "map_id": "pallet_town"},
            {"name": "Viridian City Center", "x": 10, "y": 12, "map_id": "viridian_city"},
            {"name": "Pewter City Center", "x": 8, "y": 8, "map_id": "pewter_city"},
        ]
        for center in default_centers:
            pos = Position(center["x"], center["y"], map_id=center["map_id"])
            poi = PointOfInterest(
                name=center["name"],
                position=pos,
                location_type=LocationType.POKEMON_CENTER,
                map_id=center["map_id"],
                metadata={}
            )
            self.pokemon_centers[center["name"]] = poi
            self.graph.add_poi(poi)

        default_gyms = [
            {"name": "Pewter Gym", "x": 7, "y": 5, "map_id": "pewter_city", "badge": "boulder", "leader": "Brock"},
            {"name": "Cerulean Gym", "x": 9, "y": 6, "map_id": "cerulean_city", "badge": "cascade", "leader": "Misty"},
        ]
        for gym in default_gyms:
            pos = Position(gym["x"], gym["y"], map_id=gym["map_id"])
            poi = PointOfInterest(
                name=gym["name"],
                position=pos,
                location_type=LocationType.GYM,
                map_id=gym["map_id"],
                metadata={"badge": gym["badge"], "leader": gym["leader"]}
            )
            self.gyms[gym["name"]] = poi
            self.graph.add_poi(poi)

        default_shops = [
            {"name": "Viridian Mart", "x": 11, "y": 10, "map_id": "viridian_city", "inventory": ["potion", "antidote"]},
            {"name": "Pewter Mart", "x": 9, "y": 9, "map_id": "pewter_city", "inventory": ["potion", "repel"]},
        ]
        for shop in default_shops:
            pos = Position(shop["x"], shop["y"], map_id=shop["map_id"])
            poi = PointOfInterest(
                name=shop["name"],
                position=pos,
                location_type=LocationType.POKEMART,
                map_id=shop["map_id"],
                metadata={"inventory": shop["inventory"]}
            )
            self.shops[shop["name"]] = poi
            self.graph.add_poi(poi)

    def get_nearest_pokemon_center(self, position: Position) -> Optional[PointOfInterest]:
        centers = list(self.pokemon_centers.values())
        if not centers:
            return None

        def sort_key(poi: PointOfInterest) -> int:
            if poi.position.map_id == position.map_id:
                return position.distance_to(poi.position)
            return position.distance_to(poi.position) + 100

        centers.sort(key=sort_key)
        return centers[0] if centers else None

    def get_nearest_gym(self, position: Position) -> Optional[PointOfInterest]:
        gyms = list(self.gyms.values())
        if not gyms:
            return None

        gyms.sort(key=lambda p: position.distance_to(p.position))
        return gyms[0] if gyms else None

    def get_all_gyms(self) -> List[PointOfInterest]:
        return list(self.gyms.values())

    def get_all_pokemon_centers(self) -> List[PointOfInterest]:
        return list(self.pokemon_centers.values())

    def get_all_shops(self) -> List[PointOfInterest]:
        return list(self.shops.values())

    def get_route(self, route_id: str) -> Optional[Dict]:
        return self.routes.get(route_id)

    def get_connection_maps(self, map_id: str) -> List[str]:
        connections = []
        for route in self.routes.values():
            if "connections" in route and map_id in route["connections"]:
                connections.extend(route["connections"])
        return list(set(connections) - {map_id})


class PuzzleSolver:
    """
    Solves special area puzzles (Safari Zone, Rock Tunnel, Cycling Road)
    """

    def __init__(self, graph: WorldGraph):
        self.graph = graph

    def solve_safari_zone(
        self,
        start: Position,
        goal: Position,
        context: PathfindingContext
    ) -> PathResult:
        return self._solve_with_terrain_constraints(start, goal, context, "safari")

    def solve_rock_tunnel(
        self,
        start: Position,
        goal: Position,
        context: PathfindingContext
    ) -> PathResult:
        if not context.has_flash:
            result = PathResult(
                success=False,
                warnings=["Flash required to navigate Rock Tunnel"]
            )
            return result

        return self._solve_with_terrain_constraints(start, goal, context, "darkness")

    def solve_cycling_road(
        self,
        start: Position,
        goal: Position,
        context: PathfindingContext
    ) -> PathResult:
        return self._solve_with_terrain_constraints(start, goal, context, "cycling")

    def _solve_with_terrain_constraints(
        self,
        start: Position,
        goal: Position,
        context: PathfindingContext,
        puzzle_type: str
    ) -> PathResult:
        modified_context = PathfindingContext(
            avoid_encounters=context.avoid_encounters,
            avoid_trainers=context.avoid_trainers,
            prefer_shortest=context.prefer_shortest,
            allow_hm_usage=context.allow_hm_usage,
            current_party_hp=context.current_party_hp,
            max_party_hp=context.max_party_hp,
            repel_active=context.repel_active,
            has_flash=context.has_flash or puzzle_type == "darkness",
            grind_mode=puzzle_type == "safari"
        )

        pathfinder = AStarPathfinder(self.graph)
        return pathfinder.find_path(start, goal, modified_context)

    def solve_ice_puzzle(
        self,
        start: Position,
        goal: Position,
        ice_positions: Set[Position]
    ) -> PathResult:
        modified_context = PathfindingContext(
            avoid_encounters=True,
            prefer_shortest=True,
            allow_hm_usage=False
        )

        pathfinder = AStarPathfinder(self.graph)

        result = pathfinder.find_path(start, goal, modified_context)

        if result.success:
            valid_path = self._validate_ice_path(result.path, ice_positions)
            return PathResult(
                success=valid_path,
                path=result.path if valid_path else [],
                total_cost=result.total_cost,
                warnings=["Ice slide physics applied" if valid_path else "Invalid ice path"]
            )

        return result

    def _validate_ice_path(
        self,
        path: List[Position],
        ice_positions: Set[Position]
    ) -> bool:
        if len(path) < 2:
            return True

        for i in range(len(path) - 1):
            current = path[i]
            next_pos = path[i + 1]

            if current in ice_positions:
                if not self._slide_in_direction(current, next_pos, ice_positions):
                    return False

        return True

    def _slide_in_direction(
        self,
        start: Position,
        direction: Position,
        ice_positions: Set[Position]
    ) -> bool:
        dx = direction.x - start.x
        dy = direction.y - start.y

        if dx != 0 and dy != 0:
            return False

        current = start
        while current in ice_positions:
            next_x = current.x + (1 if dx > 0 else -1 if dx < 0 else 0)
            next_y = current.y + (1 if dy > 0 else -1 if dy < 0 else 0)
            next_pos = Position(next_x, next_y, map_id=current.map_id)

            if next_pos not in ice_positions:
                return next_pos == direction

            current = next_pos

        return current == direction

    def solve_teleport_maze(
        self,
        start: Position,
        goal: Position,
        teleport_pads: Dict[Position, Position]
    ) -> PathResult:
        modified_context = PathfindingContext(
            avoid_encounters=True,
            prefer_shortest=True,
            allow_hm_usage=False
        )

        original_warps = self.graph.warps.copy()
        self.graph.warps.update(teleport_pads)

        pathfinder = AStarPathfinder(self.graph)
        result = pathfinder.find_path(start, goal, modified_context)

        self.graph.warps = original_warps

        if result.success and any(p in teleport_pads for p in result.path):
            result.warnings.append("Path uses teleport pads")

        return result


class NavigationSystem:
    """
    Main navigation system integrating all components
    """

    def __init__(self):
        self.graph = WorldGraph()
        self.pathfinder = AStarPathfinder(self.graph)
        self.route_optimizer = RouteOptimizer(self.graph, self.pathfinder)
        self.area_manager = AreaManager(self.graph)
        self.puzzle_solver = PuzzleSolver(self.graph)

    def navigate_to(
        self,
        start: Position,
        goal: Position,
        context: Optional[PathfindingContext] = None
    ) -> PathResult:
        if context is None:
            context = PathfindingContext()

        return self.pathfinder.find_path(start, goal, context)

    def navigate_to_poi(
        self,
        start: Position,
        poi_name: str,
        context: Optional[PathfindingContext] = None
    ) -> PathResult:
        poi = self.graph.get_poi_by_name(poi_name)
        if poi is None:
            return PathResult(
                success=False,
                warnings=[f"POI not found: {poi_name}"]
            )
        return self.navigate_to(start, poi.position, context)

    def find_heal_location(
        self,
        current_pos: Position,
        context: PathfindingContext
    ) -> Tuple[Optional[PointOfInterest], PathResult]:
        center = self.area_manager.get_nearest_pokemon_center(current_pos)
        if center is None:
            return None, PathResult(success=False, warnings=["No Pokemon Center found"])

        path_result = self.navigate_to(current_pos, center.position, context)
        return center, path_result

    def plan_multi_stop_route(
        self,
        start: Position,
        objectives: List[str],
        context: Optional[PathfindingContext] = None
    ) -> Tuple[List[RouteSegment], float]:
        if context is None:
            context = PathfindingContext()

        pois = []
        for obj_name in objectives:
            poi = self.graph.get_poi_by_name(obj_name)
            if poi:
                pois.append(poi)

        return self.route_optimizer.optimize_route(start, pois, context)

    def solve_puzzle(
        self,
        puzzle_type: str,
        start: Position,
        goal: Position,
        context: PathfindingContext
    ) -> PathResult:
        if puzzle_type == "safari":
            return self.puzzle_solver.solve_safari_zone(start, goal, context)
        elif puzzle_type == "rock_tunnel":
            return self.puzzle_solver.solve_rock_tunnel(start, goal, context)
        elif puzzle_type == "cycling_road":
            return self.puzzle_solver.solve_cycling_road(start, goal, context)
        else:
            return PathResult(
                success=False,
                warnings=[f"Unknown puzzle type: {puzzle_type}"]
            )

    def get_navigation_status(self) -> Dict[str, Any]:
        return {
            "total_nodes": len(self.graph.nodes),
            "total_edges": sum(len(edges) for edges in self.graph.edges.values()),
            "total_warps": len(self.graph.warps),
            "total_pois": len(self.graph.pois),
            "pokemon_centers": len(self.area_manager.pokemon_centers),
            "gyms": len(self.area_manager.gyms),
            "shops": len(self.area_manager.shops),
        }


def create_navigation_system() -> NavigationSystem:
    """Factory function to create and configure the navigation system"""
    nav = NavigationSystem()
    nav.area_manager._load_area_data()
    return nav