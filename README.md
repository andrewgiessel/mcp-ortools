# MCP-ORTools

A Model Context Protocol (MCP) server implementation using Google OR-Tools for constraint solving. Designed for use with Large Language Models through standardized constraint model specification.

## Overview

MCP-ORTools integrates Google's OR-Tools constraint programming solver with Large Language Models through the Model Context Protocol, enabling AI models to:
- Submit and validate constraint models
- Set model parameters
- Solve constraint satisfaction and optimization problems
- Retrieve and analyze solutions

## Installation

### Prerequisites

- Python 3.10+
- `uv`

1. Clone this repository:
```bash
git clone https://github.com/Jacck/mcp-ortools.git
cd mcp-ortools
```

2. Sync the project dependencies:
```bash
uv sync
```

3. Optional: install the git hooks:
```bash
uv run pre-commit install
```

4. Configure Claude Desktop
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

Models are specified in JSON format with three main sections:
- `variables`: Define variables and their domains
- `constraints`: List of constraints using OR-Tools methods
- `objective`: Optional optimization objective

### Constraint Syntax

Constraints can use ordinary comparison operators or OR-Tools method syntax:
- `<=` or `.__le__()` for less than or equal
- `>=` or `.__ge__()` for greater than or equal
- `==` or `.__eq__()` for equality
- `!=` or `.__ne__()` for not equal

## Usage Examples

### Simple Optimization Model
```json
{
    "variables": [
        {"name": "x", "domain": [0, 10]},
        {"name": "y", "domain": [0, 10]}
    ],
    "constraints": [
        "(x + y).__le__(15)",
        "x.__ge__(2 * y)"
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
        "(2*p0 + 2*p1 + p2 + p3).__le__(2)"
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
        "vm_2_start >= vm_1_start + 10",
        "makespan >= vm_2_start + 10"
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

The full Python OR-Tools API supports richer scheduling primitives such as interval variables, no-overlap constraints, and cumulative resource constraints; those are the natural next extensions for this MCP server if you want to expose more of CP-SAT's scheduling surface.

Additional constraints example:
```json
{
    "constraints": [
        "p0 == 1",
        "p1 != p2",
        "p2 + p3 >= 1"
    ]
}
```

## Features

- Full OR-Tools CP-SAT solver support
- JSON-based model specification
- Support for:
  - Integer and boolean variables (domain: [min, max])
  - Linear constraints using OR-Tools method syntax
  - Linear optimization objectives
  - Timeouts and solver parameters
  - Binary constraints and relationships
  - Portfolio selection problems
  - Knapsack problems

### Supported Operations in Constraints
- Basic arithmetic: +, -, *
- Comparisons: <=, >=, ==, !=
- Linear combinations of variables
- Binary logic through combinations of constraints

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
    "variables": {
        "p0": 0,
        "p1": 0,
        "p2": 1,
        "p3": 1
    },
    "objective_value": 3.0
}
```

Status values:
- OPTIMAL: Found optimal solution
- FEASIBLE: Found feasible solution
- INFEASIBLE: No solution exists
- UNKNOWN: Could not determine solution

## License

MIT License - see LICENSE file for details
