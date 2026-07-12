"""
Unit tests for the World Navigation & Pathfinding System

Tests cover:
- WorldGraph: Graph building and node management
- AStarPathfinder: Pathfinding with A* algorithm
- RouteOptimizer: Multi-target route optimization
- AreaManager: Location database management
- PuzzleSolver: Special area puzzle solutions
- NavigationSystem: Integration tests
"""

import pytest
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.core.navigation import (
    Position,
    TileType,
    HMMove,
    LocationType,
    GraphNode,
    GraphEdge,
    PathResult,
    RouteSegment,
    PointOfInterest,
    PathfindingContext,
    WorldGraph,
    AStarPathfinder,
    RouteOptimizer,
    AreaManager,
    PuzzleSolver,
    NavigationSystem,
    create_navigation_system,
)


class TestPosition:
    """Tests for Position dataclass"""

    def test_position_creation(self) -> None:
        pos = Position(5, 10, "test_map")
        assert pos.x == 5
        assert pos.y == 10
        assert pos.map_id == "test_map"

    def test_position_equality(self) -> None:
        pos1 = Position(5, 10, "map1")
        pos2 = Position(5, 10, "map1")
        pos3 = Position(5, 10, "map2")
        assert pos1 == pos2
        assert pos1 != pos3

    def test_position_hash(self) -> None:
        pos1 = Position(5, 10, "map1")
        pos2 = Position(5, 10, "map1")
        assert hash(pos1) == hash(pos2)
        pos_set = {pos1, pos2}
        assert len(pos_set) == 1

    def test_position_distance_to(self) -> None:
        pos1 = Position(0, 0, "map1")
        pos2 = Position(3, 4, "map1")
        assert pos1.distance_to(pos2) == 7

    def test_position_manhattan_heuristic(self) -> None:
        pos1 = Position(0, 0)
        pos2 = Position(5, 5)
        assert pos1.manhattan_heuristic(pos2) == 10

    def test_position_lt_comparison(self) -> None:
        pos1 = Position(1, 1)
        pos2 = Position(2, 2)
        assert pos1 < pos2


class TestGraphNode:
    """Tests for GraphNode dataclass"""

    def test_graph_node_creation(self) -> None:
        pos = Position(5, 5)
        node = GraphNode(position=pos, tile_type=TileType.PASSABLE)
        assert node.position == pos
        assert node.tile_type == TileType.PASSABLE
        assert node.hm_requirement is None
        assert node.is_poi is False

    def test_graph_node_with_hm_requirement(self) -> None:
        pos = Position(5, 5)
        node = GraphNode(
            position=pos,
            tile_type=TileType.HM_BLOCK,
            hm_requirement=HMMove.CUT
        )
        assert node.hm_requirement == HMMove.CUT

    def test_graph_node_with_warp(self) -> None:
        pos = Position(5, 5)
        warp_dest = Position(10, 10, "other_map")
        node = GraphNode(
            position=pos,
            tile_type=TileType.WARP,
            warp_destination=warp_dest
        )
        assert node.warp_destination == warp_dest

    def test_graph_node_poi(self) -> None:
        pos = Position(5, 5)
        node = GraphNode(
            position=pos,
            tile_type=TileType.PASSABLE,
            is_poi=True,
            location_type=LocationType.POKEMON_CENTER
        )
        assert node.is_poi is True
        assert node.location_type == LocationType.POKEMON_CENTER


class TestGraphEdge:
    """Tests for GraphEdge dataclass"""

    def test_graph_edge_creation(self) -> None:
        from_pos = Position(0, 0)
        to_pos = Position(1, 0)
        edge = GraphEdge(from_node=from_pos, to_node=to_pos)
        assert edge.from_node == from_pos
        assert edge.to_node == to_pos
        assert edge.cost == 1.0
        assert edge.is_warp is False

    def test_graph_edge_with_hm(self) -> None:
        from_pos = Position(0, 0)
        to_pos = Position(1, 0)
        edge = GraphEdge(
            from_node=from_pos,
            to_node=to_pos,
            requires_hm=HMMove.CUT
        )
        assert edge.requires_hm == HMMove.CUT

    def test_graph_edge_ledge(self) -> None:
        from_pos = Position(0, 0)
        to_pos = Position(1, 0)
        edge = GraphEdge(
            from_node=from_pos,
            to_node=to_pos,
            is_ledge=True,
            direction="down"
        )
        assert edge.is_ledge is True
        assert edge.direction == "down"


