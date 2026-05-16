from __future__ import annotations

import json
import math
import time
from typing import Any, Protocol
from uuid import uuid4

import ortools
from ortools.algorithms.python import knapsack_solver
from ortools.constraint_solver import pywrapcp, routing_enums_pb2
from ortools.graph.python import max_flow, min_cost_flow
from ortools.linear_solver import pywraplp
from ortools.sat.python import cp_model
from ortools.math_opt.python import mathopt

from .schema import get_cp_sat_capabilities
from .solver_manager import SolverError, SolverManager


class SolverAdapter(Protocol):
    family: str

    def parse_model(self, model_str: str) -> tuple[bool, str]: ...

    def solve(self, timeout: float | None = None) -> dict[str, Any]: ...

    def get_current_solution(self) -> dict[str, Any] | None: ...

    def clear(self) -> None: ...

    def get_model_schema(self) -> dict[str, Any]: ...

    def get_capabilities(self) -> dict[str, Any]: ...


class CpSatAdapter(SolverManager):
    family = "cp_sat"

    def solve(
        self, timeout: float | None = None, enumerate_solutions: bool = False, solution_limit: int = 100
    ) -> dict[str, Any]:  # type: ignore[override]
        if not enumerate_solutions:
            return super().solve(timeout)

        if not self.variables:
            raise SolverError("No model loaded or model is empty")

        callback = _CpSatEnumerationCallback(self.variables, solution_limit)
        if timeout:
            self.solver.parameters.max_time_in_seconds = timeout
        self.solver.parameters.enumerate_all_solutions = True

        start_time = time.time()
        status = self.solver.SearchForAllSolutions(self.model, callback)
        self.last_solve_time = time.time() - start_time
        self.solution_status = self.solver.StatusName(status)
        self.current_solution = callback.solutions[-1] if callback.solutions else None
        return {
            "status": self.solution_status,
            "solve_time": self.last_solve_time,
            "solution_count": len(callback.solutions),
            "solutions": callback.solutions,
            "variables": self.current_solution or {},
        }

    def get_capabilities(self) -> dict[str, Any]:
        capabilities = get_cp_sat_capabilities()
        capabilities["solver_family"] = self.family
        capabilities["supports"]["solution_enumeration"] = True
        capabilities["supports"]["callbacks"] = True
        capabilities["not_yet_covered"] = [
            item for item in capabilities["not_yet_covered"] if item != "solution enumeration callbacks"
        ]
        return capabilities


class _CpSatEnumerationCallback(cp_model.CpSolverSolutionCallback):
    def __init__(self, variables: dict[str, Any], limit: int):
        cp_model.CpSolverSolutionCallback.__init__(self)
        self.variables = variables
        self.limit = limit
        self.solutions: list[dict[str, int]] = []

    def on_solution_callback(self) -> None:
        self.solutions.append({name: self.Value(var) for name, var in self.variables.items()})
        if len(self.solutions) >= self.limit:
            self.StopSearch()


class BaseJsonAdapter:
    family = "base"
    schema_title = "MCP OR-Tools Model"

    def __init__(self):
        self.data: dict[str, Any] | None = None
        self.current_solution: dict[str, Any] | None = None

    def parse_model(self, model_str: str) -> tuple[bool, str]:
        try:
            data = json.loads(model_str)
        except json.JSONDecodeError as e:
            return False, f"Invalid JSON format: {str(e)}"
        errors = self.validate_data(data)
        if errors:
            return False, "Model validation failed: " + "; ".join(errors)
        self.data = data
        self.current_solution = None
        return True, "Model parsed successfully"

    def validate_data(self, data: Any) -> list[str]:
        if not isinstance(data, dict):
            return ["Model must be a JSON object"]
        return []

    def clear(self) -> None:
        self.data = None
        self.current_solution = None

    def get_current_solution(self) -> dict[str, Any] | None:
        return self.current_solution

    def get_model_schema(self) -> dict[str, Any]:
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": self.schema_title,
            "type": "object",
        }

    def get_capabilities(self) -> dict[str, Any]:
        return {"solver_family": self.family, "status": "implemented", "supports": {}}


