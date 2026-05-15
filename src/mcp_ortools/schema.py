from __future__ import annotations

from copy import deepcopy
from typing import Any


TOP_LEVEL_FIELDS = {
    "variables",
    "intervals",
    "constraints",
    "objective",
    "hints",
    "assumptions",
    "parameters",
}

CONSTRAINT_TYPES = {
    "linear",
    "linear_in_domain",
    "bool_or",
    "bool_and",
    "bool_xor",
    "at_least_one",
    "at_most_one",
    "exactly_one",
    "implication",
    "all_different",
    "allowed_assignments",
    "forbidden_assignments",
    "automaton",
    "circuit",
    "multiple_circuit",
    "inverse",
    "element",
    "map_domain",
    "no_overlap",
    "no_overlap_2d",
    "cumulative",
    "reservoir",
    "max_equality",
    "min_equality",
    "abs_equality",
    "multiplication_equality",
    "division_equality",
    "modulo_equality",
    "assumption",
    "decision_strategy",
}

VARIABLE_STRATEGY_NAMES = [
    "choose_first",
    "choose_lowest_min",
    "choose_highest_max",
    "choose_min_domain_size",
    "choose_max_domain_size",
]

DOMAIN_STRATEGY_NAMES = [
    "select_min_value",
    "select_max_value",
    "select_lower_half",
    "select_upper_half",
    "select_median_value",
    "select_random_half",
]

CP_SAT_MODEL_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://github.com/Jacck/mcp-ortools/schemas/cp-sat-model.json",
    "title": "MCP OR-Tools CP-SAT Model",
    "type": "object",
    "additionalProperties": False,
    "required": ["variables"],
    "properties": {
        "variables": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "domain"],
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "domain": {
                        "description": "Either [lower, upper], explicit values, interval pairs, or a domain object.",
                        "oneOf": [
                            {"type": "array", "items": {"type": "integer"}, "minItems": 1},
                            {
                                "type": "array",
                                "items": {
                                    "type": "array",
                                    "items": {"type": "integer"},
                                    "minItems": 2,
                                    "maxItems": 2,
                                },
                            },
                            {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "values": {"type": "array", "items": {"type": "integer"}, "minItems": 1},
                                    "intervals": {
                                        "type": "array",
                                        "items": {
                                            "type": "array",
                                            "items": {"type": "integer"},
                                            "minItems": 2,
                                            "maxItems": 2,
                                        },
                                    },
                                    "flat_intervals": {
                                        "type": "array",
                                        "items": {"type": "integer"},
                                        "minItems": 2,
                                    },
                                },
                            },
                        ],
                    },
                },
            },
        },
        "intervals": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "start", "size"],
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "start": {},
                    "size": {},
                    "end": {},
                    "presence": {},
                    "fixed_size": {"type": "boolean"},
                },
            },
        },
        "constraints": {
            "type": "array",
            "items": {
                "oneOf": [
                    {"type": "string"},
                    {
                        "type": "object",
                        "required": ["type"],
                        "properties": {
                            "type": {"type": "string", "enum": sorted(CONSTRAINT_TYPES)},
                            "name": {"type": "string"},
                            "enforce_if": {},
                        },
                    },
                ]
            },
        },
        "objective": {
            "type": "object",
            "required": ["expression"],
            "properties": {
                "expression": {"type": "string", "minLength": 1},
                "maximize": {"type": "boolean", "default": True},
            },
        },
        "hints": {
            "oneOf": [
                {"type": "object", "additionalProperties": {"type": "integer"}},
                {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["variable", "value"],
                        "properties": {
                            "variable": {"type": "string"},
                            "value": {"type": "integer"},
                        },
                    },
                },
            ]
        },
        "assumptions": {"type": "array"},
        "parameters": {"type": "object"},
    },
}

CP_SAT_CAPABILITIES: dict[str, Any] = {
    "solver_family": "cp-sat",
    "status": "comprehensive-main-cpmodel-primitives",
    "model_fields": sorted(TOP_LEVEL_FIELDS),
    "constraint_types": sorted(CONSTRAINT_TYPES),
    "variable_strategies": VARIABLE_STRATEGY_NAMES,
    "domain_strategies": DOMAIN_STRATEGY_NAMES,
    "supports": {
        "integer_variables": True,
        "boolean_variables": True,
        "custom_domains": True,
        "interval_variables": True,
        "optional_intervals": True,
        "reified_constraints": True,
        "solver_parameters": True,
        "solution_hints": True,
        "assumptions": True,
        "solve_statistics": True,
        "solution_enumeration": False,
        "callbacks": False,
        "serialized_protos": False,
    },
    "not_yet_covered": [
        "solution enumeration callbacks",
        "full model proto import/export",
        "named assumption to unsat-core mapping",
        "dedicated examples for every constraint family",
    ],
}


