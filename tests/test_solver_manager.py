import json

import pytest

from mcp_ortools.solver_manager import SolverError, SolverManager


def test_parse_and_solve_optimization_model_with_documented_constraint_syntax():
    manager = SolverManager()
    model = {
        "variables": [
            {"name": "x", "domain": [0, 10]},
            {"name": "y", "domain": [0, 10]},
        ],
        "constraints": [
            "(x + y).__le__(15)",
            "x.__ge__(2 * y)",
        ],
        "objective": {
            "expression": "40 * x + 100 * y",
            "maximize": True,
        },
    }

    valid, message = manager.parse_model(json.dumps(model))
    result = manager.solve()

    assert valid is True
    assert message == "Model parsed successfully"
    assert result["status"] == "OPTIMAL"
    assert result["variables"] == {"x": 10, "y": 5}
    assert result["objective_value"] == 900
    current_solution = manager.get_current_solution()
    assert current_solution is not None
    assert current_solution["variables"] == {"x": 10, "y": 5}


def test_parse_and_solve_model_with_operator_constraint_syntax():
    manager = SolverManager()
    model = {
        "variables": [
            {"name": "vm_1_start", "domain": [0, 20]},
            {"name": "vm_2_start", "domain": [0, 20]},
            {"name": "makespan", "domain": [0, 30]},
        ],
        "constraints": [
            "vm_2_start >= vm_1_start + 10",
            "makespan >= vm_2_start + 10",
        ],
        "objective": {
            "expression": "makespan",
            "maximize": False,
        },
    }

    valid, message = manager.parse_model(json.dumps(model))
    result = manager.solve()

    assert valid is True
    assert message == "Model parsed successfully"
    assert result["status"] == "OPTIMAL"
    assert result["variables"] == {
        "vm_1_start": 0,
        "vm_2_start": 10,
        "makespan": 20,
    }


def test_parse_model_rejects_missing_variables():
    manager = SolverManager()

    valid, message = manager.parse_model(json.dumps({"constraints": []}))

    assert valid is False
    assert message == "Model must contain 'variables' field"


def test_parse_model_reports_invalid_constraint():
    manager = SolverManager()
    model = {
        "variables": [{"name": "x", "domain": [0, 10]}],
        "constraints": ["missing_var <= 5"],
    }

    valid, message = manager.parse_model(json.dumps(model))

    assert valid is False
    assert "Invalid constraint" in message
    assert "missing_var" in message


def test_solve_requires_loaded_model():
    manager = SolverManager()

    with pytest.raises(SolverError, match="No model loaded"):
        manager.solve()