class RoutingAdapter(BaseJsonAdapter):
    family = "routing"
    schema_title = "MCP OR-Tools Routing Model"

    def validate_data(self, data: Any) -> list[str]:
        errors = super().validate_data(data)
        if errors:
            return errors
        if "distance_matrix" not in data and "time_matrix" not in data:
            errors.append("Routing model must include 'distance_matrix' or 'time_matrix'")
        if "num_vehicles" not in data:
            errors.append("Routing model must include 'num_vehicles'")
        if "depot" not in data and ("starts" not in data or "ends" not in data):
            errors.append("Routing model must include 'depot' or both 'starts' and 'ends'")
        return errors

    def solve(self, timeout: float | None = None) -> dict[str, Any]:
        if self.data is None:
            raise SolverError("No model loaded or model is empty")
        data = self.data

        matrix = data.get("time_matrix", data.get("distance_matrix"))
        if matrix is None:
            raise SolverError("Routing model must include a matrix")
        num_locations = len(matrix)
        num_vehicles = int(data["num_vehicles"])
        if "starts" in data and "ends" in data:
            manager = pywrapcp.RoutingIndexManager(num_locations, num_vehicles, data["starts"], data["ends"])
        else:
            manager = pywrapcp.RoutingIndexManager(num_locations, num_vehicles, int(data["depot"]))
        routing = pywrapcp.RoutingModel(manager)

        def transit_callback(from_index: int, to_index: int) -> int:
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            return int(matrix[from_node][to_node])

        transit_index = routing.RegisterTransitCallback(transit_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_index)

        demands = data.get("demands")
        capacities = data.get("vehicle_capacities")
        if demands is not None and capacities is not None:
            demand_index = routing.RegisterUnaryTransitCallback(lambda index: int(demands[manager.IndexToNode(index)]))
            routing.AddDimensionWithVehicleCapacity(demand_index, 0, [int(c) for c in capacities], True, "capacity")

        time_windows = data.get("time_windows")
        if time_windows is not None:
            horizon = int(data.get("time_horizon", max(window[1] for window in time_windows)))
            routing.AddDimension(transit_index, int(data.get("time_slack", 0)), horizon, False, "time")
            time_dimension = routing.GetDimensionOrDie("time")
            for node, window in enumerate(time_windows):
                index = manager.NodeToIndex(node)
                if index >= 0:
                    time_dimension.CumulVar(index).SetRange(int(window[0]), int(window[1]))

        for disjunction in data.get("disjunctions", []):
            routing.AddDisjunction(
                [manager.NodeToIndex(int(node)) for node in disjunction["nodes"]],
                int(disjunction.get("penalty", 0)),
            )

        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        params = data.get("search_parameters", {})
        first_solution = params.get("first_solution_strategy", "PATH_CHEAPEST_ARC")
        metaheuristic = params.get("local_search_metaheuristic")
        search_parameters.first_solution_strategy = _routing_enum_value(
            routing_enums_pb2.FirstSolutionStrategy, first_solution
        )
        if metaheuristic:
            search_parameters.local_search_metaheuristic = _routing_enum_value(
                routing_enums_pb2.LocalSearchMetaheuristic, metaheuristic
            )
        if timeout:
            search_parameters.time_limit.FromSeconds(int(timeout))
        elif "time_limit_seconds" in params:
            search_parameters.time_limit.FromSeconds(int(params["time_limit_seconds"]))

        assignment = routing.SolveWithParameters(search_parameters)
        if assignment is None:
            self.current_solution = {"status": "NO_SOLUTION"}
            return self.current_solution

        routes = []
        for vehicle_id in range(num_vehicles):
            index = routing.Start(vehicle_id)
            route_nodes = []
            route_cost = 0
            while not routing.IsEnd(index):
                route_nodes.append(manager.IndexToNode(index))
                previous_index = index
                index = assignment.Value(routing.NextVar(index))
                route_cost += routing.GetArcCostForVehicle(previous_index, index, vehicle_id)
            route_nodes.append(manager.IndexToNode(index))
            routes.append({"vehicle": vehicle_id, "nodes": route_nodes, "cost": route_cost})

        dropped_nodes = []
        for node in range(num_locations):
            index = manager.NodeToIndex(node)
            if index >= 0 and assignment.Value(routing.NextVar(index)) == index:
                dropped_nodes.append(node)

        self.current_solution = {
            "status": "OPTIMAL_OR_FEASIBLE",
            "objective_value": assignment.ObjectiveValue(),
            "routes": routes,
            "dropped_nodes": dropped_nodes,
        }
        return self.current_solution

    def get_capabilities(self) -> dict[str, Any]:
        return {
            "solver_family": self.family,
            "supports": {
                "tsp": True,
                "vrp": True,
                "capacities": True,
                "time_windows": True,
                "disjunctions": True,
                "pickup_delivery": False,
            },
        }


