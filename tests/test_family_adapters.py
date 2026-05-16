import json

from mcp_ortools.adapters import SolverSessionManager


def test_routing_adapter_solves_small_tsp():
    manager = SolverSessionManager()
    model = {
        "distance_matrix": [
            [0, 1, 2],
            [1, 0, 4],
            [2, 4, 0],
        ],
        "num_vehicles": 1,
        "depot": 0,
    }

    valid, message, session_id = manager.submit_model("routing", json.dumps(model), "routing")
    result = manager.solve_model(session_id)

    assert valid is True
    assert message == "Model parsed successfully"
    assert result["status"] == "OPTIMAL_OR_FEASIBLE"
    assert result["routes"][0]["nodes"][0] == 0
    assert result["routes"][0]["nodes"][-1] == 0


def test_mathopt_adapter_solves_linear_program():
    manager = SolverSessionManager()
    model = {
        "variables": [{"name": "x", "lb": 0, "ub": 10}],
        "constraints": [{"expression": "x", "lb": 2, "ub": 10}],
        "objective": {"expression": "x", "maximize": True},
        "solver_type": "GLOP",
    }

    valid, _, session_id = manager.submit_model("mathopt", json.dumps(model), "mathopt")
    result = manager.solve_model(session_id)

    assert valid is True
    assert result["status"] == "OPTIMAL"
    assert result["variables"]["x"] == 10


def test_linear_solver_adapter_solves_mip():
    manager = SolverSessionManager()
    model = {
        "solver_type": "SCIP",
        "variables": [
            {"name": "x", "lb": 0, "ub": 1, "integer": True},
            {"name": "y", "lb": 0, "ub": 1, "integer": True},
        ],
        "constraints": [{"coefficients": {"x": 1, "y": 1}, "lb": 1, "ub": 1}],
        "objective": {"coefficients": {"x": 3, "y": 2}, "maximize": True},
    }

    valid, _, session_id = manager.submit_model("linear_solver", json.dumps(model), "linear")
    result = manager.solve_model(session_id)

    assert valid is True
    assert result["status"] == "OPTIMAL"
    assert result["objective_value"] == 3
    assert result["variables"]["x"] == 1


def test_graph_adapter_solves_max_flow():
    manager = SolverSessionManager()
    model = {
        "algorithm": "max_flow",
        "source": 0,
        "sink": 3,
        "arcs": [
            {"tail": 0, "head": 1, "capacity": 3},
            {"tail": 0, "head": 2, "capacity": 2},
            {"tail": 1, "head": 3, "capacity": 2},
            {"tail": 2, "head": 3, "capacity": 4},
        ],
    }

    valid, _, session_id = manager.submit_model("graph", json.dumps(model), "flow")
    result = manager.solve_model(session_id)

    assert valid is True
    assert result["status"] == "OPTIMAL"
    assert result["optimal_flow"] == 4


def test_graph_adapter_solves_min_cost_flow():
    manager = SolverSessionManager()
    model = {
        "algorithm": "min_cost_flow",
        "supplies": {"0": 2, "2": -2},
        "arcs": [
            {"tail": 0, "head": 1, "capacity": 2, "unit_cost": 1},
            {"tail": 1, "head": 2, "capacity": 2, "unit_cost": 1},
            {"tail": 0, "head": 2, "capacity": 2, "unit_cost": 5},
        ],
    }

    valid, _, session_id = manager.submit_model("graph", json.dumps(model), "min-cost")
    result = manager.solve_model(session_id)

    assert valid is True
    assert result["status"] == "OPTIMAL"
    assert result["optimal_cost"] == 4


def test_knapsack_adapter_solves_small_problem():
    manager = SolverSessionManager()
    model = {
        "values": [6, 10, 12],
        "weights": [[1, 2, 3]],
        "capacities": [5],
        "solver_type": "dynamic_programming",
    }

    valid, _, session_id = manager.submit_model("knapsack", json.dumps(model), "knapsack")
    result = manager.solve_model(session_id)

    assert valid is True
    assert result["status"] == "OPTIMAL"
    assert result["objective_value"] == 22
    assert result["packed_items"] == [1, 2]
