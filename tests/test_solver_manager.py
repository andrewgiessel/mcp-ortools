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


def test_parse_and_solve_model_with_structured_all_different_constraint():
    manager = SolverManager()
    model = {
        "variables": [
            {"name": "x", "domain": [1, 3]},
            {"name": "y", "domain": [1, 3]},
            {"name": "z", "domain": [1, 3]},
        ],
        "constraints": [
            {"type": "all_different", "variables": ["x", "y", "z"]},
            "x + y + z == 6",
        ],
    }

    valid, message = manager.parse_model(json.dumps(model))
    result = manager.solve()

    assert valid is True
    assert message == "Model parsed successfully"
    assert result["status"] == "OPTIMAL"
    assert sorted(result["variables"].values()) == [1, 2, 3]


def test_parse_and_solve_model_with_scheduling_intervals_and_no_overlap():
    manager = SolverManager()
    model = {
        "variables": [
            {"name": "task_1_start", "domain": [0, 10]},
            {"name": "task_1_end", "domain": [0, 10]},
            {"name": "task_2_start", "domain": [0, 10]},
            {"name": "task_2_end", "domain": [0, 10]},
            {"name": "makespan", "domain": [0, 10]},
        ],
        "intervals": [
            {"name": "task_1", "start": "task_1_start", "size": 3, "end": "task_1_end"},
            {"name": "task_2", "start": "task_2_start", "size": 4, "end": "task_2_end"},
        ],
        "constraints": [
            {"type": "no_overlap", "intervals": ["task_1", "task_2"]},
            {"type": "max_equality", "target": "makespan", "expressions": ["task_1_end", "task_2_end"]},
        ],
        "objective": {"expression": "makespan", "maximize": False},
    }

    valid, message = manager.parse_model(json.dumps(model))
    result = manager.solve()

    assert valid is True
    assert message == "Model parsed successfully"
    assert result["status"] == "OPTIMAL"
    assert result["objective_value"] == 7
    assert result["variables"]["makespan"] == 7
    assert (
        result["variables"]["task_1_end"] <= result["variables"]["task_2_start"]
        or result["variables"]["task_2_end"] <= result["variables"]["task_1_start"]
    )


def test_parse_and_solve_model_with_cumulative_constraint_and_hints():
    manager = SolverManager()
    model = {
        "variables": [
            {"name": "task_1_start", "domain": [0, 10]},
            {"name": "task_1_end", "domain": [0, 10]},
            {"name": "task_2_start", "domain": [0, 10]},
            {"name": "task_2_end", "domain": [0, 10]},
            {"name": "makespan", "domain": [0, 10]},
        ],
        "intervals": [
            {"name": "task_1", "start": "task_1_start", "size": 3, "end": "task_1_end"},
            {"name": "task_2", "start": "task_2_start", "size": 4, "end": "task_2_end"},
        ],
        "constraints": [
            {"type": "cumulative", "intervals": ["task_1", "task_2"], "demands": [2, 2], "capacity": 3},
            {"type": "max_equality", "target": "makespan", "expressions": ["task_1_end", "task_2_end"]},
        ],
        "hints": {
            "task_1_start": 0,
            "task_1_end": 3,
            "task_2_start": 3,
            "task_2_end": 7,
            "makespan": 7,
        },
        "objective": {"expression": "makespan", "maximize": False},
    }

    valid, message = manager.parse_model(json.dumps(model))
    result = manager.solve()

    assert valid is True
    assert message == "Model parsed successfully"
    assert result["status"] == "OPTIMAL"
    assert result["objective_value"] == 7
    assert result["variables"]["makespan"] == 7


def test_parse_and_solve_model_with_boolean_and_reified_constraints():
    manager = SolverManager()
    model = {
        "variables": [
            {"name": "a", "domain": [0, 1]},
            {"name": "b", "domain": [0, 1]},
            {"name": "c", "domain": [0, 1]},
            {"name": "x", "domain": [0, 5]},
        ],
        "constraints": [
            {"type": "exactly_one", "literals": ["a", "b"]},
            {"type": "implication", "if": "a", "then": "c"},
            {"type": "linear", "expression": "a == 1"},
            {"type": "linear", "expression": "x == 5", "enforce_if": "c"},
        ],
    }

    valid, message = manager.parse_model(json.dumps(model))
    result = manager.solve()

    assert valid is True
    assert message == "Model parsed successfully"
    assert result["status"] == "OPTIMAL"
    assert result["variables"] == {"a": 1, "b": 0, "c": 1, "x": 5}