class MathOptAdapter(BaseJsonAdapter):
    family = "mathopt"
    schema_title = "MCP OR-Tools MathOpt Model"

    def validate_data(self, data: Any) -> list[str]:
        errors = super().validate_data(data)
        if errors:
            return errors
        if not isinstance(data.get("variables"), list):
            errors.append("MathOpt model must include 'variables' list")
        return errors

    def solve(self, timeout: float | None = None) -> dict[str, Any]:
        if self.data is None:
            raise SolverError("No model loaded or model is empty")

        model = mathopt.Model(name=str(self.data.get("name", "mcp_mathopt")))
        variables = {}
        for var_def in self.data.get("variables", []):
            name = var_def["name"]
            if var_def.get("domain") == "binary":
                variables[name] = model.add_binary_variable(name=name)
            else:
                variables[name] = model.add_variable(
                    lb=float(var_def.get("lb", 0)),
                    ub=float(var_def.get("ub", math.inf)),
                    is_integer=bool(var_def.get("integer", False)),
                    name=name,
                )

        for constraint in self.data.get("constraints", []):
            expr = _eval_linear_expression(str(constraint["expression"]), variables)
            model.add_linear_constraint(
                expr=expr,
                lb=constraint.get("lb"),
                ub=constraint.get("ub"),
                name=str(constraint.get("name", "")),
            )

        objective = self.data.get("objective")
        if objective:
            expr = _eval_linear_expression(str(objective["expression"]), variables)
            if objective.get("maximize", True):
                model.maximize(expr)
            else:
                model.minimize(expr)

        solver_type = getattr(mathopt.SolverType, str(self.data.get("solver_type", "GLOP")))
        result = mathopt.solve(model, solver_type)
        values = result.variable_values()
        self.current_solution = {
            "status": result.termination.reason.name,
            "objective_value": result.objective_value() if result.has_primal_feasible_solution() else None,
            "variables": {name: values[var] for name, var in variables.items()} if values else {},
            "best_objective_bound": result.best_objective_bound(),
            "solve_time": result.solve_time().total_seconds() if result.solve_time() else None,
        }
        return self.current_solution

    def get_capabilities(self) -> dict[str, Any]:
        return {
            "solver_family": self.family,
            "supports": {"linear_constraints": True, "integer_variables": True, "quadratic": False},
            "solver_types": [name for name in dir(mathopt.SolverType) if name.isupper()],
        }


class LinearSolverAdapter(BaseJsonAdapter):
    family = "linear_solver"
    schema_title = "MCP OR-Tools pywraplp Model"

    def validate_data(self, data: Any) -> list[str]:
        errors = super().validate_data(data)
        if errors:
            return errors
        if not isinstance(data.get("variables"), list):
            errors.append("Linear solver model must include 'variables' list")
        return errors

    def solve(self, timeout: float | None = None) -> dict[str, Any]:
        if self.data is None:
            raise SolverError("No model loaded or model is empty")

        solver_type = str(self.data.get("solver_type", "GLOP"))
        solver = pywraplp.Solver.CreateSolver(solver_type)
        if solver is None:
            raise SolverError(f"Could not create linear solver '{solver_type}'")
        if timeout:
            solver.SetTimeLimit(int(timeout * 1000))

        variables = {}
        for var_def in self.data.get("variables", []):
            name = var_def["name"]
            lb = float(var_def.get("lb", 0))
            ub = float(var_def.get("ub", solver.infinity()))
            variables[name] = solver.IntVar(lb, ub, name) if var_def.get("integer") else solver.NumVar(lb, ub, name)

        for constraint in self.data.get("constraints", []):
            ct = solver.Constraint(
                float(constraint.get("lb", -solver.infinity())), float(constraint.get("ub", solver.infinity()))
            )
            for name, coefficient in constraint.get("coefficients", {}).items():
                ct.SetCoefficient(variables[name], float(coefficient))

        objective_def = self.data.get("objective", {})
        objective = solver.Objective()
        for name, coefficient in objective_def.get("coefficients", {}).items():
            objective.SetCoefficient(variables[name], float(coefficient))
        if objective_def.get("maximize", True):
            objective.SetMaximization()
        else:
            objective.SetMinimization()

        status = solver.Solve()
        status_map = {
            pywraplp.Solver.OPTIMAL: "OPTIMAL",
            pywraplp.Solver.FEASIBLE: "FEASIBLE",
            pywraplp.Solver.INFEASIBLE: "INFEASIBLE",
            pywraplp.Solver.UNBOUNDED: "UNBOUNDED",
            pywraplp.Solver.ABNORMAL: "ABNORMAL",
            pywraplp.Solver.NOT_SOLVED: "NOT_SOLVED",
        }
        self.current_solution = {
            "status": status_map.get(status, "UNKNOWN"),
            "objective_value": objective.Value()
            if status in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE)
            else None,
            "variables": {
                name: variable.solution_value()
                for name, variable in variables.items()
                if status in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE)
            },
        }
        return self.current_solution

    def get_capabilities(self) -> dict[str, Any]:
        return {
            "solver_family": self.family,
            "supports": {"lp": True, "mip": True, "dual_values": False},
            "solver_types": [name for name in dir(pywraplp.Solver) if name.isupper() and "PROGRAMMING" in name],
        }


