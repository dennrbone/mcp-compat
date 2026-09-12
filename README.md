# MCP-Compat

MCP-Compat is a research project about safely restoring LLM-agent compatibility after MCP tool contracts evolve. It is not production-ready.

Phase 1 provides typed `ToolContract`, `ToolCall`, and `EvolutionScenario` models, JSON Schema Draft 2020-12 validation, and deterministic JSON serialization. It does not include MCP transport, LLM integrations, benchmark generation, schema diffing, or recovery algorithms.

## Setup

Use Python 3.11.4:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Validation example

`ToolCall.validate_against` returns `None` for a valid call and raises `ToolCallValidationError` for a wrong tool name or invalid arguments.

```python
from mcp_compat import ToolCall, ToolCallValidationError, ToolContract

contract = ToolContract(
    name="reserve_stock",
    input_schema={
        "type": "object",
        "properties": {"quantity": {"type": "integer", "minimum": 1}},
        "required": ["quantity"],
    },
)

ToolCall(tool_name="reserve_stock", arguments={"quantity": 2}).validate_against(contract)

try:
    ToolCall(tool_name="reserve_stock", arguments={}).validate_against(contract)
except ToolCallValidationError as error:
    print(error)
```

Models use Pydantic's `model_dump_json` and `model_validate_json` for JSON round trips. Pass `model_dump(mode="json")` to `canonical_json` or `canonical_bytes` when deterministic serialization is required.

## Tests

Run the tests:

```bash
pytest -q
```

Run the Phase 1 quality gate:

```bash
pytest -q --cov=mcp_compat --cov-report=term-missing --cov-report=xml --cov-fail-under=100
```

Phase 1 requires 100% statement coverage for `src/mcp_compat`. GitHub Actions runs the same gate on pushes to `main` and `phase/**`, and on pull requests targeting `main`.

Development for this phase belongs on `phase/01-domain-model`; merge into `main` only after local tests and CI pass.