def get_cp_sat_model_schema() -> dict[str, Any]:
    """Return a defensive copy of the public CP-SAT JSON schema."""
    return deepcopy(CP_SAT_MODEL_SCHEMA)


def get_cp_sat_capabilities() -> dict[str, Any]:
    """Return a defensive copy of the public CP-SAT capability metadata."""
    return deepcopy(CP_SAT_CAPABILITIES)


def validate_model_shape(data: Any) -> list[str]:
    """Validate broad model shape before building an OR-Tools model.

    This intentionally complements the parser instead of replacing it: the
    parser still checks references, expressions, and solver-specific semantics.
    """
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["Model must be a JSON object"]

    unknown_fields = sorted(set(data) - TOP_LEVEL_FIELDS)
    if unknown_fields:
        errors.append(f"Unknown top-level field(s): {', '.join(unknown_fields)}")

    variables = data.get("variables")
    if variables is None:
        errors.append("Model must contain 'variables' field")
    elif not isinstance(variables, list):
        errors.append("'variables' must be a list")
    else:
        _validate_variables(variables, errors)

    _validate_optional_list(data, "intervals", errors)
    _validate_optional_list(data, "constraints", errors)
    _validate_optional_list(data, "assumptions", errors)

    if "objective" in data and not isinstance(data["objective"], dict):
        errors.append("'objective' must be an object")
    elif isinstance(data.get("objective"), dict) and not data["objective"].get("expression"):
        errors.append("'objective' must include non-empty 'expression'")

    if "parameters" in data and not isinstance(data["parameters"], dict):
        errors.append("'parameters' must be an object")

    _validate_constraints(data.get("constraints", []), errors)
    _validate_intervals(data.get("intervals", []), errors)
    _validate_hints(data.get("hints", {}), errors)

    return errors


def _validate_optional_list(data: dict[str, Any], field: str, errors: list[str]) -> None:
    if field in data and not isinstance(data[field], list):
        errors.append(f"'{field}' must be a list")


def _validate_variables(variables: list[Any], errors: list[str]) -> None:
    seen_names: set[str] = set()
    for index, variable in enumerate(variables):
        prefix = f"variables[{index}]"
        if not isinstance(variable, dict):
            errors.append(f"{prefix} must be an object")
            continue

        name = variable.get("name")
        if not isinstance(name, str) or not name:
            errors.append(f"{prefix}.name must be a non-empty string")
        elif name in seen_names:
            errors.append(f"Duplicate variable name: {name}")
        elif name:
            seen_names.add(name)

        if "domain" not in variable:
            errors.append(f"{prefix}.domain is required")
        elif not _is_domain_shape(variable["domain"]):
            errors.append(f"{prefix}.domain must be [lower, upper], a value list, interval pairs, or a domain object")


def _validate_intervals(intervals: Any, errors: list[str]) -> None:
    if not isinstance(intervals, list):
        return

    seen_names: set[str] = set()
    for index, interval in enumerate(intervals):
        prefix = f"intervals[{index}]"
        if not isinstance(interval, dict):
            errors.append(f"{prefix} must be an object")
            continue

        name = interval.get("name")
        if not isinstance(name, str) or not name:
            errors.append(f"{prefix}.name must be a non-empty string")
        elif name in seen_names:
            errors.append(f"Duplicate interval name: {name}")
        elif name:
            seen_names.add(name)

        for field in ("start", "size"):
            if field not in interval:
                errors.append(f"{prefix}.{field} is required")


def _validate_constraints(constraints: Any, errors: list[str]) -> None:
    if not isinstance(constraints, list):
        return

    for index, constraint in enumerate(constraints):
        prefix = f"constraints[{index}]"
        if isinstance(constraint, str):
            if not constraint:
                errors.append(f"{prefix} must not be empty")
            continue

        if not isinstance(constraint, dict):
            errors.append(f"{prefix} must be a string or object")
            continue

        constraint_type = constraint.get("type")
        if not isinstance(constraint_type, str) or not constraint_type:
            errors.append(f"{prefix}.type is required")
        elif constraint_type not in CONSTRAINT_TYPES:
            errors.append(f"{prefix}.type '{constraint_type}' is not supported")


def _validate_hints(hints: Any, errors: list[str]) -> None:
    if not hints:
        return
    if isinstance(hints, dict):
        return
    if isinstance(hints, list):
        for index, hint in enumerate(hints):
            if not isinstance(hint, dict) or "variable" not in hint or "value" not in hint:
                errors.append(f"hints[{index}] must include 'variable' and 'value'")
        return
    errors.append("'hints' must be an object or list")


def _is_domain_shape(domain: Any) -> bool:
    if isinstance(domain, dict):
        return bool({"values", "intervals", "flat_intervals"} & set(domain))
    if not isinstance(domain, list) or not domain:
        return False
    if all(isinstance(value, int) for value in domain):
        return True
    return all(isinstance(interval, list) and len(interval) == 2 for interval in domain)