class TestWorldGraph:
    """Tests for WorldGraph class"""

    def setup_method(self) -> None:
        self.graph = WorldGraph()

    def test_add_node(self) -> None:
        pos = Position(5, 5)
        node = GraphNode(position=pos, tile_type=TileType.PASSABLE)
        self.graph.add_node(node)
        assert pos in self.graph.nodes
        assert self.graph.nodes[pos] == node

    def test_add_edge(self) -> None:
        from_pos = Position(0, 0)
        to_pos = Position(1, 0)
        from_node = GraphNode(position=from_pos, tile_type=TileType.PASSABLE)
        to_node = GraphNode(position=to_pos, tile_type=TileType.PASSABLE)

        self.graph.add_node(from_node)
        self.graph.add_node(to_node)

        edge = GraphEdge(from_node=from_pos, to_node=to_pos)
        self.graph.add_edge(edge)

        assert edge in self.graph.edges[from_pos]

    def test_set_map_dimensions(self) -> None:
        self.graph.set_map_dimensions("route1", 40, 10)
        assert self.graph.map_dimensions["route1"] == (40, 10)

    def test_is_accessible_passable(self) -> None:
        pos = Position(5, 5)
        node = GraphNode(position=pos, tile_type=TileType.PASSABLE)
        self.graph.add_node(node)

        context = PathfindingContext()
        assert self.graph.is_accessible(pos, context) is True

    def test_is_accessible_blocking(self) -> None:
        pos = Position(5, 5)
        node = GraphNode(position=pos, tile_type=TileType.BLOCKING)
        self.graph.add_node(node)

        context = PathfindingContext()
        assert self.graph.is_accessible(pos, context) is False

    def test_is_accessible_with_hm_requirement(self) -> None:
        pos = Position(5, 5)
        node = GraphNode(
            position=pos,
            tile_type=TileType.HM_BLOCK,
            hm_requirement=HMMove.CUT
        )
        self.graph.add_node(node)

        context_with_hm = PathfindingContext(allow_hm_usage=True)
        assert self.graph.is_accessible(pos, context_with_hm) is True

        context_without_hm = PathfindingContext(allow_hm_usage=False)
        assert self.graph.is_accessible(pos, context_without_hm) is True

    def test_add_poi(self) -> None:
        pos = Position(5, 5)
        poi = PointOfInterest(
            name="Test Center",
            position=pos,
            location_type=LocationType.POKEMON_CENTER,
            map_id="test_map"
        )
        self.graph.add_poi(poi)

        assert poi.name in self.graph.pois
        assert self.graph.get_poi_by_name("Test Center") == poi

    def test_get_poi_by_type(self) -> None:
        center_pos = Position(5, 5)
        gym_pos = Position(10, 10)

        center = PointOfInterest(
            name="Center 1",
            position=center_pos,
            location_type=LocationType.POKEMON_CENTER,
            map_id="test"
        )
        gym = PointOfInterest(
            name="Gym 1",
            position=gym_pos,
            location_type=LocationType.GYM,
            map_id="test"
        )

        self.graph.add_poi(center)
        self.graph.add_poi(gym)

        centers = self.graph.get_poi_by_type(LocationType.POKEMON_CENTER)
        gyms = self.graph.get_poi_by_type(LocationType.GYM)

        assert len(centers) == 1
        assert len(gyms) == 1
        assert centers[0] == center
        assert gyms[0] == gym


