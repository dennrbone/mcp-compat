"""Public API for MCP-Compat Phases 1–2."""

from mcp_compat.diff import ContractChange, OpaqueChange, SchemaDiff, SchemaDiffEngine
from mcp_compat.domain.decisions import MigrationDecision
from mcp_compat.domain.calls import ToolCall, ToolCallValidationError
from mcp_compat.domain.contracts import ToolContract
from mcp_compat.domain.scenarios import EvolutionScenario
from mcp_compat.schema.canonical import canonical_bytes, canonical_json

__all__ = [
    "ContractChange",
    "OpaqueChange",
    "SchemaDiff",
    "SchemaDiffEngine",
    "MigrationDecision",
    "EvolutionScenario",
    "ToolCall",
    "ToolCallValidationError",
    "ToolContract",
    "canonical_bytes",
    "canonical_json",
]
