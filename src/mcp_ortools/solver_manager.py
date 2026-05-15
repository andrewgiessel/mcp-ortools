import json
import logging
import time
from typing import Any, Optional, Tuple

from ortools.sat.python import cp_model

from .schema import get_cp_sat_capabilities, get_cp_sat_model_schema, validate_model_shape

logger = logging.getLogger(__name__)

VARIABLE_STRATEGIES = {
    "choose_first": cp_model.CHOOSE_FIRST,
    "choose_lowest_min": cp_model.CHOOSE_LOWEST_MIN,
    "choose_highest_max": cp_model.CHOOSE_HIGHEST_MAX,
    "choose_min_domain_size": cp_model.CHOOSE_MIN_DOMAIN_SIZE,
    "choose_max_domain_size": cp_model.CHOOSE_MAX_DOMAIN_SIZE,
}

DOMAIN_STRATEGIES = {
    "select_min_value": cp_model.SELECT_MIN_VALUE,
    "select_max_value": cp_model.SELECT_MAX_VALUE,
    "select_lower_half": cp_model.SELECT_LOWER_HALF,
    "select_upper_half": cp_model.SELECT_UPPER_HALF,
    "select_median_value": cp_model.SELECT_MEDIAN_VALUE,
    "select_random_half": cp_model.SELECT_RANDOM_HALF,
}


class SolverError(Exception):
    """Custom exception for solver-related errors"""

    pass


