import asyncio
import json

from mcp_ortools.schema import CONSTRAINT_TYPES, get_cp_sat_capabilities, get_cp_sat_model_schema, validate_model_shape
from mcp_ortools.server import handle_tool_call, list_mcp_tools
from mcp_ortools.solver_manager import SolverManager


def text_json(content):
    return json.loads(content[0].text)


def test_schema_metadata_includes_supported_constraint_types():
    schema = get_cp_sat_model_schema()
    capabilities = get_cp_sat_capabilities()

    assert schema["title"] == "MCP OR-Tools CP-SAT Model"
    assert set(capabilities["constraint_types"]) == CONSTRAINT_TYPES
    assert capabilities["supports"]["solver_parameters"] is True
    assert capabilities["supports"]["solution_enumeration"] is False


def test_validate_model_shape_reports_unknown_fields_and_bad_constraints():
    errors = validate_model_shape(
        {
            "variables": [{"name": "x", "domain": [0, 1]}],
            "constraints": [{"type": "not_a_real_constraint"}],
            "surprise": True,
        }
    )

    assert "Unknown top-level field(s): surprise" in errors
    assert "constraints[0].type 'not_a_real_constraint' is not supported" in errors


def test_solver_manager_uses_shape_validation_before_parsing():
    manager = SolverManager()

    valid, message = manager.parse_model(json.dumps({"variables": [{"name": "x"}]}))

    assert valid is False
    assert "Model validation failed" in message
    assert "variables[0].domain is required" in message


def test_mcp_tools_expose_schema_and_capabilities():
    tool_names = {tool.name for tool in list_mcp_tools()}

    assert {"submit_model", "validate_model", "solve_model", "get_solution", "describe_schema", "list_capabilities"} <= tool_names


def test_mcp_validate_model_does_not_replace_active_model():
    manager = SolverManager()
    first_model = {
        "variables": [{"name": "x", "domain": [0, 1]}],
        "constraints": [{"type": "linear", "expression": "x == 1"}],
    }
    second_model = {
        "variables": [{"name": "y", "domain": [0, 1]}],
        "constraints": [{"type": "linear", "expression": "y == 0"}],
    }

    submit_result = text_json(
        asyncio.run(handle_tool_call(manager, "submit_model", {"model": json.dumps(first_model)}))
    )
    validate_result = text_json(
        asyncio.run(handle_tool_call(manager, "validate_model", {"model": json.dumps(second_model)}))
    )
    solve_result = text_json(asyncio.run(handle_tool_call(manager, "solve_model", {})))

    assert submit_result == {"message": "Model submitted successfully", "valid": True}
    assert validate_result == {"message": "Model parsed successfully", "valid": True}
    assert solve_result["variables"] == {"x": 1}


def test_mcp_schema_and_capability_tools_return_json():
    manager = SolverManager()

    schema = text_json(asyncio.run(handle_tool_call(manager, "describe_schema", {})))
    capabilities = text_json(asyncio.run(handle_tool_call(manager, "list_capabilities", {})))

    assert schema["title"] == "MCP OR-Tools CP-SAT Model"
    assert "linear" in capabilities["constraint_types"]