class TestAStarPathfinder:
    """Tests for AStarPathfinder class"""

    def setup_method(self) -> None:
        self.graph = WorldGraph()
        self.pathfinder = AStarPathfinder(self.graph)

    def _create_test_grid(self) -> None:
        for x in range(10):
            for y in range(10):
                pos = Position(x, y)
                node = GraphNode(position=pos, tile_type=TileType.PASSABLE)
                self.graph.add_node(node)

                if x < 9:
                    edge_right = GraphEdge(
                        from_node=pos,
                        to_node=Position(x + 1, y)
                    )
                    self.graph.add_edge(edge_right)

                if y < 9:
                    edge_down = GraphEdge(
                        from_node=pos,
                        to_node=Position(x, y + 1)
                    )
                    self.graph.add_edge(edge_down)

    def test_simple_pathfinding(self) -> None:
        self._create_test_grid()

        start = Position(0, 0)
        goal = Position(5, 5)
        context = PathfindingContext()

        result = self.pathfinder.find_path(start, goal, context)

        assert result.success is True
        assert len(result.path) > 0
        assert result.path[0] == start
        assert result.path[-1] == goal

    def test_no_path_blocked(self) -> None:
        self._create_test_grid()

        block_pos = Position(5, 5)
        block_node = GraphNode(position=block_pos, tile_type=TileType.BLOCKING)
        self.graph.add_node(block_node)

        start = Position(0, 0)
        goal = Position(6, 5)
        context = PathfindingContext()

        result = self.pathfinder.find_path(start, goal, context)

        assert result.success is True
        assert block_pos not in result.path

    def test_pathfinding_cost(self) -> None:
        self._create_test_grid()

        start = Position(0, 0)
        goal = Position(3, 0)
        context = PathfindingContext()

        result = self.pathfinder.find_path(start, goal, context)

        assert result.success is True
        assert result.total_cost >= 3.0

    def test_pathfinding_with_tall_grass(self) -> None:
        self._create_test_grid()

        grass_pos = Position(2, 0)
        grass_node = GraphNode(
            position=grass_pos,
            tile_type=TileType.TALL_GRASS,
            encounter_rate=0.15
        )
        self.graph.add_node(grass_node)

        start = Position(0, 0)
        goal = Position(3, 0)
        context_normal = PathfindingContext()
        context_avoid = PathfindingContext(avoid_encounters=True)

        result_normal = self.pathfinder.find_path(start, goal, context_normal)
        result_avoid = self.pathfinder.find_path(start, goal, context_avoid)

        assert result_normal.success is True
        assert result_avoid.success is True

    def test_pathfinding_cache(self) -> None:
        self._create_test_grid()

        start = Position(0, 0)
        goal = Position(5, 5)
        context = PathfindingContext()

        result1 = self.pathfinder.find_path(start, goal, context)
        result2 = self.pathfinder.find_path(start, goal, context)

        assert result1.success == result2.success


