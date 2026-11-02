# Local MCP integration

The `mcp` extra pins the official Python SDK **1.30.0**, verified against its
installed source and [official repository](https://github.com/modelcontextprotocol/python-sdk).
`make_server(contract, async_implementation, state)` creates a low-level SDK
Server with discovery and structured tool calls. Input and output validation
uses our non-fetching Draft 2020-12 validator. No arbitrary remote tools are
registered. The fixtures are in-memory only, not production gateways.

`make_proxy(old, new, upstream_session, strategy, context=..., timeout=...)`
exposes the old tool schema, obtains a MigrationDecision and forwards only the
validated adapted call. Successful structured results must satisfy the old
output schema. Abstention/upstream failures are MCP error results with a JSON
ABSTAIN envelope, not silent success. Calls and strategy waiting have deadlines;
cancelled worker threads may finish their trusted local computation, but cannot
forward a call after the proxy has returned a timeout.

Run `.venv/bin/python -m pytest -q tests/test_mcp.py` for actual SDK protocol
handshake/ping, discovery, schemas, v1/v2 calls, verified RUB→kopecks compatibility,
bad payloads/names/results, abstention, server errors, timeouts and disconnects.
These tests do not contact an external MCP server or use user data.

## Standard stdio clients

`serve_stdio(server)` runs an existing SDK Server through the official stdio
transport. The runnable `examples/mcp_server.py` exposes a model-independent
migration-decision endpoint. A real subprocess/client test verifies handshake,
ping, discovery, structured abstention and invalid input. The additional opt-in
CodeAgent smoke verifies that the installed agent actually calls that MCP tool.
See CLIENT_INTEGRATION.md for model injection and agent connection instructions.

Версия научного прототипа закреплена на SDK 1.30.0. Актуальная спецификация
2026-07-28 меняет протокольное ядро; успешный тест прежнего handshake не является
проверкой всех возможностей новой редакции. Массовый runner вызывает стратегии
напрямую. Протокольные тесты, включая 192 прикладных сценария, учитываются
отдельно от количества модельных решений.