class SolverManager:
    """Manages OR-Tools solver operations and state"""

    def __init__(self):
        self.model = cp_model.CpModel()
        self.solver = cp_model.CpSolver()
        self.variables: dict[str, cp_model.IntVar] = {}
        self.intervals: dict[str, cp_model.IntervalVar] = {}
        self.current_solution: Optional[dict[str, Any]] = None
        self.last_solve_time: Optional[float] = None
        self.objective_value: Optional[float] = None
        self.solution_status: Optional[str] = None

    def clear(self) -> None:
        """Clear current model and solution state"""
        self.model = cp_model.CpModel()
        self.solver = cp_model.CpSolver()
        self.variables.clear()
        self.intervals.clear()
        self.current_solution = None
        self.last_solve_time = None
        self.objective_value = None
        self.solution_status = None

    def parse_model(self, model_str: str) -> Tuple[bool, str]:
        """Parse and validate model definition"""
        try:
            data = json.loads(model_str)

            validation_errors = validate_model_shape(data)
            if validation_errors:
                return False, "Model validation failed: " + "; ".join(validation_errors)

            # Clear previous state
            self.clear()

            # Create variables
            for var_def in data.get("variables", []):
                if "name" not in var_def or "domain" not in var_def:
                    return False, "Each variable must have 'name' and 'domain'"
                name = var_def["name"]
                try:
                    self._create_variable(name, var_def["domain"])
                except Exception as e:
                    return False, f"Invalid variable '{name}': {str(e)}"

            # Create scheduling interval variables after scalar variables are available.
            for interval_def in data.get("intervals", []):
                try:
                    if not isinstance(interval_def, dict):
                        raise ValueError("Interval must be an object")
                    self._create_interval(interval_def)
                except Exception as e:
                    interval_name = (
                        interval_def.get("name", "<unnamed>") if isinstance(interval_def, dict) else "<unnamed>"
                    )
                    return False, f"Invalid interval '{interval_name}': {str(e)}"

            # Add constraints
            for constraint_def in data.get("constraints", []):
                try:
                    self._add_constraint(constraint_def)
                except Exception as e:
                    return False, f"Invalid constraint '{constraint_def}': {str(e)}"

            # Add optional warm-start hints.
            try:
                self._add_hints(data.get("hints", {}))
            except Exception as e:
                return False, f"Invalid hints: {str(e)}"

            # Add optional assumptions after variables and constraints exist.
            try:
                self._add_assumptions(data.get("assumptions", []))
            except Exception as e:
                return False, f"Invalid assumptions: {str(e)}"

            # Apply optional solver parameters at model submission time.
            try:
                self._set_parameters(data.get("parameters", {}))
            except Exception as e:
                return False, f"Invalid parameters: {str(e)}"

            # Set objective if present
            objective = data.get("objective")
            if objective:
                if "expression" not in objective:
                    return False, "Objective must have 'expression' field"
                try:
                    expr = self._build_expression(objective["expression"])
                    if objective.get("maximize", True):
                        self.model.maximize(expr)
                    else:
                        self.model.minimize(expr)
                except Exception as e:
                    return False, f"Invalid objective expression: {str(e)}"

            return True, "Model parsed successfully"

        except json.JSONDecodeError as e:
            return False, f"Invalid JSON format: {str(e)}"
        except Exception as e:
            logger.exception("Error parsing model")
            return False, f"Error parsing model: {str(e)}"

    def _create_variable(self, name: str, domain_def: Any) -> None:
        """Create an integer, boolean, or custom-domain variable."""
        if name in self.variables:
            raise ValueError(f"Variable '{name}' is already defined")

        if domain_def == [0, 1]:
            self.variables[name] = self.model.new_bool_var(name)
            return

        if (
            isinstance(domain_def, list)
            and len(domain_def) == 2
            and all(isinstance(value, int) for value in domain_def)
        ):
            self.variables[name] = self.model.new_int_var(domain_def[0], domain_def[1], name)
            return

        domain = self._build_domain(domain_def)
        self.variables[name] = self.model.new_int_var_from_domain(domain, name)

    def _create_interval(self, interval_def: dict[str, Any]) -> None:
        """Create an interval variable for scheduling constraints."""
        for field in ("name", "start", "size"):
            if field not in interval_def:
                raise ValueError(f"Interval must have '{field}' field")

        name = interval_def["name"]
        if name in self.intervals:
            raise ValueError(f"Interval '{name}' is already defined")

        start = self._build_expression(str(interval_def["start"]))
        size = self._build_expression(str(interval_def["size"]))
        presence = interval_def.get("presence")
        fixed_size = bool(interval_def.get("fixed_size", False))

        if "end" not in interval_def:
            if presence is None:
                self.intervals[name] = self.model.new_fixed_size_interval_var(start, int(interval_def["size"]), name)
                return

            self.intervals[name] = self.model.new_optional_fixed_size_interval_var(
                start,
                int(interval_def["size"]),
                self._build_literal(presence),
                name,
            )
            return

        end = self._build_expression(str(interval_def["end"]))

        if presence is None and fixed_size:
            self.intervals[name] = self.model.new_fixed_size_interval_var(start, int(interval_def["size"]), name)
            return
        if presence is None:
            self.intervals[name] = self.model.new_interval_var(start, size, end, name)
            return

        if fixed_size:
            self.intervals[name] = self.model.new_optional_fixed_size_interval_var(
                start,
                int(interval_def["size"]),
                self._build_literal(presence),
                name,
            )
            return

        self.intervals[name] = self.model.new_optional_interval_var(
            start, size, end, self._build_literal(presence), name
        )

    def _add_constraint(self, constraint_def: Any) -> None:
        """Add either a legacy string constraint or a structured constraint."""
        if isinstance(constraint_def, str):
            self.model.add(self._build_constraint(constraint_def))
            return

        if not isinstance(constraint_def, dict):
            raise ValueError("Constraint must be a string or object")

        constraint_type = constraint_def.get("type")
        if not constraint_type:
            raise ValueError("Structured constraint must have 'type' field")

        constraint = None
        match constraint_type:
            case "linear":
                constraint = self._add_linear_constraint(constraint_def)
            case "linear_in_domain":
                expression = self._required_expression(constraint_def, "expression")
                domain = self._build_domain(constraint_def.get("domain"))
                constraint = self.model.add_linear_expression_in_domain(expression, domain)
            case "bool_or":
                constraint = self.model.add_bool_or(*self._build_literals(constraint_def.get("literals", [])))
            case "bool_and":
                constraint = self.model.add_bool_and(*self._build_literals(constraint_def.get("literals", [])))
            case "bool_xor":
                constraint = self.model.add_bool_xor(*self._build_literals(constraint_def.get("literals", [])))
            case "at_least_one":
                constraint = self.model.add_at_least_one(*self._build_literals(constraint_def.get("literals", [])))
            case "at_most_one":
                constraint = self.model.add_at_most_one(*self._build_literals(constraint_def.get("literals", [])))
            case "exactly_one":
                constraint = self.model.add_exactly_one(*self._build_literals(constraint_def.get("literals", [])))
            case "implication":
                constraint = self.model.add_implication(
                    self._build_literal(constraint_def.get("if")),
                    self._build_literal(constraint_def.get("then")),
                )
            case "all_different":
                expressions = self._build_expressions(
                    constraint_def.get("expressions", constraint_def.get("variables", []))
                )
                if not expressions:
                    raise ValueError("all_different constraint requires at least one variable")
                constraint = self.model.add_all_different(*expressions)
            case "allowed_assignments":
                constraint = self.model.add_allowed_assignments(
                    self._build_expressions(constraint_def.get("expressions", constraint_def.get("variables", []))),
                    self._int_tuples(constraint_def.get("tuples", [])),
                )
            case "forbidden_assignments":
                constraint = self.model.add_forbidden_assignments(
                    self._build_expressions(constraint_def.get("expressions", constraint_def.get("variables", []))),
                    self._int_tuples(constraint_def.get("tuples", [])),
                )
            case "automaton":
                constraint = self.model.add_automaton(
                    self._build_expressions(constraint_def.get("expressions", constraint_def.get("variables", []))),
                    self._required_int(constraint_def, "starting_state"),
                    [int(state) for state in constraint_def.get("final_states", [])],
                    self._transition_triples(constraint_def.get("transitions", [])),
                )
            case "circuit":
                constraint = self.model.add_circuit(self._build_arcs(constraint_def.get("arcs", [])))
            case "multiple_circuit":
                constraint = self.model.add_multiple_circuit(self._build_arcs(constraint_def.get("arcs", [])))
            case "inverse":
                constraint = self.model.add_inverse(
                    self._build_expressions(constraint_def.get("variables", [])),
                    self._build_expressions(constraint_def.get("inverse_variables", [])),
                )
            case "element":
                constraint = self.model.add_element(
                    self._required_expression(constraint_def, "index"),
                    self._build_expressions(constraint_def.get("expressions", constraint_def.get("variables", []))),
                    self._required_expression(constraint_def, "target"),
                )
            case "map_domain":
                constraint = self.model.add_map_domain(
                    self._required_variable(constraint_def, "variable"),
                    [self._get_variable(str(name)) for name in constraint_def.get("bool_variables", [])],
                    int(constraint_def.get("offset", 0)),
                )
            case "no_overlap":
                intervals = [self._get_interval(name) for name in constraint_def.get("intervals", [])]
                if not intervals:
                    raise ValueError("no_overlap constraint requires at least one interval")
                constraint = self.model.add_no_overlap(intervals)
            case "no_overlap_2d":
                x_intervals = [self._get_interval(name) for name in constraint_def.get("x_intervals", [])]
                y_intervals = [self._get_interval(name) for name in constraint_def.get("y_intervals", [])]
                if not x_intervals or not y_intervals:
                    raise ValueError("no_overlap_2d constraint requires x_intervals and y_intervals")
                if len(x_intervals) != len(y_intervals):
                    raise ValueError("no_overlap_2d requires matching x/y interval counts")
                constraint = self.model.add_no_overlap_2d(x_intervals, y_intervals)
            case "cumulative":
                intervals = [self._get_interval(name) for name in constraint_def.get("intervals", [])]
                demands = [self._build_expression(str(demand)) for demand in constraint_def.get("demands", [])]
                if "capacity" not in constraint_def:
                    raise ValueError("cumulative constraint must have 'capacity' field")
                capacity = self._build_expression(str(constraint_def.get("capacity")))
                if not intervals:
                    raise ValueError("cumulative constraint requires at least one interval")
                if len(intervals) != len(demands):
                    raise ValueError("cumulative constraint requires one demand per interval")
                constraint = self.model.add_cumulative(intervals, demands, capacity)
            case "reservoir":
                times = self._build_expressions(constraint_def.get("times", []))
                level_changes = self._build_expressions(constraint_def.get("level_changes", []))
                min_level = self._required_int(constraint_def, "min_level")
                max_level = self._required_int(constraint_def, "max_level")
                actives = constraint_def.get("actives")
                if actives is None:
                    constraint = self.model.add_reservoir_constraint(times, level_changes, min_level, max_level)
                else:
                    constraint = self.model.add_reservoir_constraint_with_active(
                        times,
                        level_changes,
                        self._build_literals(actives),
                        min_level,
                        max_level,
                    )
            case "max_equality":
                expressions = [self._build_expression(str(expr)) for expr in constraint_def.get("expressions", [])]
                if not expressions:
                    raise ValueError("max_equality constraint requires at least one expression")
                constraint = self.model.add_max_equality(
                    self._required_expression(constraint_def, "target"), *expressions
                )
            case "min_equality":
                expressions = [self._build_expression(str(expr)) for expr in constraint_def.get("expressions", [])]
                if not expressions:
                    raise ValueError("min_equality constraint requires at least one expression")
                constraint = self.model.add_min_equality(
                    self._required_expression(constraint_def, "target"), *expressions
                )
            case "abs_equality":
                constraint = self.model.add_abs_equality(
                    self._required_expression(constraint_def, "target"),
                    self._required_expression(constraint_def, "expression"),
                )
            case "multiplication_equality":
                expressions = self._build_expressions(constraint_def.get("expressions", []))
                if not expressions:
                    raise ValueError("multiplication_equality constraint requires at least one expression")
                constraint = self.model.add_multiplication_equality(
                    self._required_expression(constraint_def, "target"),
                    *expressions,
                )
            case "division_equality":
                constraint = self.model.add_division_equality(
                    self._required_expression(constraint_def, "target"),
                    self._required_expression(constraint_def, "num"),
                    self._required_expression(constraint_def, "denom"),
                )
            case "modulo_equality":
                constraint = self.model.add_modulo_equality(
                    self._required_expression(constraint_def, "target"),
                    self._required_expression(constraint_def, "expression"),
                    self._required_expression(constraint_def, "mod"),
                )
            case "assumption":
                self.model.add_assumption(self._build_literal(constraint_def.get("literal")))
            case "decision_strategy":
                variables = [self._get_variable(str(name)) for name in constraint_def.get("variables", [])]
                if not variables:
                    raise ValueError("decision_strategy requires at least one variable")
                variable_strategy = self._decision_strategy(
                    VARIABLE_STRATEGIES,
                    constraint_def.get("variable_strategy", "choose_first"),
                    "variable_strategy",
                )
                domain_strategy = self._decision_strategy(
                    DOMAIN_STRATEGIES,
                    constraint_def.get("domain_strategy", "select_min_value"),
                    "domain_strategy",
                )
                self.model.add_decision_strategy(variables, variable_strategy, domain_strategy)
            case _:
                raise ValueError(f"Unsupported structured constraint type: {constraint_type}")

        if constraint is not None:
            self._configure_constraint(constraint, constraint_def)

    def _add_linear_constraint(self, constraint_def: dict[str, Any]) -> Any:
        if "expression" in constraint_def and ("lb" in constraint_def or "ub" in constraint_def):
            expression = self._build_expression(str(constraint_def["expression"]))
            lb = int(constraint_def.get("lb", -cp_model.INT32_MAX))
            ub = int(constraint_def.get("ub", cp_model.INT32_MAX))
            return self.model.add_linear_constraint(expression, lb, ub)

        expression = constraint_def.get("expression")
        if not expression:
            raise ValueError("Linear constraint must have 'expression' field")
        return self.model.add(self._build_constraint(str(expression)))

    def _configure_constraint(self, constraint: Any, constraint_def: dict[str, Any]) -> None:
        if "name" in constraint_def:
            constraint.with_name(str(constraint_def["name"]))

        if "enforce_if" in constraint_def:
            constraint.only_enforce_if(self._build_literals(constraint_def["enforce_if"]))

    def _add_hints(self, hints: Any) -> None:
        """Add optional solution hints to the CP-SAT model."""
        if not hints:
            return

        if isinstance(hints, dict):
            hint_items = hints.items()
        elif isinstance(hints, list):
            hint_items = []
            for hint in hints:
                if not isinstance(hint, dict) or "variable" not in hint or "value" not in hint:
                    raise ValueError("Hint list entries must have 'variable' and 'value' fields")
                hint_items.append((hint["variable"], hint["value"]))
        else:
            raise ValueError("Hints must be an object or list")

        for name, value in hint_items:
            self.model.add_hint(self._get_variable(str(name)), int(value))

    def _add_assumptions(self, assumptions: Any) -> None:
        if not assumptions:
            return
        self.model.add_assumptions(self._build_literals(assumptions))

    def _set_parameters(self, parameters: Any) -> None:
        if not parameters:
            return
        if not isinstance(parameters, dict):
            raise ValueError("Parameters must be an object")

        for name, value in parameters.items():
            if not hasattr(self.solver.parameters, name):
                raise ValueError(f"Unknown CP-SAT solver parameter: {name}")
            setattr(self.solver.parameters, name, value)

    def _build_domain(self, domain_def: Any) -> cp_model.Domain:
        if isinstance(domain_def, dict):
            if "values" in domain_def:
                return cp_model.Domain.FromValues([int(value) for value in domain_def["values"]])
            if "intervals" in domain_def:
                return cp_model.Domain.FromIntervals(
                    [[int(interval[0]), int(interval[1])] for interval in domain_def["intervals"]]
                )
            if "flat_intervals" in domain_def:
                return cp_model.Domain.FromFlatIntervals([int(value) for value in domain_def["flat_intervals"]])

        if isinstance(domain_def, list):
            if all(isinstance(value, int) for value in domain_def):
                return cp_model.Domain.FromValues([int(value) for value in domain_def])
            if all(isinstance(interval, list) and len(interval) == 2 for interval in domain_def):
                return cp_model.Domain.FromIntervals([[int(interval[0]), int(interval[1])] for interval in domain_def])

        raise ValueError("Domain must be [lower, upper], a value list, or interval list")

    def _build_expressions(self, values: Any) -> list[Any]:
        if not isinstance(values, list):
            raise ValueError("Expressions must be a list")
        return [self._build_expression(str(value)) for value in values]

    def _required_expression(self, constraint_def: dict[str, Any], field: str) -> Any:
        if field not in constraint_def:
            raise ValueError(f"Constraint must have '{field}' field")
        return self._build_expression(str(constraint_def[field]))

    def _required_variable(self, constraint_def: dict[str, Any], field: str) -> cp_model.IntVar:
        if field not in constraint_def:
            raise ValueError(f"Constraint must have '{field}' field")
        return self._get_variable(str(constraint_def[field]))

    def _required_int(self, constraint_def: dict[str, Any], field: str) -> int:
        if field not in constraint_def:
            raise ValueError(f"Constraint must have '{field}' field")
        return int(constraint_def[field])

    def _build_literal(self, literal_def: Any) -> Any:
        if isinstance(literal_def, bool):
            return literal_def
        if isinstance(literal_def, int):
            return literal_def
        if isinstance(literal_def, str):
            if literal_def.startswith("not "):
                return self._get_variable(literal_def[4:].strip()).Not()
            if literal_def.startswith("~"):
                return self._get_variable(literal_def[1:].strip()).Not()
            return self._get_variable(literal_def)
        if isinstance(literal_def, dict) and "not" in literal_def:
            return self._get_variable(str(literal_def["not"])).Not()
        raise ValueError(f"Invalid literal: {literal_def}")

    def _build_literals(self, literal_defs: Any) -> list[Any]:
        if isinstance(literal_defs, (str, dict, bool, int)):
            return [self._build_literal(literal_defs)]
        if not isinstance(literal_defs, list):
            raise ValueError("Literals must be a literal or list")
        return [self._build_literal(literal_def) for literal_def in literal_defs]

    def _build_arcs(self, arc_defs: Any) -> list[tuple[int, int, Any]]:
        if not isinstance(arc_defs, list):
            raise ValueError("Arcs must be a list")

        arcs = []
        for arc in arc_defs:
            if isinstance(arc, dict):
                arcs.append((int(arc["tail"]), int(arc["head"]), self._build_literal(arc["literal"])))
            elif isinstance(arc, list) and len(arc) == 3:
                arcs.append((int(arc[0]), int(arc[1]), self._build_literal(arc[2])))
            else:
                raise ValueError("Arcs must be [tail, head, literal] arrays or objects")
        return arcs

    def _int_tuples(self, tuples_def: Any) -> list[list[int]]:
        if not isinstance(tuples_def, list):
            raise ValueError("Tuples must be a list")
        return [[int(value) for value in row] for row in tuples_def]

    def _transition_triples(self, triples_def: Any) -> list[tuple[int, int, int]]:
        if not isinstance(triples_def, list):
            raise ValueError("Transitions must be a list")
        triples = []
        for triple in triples_def:
            if not isinstance(triple, list) or len(triple) != 3:
                raise ValueError("Automaton transitions must be [tail, label, head] triples")
            triples.append((int(triple[0]), int(triple[1]), int(triple[2])))
        return triples

    def _decision_strategy(self, options: dict[str, Any], value: Any, field: str) -> Any:
        key = str(value)
        if key not in options:
            allowed = ", ".join(sorted(options))
            raise ValueError(f"Unknown {field}: {key}. Expected one of: {allowed}")
        return options[key]

    def _get_variable(self, name: str) -> cp_model.IntVar:
        if name not in self.variables:
            raise ValueError(f"Unknown variable: {name}")
        return self.variables[name]

    def _get_interval(self, name: str) -> cp_model.IntervalVar:
        if name not in self.intervals:
            raise ValueError(f"Unknown interval: {name}")
        return self.intervals[name]

    def solve(self, timeout: Optional[float] = None) -> dict[str, Any]:
        """Solve current model with optional timeout"""
        if not self.variables:
            raise SolverError("No model loaded or model is empty")

        try:
            if timeout:
                self.solver.parameters.max_time_in_seconds = timeout

            start_time = time.time()
            status = self.solver.Solve(self.model)
            self.last_solve_time = time.time() - start_time

            status_map = {
                cp_model.OPTIMAL: "OPTIMAL",
                cp_model.FEASIBLE: "FEASIBLE",
                cp_model.INFEASIBLE: "INFEASIBLE",
                cp_model.UNKNOWN: "UNKNOWN",
                cp_model.MODEL_INVALID: "INVALID",
            }

            self.solution_status = status_map.get(status, "UNKNOWN")
            result = {
                "status": self.solution_status,
                "solve_time": self.last_solve_time,
                "stats": {
                    "num_booleans": self.solver.NumBooleans(),
                    "num_branches": self.solver.NumBranches(),
                    "num_conflicts": self.solver.NumConflicts(),
                    "wall_time": self.solver.WallTime(),
                    "user_time": self.solver.UserTime(),
                    "solution_info": self.solver.SolutionInfo(),
                },
            }

            if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
                self.current_solution = {name: self.solver.Value(var) for name, var in self.variables.items()}
                result["variables"] = self.current_solution
                if self.model.has_objective():
                    self.objective_value = self.solver.ObjectiveValue()
                    result["objective_value"] = self.objective_value
                    result["best_objective_bound"] = self.solver.BestObjectiveBound()
            elif status == cp_model.INFEASIBLE:
                result["message"] = "Problem is infeasible"
                result["sufficient_assumptions_for_infeasibility"] = list(
                    self.solver.SufficientAssumptionsForInfeasibility()
                )
            else:
                result["message"] = "No solution found"

            return result

        except Exception as e:
            logger.exception("Error solving model")
            raise SolverError(f"Error solving model: {str(e)}")

    def _eval_model_expression(self, expression: str) -> Any:
        """Evaluate a model expression with only declared variables in scope."""
        return eval(expression, {"__builtins__": {}}, self.variables)

    def _build_constraint(self, constraint_str: str) -> Any:
        """Build OR-Tools constraint from string expression"""
        if not constraint_str:
            raise ValueError("Empty constraint string")

        try:
            return self._eval_model_expression(constraint_str)
        except Exception as e:
            raise ValueError(f"Invalid constraint expression: {str(e)}")

    def _build_expression(self, expr_str: str) -> Any:
        """Build OR-Tools expression from string"""
        if not expr_str:
            raise ValueError("Empty expression string")

        try:
            return self._eval_model_expression(expr_str)
        except Exception as e:
            raise ValueError(f"Invalid expression: {str(e)}")

    def get_current_solution(self) -> Optional[dict[str, Any]]:
        """Get current solution if available"""
        if self.current_solution is None:
            return None
        return {
            "variables": self.current_solution,
            "status": self.solution_status,
            "solve_time": self.last_solve_time,
            "objective_value": self.objective_value,
        }

    def get_solve_time(self) -> Optional[float]:
        """Get last solve time"""
        return self.last_solve_time

    def get_model_schema(self) -> dict[str, Any]:
        """Get the public CP-SAT model schema."""
        return get_cp_sat_model_schema()

    def get_capabilities(self) -> dict[str, Any]:
        """Get the public CP-SAT capability metadata."""
        return get_cp_sat_capabilities()
