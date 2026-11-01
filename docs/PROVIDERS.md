# GigaCode CodeAgent

The configured real-test provider is the already installed GigaCode CLI
**26.10.76**, model **CodeAgent**. Its actual catalog identifier is
`gigacode/GigaCode`; the installed extension's older examples use another
spelling. The catalog reports zero token cost. Its underlying model family and
immutable service revision are not exposed and must not be invented.

The [official CLI documentation](https://gitverse.ru/docs/ai/ai-assistant-gigacode/gigacode-cli/commands)
and the installed CLI's `run --help`, `models gigacode --verbose` and
`mcp --help` were inspected. The local extension supplies the executable;
no additional client is installed by this project.

Set `GIGACODE_BIN` to its absolute path when absent from PATH. Credentials remain
in the existing client store; never put them in repository files or transcripts.
The adapter does not change global authentication or shell profiles.

```sh
mcp-compat-agents --output experiments/codeagent-smoke
mcp-compat-agents --pilot --output experiments/codeagent-pilot
```

Each output directory is new: smoke evidence is written exclusively. The nested
pilot runner supports identical-configuration resume through its Python API.
The pilot starts only after a strict JSON smoke succeeds. The separate real
pytest case requires `MCP_COMPAT_RUN_PROVIDER_SMOKE=1`; enabled failures fail.
Missing credentials/configuration, quota errors, malformed JSON and timeouts
are never converted to passes. Actual results: [AGENT_TESTS.md](AGENT_TESTS.md).

The adapter uses an empty temporary workspace and isolated config directories,
`--pure`, disabled plugins/external skills/project config/title/summary/compaction,
disabled sharing/snapshots, and denied tools. Normal and small-model IDs are both
pinned to CodeAgent. The installed client still supplies its own system context;
this is a CLI-harness experiment, not a bare-API comparison. Mapping instructions
are repeated in the final user message because the client otherwise treated a
schema-only message as an ordinary coding question.

One step, temperature 0, an output-token cap of 2048 and a deadline up to 120 s
are configured. Tool/error/incomplete/multiple-step events and nonzero reported
cost are rejected. A temporary file captures stdout; at most 1 MiB is decoded.
CLI stderr and credentials never appear in provider exceptions. TLS verification
remains enabled. Model output cannot create shell commands.

`calls` measures wrapper invocations, not an independently audited count of
backend requests or invisible client retries. Reported input usage includes
cache reads/writes; output includes reasoning when present. Missing usage remains
null. A reported zero cost is not an independent billing audit.

Prompt `mapping-1.1` explicitly requires one JSON object. Fenced/prose responses
remain rejected. Historical artifacts retain their original prompt/fingerprint.

Other models use the existing `LLMClient.complete(request, timeout)` protocol and
`Mapper` injection. Standard MCP agents connect through stdio. These extension
points require no provider-specific recovery logic; see
[CLIENT_INTEGRATION.md](CLIENT_INTEGRATION.md).