def test_parse_and_solve_model_with_tables_element_and_arithmetic_equalities():
    manager = SolverManager()
    model = {
        "variables": [
            {"name": "index", "domain": [0, 2]},
            {"name": "value", "domain": [0, 10]},
            {"name": "x", "domain": [0, 10]},
            {"name": "y", "domain": [1, 10]},
            {"name": "product", "domain": [0, 100]},
            {"name": "quotient", "domain": [0, 10]},
            {"name": "remainder", "domain": [0, 10]},
            {"name": "abs_diff", "domain": [0, 10]},
        ],
        "constraints": [
            {"type": "linear", "expression": "index == 2"},
            {"type": "linear", "expression": "x == 5"},
            {"type": "linear", "expression": "y == 2"},
            {"type": "allowed_assignments", "expressions": ["x", "y"], "tuples": [[5, 2]]},
            {"type": "element", "index": "index", "expressions": [2, 4, 6], "target": "value"},
            {"type": "multiplication_equality", "target": "product", "expressions": ["x", "y"]},
            {"type": "division_equality", "target": "quotient", "num": "x", "denom": "y"},
            {"type": "modulo_equality", "target": "remainder", "expression": "x", "mod": "y"},
            {"type": "abs_equality", "target": "abs_diff", "expression": "x - value"},
        ],
    }

    valid, message = manager.parse_model(json.dumps(model))
    result = manager.solve()

    assert valid is True
    assert message == "Model parsed successfully"
    assert result["status"] == "OPTIMAL"
    assert result["variables"]["value"] == 6
    assert result["variables"]["product"] == 10
    assert result["variables"]["quotient"] == 2
    assert result["variables"]["remainder"] == 1
    assert result["variables"]["abs_diff"] == 1


def test_parse_and_solve_model_with_automaton_inverse_and_map_domain():
    manager = SolverManager()
    model = {
        "variables": [
            {"name": "s0", "domain": [0, 1]},
            {"name": "s1", "domain": [0, 1]},
            {"name": "s2", "domain": [0, 1]},
            {"name": "p0", "domain": [0, 1]},
            {"name": "p1", "domain": [0, 1]},
            {"name": "q0", "domain": [0, 1]},
            {"name": "q1", "domain": [0, 1]},
            {"name": "mapped", "domain": [0, 2]},
            {"name": "is_0", "domain": [0, 1]},
            {"name": "is_1", "domain": [0, 1]},
            {"name": "is_2", "domain": [0, 1]},
        ],
        "constraints": [
            {
                "type": "automaton",
                "expressions": ["s0", "s1", "s2"],
                "starting_state": 0,
                "final_states": [1],
                "transitions": [[0, 0, 0], [0, 1, 1], [1, 1, 0], [1, 0, 1]],
            },
            {"type": "linear", "expression": "s0 + s1 + s2 == 1"},
            {"type": "inverse", "variables": ["p0", "p1"], "inverse_variables": ["q0", "q1"]},
            {"type": "linear", "expression": "p0 == 1"},
            {"type": "map_domain", "variable": "mapped", "bool_variables": ["is_0", "is_1", "is_2"]},
            {"type": "linear", "expression": "mapped == 2"},
        ],
    }

    valid, message = manager.parse_model(json.dumps(model))
    result = manager.solve()

    assert valid is True
    assert message == "Model parsed successfully"
    assert result["status"] == "OPTIMAL"
    assert result["variables"]["q1"] == 0
    assert result["variables"]["is_2"] == 1
    assert result["variables"]["is_0"] == 0
    assert result["variables"]["is_1"] == 0


def test_parse_and_solve_model_with_2d_no_overlap_reservoir_and_decision_strategy():
    manager = SolverManager()
    model = {
        "variables": [
            {"name": "x1_start", "domain": [0, 4]},
            {"name": "x2_start", "domain": [0, 4]},
            {"name": "y1_start", "domain": [0, 4]},
            {"name": "y2_start", "domain": [0, 4]},
            {"name": "t0", "domain": [0, 5]},
            {"name": "t1", "domain": [0, 5]},
        ],
        "intervals": [
            {"name": "x1", "start": "x1_start", "size": 2, "fixed_size": True},
            {"name": "x2", "start": "x2_start", "size": 2, "fixed_size": True},
            {"name": "y1", "start": "y1_start", "size": 2, "fixed_size": True},
            {"name": "y2", "start": "y2_start", "size": 2, "fixed_size": True},
        ],
        "constraints": [
            {"type": "no_overlap_2d", "x_intervals": ["x1", "x2"], "y_intervals": ["y1", "y2"]},
            {"type": "linear", "expression": "x1_start == 0"},
            {"type": "linear", "expression": "y1_start == 0"},
            {"type": "linear", "expression": "x2_start == 1"},
            {"type": "reservoir", "times": ["t0", "t1"], "level_changes": [1, -1], "min_level": 0, "max_level": 1},
            {"type": "linear", "expression": "t0 == 0"},
            {"type": "linear", "expression": "t1 == 1"},
            {
                "type": "decision_strategy",
                "variables": ["x2_start", "y2_start"],
                "variable_strategy": "choose_first",
                "domain_strategy": "select_min_value",
            },
        ],
    }

    valid, message = manager.parse_model(json.dumps(model))
    result = manager.solve()

    assert valid is True
    assert message == "Model parsed successfully"
    assert result["status"] == "OPTIMAL"
    assert result["variables"]["x2_start"] == 1
    assert result["variables"]["y2_start"] >= 2


def test_parse_model_rejects_missing_variables():
    manager = SolverManager()

    valid, message = manager.parse_model(json.dumps({"constraints": []}))

    assert valid is False
    assert message == "Model validation failed: Model must contain 'variables' field"


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