class GraphFlowAdapter(BaseJsonAdapter):
    family = "graph"
    schema_title = "MCP OR-Tools Graph Flow Model"

    def validate_data(self, data: Any) -> list[str]:
        errors = super().validate_data(data)
        if errors:
            return errors
        if data.get("algorithm") not in {"max_flow", "min_cost_flow"}:
            errors.append("Graph model algorithm must be 'max_flow' or 'min_cost_flow'")
        if not isinstance(data.get("arcs"), list):
            errors.append("Graph model must include 'arcs' list")
        return errors

    def solve(self, timeout: float | None = None) -> dict[str, Any]:
        if self.data is None:
            raise SolverError("No model loaded or model is empty")
        data = self.data
        if data["algorithm"] == "max_flow":
            return self._solve_max_flow(data)
        return self._solve_min_cost_flow(data)

    def _solve_max_flow(self, data: dict[str, Any]) -> dict[str, Any]:
        solver = max_flow.SimpleMaxFlow()
        for arc in data["arcs"]:
            solver.add_arc_with_capacity(int(arc["tail"]), int(arc["head"]), int(arc["capacity"]))
        status = solver.solve(int(data["source"]), int(data["sink"]))
        self.current_solution = {
            "status": str(status).split(".")[-1],
            "optimal_flow": solver.optimal_flow() if status == solver.OPTIMAL else None,
            "arcs": [
                {
                    "tail": solver.tail(i),
                    "head": solver.head(i),
                    "capacity": solver.capacity(i),
                    "flow": solver.flow(i),
                }
                for i in range(solver.num_arcs())
            ],
        }
        return self.current_solution

    def _solve_min_cost_flow(self, data: dict[str, Any]) -> dict[str, Any]:
        solver = min_cost_flow.SimpleMinCostFlow()
        for arc in data["arcs"]:
            solver.add_arc_with_capacity_and_unit_cost(
                int(arc["tail"]), int(arc["head"]), int(arc["capacity"]), int(arc["unit_cost"])
            )
        for node, supply in data.get("supplies", {}).items():
            solver.set_node_supply(int(node), int(supply))
        status = solver.solve()
        self.current_solution = {
            "status": str(status).split(".")[-1],
            "optimal_cost": solver.optimal_cost() if status == solver.OPTIMAL else None,
            "maximum_flow": solver.maximum_flow() if status == solver.OPTIMAL else None,
            "arcs": [
                {
                    "tail": solver.tail(i),
                    "head": solver.head(i),
                    "capacity": solver.capacity(i),
                    "unit_cost": solver.unit_cost(i),
                    "flow": solver.flow(i),
                }
                for i in range(solver.num_arcs())
            ],
        }
        return self.current_solution

    def get_capabilities(self) -> dict[str, Any]:
        return {"solver_family": self.family, "supports": {"max_flow": True, "min_cost_flow": True}}


class KnapsackAdapter(BaseJsonAdapter):
    family = "knapsack"
    schema_title = "MCP OR-Tools Knapsack Model"

    SOLVER_TYPES = {
        "dynamic_programming": knapsack_solver.KNAPSACK_DYNAMIC_PROGRAMMING_SOLVER,
        "branch_and_bound": knapsack_solver.KNAPSACK_MULTIDIMENSION_BRANCH_AND_BOUND_SOLVER,
        "cp_sat": knapsack_solver.KNAPSACK_MULTIDIMENSION_CP_SAT_SOLVER,
    }

    def validate_data(self, data: Any) -> list[str]:
        errors = super().validate_data(data)
        if errors:
            return errors
        for field in ("values", "weights", "capacities"):
            if field not in data:
                errors.append(f"Knapsack model must include '{field}'")
        return errors

    def solve(self, timeout: float | None = None) -> dict[str, Any]:
        if self.data is None:
            raise SolverError("No model loaded or model is empty")

        solver_type = self.SOLVER_TYPES.get(str(self.data.get("solver_type", "dynamic_programming")))
        if solver_type is None:
            raise SolverError(f"Unsupported knapsack solver type: {self.data.get('solver_type')}")
        solver = knapsack_solver.KnapsackSolver(solver_type, str(self.data.get("name", "mcp_knapsack")))
        if timeout:
            solver.set_time_limit(float(timeout))
        solver.init(
            [int(value) for value in self.data["values"]],
            [[int(weight) for weight in dimension] for dimension in self.data["weights"]],
            [int(capacity) for capacity in self.data["capacities"]],
        )
        objective = solver.solve()
        packed_items = [item for item in range(len(self.data["values"])) if solver.best_solution_contains(item)]
        self.current_solution = {
            "status": "OPTIMAL" if solver.is_solution_optimal() else "FEASIBLE",
            "objective_value": objective,
            "packed_items": packed_items,
        }
        return self.current_solution

    def get_capabilities(self) -> dict[str, Any]:
        return {
            "solver_family": self.family,
            "supports": {"multi_dimensional": True},
            "solver_types": sorted(self.SOLVER_TYPES),
        }