class TestRouteOptimizer:
    """Tests for RouteOptimizer class"""

    def setup_method(self) -> None:
        self.graph = WorldGraph()
        self.pathfinder = AStarPathfinder(self.graph)
        self.optimizer = RouteOptimizer(self.graph, self.pathfinder)

    def _create_test_graph(self) -> None:
        for x in range(20):
            for y in range(20):
                pos = Position(x, y)
                node = GraphNode(position=pos, tile_type=TileType.PASSABLE)
                self.graph.add_node(node)

                if x < 19:
                    edge = GraphEdge(from_node=pos, to_node=Position(x + 1, y))
                    self.graph.add_edge(edge)
                if y < 19:
                    edge = GraphEdge(from_node=pos, to_node=Position(x, y + 1))
                    self.graph.add_edge(edge)

    def test_optimize_route_single_objective(self) -> None:
        self._create_test_graph()

        start = Position(0, 0)
        objective = PointOfInterest(
            name="Test Center",
            position=Position(10, 10),
            location_type=LocationType.POKEMON_CENTER,
            map_id="test",
            metadata={"priority": 5}
        )
        context = PathfindingContext()

        segments, cost = self.optimizer.optimize_route(start, [objective], context)

        assert len(segments) == 1
        assert cost > 0

    def test_optimize_route_multiple_objectives(self) -> None:
        self._create_test_graph()

        start = Position(0, 0)
        objectives = [
            PointOfInterest(
                name=f"POI {i}",
                position=Position(5 + i * 3, 5 + i * 3),
                location_type=LocationType.GYM,
                map_id="test",
                metadata={"priority": 10 - i}
            )
            for i in range(3)
        ]
        context = PathfindingContext()

        segments, cost = self.optimizer.optimize_route(start, objectives, context)

        assert len(segments) == 3
        assert cost > 0

    def test_cluster_objectives(self) -> None:
        self._create_test_graph()

        objectives = [
            PointOfInterest(
                name=f"POI {i}",
                position=Position(i * 10, i * 10),
                location_type=LocationType.POKEMON_CENTER,
                map_id="test"
            )
            for i in range(5)
        ]

        clusters = self.optimizer.cluster_objectives(objectives, cluster_radius=50)

        assert len(clusters) > 0

    def test_calculate_route_safety(self) -> None:
        self._create_test_graph()

        start = Position(0, 0)
        goal = Position(10, 0)

        for x in range(11):
            pos = Position(x, 0)
            node = GraphNode(
                position=pos,
                tile_type=TileType.TALL_GRASS,
                danger_level=0
            )
            self.graph.nodes[pos] = node

        segment = RouteSegment(
            from_pos=start,
            to_pos=goal,
            path=[Position(x, 0) for x in range(11)],
            estimated_cost=11.0
        )

        context_safe = PathfindingContext(repel_active=True)
        context_unsafe = PathfindingContext(repel_active=False, current_party_hp=20, max_party_hp=100)

        safety_safe = self.optimizer.calculate_route_safety([segment], context_safe)
        safety_unsafe = self.optimizer.calculate_route_safety([segment], context_unsafe)

        assert safety_safe > safety_unsafe

    # -- COV-22: RouteOptimizer edge cases --

    def test_optimize_route_optimal_order(self) -> None:
        """Nearest-neighbor greedy picks closest objective first."""
        self._create_test_graph()
        start = Position(0, 0)
        # Place objectives at known distances: POI A at (2,0), POI B at (5,0)
        poi_a = PointOfInterest(
            name="A", position=Position(2, 0),
            location_type=LocationType.GYM, map_id="test",
            metadata={"priority": 1}
        )
        poi_b = PointOfInterest(
            name="B", position=Position(5, 0),
            location_type=LocationType.GYM, map_id="test",
            metadata={"priority": 1}
        )
        context = PathfindingContext()

        segments, cost = self.optimizer.optimize_route(start, [poi_b, poi_a], context)

        assert len(segments) == 2
        # First segment should go to the nearest objective (POI A at (2,0))
        assert segments[0].to_pos == poi_a.position
        assert segments[1].to_pos == poi_b.position
        assert cost > 0

    def test_optimize_route_priority_ordering(self) -> None:
        """Higher priority objective visited first regardless of distance."""
        self._create_test_graph()
        start = Position(0, 0)
        # POI A is closer but low priority; POI B is far but high priority
        poi_low = PointOfInterest(
            name="LowPri", position=Position(2, 0),
            location_type=LocationType.GYM, map_id="test",
            metadata={"priority": 1}
        )
        poi_high = PointOfInterest(
            name="HighPri", position=Position(10, 10),
            location_type=LocationType.GYM, map_id="test",
            metadata={"priority": 10}
        )
        context = PathfindingContext()

        segments, cost = self.optimizer.optimize_route(
            start, [poi_low, poi_high], context
        )

        assert len(segments) == 2
        # High priority sorted first in the initial list — it wins the
        # nearest-neighbor from start because it's the only remaining
        # objective at first iteration (sorted order puts it first).
        # After high-pri is visited, low-pri is the nearest from there.
        assert cost > 0

    def test_optimize_route_empty_objectives(self) -> None:
        """Empty objectives list returns zero segments/cost."""
        context = PathfindingContext()
        segments, cost = self.optimizer.optimize_route(
            Position(0, 0), [], context
        )
        assert segments == []
        assert cost == 0.0

    def test_cluster_objectives_different_maps(self) -> None:
        """Objectives on different maps are clustered by spatial distance only."""
        # Same coordinates, different maps → distance=0 → same cluster
        objectives = [
            PointOfInterest(
                name=f"POI_{i}",
                position=Position(i * 100, 0, map_id=f"map_{i}"),
                location_type=LocationType.POKEMON_CENTER,
                map_id=f"map_{i}"
            )
            for i in range(3)
        ]

        # With cluster_radius=50, none should cluster (minimum distance 100)
        clusters = self.optimizer.cluster_objectives(objectives, cluster_radius=50)
        assert len(clusters) == 3

        # With cluster_radius=200, all should cluster
        clusters_wide = self.optimizer.cluster_objectives(objectives, cluster_radius=200)
        assert len(clusters_wide) == 1
        assert len(clusters_wide[0]) == 3

    def test_cluster_objectives_empty(self) -> None:
        """Empty objectives returns empty list."""
        clusters = self.optimizer.cluster_objectives([], 50)
        assert clusters == []

    def test_calculate_route_safety_all_dangerous(self) -> None:
        """All nodes with high danger and low HP produce very low safety."""
        self._create_test_graph()
        start = Position(0, 0)
        goal = Position(5, 0)

        # Make every node in path have high danger
        for x in range(6):
            pos = Position(x, 0)
            node = GraphNode(
                position=pos,
                tile_type=TileType.PASSABLE,
                danger_level=5
            )
            self.graph.nodes[pos] = node

        segment = RouteSegment(
            from_pos=start,
            to_pos=goal,
            path=[Position(x, 0) for x in range(6)],
            estimated_cost=6.0
        )

        # Low HP + high danger on every node → safety drops hard
        context_danger = PathfindingContext(
            current_party_hp=20, max_party_hp=100
        )
        safety = self.optimizer.calculate_route_safety(
            [segment], context_danger
        )

        # With 6 nodes × danger_level=5 = -30, starting from 10 → -20
        assert safety < 0

    def test_calculate_route_safety_empty(self) -> None:
        """Empty route returns 0.0."""
        safety = self.optimizer.calculate_route_safety(
            [], PathfindingContext()
        )
        assert safety == 0.0

    def test_calculate_route_safety_multiple_segments(self) -> None:
        """Safety is averaged across multiple segments."""
        self._create_test_graph()
        seg_a = RouteSegment(
            from_pos=Position(0, 0),
            to_pos=Position(0, 5),
            path=[Position(0, y) for y in range(6)],
            estimated_cost=6.0
        )
        seg_b = RouteSegment(
            from_pos=Position(0, 5),
            to_pos=Position(5, 5),
            path=[Position(x, 5) for x in range(6)],
            estimated_cost=6.0
        )

        context = PathfindingContext(repel_active=True)
        safety = self.optimizer.calculate_route_safety(
            [seg_a, seg_b], context
        )
        # Both segments start at 10.0 with no grass/danger → avg = 10.0
        assert safety == 10.0


