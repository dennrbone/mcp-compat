"""Comparable strategy decisions; schema validity never asserts semantics."""

from typing import Protocol

from mcp_compat import MigrationDecision, SchemaDiffEngine, ToolCall
from mcp_compat.benchmark import RecoveryInput


class Strategy(Protocol):
    name: str

    def recover(self, request: RecoveryInput) -> MigrationDecision: ...


def abstain(reason: str, **evidence) -> MigrationDecision:
    return MigrationDecision(action="ABSTAIN", reasons=[reason], evidence=evidence)


def validate_candidate(request: RecoveryInput, call: ToolCall, method: str) -> MigrationDecision:
    evidence = dict(method=method, candidate=call.model_dump(), semantic_verified=False)
    try:
        call.validate_against(request.new_contract)
    except ValueError as error:
        return abstain("schema_invalid", **evidence, schema_valid=False, error=str(error))
    return MigrationDecision(action="EXECUTE", adapted_call=call.model_copy(deep=True),
                             reasons=["schema_valid"], evidence=dict(evidence, schema_valid=True))


class NoRecovery:
    name = "B0"

    def recover(self, request: RecoveryInput) -> MigrationDecision:
        return validate_candidate(request, request.old_call, self.name)


class RuleBased:
    """No rename/value guessing. Only changes leaving supplied values intact."""

    name = "B3"

    def recover(self, request: RecoveryInput) -> MigrationDecision:
        diff = SchemaDiffEngine.compare(request.old_contract, request.new_contract)
        if not diff.is_complete:
            return abstain("opaque", diff=diff.model_dump())
        for change in diff.changes:
            if change.family == "C1" and change.subtype == "tool_renamed":
                continue
            if change.family == "C2" and change.subtype == "parameter_added":
                continue
            if change.family == "C6" and change.subtype in ("enum_values_added", "enum_values_removed"):
                continue
            if change.family == "C3" and change.subtype == "required_changed" and change.new_value is True:
                continue
            return abstain("no_structural_rule", diff=diff.model_dump())
        call = ToolCall(tool_name=request.new_contract.name, arguments=request.old_call.arguments)
        decision = validate_candidate(request, call, self.name)
        decision.evidence["diff"] = diff.model_dump()
        return decision
