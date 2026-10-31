"""Official MCP SDK fixtures/proxy, in-memory tools and bounded local calls."""

from copy import deepcopy
from datetime import timedelta
import json
import re
from typing import Any, Awaitable, Callable

import anyio
from mcp import ClientSession, types
from mcp.server import Server

from mcp_compat import MigrationDecision, ToolCall, ToolContract, canonical_json
from mcp_compat.benchmark import RecoveryInput
from mcp_compat.recovery import Strategy
from mcp_compat.schema import validate_instance

Implementation = Callable[[dict, dict], Awaitable[dict | types.CallToolResult]]


def _error(reason: str, decision: MigrationDecision | None = None) -> types.CallToolResult:
    data = dict(action="ABSTAIN", reasons=[reason], decision=None if decision is None else decision.model_dump())
    return types.CallToolResult(isError=True, content=[types.TextContent(type="text",text=canonical_json(data))])


def make_server(contract: ToolContract, implementation: Implementation, state: dict | None = None) -> Server:
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", contract.name):
        raise ValueError("invalid synthetic MCP tool name")
    server: Server = Server("mcp-compat-synthetic", version="1.0")
    memory = {} if state is None else state

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [types.Tool(name=contract.name, description=contract.description,
            inputSchema=deepcopy(contract.input_schema), outputSchema=deepcopy(contract.output_schema))]

    @server.call_tool(validate_input=False)
    async def call_tool(name: str, arguments: dict) -> types.CallToolResult:
        try:
            ToolCall(tool_name=name, arguments=arguments).validate_against(contract)
            result = await implementation(deepcopy(arguments), memory)
            if isinstance(result, types.CallToolResult):
                return result
            json.dumps(result, allow_nan=False)
            if not isinstance(result, dict):
                raise ValueError("structured object required")
            if contract.output_schema is not None:
                validate_instance(result, contract.output_schema)
            return types.CallToolResult(isError=False, structuredContent=result,
                content=[types.TextContent(type="text",text=canonical_json(result))])
        except Exception:
            return _error("invalid_or_failed_call")

    return server


def make_proxy(old: ToolContract, new: ToolContract, upstream: ClientSession, strategy: Strategy,
               *, context: dict[str, Any] | None = None, timeout: float = 1) -> Server:
    if timeout <= 0:
        raise ValueError("timeout must be positive")

    async def compatible(arguments: dict, state: dict) -> dict | types.CallToolResult:
        request = RecoveryInput(old_contract=old, new_contract=new,
            old_call=ToolCall(tool_name=old.name, arguments=arguments), context=deepcopy(context or {}))
        try:
            with anyio.fail_after(timeout):
                decision = await anyio.to_thread.run_sync(strategy.recover, request, abandon_on_cancel=True)
                if decision.action == "ABSTAIN":
                    return _error("migration_abstain", decision)
                assert decision.adapted_call is not None
                call = decision.adapted_call
                call.validate_against(new)
                result = await upstream.call_tool(call.tool_name,call.arguments,
                    read_timeout_seconds=timedelta(seconds=timeout))
                if result.isError or result.structuredContent is None:
                    return _error("upstream_error")
                return result.structuredContent
        except TimeoutError:
            return _error("proxy_timeout")
        except Exception:
            return _error("upstream_unavailable")

    return make_server(old, compatible)