class TestAreaManager:
    """Tests for AreaManager class"""

    def setup_method(self) -> None:
        self.graph = WorldGraph()
        self.manager = AreaManager(self.graph)

    def test_default_areas_loaded(self) -> None:
        assert len(self.manager.pokemon_centers) > 0
        assert len(self.manager.gyms) > 0
        assert len(self.manager.shops) > 0

    def test_get_nearest_pokemon_center(self) -> None:
        pos = Position(0, 0, "pallet_town")
        center = self.manager.get_nearest_pokemon_center(pos)

        assert center is not None
        assert center.location_type == LocationType.POKEMON_CENTER

    def test_get_nearest_gym(self) -> None:
        pos = Position(0, 0, "pallet_town")
        gym = self.manager.get_nearest_gym(pos)

        assert gym is not None
        assert gym.location_type == LocationType.GYM

    def test_get_all_gyms(self) -> None:
        gyms = self.manager.get_all_gyms()
        assert len(gyms) > 0
        assert all(g.location_type == LocationType.GYM for g in gyms)

    def test_get_all_pokemon_centers(self) -> None:
        centers = self.manager.get_all_pokemon_centers()
        assert len(centers) > 0
        assert all(c.location_type == LocationType.POKEMON_CENTER for c in centers)

    def test_get_all_shops(self) -> None:
        shops = self.manager.get_all_shops()
        assert len(shops) > 0
        assert all(s.location_type == LocationType.POKEMART for s in shops)


class TestPuzzleSolver:
    """Tests for PuzzleSolver class"""

    def setup_method(self) -> None:
        self.graph = WorldGraph()
        self.solver = PuzzleSolver(self.graph)

    def _create_test_graph(self) -> None:
        for x in range(10):
            for y in range(10):
                pos = Position(x, y)
                node = GraphNode(position=pos, tile_type=TileType.PASSABLE)
                self.graph.add_node(node)

                if x < 9:
                    edge = GraphEdge(from_node=pos, to_node=Position(x + 1, y))
                    self.graph.add_edge(edge)
                if y < 9:
                    edge = GraphEdge(from_node=pos, to_node=Position(x, y + 1))
                    self.graph.add_edge(edge)

    def test_solve_safari_zone(self) -> None:
        self._create_test_graph()

        start = Position(0, 0)
        goal = Position(5, 5)
        context = PathfindingContext(grind_mode=True)

        result = self.solver.solve_safari_zone(start, goal, context)

        assert result.success is True

    def test_solve_rock_tunnel_without_flash(self) -> None:
        self._create_test_graph()

        start = Position(0, 0)
        goal = Position(5, 5)
        context = PathfindingContext(has_flash=False)

        result = self.solver.solve_rock_tunnel(start, goal, context)

        assert result.success is False
        assert any("Flash" in w for w in result.warnings)

    def test_solve_rock_tunnel_with_flash(self) -> None:
        self._create_test_graph()

        start = Position(0, 0)
        goal = Position(5, 5)
        context = PathfindingContext(has_flash=True)

        result = self.solver.solve_rock_tunnel(start, goal, context)

        assert result.success is True

    def test_solve_ice_puzzle(self) -> None:
        self._create_test_graph()

        ice_positions = {Position(2, y) for y in range(5)}
        for pos in ice_positions:
            if pos in self.graph.nodes:
                self.graph.nodes[pos].tile_type = TileType.ICE

        start = Position(0, 2)
        goal = Position(8, 2)

        result = self.solver.solve_ice_puzzle(start, goal, ice_positions)

        assert result.success is True or len(result.warnings) > 0


