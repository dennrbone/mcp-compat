"""Model-independent MCP decision endpoint; no business tool is executed."""

import anyio

from mcp_compat import MigrationDecision, ToolContract
from mcp_compat.benchmark import RecoveryInput
from mcp_compat.hybrid import Hybrid
from mcp_compat.mcp_integration import make_server, serve_stdio
from mcp_compat.runtime_fixtures import fixture_verifier

engine = Hybrid(verifier=fixture_verifier())


async def recover(arguments: dict, state: dict) -> dict:
    request = RecoveryInput.model_validate(arguments)
    return engine.recover(request).model_dump(mode="json")


server = make_server(ToolContract(name="check_migration",
    description="Inspect migration using trusted synthetic runtimes. Unknown bindings yield ABSTAIN; no external tool is invoked.",
    input_schema=RecoveryInput.model_json_schema(),
    output_schema=MigrationDecision.model_json_schema()), recover)

if __name__ == "__main__":
    anyio.run(serve_stdio, server)
