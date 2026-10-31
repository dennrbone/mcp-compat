"""Comparable strategy decisions; schema validity never asserts semantics."""

from typing import Protocol

from mcp_compat import MigrationDecision, SchemaDiffEngine, ToolCall
from mcp_compat.benchmark import RecoveryInput
from mcp_compat.llm import SemanticMapper


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


class LLMBaseline:
    def __init__(self, name: str, mapper: SemanticMapper):
        if name not in ("B1", "B2"):
            raise ValueError("unknown LLM baseline")
        self.name, self.mapper = name, mapper

    def recover(self, request: RecoveryInput) -> MigrationDecision:
        initial = None
        error = None
        if self.name == "B1":
            initial = NoRecovery().recover(request)
            if initial.action == "EXECUTE":
                initial.evidence["method"] = self.name
                return initial
            error = initial.evidence["error"]
        result = self.mapper.propose_mapping(request, self.name, error)
        proposal = result.proposal
        if proposal is None or proposal.action == "ABSTAIN" or proposal.call is None:
            decision = abstain("llm_abstain", mapping_reason=result.reason)
        else:
            decision = validate_candidate(request, proposal.call, self.name)
        decision.evidence.update(llm=result.trace, initial_attempt=None if initial is None else initial.model_dump())
        return decision
