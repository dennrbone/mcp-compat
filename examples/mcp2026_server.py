"""Отдельный профиль SDK 2.3.0; исторический SDK 1.30.0 не заменяется."""

from copy import deepcopy

import anyio
from mcp import types
from mcp.server import Server
from mcp.shared.exceptions import MCPError

from mcp_compat import ToolCall, canonical_json
from mcp_compat.benchmark import RecoveryInput
from mcp_compat.schema import validate_instance


def make_server_2026(contract, implementation):
    async def list_tools(ctx, params):
        return types.ListToolsResult(tools=[types.Tool(name=contract.name,
            description=contract.description, input_schema=deepcopy(contract.input_schema),
            output_schema=deepcopy(contract.output_schema))])

    async def call_tool(ctx, params):
        if params.name != contract.name:
            raise MCPError(code=-32602, message="Unknown tool")
        try:
            ToolCall(tool_name=params.name, arguments=params.arguments or {}).validate_against(contract)
            result = await implementation(deepcopy(params.arguments or {}))
            if result is None:
                raise ValueError("null structured output is outside this profile")
            text = canonical_json(result)
            if contract.output_schema is not None:
                validate_instance(result, contract.output_schema)
            return types.CallToolResult(content=[types.TextContent(type="text", text=text)],
                structured_content=result)
        except Exception:
            return types.CallToolResult(content=[types.TextContent(type="text", text="invalid_or_failed_call")],
                is_error=True)

    return Server("mcp-compat-2026", version="1.0", on_list_tools=list_tools, on_call_tool=call_tool,
        get_tool_input_schema=lambda name: contract.input_schema if name == contract.name else None)


def make_proxy_2026(old, new, upstream, strategy, *, context=None, timeout=1,
                    admission=None, current_state=None):
    if not 0 < timeout < float("inf"):
        raise ValueError("finite positive timeout required")
    if (admission is None) != (current_state is None):
        raise ValueError("admission verifier and current-state provider are required together")

    async def compatible(arguments):
        request = RecoveryInput(old_contract=old, new_contract=new,
            old_call=ToolCall(tool_name=old.name, arguments=arguments), context=deepcopy(context or {}))
        with anyio.fail_after(timeout):
            decision = await anyio.to_thread.run_sync(strategy.recover, request, abandon_on_cancel=True)
            if admission is not None:
                decision = await anyio.to_thread.run_sync(
                    lambda: admission.admit(request,decision,current_state=current_state()),abandon_on_cancel=True)
            if decision.action != "EXECUTE":
                raise ValueError("migration_abstain")
            call = decision.adapted_call
            call.validate_against(new)
            result = await upstream.call_tool(call.tool_name, call.arguments)
            if result.is_error or result.structured_content is None:
                raise ValueError("upstream_error")
            return result.structured_content

    return make_server_2026(old, compatible)


if __name__ == "__main__":
    from mcp.server.stdio import stdio_server
    from mcp_compat import ToolContract

    async def echo(arguments):
        return arguments

    async def serve():
        server = make_server_2026(ToolContract(name="echo", input_schema={"type":"object"},
            output_schema={"type":"object"}), echo)
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    anyio.run(serve)