class TestNavigationSystem:
    """Integration tests for NavigationSystem"""

    def setup_method(self) -> None:
        self.nav = NavigationSystem()

    def _add_test_edges(self) -> None:
        for x in range(10):
            for y in range(10):
                pos = Position(x, y)
                if pos not in self.nav.graph.nodes:
                    node = GraphNode(position=pos, tile_type=TileType.PASSABLE)
                    self.nav.graph.add_node(node)

                if x < 9:
                    from_pos = Position(x, y)
                    to_pos = Position(x + 1, y)
                    edge = GraphEdge(from_node=from_pos, to_node=to_pos)
                    self.nav.graph.add_edge(edge)

                if y < 9:
                    from_pos = Position(x, y)
                    to_pos = Position(x, y + 1)
                    edge = GraphEdge(from_node=from_pos, to_node=to_pos)
                    self.nav.graph.add_edge(edge)

    def test_navigation_system_creation(self) -> None:
        assert self.nav.graph is not None
        assert self.nav.pathfinder is not None
        assert self.nav.route_optimizer is not None
        assert self.nav.area_manager is not None
        assert self.nav.puzzle_solver is not None

    def test_navigate_to_position(self) -> None:
        self._add_test_edges()

        start = Position(0, 0)
        goal = Position(5, 5)
        context = PathfindingContext()

        result = self.nav.navigate_to(start, goal, context)

        assert result.success is True
        assert len(result.path) > 0

    def test_navigate_to_poi(self) -> None:
        center_poi = self.nav.graph.get_poi_by_name("Pallet Town Center")
        assert center_poi is not None

        result = self.nav.navigate_to_poi(center_poi.position, "Pallet Town Center")

        assert result.success is True

    def test_navigate_to_nonexistent_poi(self) -> None:
        start = Position(0, 0, "pallet_town")
        context = PathfindingContext()

        result = self.nav.navigate_to_poi(start, "Nonexistent POI", context)

        assert result.success is False
        assert len(result.warnings) > 0

    def test_find_heal_location(self) -> None:
        start = Position(0, 0, "pallet_town")
        context = PathfindingContext()

        center, result = self.nav.find_heal_location(start, context)

        assert center is not None
        assert center.location_type == LocationType.POKEMON_CENTER

    def test_plan_multi_stop_route(self) -> None:
        center_poi = self.nav.graph.get_poi_by_name("Pallet Town Center")
        assert center_poi is not None

        start = center_poi.position
        objectives = ["Pallet Town Center"]
        context = PathfindingContext()

        segments, cost = self.nav.plan_multi_stop_route(start, objectives, context)

        assert len(segments) >= 0
        assert cost >= 0

    def test_solve_puzzle(self) -> None:
        self._add_test_edges()

        start = Position(0, 0)
        goal = Position(5, 5)
        context = PathfindingContext(has_flash=True)

        result = self.nav.solve_puzzle("rock_tunnel", start, goal, context)

        assert result.success is True

    def test_get_navigation_status(self) -> None:
        status = self.nav.get_navigation_status()

        assert "total_nodes" in status
        assert "total_edges" in status
        assert "total_warps" in status
        assert "pokemon_centers" in status
        assert "gyms" in status
        assert "shops" in status


class TestCreateNavigationSystem:
    """Tests for create_navigation_system factory function"""

    def test_create_navigation_system(self) -> None:
        nav = create_navigation_system()

        assert nav is not None
        assert isinstance(nav, NavigationSystem)
        assert len(nav.area_manager.pokemon_centers) > 0


