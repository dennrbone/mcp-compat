# Connecting a model or agent

Only GigaCode CodeAgent is configured and used for real tests. The recovery
engine depends on the `LLMClient` protocol, not a provider name or SDK. A new
client supplies one method:

```python
from mcp_compat.llm import LLMClient, LLMRequest, LLMResponse, Mapper

# your_client implements complete(request: LLMRequest, timeout: float) -> LLMResponse
mapper = Mapper(your_client, attempts=1, timeout=120)
```

The method sends the supplied system/data/response schema to the chosen model,
honors the timeout, and returns raw text plus its real model ID and measured
usage (or null for unknown usage). Credentials belong to that client's local
configuration. Do not strip Markdown, fabricate tokens/cost or convert transport
errors into successful model replies. `Mapper` already validates strict JSON,
limits, retries and declarative operations.

Pass this mapper into `LLMBaseline("B2", mapper)` or `Hybrid(mapper, verifier)`.
The verifier must use independently authored, contract-bound implementations;
the benchmark oracle is never a substitute. The generic interface is exercised
with injected clients in `test_llm.py` and `test_providers.py`.

## Standard MCP agents

The runnable `examples/mcp_server.py` exposes `check_migration` over the official
MCP SDK's stdio transport. Use an absolute Python executable with the project's
`mcp` dependency and the absolute script path as the MCP server command. No
provider SDK is needed in the connecting agent.

```sh
/path/to/python /path/to/mcp-compat/examples/mcp_server.py
```

This is a protocol process: stdout is reserved for MCP messages. An MCP client
starts it, initializes a session, lists tools and sends a `RecoveryInput` JSON
object to `check_migration`. Tool descriptions expose the complete input/output
schemas. The example computes a migration decision and never invokes a business
tool. Its verifier is deliberately unbound: it returns ABSTAIN rather than
claiming verified execution. Bind trusted runtimes and your mapper when embedding
the engine in an application.

In installed GigaCode use `gigacode mcp add`, select a local stdio server and set
the executable/arguments above. Other MCP clients use their own server settings;
the wire protocol is the same. This project does not edit global agent settings.

`serve_stdio(server)` exposes any existing server built by `make_server` or
`make_proxy`. The proxy accepts a standard upstream `ClientSession` and an
injected recovery strategy. Existing input/output checks and fail-closed behavior
apply independently of which agent/model connects.

`test_model_independent_stdio_example` starts a real subprocess and verifies
handshake, ping, discovery, a structured ABSTAIN and invalid-input handling through
the official SDK client. It does not claim every third-party agent has been tested.
