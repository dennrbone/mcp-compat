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
are never converted to passes. Current results: [IMPROVEMENTS.md](IMPROVEMENTS.md).
Historical Phase 11 failures: [AGENT_TESTS.md](AGENT_TESTS.md).

The adapter uses an empty temporary workspace and isolated config directories,
`--pure`, disabled plugins/external skills/project config/title/summary/compaction,
disabled sharing/snapshots, and denied tools. Normal and small-model IDs are both
pinned to CodeAgent. The installed client still supplies its own system context;
this is a CLI-harness experiment, not a bare-API comparison. Mapping instructions
are repeated in the final user message because the client otherwise treated a
schema-only message as an ordinary coding question.

The CLI agent has a two-step ceiling with tools denied; successful requests must
still emit exactly one completed text-generation step. The previous one-step
ceiling could inject a summarization instruction on the first response. Temperature
0, a 2048-token output cap and a shared deadline up to 120 s remain fixed.
Inherited client-specific config variables are removed before applying the
isolated profile. Tool/error/incomplete/multiple-step events and nonzero reported
cost are rejected. Stderr is discarded; at most 1 MiB of stdout is decoded.

Protocol **mapping-2.0** supplies separate wire schemas. Mapping replies contain
`operations`; B1/B2 replies contain a `candidate` object, converted to the existing
internal `Proposal.call` only after validation. Unused mode definitions are absent.
The schema enforces opcode-specific operands and observable argument-path roots.
Paths are relative to arguments, with no `arguments` or `old_call` prefix.

The common parser accepts plain JSON or one complete JSON Markdown fence. Prose,
multiple objects/blocks, duplicate keys, nonfinite numbers, extra fields and
incorrect mode/operand shapes remain rejected. Raw replies are preserved. A
bounded retry supplies the required shape and error class, without copying error
messages or treating model output as instructions. Every request, response,
normalization and retry is recorded under the same total deadline.

`calls` counts wrapper invocations; response details record observed CLI steps.
These are not an independent audit of hidden backend retries or billing. Missing
usage remains null; reported cache reads/writes and reasoning count toward usage.

A native structured-output calibration was also attempted. The installed client
sometimes captured schema-invalid objects or timed out. It was not adopted as a
conformance guarantee. Production parsing remains in the shared validated mapper.
The earlier `mapping-1.1` pilot is historical evidence and is preserved unchanged.

Other models use the existing `LLMClient.complete(request, timeout)` protocol and
`Mapper` injection. Standard MCP agents connect through stdio. These extension
points require no provider-specific recovery logic; see
[CLIENT_INTEGRATION.md](CLIENT_INTEGRATION.md).