class SolverSessionManager:
    def __init__(self):
        self.factories = {
            "cp_sat": CpSatAdapter,
            "routing": RoutingAdapter,
            "mathopt": MathOptAdapter,
            "linear_solver": LinearSolverAdapter,
            "graph": GraphFlowAdapter,
            "knapsack": KnapsackAdapter,
        }
        self.sessions: dict[str, SolverAdapter] = {}

    def list_solver_families(self) -> list[str]:
        return sorted(self.factories)

    def create_adapter(self, family: str) -> SolverAdapter:
        normalized = self.normalize_family(family)
        return self.factories[normalized]()

    def normalize_family(self, family: str | None) -> str:
        normalized = (family or "cp_sat").replace("-", "_")
        if normalized not in self.factories:
            raise SolverError(f"Unknown solver family: {family}")
        return normalized

    def validate_model(self, family: str | None, model: str) -> tuple[bool, str]:
        return self.create_adapter(self.normalize_family(family)).parse_model(model)

    def submit_model(self, family: str | None, model: str, session_id: str | None = None) -> tuple[bool, str, str]:
        adapter = self.create_adapter(self.normalize_family(family))
        valid, message = adapter.parse_model(model)
        if valid:
            resolved_session = session_id or str(uuid4())
            self.sessions[resolved_session] = adapter
            return True, message, resolved_session
        return False, message, session_id or ""

    def solve_model(
        self,
        session_id: str | None = None,
        timeout: float | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        adapter = self.get_session(session_id)
        parameters = parameters or {}
        if isinstance(adapter, CpSatAdapter):
            return adapter.solve(timeout, **parameters)
        return adapter.solve(timeout)

    def get_solution(self, session_id: str | None = None) -> dict[str, Any] | None:
        return self.get_session(session_id).get_current_solution()

    def clear_model(self, session_id: str | None = None) -> None:
        if session_id is None:
            self.sessions.clear()
            return
        adapter = self.sessions.pop(session_id, None)
        if adapter is not None:
            adapter.clear()

    def get_session(self, session_id: str | None = None) -> SolverAdapter:
        if session_id is None:
            if "default" in self.sessions:
                return self.sessions["default"]
            if len(self.sessions) == 1:
                return next(iter(self.sessions.values()))
            raise SolverError("No session_id provided and no default session is available")
        if session_id not in self.sessions:
            raise SolverError(f"Unknown model session: {session_id}")
        return self.sessions[session_id]

    def get_schema(self, family: str | None = None) -> dict[str, Any]:
        return self.create_adapter(self.normalize_family(family)).get_model_schema()

    def get_capabilities(self, family: str | None = None) -> dict[str, Any]:
        if family is not None:
            capabilities = self.create_adapter(self.normalize_family(family)).get_capabilities()
            capabilities["ortools_version"] = getattr(ortools, "__version__", "unknown")
            return capabilities
        return {
            "ortools_version": getattr(ortools, "__version__", "unknown"),
            "solver_families": {
                family_name: self.create_adapter(family_name).get_capabilities()
                for family_name in self.list_solver_families()
            },
        }


def _eval_linear_expression(expression: str, variables: dict[str, Any]) -> Any:
    return eval(expression, {"__builtins__": {}}, variables)


def _routing_enum_value(enum_cls: Any, name: str) -> int:
    enum_type = next(iter(enum_cls.DESCRIPTOR.enum_types_by_name.values()))
    values = {value.name: value.number for value in enum_type.values}
    if name not in values:
        allowed = ", ".join(sorted(values))
        raise SolverError(f"Unknown routing enum value {name}. Expected one of: {allowed}")
    return values[name]
