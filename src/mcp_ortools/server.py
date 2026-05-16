import asyncio
import json
import logging
from typing import Any

import mcp.server.stdio
import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.shared.exceptions import McpError

from .adapters import SolverSessionManager
from .solver_manager import SolverError

logger = logging.getLogger(__name__)


def mcp_error(code: int, message: str, data: Any | None = None) -> McpError:
    return McpError(types.ErrorData(code=code, message=message, data=data))


def json_text(data: Any) -> list[types.TextContent]:
    return [types.TextContent(type="text", text=json.dumps(data, indent=2, sort_keys=True))]


def list_mcp_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="list_solver_families",
            description="List available OR-Tools solver families",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="submit_model",
            description="Submit and validate an OR-Tools model in JSON format",
            inputSchema={
                "type": "object",
                "properties": {
                    "family": {"type": ["string", "null"], "description": "Solver family, default cp_sat"},
                    "model": {"type": "string", "description": "Model specification as JSON"},
                    "session_id": {"type": ["string", "null"], "description": "Optional model session id"},
                },
                "required": ["model"],
            },
        ),
        types.Tool(
            name="validate_model",
            description="Validate an OR-Tools model without storing it as the active model",
            inputSchema={
                "type": "object",
                "properties": {
                    "family": {"type": ["string", "null"], "description": "Solver family, default cp_sat"},
                    "model": {"type": "string", "description": "Model specification as JSON"},
                },
                "required": ["model"],
            },
        ),
        types.Tool(
            name="solve_model",
            description="Solve a submitted OR-Tools model session",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": ["string", "null"], "description": "Optional model session id"},
                    "timeout": {"type": ["number", "null"], "description": "Optional solve timeout in seconds"},
                    "parameters": {"type": ["object", "null"], "description": "Optional solve-time parameters"},
                },
            },
        ),
        types.Tool(
            name="get_solution",
            description="Get the current solution for a model session if available",
            inputSchema={
                "type": "object",
                "properties": {"session_id": {"type": ["string", "null"], "description": "Optional model session id"}},
            },
        ),
        types.Tool(
            name="clear_model",
            description="Clear one model session or all sessions",
            inputSchema={
                "type": "object",
                "properties": {"session_id": {"type": ["string", "null"], "description": "Optional model session id"}},
            },
        ),
        types.Tool(
            name="describe_schema",
            description="Return the JSON schema for a solver-family model format",
            inputSchema={
                "type": "object",
                "properties": {"family": {"type": ["string", "null"], "description": "Solver family, default cp_sat"}},
            },
        ),
        types.Tool(
            name="list_capabilities",
            description="Return supported OR-Tools capabilities and known gaps",
            inputSchema={
                "type": "object",
                "properties": {"family": {"type": ["string", "null"], "description": "Optional solver family"}},
            },
        ),
    ]


async def handle_tool_call(
    solver_mgr: SolverSessionManager, name: str, arguments: dict[str, Any]
) -> list[types.TextContent]:
    """Handle tool calls and map them to solver operations."""
    logger.debug(f"Tool call: {name} with arguments {arguments}")

    try:
        match name:
            case "list_solver_families":
                return json_text({"solver_families": solver_mgr.list_solver_families()})

            case "submit_model":
                model_str = arguments.get("model")
                if not model_str:
                    raise mcp_error(types.INVALID_PARAMS, "model parameter is required")

                valid, message, session_id = solver_mgr.submit_model(
                    arguments.get("family"),
                    model_str,
                    arguments.get("session_id") or "default",
                )
                if not valid:
                    raise mcp_error(types.INVALID_PARAMS, message)

                logger.info("Model submitted successfully")
                return json_text({"valid": True, "message": "Model submitted successfully", "session_id": session_id})

            case "validate_model":
                model_str = arguments.get("model")
                if not model_str:
                    raise mcp_error(types.INVALID_PARAMS, "model parameter is required")

                valid, message = solver_mgr.validate_model(arguments.get("family"), model_str)
                return json_text({"valid": valid, "message": message})

            case "solve_model":
                try:
                    timeout = arguments.get("timeout")
                    result = solver_mgr.solve_model(
                        arguments.get("session_id") or "default", timeout, arguments.get("parameters")
                    )
                    logger.info(f"Solve completed with status {result.get('status')}")
                    return json_text(result)
                except SolverError as e:
                    raise mcp_error(types.INTERNAL_ERROR, str(e)) from e

            case "get_solution":
                solution = solver_mgr.get_solution(arguments.get("session_id") or "default")
                if solution is None:
                    raise mcp_error(types.INVALID_PARAMS, "No solution is available")
                return json_text(solution)

            case "clear_model":
                solver_mgr.clear_model(arguments.get("session_id"))
                return json_text({"cleared": True})

            case "describe_schema":
                return json_text(solver_mgr.get_schema(arguments.get("family")))

            case "list_capabilities":
                return json_text(solver_mgr.get_capabilities(arguments.get("family")))

            case _:
                raise mcp_error(types.METHOD_NOT_FOUND, f"Tool {name} not found")

    except McpError:
        raise
    except Exception as e:
        logger.exception(f"Error in {name}")
        raise mcp_error(types.INTERNAL_ERROR, str(e)) from e


async def serve() -> None:
    """Main server function that handles the MCP protocol"""
    logger.info("Starting OR-Tools MCP server")

    server = Server("ortools")
    solver_mgr = SolverSessionManager()

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return list_mcp_tools()

    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
        return await handle_tool_call(solver_mgr, name, arguments)

    logger.info("Starting STDIO server")
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        logger.info("STDIO server started")
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="ortools",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


def main() -> int:
    """Main entry point"""
    try:
        asyncio.run(serve())
        return 0
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
        return 0
    except Exception:
        logger.exception("Server error")
        return 1


if __name__ == "__main__":
    main()
