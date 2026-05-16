# MCP-ORTools

A Model Context Protocol (MCP) server for Google OR-Tools. The current implementation provides LLM-friendly JSON interfaces for CP-SAT, Routing, MathOpt, pywraplp linear/MIP solving, graph flow algorithms, and knapsack.

## Overview

MCP-ORTools integrates Google OR-Tools with Large Language Models through the Model Context Protocol, enabling AI models to:

- Submit and validate constraint models
- Discover the supported JSON schema and solver capabilities
- Set model parameters
- Solve constraint satisfaction and optimization problems
- Retrieve and analyze solutions

## Current Scope

The server exposes separate solver-family surfaces that match OR-Tools' own API boundaries:

- `cp_sat`: CP-SAT through `CpModel`, including linear constraints, boolean logic, tables, automata, circuits, intervals, no-overlap, cumulative, reservoir, arithmetic equality constraints, assumptions, hints, solver parameters, and solution enumeration.
- `routing`: matrix-backed TSP/VRP models through `RoutingIndexManager` and `RoutingModel`, with capacities, time windows, disjunctions, and routing search parameters.
- `mathopt`: linear MathOpt models with continuous, integer, and binary variables.
- `linear_solver`: legacy `pywraplp` LP/MIP models with coefficient-based constraints and objectives.
- `graph`: max-flow and min-cost-flow one-shot models.
- `knapsack`: multidimensional knapsack models through OR-Tools' specialized knapsack solver.

The remaining gaps are deeper feature coverage inside each family: advanced Routing callbacks, full MathOpt quadratic/conic features, proto import/export, richer infeasibility diagnostics, and larger example suites.

## Installation

### Prerequisites

- Python 3.10+
- `uv`

1. Clone this repository:

```bash
git clone https://github.com/Jacck/mcp-ortools.git
cd mcp-ortools
```

1. Sync the project dependencies:

```bash
uv sync
```

1. Optional: install the git hooks:

```bash
uv run pre-commit install
```

1. Configure Claude Desktop

Create the configuration file at `%APPDATA%\Claude\claude_desktop_config.json` (Windows) or `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "ortools": {
      "command": "uv",
      "args": ["run", "mcp-ortools"]
    }
  }
}
```

## CP-SAT Model Specification

Models are specified in JSON format with these top-level fields:

- `variables`: Integer and boolean variables. Domains can be `[lower, upper]`, explicit value lists, interval lists, or objects such as `{"values": [1, 3, 5]}` and `{"intervals": [[0, 2], [5, 8]]}`.
- `intervals`: Optional interval variables for scheduling models. Intervals support `start`, `size`, `end`, `presence`, and fixed-size variants.
- `constraints`: Structured CP-SAT constraints.
- `objective`: Optional linear optimization objective.
- `hints`: Optional warm-start values for selected variables.
- `assumptions`: Optional assumption literals for infeasibility analysis.
- `parameters`: Optional CP-SAT solver parameters, using the Python parameter field names.

### Constraint Syntax

Linear constraints can use ordinary comparison operators or OR-Tools method syntax:

- `<=` or `.__le__()` for less than or equal
- `>=` or `.__ge__()` for greater than or equal
- `==` or `.__eq__()` for equality
- `!=` or `.__ne__()` for not equal

Prefer structured JSON constraints for new models:

- `{"type": "linear", "expression": "x + y <= 10"}`
- `{"type": "linear", "expression": "x + y", "lb": 0, "ub": 10}`
- `{"type": "linear_in_domain", "expression": "x + y", "domain": [[0, 2], [5, 8]]}`
- `{"type": "bool_or", "literals": ["a", {"not": "b"}]}`
- `{"type": "bool_and", "literals": ["a", "b"]}`
- `{"type": "bool_xor", "literals": ["a", "b", "c"]}`
- `{"type": "at_least_one", "literals": ["a", "b"]}`
- `{"type": "at_most_one", "literals": ["a", "b"]}`
- `{"type": "exactly_one", "literals": ["a", "b"]}`
- `{"type": "implication", "if": "a", "then": {"not": "b"}}`
- `{"type": "all_different", "variables": ["x", "y", "z"]}`
- `{"type": "allowed_assignments", "expressions": ["x", "y"], "tuples": [[1, 2], [3, 4]]}`
- `{"type": "forbidden_assignments", "expressions": ["x", "y"], "tuples": [[0, 0]]}`
- `{"type": "automaton", "expressions": ["s0", "s1"], "starting_state": 0, "final_states": [1], "transitions": [[0, 1, 1]]}`
- `{"type": "circuit", "arcs": [[0, 1, "arc_0_1"], [1, 0, "arc_1_0"]]}`
- `{"type": "multiple_circuit", "arcs": [[0, 1, "arc_0_1"], [1, 0, "arc_1_0"]]}`
- `{"type": "inverse", "variables": ["p0", "p1"], "inverse_variables": ["q0", "q1"]}`
- `{"type": "element", "index": "i", "expressions": [2, 4, 6], "target": "value"}`
- `{"type": "map_domain", "variable": "x", "bool_variables": ["x_is_0", "x_is_1"], "offset": 0}`
- `{"type": "no_overlap", "intervals": ["task_1", "task_2"]}`
- `{"type": "no_overlap_2d", "x_intervals": ["box_1_x", "box_2_x"], "y_intervals": ["box_1_y", "box_2_y"]}`
- `{"type": "cumulative", "intervals": ["task_1", "task_2"], "demands": [2, 1], "capacity": 3}`
- `{"type": "reservoir", "times": ["t0", "t1"], "level_changes": [1, -1], "min_level": 0, "max_level": 2}`
- `{"type": "max_equality", "target": "makespan", "expressions": ["task_1_end", "task_2_end"]}`
- `{"type": "min_equality", "target": "earliest", "expressions": ["task_1_start", "task_2_start"]}`
- `{"type": "abs_equality", "target": "distance", "expression": "x - y"}`
- `{"type": "multiplication_equality", "target": "product", "expressions": ["x", "y"]}`
- `{"type": "division_equality", "target": "quotient", "num": "x", "denom": "y"}`
- `{"type": "modulo_equality", "target": "remainder", "expression": "x", "mod": "y"}`
- `{"type": "assumption", "literal": "scenario_enabled"}`
- `{"type": "decision_strategy", "variables": ["x", "y"], "variable_strategy": "choose_first", "domain_strategy": "select_min_value"}`

Most structured constraints also support optional `name` and `enforce_if` fields. Literals can be written as `"flag"`, `"~flag"`, `"not flag"`, or `{"not": "flag"}`.

## MCP Tools

- `list_solver_families`: returns available solver families.
- `submit_model`: validates and stores a model for a solver family. Accepts `family`, `model`, and optional `session_id`.
- `validate_model`: validates a model without replacing the active model.
- `solve_model`: solves a submitted model session and returns JSON-formatted status, solution values, objective metadata, and solver stats where available.
- `get_solution`: returns the latest solution for a model session.
- `clear_model`: clears one model session, or all sessions when no `session_id` is supplied.
- `describe_schema`: returns the JSON schema for a solver-family model format.
- `list_capabilities`: returns supported OR-Tools features, strategy names, and known gaps by family.

Recommended client workflow:

1. Call `list_solver_families` to discover available families.
2. Call `list_capabilities` with a `family` to confirm supported features.
3. Call `describe_schema` with a `family` when constructing or repairing a model.
4. Call `validate_model` before replacing a session.
5. Call `submit_model`, then `solve_model`.
6. Call `get_solution` when you need to inspect the latest result again.

## Additional Solver Family Models

### Routing

Routing models use matrix-backed callbacks for safe MCP use. A minimal TSP model:

```json
{
    "distance_matrix": [
        [0, 1, 2],
        [1, 0, 4],
        [2, 4, 0]
    ],
    "num_vehicles": 1,
    "depot": 0,
    "search_parameters": {
        "first_solution_strategy": "PATH_CHEAPEST_ARC"
    }
}
```

Optional routing fields include `demands`, `vehicle_capacities`, `time_matrix`, `time_windows`, `time_horizon`, `time_slack`, and `disjunctions`.

### MathOpt

MathOpt models currently support linear variables, linear constraints, and linear objectives:

```json
{
    "variables": [{"name": "x", "lb": 0, "ub": 10}],
    "constraints": [{"expression": "x", "lb": 2, "ub": 10}],
    "objective": {"expression": "x", "maximize": true},
    "solver_type": "GLOP"
}
```

### pywraplp Linear Solver

The `linear_solver` family provides coefficient-based LP/MIP models:

```json
{
    "solver_type": "SCIP",
    "variables": [
        {"name": "x", "lb": 0, "ub": 1, "integer": true},
        {"name": "y", "lb": 0, "ub": 1, "integer": true}
    ],
    "constraints": [{"coefficients": {"x": 1, "y": 1}, "lb": 1, "ub": 1}],
    "objective": {"coefficients": {"x": 3, "y": 2}, "maximize": true}
}
```

### Graph Flow

The `graph` family supports `max_flow` and `min_cost_flow`:

```json
{
    "algorithm": "max_flow",
    "source": 0,
    "sink": 3,
    "arcs": [
        {"tail": 0, "head": 1, "capacity": 3},
        {"tail": 0, "head": 2, "capacity": 2},
        {"tail": 1, "head": 3, "capacity": 2},
        {"tail": 2, "head": 3, "capacity": 4}
    ]
}
```

### Knapsack

The `knapsack` family wraps OR-Tools' specialized knapsack solver:

```json
{
    "values": [6, 10, 12],
    "weights": [[1, 2, 3]],
    "capacities": [5],
    "solver_type": "dynamic_programming"
}
```

## Usage Examples

### Simple Optimization Model

```json
{
    "variables": [
        {"name": "x", "domain": [0, 10]},
        {"name": "y", "domain": [0, 10]}
    ],
    "constraints": [
        {"type": "linear", "expression": "x + y <= 15"},
        {"type": "linear", "expression": "x >= 2 * y"}
    ],
    "objective": {
        "expression": "40 * x + 100 * y",
        "maximize": true
    }
}
```

### Knapsack Problem

Example: Select items with values [3,1,2,1] and weights [2,2,1,1] with total weight limit of 2.

```json
{
    "variables": [
        {"name": "p0", "domain": [0, 1]},
        {"name": "p1", "domain": [0, 1]},
        {"name": "p2", "domain": [0, 1]},
        {"name": "p3", "domain": [0, 1]}
    ],
    "constraints": [
        {"type": "linear", "expression": "2*p0 + 2*p1 + p2 + p3 <= 2"}
    ],
    "objective": {
        "expression": "3*p0 + p1 + 2*p2 + p3",
        "maximize": true
    }
}
```

### Maintenance Scheduling Example

