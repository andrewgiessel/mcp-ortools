# MCP-ORTools

A Model Context Protocol (MCP) server for Google OR-Tools. The current implementation focuses on an LLM-friendly JSON interface for CP-SAT constraint programming models.

## Overview

MCP-ORTools integrates Google's OR-Tools constraint programming solver with Large Language Models through the Model Context Protocol, enabling AI models to:

- Submit and validate constraint models
- Discover the supported JSON schema and solver capabilities
- Set model parameters
- Solve constraint satisfaction and optimization problems
- Retrieve and analyze solutions

## Current Scope

The server currently targets OR-Tools CP-SAT through `CpModel`. It covers the main CP-SAT modeling primitives through structured JSON, including linear constraints, boolean logic, tables, automata, circuits, scheduling intervals, no-overlap, cumulative, reservoir, and integer arithmetic equality constraints.

It does not yet expose the full OR-Tools package. Routing, linear/MIP optimization, network flow, MathOpt, and specialized algorithm modules are tracked in the roadmap below.

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

## Model Specification

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

- `submit_model`: validates and stores a CP-SAT model as the active model.
- `validate_model`: validates a CP-SAT model without replacing the active model.
- `solve_model`: solves the active model and returns JSON-formatted status, solution values, objective metadata, and solver stats.
- `get_solution`: returns the latest solution for the active model.
- `describe_schema`: returns the JSON schema for the CP-SAT model format.
- `list_capabilities`: returns supported CP-SAT features, strategy names, and known gaps.

Recommended client workflow:

1. Call `list_capabilities` to confirm supported features.
2. Call `describe_schema` when constructing or repairing a model.
3. Call `validate_model` before replacing the active model.
4. Call `submit_model`, then `solve_model`.
5. Call `get_solution` when you need to inspect the latest result again.

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

- Comprehensive JSON coverage for the main OR-Tools CP-SAT `CpModel` primitives
- JSON-based model specification
- Support for:
  - Integer and boolean variables, including custom value and interval domains
  - Structured JSON constraints
  - Linear constraints and linear expression domains
  - Boolean constraints, implications, and reified enforcement
  - All-different constraints
  - Table constraints with allowed and forbidden assignments
  - Automata, circuits, multiple circuits, inverse, element, and map-domain constraints
  - Scheduling intervals
  - No-overlap, 2D no-overlap, cumulative, and reservoir resource constraints
  - Min, max, absolute value, multiplication, division, and modulo equality constraints
  - Linear optimization objectives
  - Warm-start solution hints
  - Assumptions for infeasibility analysis
  - Decision strategies
  - Timeouts and CP-SAT solver parameters
  - Binary constraints and relationships
  - Portfolio selection problems
  - Knapsack problems
  - Scheduling, packing, sequencing, routing-like, and state-machine models

### Supported Operations in Constraints

- Basic arithmetic: +, -, *
- Comparisons: <=, >=, ==, !=
- Linear combinations of variables
- Binary logic through combinations of constraints
- Interval scheduling with no-overlap and cumulative constraints
- Tables, automata, circuits, reservoirs, and integer arithmetic equalities

## Roadmap

This project currently focuses on a structured MCP interface for OR-Tools CP-SAT. Full MCP coverage of OR-Tools would require adding the other solver families, richer solver workflows, and API ergonomics that make those capabilities discoverable and safe for LLM clients.

### Current Coverage

- CP-SAT model submission, validation, solving, and solution retrieval.
- Structured JSON coverage for the main `CpModel` primitives listed above.
- Solver parameters, timeouts, warm-start hints, assumptions, basic infeasibility metadata, objective values, and solve statistics.
- MCP tools for submitting, validating, solving, retrieving solutions, describing the schema, and listing capabilities.

### Further CP-SAT Hardening

- Add solution enumeration with callbacks and configurable solution limits.
- Return richer solver artifacts, including full response stats, model validation output, serialized model protos, and optional solver logs.
- Improve infeasibility tooling with assumption-name mapping and clearer unsat-core reporting.
- Tighten the JSON schema with per-constraint required fields and stronger type-specific validation.
- Add more examples for circuit-style models and larger scheduling workloads.

### Additional OR-Tools APIs

- Routing: expose vehicle routing, TSP, VRP, pickup-and-delivery, capacities, time windows, penalties, dimensions, and route extraction.
- Linear and mixed-integer optimization: expose `pywraplp` or MathOpt model creation, constraints, objectives, solver selection, parameters, and dual/basis information where available.
- Network flows: expose max flow, min-cost flow, assignment, and matching-style APIs.
- Specialized algorithms: expose knapsack/bin-packing helpers and other OR-Tools algorithm modules where they remain supported upstream.
- MathOpt: evaluate whether the newer MathOpt API should become the preferred interface for LP/MIP/QP style models.

### MCP Surface

- Add separate tools for `clear_model` and solver-family-specific submissions.
- Support named model sessions so clients can keep multiple models active at once.
- Add import/export tools for model JSON, CP-SAT protos, and solver responses.
- Add resource endpoints for schemas, examples, capability matrices, and last-solve diagnostics.
- Consider returning structured MCP resource content in addition to JSON text where clients support it.

### Quality And Compatibility

- Build a cross-solver test corpus with known optimal solutions.
- Add property-style tests for schema validation and parser error messages.
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