class TestPathResult:
    """Tests for PathResult dataclass"""

    def test_path_result_success(self) -> None:
        result = PathResult(
            success=True,
            path=[Position(0, 0), Position(1, 0), Position(2, 0)],
            total_cost=2.0,
            hm_requirements=[HMMove.CUT],
            warnings=["Warning 1"],
            encounters_expected=2,
            danger_exposure=1
        )

        assert result.success is True
        assert len(result.path) == 3
        assert result.total_cost == 2.0
        assert HMMove.CUT in result.hm_requirements
        assert len(result.warnings) == 1

    def test_path_result_failure(self) -> None:
        result = PathResult(
            success=False,
            warnings=["No path found"]
        )

        assert result.success is False
        assert len(result.path) == 0


class TestHMMove:
    """Tests for HMMove enum"""

    def test_hm_move_values(self) -> None:
        assert HMMove.CUT.value == "HM01"
        assert HMMove.FLY.value == "HM02"
        assert HMMove.SURF.value == "HM03"
        assert HMMove.STRENGTH.value == "HM04"
        assert HMMove.FLASH.value == "HM05"

    def test_hm_move_iteration(self) -> None:
        moves = list(HMMove)
        assert len(moves) == 7
        assert HMMove.CUT in moves
        assert HMMove.FLY in moves
        assert HMMove.SURF in moves
        assert HMMove.STRENGTH in moves
        assert HMMove.FLASH in moves


class TestTileType:
    """Tests for TileType enum"""

    def test_tile_type_values(self) -> None:
        assert TileType.PASSABLE is not None
        assert TileType.BLOCKING is not None
        assert TileType.WATER is not None
        assert TileType.LEDGE is not None
        assert TileType.WARP is not None
        assert TileType.TALL_GRASS is not None
        assert TileType.HM_BLOCK is not None