OR-Tools CP-SAT is also a good fit for scheduling problems where work must be placed on a timeline while respecting capacity and concurrency constraints. For example, [Atalay Kutlay's maintenance scheduling write-up](https://atalaykutlay.com/or-tools-cp-sat-for-scheduling-problems.html) models VM migrations during hypervisor maintenance and uses CP-SAT to reason about capacity, concurrency, and customer-disruption conflicts.

This server's JSON model format can express a small linear version of that idea. In this example, `vm_1` must run before `vm_2`, each migration takes 10 time units, and the objective minimizes the final completion time:

```json
{
    "variables": [
        {"name": "vm_1_start", "domain": [0, 20]},
        {"name": "vm_2_start", "domain": [0, 20]},
        {"name": "makespan", "domain": [0, 30]}
    ],
    "constraints": [
        {"type": "linear", "expression": "vm_2_start >= vm_1_start + 10"},
        {"type": "linear", "expression": "makespan >= vm_2_start + 10"}
    ],
    "objective": {
        "expression": "makespan",
        "maximize": false
    }
}
```

Expected solution:

```json
{
    "status": "OPTIMAL",
    "variables": {
        "vm_1_start": 0,
        "vm_2_start": 10,
        "makespan": 20
    },
    "objective_value": 20.0
}
```

The JSON model format also supports richer CP-SAT scheduling primitives such as interval variables, no-overlap constraints, and cumulative resource constraints. This example schedules two tasks on a single machine and minimizes the final completion time:

```json
{
    "variables": [
        {"name": "task_1_start", "domain": [0, 10]},
        {"name": "task_1_end", "domain": [0, 10]},
        {"name": "task_2_start", "domain": [0, 10]},
        {"name": "task_2_end", "domain": [0, 10]},
        {"name": "makespan", "domain": [0, 10]}
    ],
    "intervals": [
        {"name": "task_1", "start": "task_1_start", "size": 3, "end": "task_1_end"},
        {"name": "task_2", "start": "task_2_start", "size": 4, "end": "task_2_end"}
    ],
    "constraints": [
        {"type": "no_overlap", "intervals": ["task_1", "task_2"]},
        {"type": "max_equality", "target": "makespan", "expressions": ["task_1_end", "task_2_end"]}
    ],
    "hints": {
        "task_1_start": 0,
        "task_1_end": 3,
        "task_2_start": 3,
        "task_2_end": 7,
        "makespan": 7
    },
    "objective": {
        "expression": "makespan",
        "maximize": false
    }
}
```

Additional constraints example:

```json
{
    "constraints": [
        {"type": "linear", "expression": "p0 == 1"},
        {"type": "linear", "expression": "p1 != p2"},
        {"type": "linear", "expression": "p2 + p3 >= 1"}
    ]
}
```

### Assignment Pattern

Use boolean decision variables plus `exactly_one`, `at_most_one`, and a linear objective for assignment-style problems:

```json
{
    "variables": [
        {"name": "worker_0_task_0", "domain": [0, 1]},
        {"name": "worker_0_task_1", "domain": [0, 1]},
        {"name": "worker_1_task_0", "domain": [0, 1]},
        {"name": "worker_1_task_1", "domain": [0, 1]}
    ],
    "constraints": [
        {"type": "exactly_one", "literals": ["worker_0_task_0", "worker_1_task_0"]},
        {"type": "exactly_one", "literals": ["worker_0_task_1", "worker_1_task_1"]},
        {"type": "at_most_one", "literals": ["worker_0_task_0", "worker_0_task_1"]},
        {"type": "at_most_one", "literals": ["worker_1_task_0", "worker_1_task_1"]}
    ],
    "objective": {
        "expression": "3 * worker_0_task_0 + 8 * worker_0_task_1 + 4 * worker_1_task_0 + 2 * worker_1_task_1",
        "maximize": false
    }
}
```

### State Machine Pattern

Use `automaton` to constrain a sequence of state labels. This example accepts binary sequences with exactly one `1`:

```json
{
    "variables": [
        {"name": "s0", "domain": [0, 1]},
        {"name": "s1", "domain": [0, 1]},
        {"name": "s2", "domain": [0, 1]}
    ],
    "constraints": [
        {
            "type": "automaton",
            "expressions": ["s0", "s1", "s2"],
            "starting_state": 0,
            "final_states": [1],
            "transitions": [[0, 0, 0], [0, 1, 1], [1, 0, 1], [1, 1, 2], [2, 0, 2], [2, 1, 2]]
        }
    ]
}
```

### Packing Pattern

Use `no_overlap_2d` for rectangle packing by pairing each rectangle's x and y intervals:

```json
{
    "variables": [
        {"name": "box_1_x", "domain": [0, 4]},
        {"name": "box_1_y", "domain": [0, 4]},
        {"name": "box_2_x", "domain": [0, 4]},
        {"name": "box_2_y", "domain": [0, 4]}
    ],
    "intervals": [
        {"name": "box_1_x_interval", "start": "box_1_x", "size": 2, "fixed_size": true},
        {"name": "box_1_y_interval", "start": "box_1_y", "size": 2, "fixed_size": true},
        {"name": "box_2_x_interval", "start": "box_2_x", "size": 2, "fixed_size": true},
        {"name": "box_2_y_interval", "start": "box_2_y", "size": 2, "fixed_size": true}
    ],
    "constraints": [
        {
            "type": "no_overlap_2d",
            "x_intervals": ["box_1_x_interval", "box_2_x_interval"],
            "y_intervals": ["box_1_y_interval", "box_2_y_interval"]
        }
    ]
}
```

## Features

- Solver-family registry with capability and schema discovery.
- Session-aware model submission, solving, solution retrieval, and clearing.
- Comprehensive JSON coverage for the main OR-Tools CP-SAT `CpModel` primitives.
- Matrix-backed Routing support for TSP/VRP, capacities, time windows, disjunctions, and search parameters.
- MathOpt linear optimization support for continuous, integer, and binary variables.
- pywraplp linear/MIP support for coefficient-based models.
- Graph support for max-flow and min-cost-flow algorithms.
- Specialized multidimensional knapsack support.
- Cross-family tests with known optimal or feasible solutions.

### Supported Operations in Constraints

- Basic arithmetic: +, -, *
- Comparisons: <=, >=, ==, !=
- Linear combinations of variables
- Binary logic through combinations of constraints
- Interval scheduling with no-overlap and cumulative constraints
- Tables, automata, circuits, reservoirs, and integer arithmetic equalities

## Roadmap

This project now exposes the major OR-Tools solver families through separate MCP model surfaces. Remaining work is mostly depth: richer family-specific features, import/export, diagnostics, examples, and compatibility hardening.

### Current Coverage

- CP-SAT model submission, validation, solving, enumeration, and solution retrieval.
- Structured JSON coverage for the main `CpModel` primitives listed above.
- Solver parameters, timeouts, warm-start hints, assumptions, basic infeasibility metadata, objective values, and solve statistics.
- Routing, MathOpt, pywraplp, graph flow, and knapsack adapters for common model shapes.
- MCP tools for listing solver families, submitting, validating, solving, retrieving solutions, clearing sessions, describing schemas, and listing capabilities.

### Further CP-SAT Hardening

- Return richer solver artifacts, including full response stats, model validation output, serialized model protos, and optional solver logs.
- Improve infeasibility tooling with assumption-name mapping and clearer unsat-core reporting.
- Tighten the JSON schema with per-constraint required fields and stronger type-specific validation.
- Add more examples for circuit-style models and larger scheduling workloads.

### Additional OR-Tools APIs

- Routing: add pickup-and-delivery, richer dimensions, vehicle-specific transit/cost callbacks, and route diagnostics.
- MathOpt: add quadratic objectives/constraints, duals, reduced costs, basis information, and broader solver parameter support where available.
- pywraplp: add export formats, dual/basis metadata where supported, and clearer solver availability diagnostics.
- Graph algorithms: add assignment/matching-style helpers if they remain supported upstream.
- Specialized algorithms: evaluate bin-packing helpers and document when to prefer CP-SAT or MathOpt instead.

### MCP Surface

- Add import/export tools for model JSON, CP-SAT protos, and solver responses.
- Add resource endpoints for schemas, examples, capability matrices, and last-solve diagnostics.
- Consider returning structured MCP resource content in addition to JSON text where clients support it.

### Quality And Compatibility

- Expand the cross-solver test corpus with larger known-optimal examples.
- Add property-style tests for schema validation, parser error messages, and adapter session behavior.
- Track OR-Tools version compatibility and gate capabilities based on the installed package.
- Document unsupported OR-Tools features explicitly so clients can distinguish "not implemented" from "not supported upstream."

## Development

To setup for development:

```bash
git clone https://github.com/Jacck/mcp-ortools.git
cd mcp-ortools
uv sync --all-groups
uv run pytest
uv run ruff check .
uv run pyright
```

## Model Response Format

The solver returns solutions in JSON format:

```json
{
    "status": "OPTIMAL",
    "solve_time": 0.045,
    "stats": {
        "num_booleans": 4,
        "num_branches": 0,
        "num_conflicts": 0,
        "wall_time": 0.045,
        "user_time": 0.045,
        "solution_info": ""
    },
    "variables": {
        "p0": 0,
        "p1": 0,
        "p2": 1,
        "p3": 1
    },
    "objective_value": 3.0,
    "best_objective_bound": 3.0
}
```

Status values:

- OPTIMAL: Found optimal solution
- FEASIBLE: Found feasible solution
- INFEASIBLE: No solution exists
- UNKNOWN: Could not determine solution

For infeasible models with assumptions, responses also include `sufficient_assumptions_for_infeasibility`.

## License

MIT License - see LICENSE file for details