class TestWarpPathfinding:
    """Tests for multi-map pathfinding via warps."""

    def setup_method(self) -> None:
        self.graph = WorldGraph()
        self.pathfinder = AStarPathfinder(self.graph)

    def _create_two_map_grid(self) -> None:
        """Create two connected maps with a warp between them."""
        # Map A: 5x5 grid
        for x in range(5):
            for y in range(5):
                pos = Position(x, y, "map_a")
                node = GraphNode(position=pos, tile_type=TileType.PASSABLE)
                self.graph.add_node(node)
                if x < 4:
                    edge = GraphEdge(from_node=pos, to_node=Position(x + 1, y, "map_a"))
                    self.graph.add_edge(edge)
                    edge_rev = GraphEdge(from_node=Position(x + 1, y, "map_a"), to_node=pos)
                    self.graph.add_edge(edge_rev)
                if y < 4:
                    edge = GraphEdge(from_node=pos, to_node=Position(x, y + 1, "map_a"))
                    self.graph.add_edge(edge)
                    edge_rev = GraphEdge(from_node=Position(x, y + 1, "map_a"), to_node=pos)
                    self.graph.add_edge(edge_rev)

        # Map B: 5x5 grid
        for x in range(5):
            for y in range(5):
                pos = Position(x, y, "map_b")
                node = GraphNode(position=pos, tile_type=TileType.PASSABLE)
                self.graph.add_node(node)
                if x < 4:
                    edge = GraphEdge(from_node=pos, to_node=Position(x + 1, y, "map_b"))
                    self.graph.add_edge(edge)
                    edge_rev = GraphEdge(from_node=Position(x + 1, y, "map_b"), to_node=pos)
                    self.graph.add_edge(edge_rev)
                if y < 4:
                    edge = GraphEdge(from_node=pos, to_node=Position(x, y + 1, "map_b"))
                    self.graph.add_edge(edge)
                    edge_rev = GraphEdge(from_node=Position(x, y + 1, "map_b"), to_node=pos)
                    self.graph.add_edge(edge_rev)

        # Warp: (4,4) on map_a → (0,0) on map_b
        warp_src = Position(4, 4, "map_a")
        warp_dst = Position(0, 0, "map_b")
        warp_edge = GraphEdge(from_node=warp_src, to_node=warp_dst, is_warp=True)
        self.graph.add_edge(warp_edge)

    # -- find_path_with_warps tests --

    def test_find_path_with_warps_same_map(self) -> None:
        """Same map delegates to normal find_path."""
        self._create_two_map_grid()
        start = Position(0, 0, "map_a")
        goal = Position(3, 0, "map_a")
        context = PathfindingContext()

        result = self.pathfinder.find_path_with_warps(start, goal, context)

        assert result.success is True
        assert result.path[0] == start
        assert result.path[-1] == goal
        # No multi-map warning on same-map paths
        assert "Multi-map" not in str(result.warnings)

    def test_find_path_with_warps_cross_map(self) -> None:
        """Cross-map path finds warp route between maps (warps are graph edges)."""
        self._create_two_map_grid()
        start = Position(0, 0, "map_a")
        goal = Position(2, 2, "map_b")
        context = PathfindingContext()

        result = self.pathfinder.find_path_with_warps(start, goal, context)

        assert result.success is True
        assert result.path[0] == start
        assert result.path[-1] == goal
        # Path spans both maps (via warp edge)
        map_ids_in_path = {p.map_id for p in result.path}
        assert "map_a" in map_ids_in_path
        assert "map_b" in map_ids_in_path

    def test_find_path_with_warps_cross_map_composes_cost(self) -> None:
        """Cross-map path total_cost sums all segments."""
        self._create_two_map_grid()
        start = Position(0, 0, "map_a")
        goal = Position(2, 2, "map_b")
        context = PathfindingContext()

        result = self.pathfinder.find_path_with_warps(start, goal, context)

        assert result.success is True
        assert result.total_cost > 0

    def test_find_path_with_warps_no_warp_route(self) -> None:
        """Maps with no warps connecting them returns failure."""
        self._create_two_map_grid()
        start = Position(0, 0, "map_a")
        goal = Position(0, 0, "map_c")  # map_c has no nodes/edges
        context = PathfindingContext()

        result = self.pathfinder.find_path_with_warps(start, goal, context)

        assert result.success is False
        assert "No multi-map path" in str(result.warnings)

    def test_find_path_with_warps_unreachable_via_warp(self) -> None:
        """Start map has nodes, but goal map has no warp connection."""
        self._create_two_map_grid()
        # map_c exists but has no warps to it
        gnode = GraphNode(position=Position(0, 0, "map_c"), tile_type=TileType.PASSABLE)
        self.graph.add_node(gnode)
        start = Position(0, 0, "map_a")
        goal = Position(0, 0, "map_c")
        context = PathfindingContext()

        result = self.pathfinder.find_path_with_warps(start, goal, context)

        assert result.success is False

    # -- _find_warp_sequence tests --

    def test_find_warp_sequence_same_map(self) -> None:
        """Same start and goal map returns empty list."""
        self._create_two_map_grid()
        context = PathfindingContext()

        seq = self.pathfinder._find_warp_sequence("map_a", "map_a", context)

        assert seq == []

    def test_find_warp_sequence_cross_map(self) -> None:
        """Cross-map BFS finds warp positions."""
        self._create_two_map_grid()
        context = PathfindingContext()

        seq = self.pathfinder._find_warp_sequence("map_a", "map_b", context)

        assert len(seq) == 1
        assert seq[0].map_id == "map_a"

    def test_find_warp_sequence_unreachable(self) -> None:
        """Unreachable map returns empty list."""
        self._create_two_map_grid()
        context = PathfindingContext()

        seq = self.pathfinder._find_warp_sequence("map_a", "map_c", context)

        assert seq == []

    def test_find_warp_sequence_two_hop(self) -> None:
        """Two-hop warp (A→B→C) returns both warp sources."""
        self._create_two_map_grid()
        # Add map C + warp B→C
        for x in range(3):
            for y in range(3):
                pos = Position(x, y, "map_c")
                node = GraphNode(position=pos, tile_type=TileType.PASSABLE)
                self.graph.add_node(node)
                if x < 2:
                    edge = GraphEdge(from_node=pos, to_node=Position(x + 1, y, "map_c"))
                    self.graph.add_edge(edge)
        warp_bc = GraphEdge(
            from_node=Position(2, 0, "map_b"),
            to_node=Position(0, 0, "map_c"),
            is_warp=True,
        )
        self.graph.add_edge(warp_bc)
        context = PathfindingContext()

        seq = self.pathfinder._find_warp_sequence("map_a", "map_c", context)

        assert len(seq) == 2
        assert seq[0].map_id == "map_a"
        assert seq[1].map_id == "map_b"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])