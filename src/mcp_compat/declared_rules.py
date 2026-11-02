"""Детерминированные контроли для явно заданных операций миграции."""

from mcp_compat import MigrationDecision, canonical_json
from mcp_compat.benchmark import RecoveryInput
from mcp_compat.hybrid import Hybrid, RuntimeVerifier, adapt
from mcp_compat.llm import MappingResult, parse_proposal, response_schema
from mcp_compat.recovery import abstain, validate_candidate


class DeclaredRuleMapper:
    def propose_mapping(self, request: RecoveryInput, purpose: str = "mapping",
                        error: str | None = None) -> MappingResult:
        trace = dict(source="declared_rules", calls=0, responses=[])
        try:
            payload = dict(action="EXECUTE", operations=request.context.get("rules", []))
            proposal, _ = parse_proposal(canonical_json(payload), "mapping", response_schema("mapping", request))
            return MappingResult(proposal=proposal, reason="declared_rules", trace=trace)
        except (ValueError, TypeError):
            return MappingResult(reason="invalid_declared_rules", trace=trace)


class DeclaredRules:
    """D0 исполняет объявленные операции с проверкой схемы."""

    name = "D0"

    def recover(self, request: RecoveryInput) -> MigrationDecision:
        result = DeclaredRuleMapper().propose_mapping(request)
        if result.proposal is None:
            return abstain(result.reason, method=self.name, declared_rules=result.trace)
        try:
            request.old_call.validate_against(request.old_contract)
            call = adapt(request, result.proposal.operations)
            decision = validate_candidate(request, call, self.name)
            decision.evidence["declared_rules"] = result.trace
            return decision
        except (ValueError, KeyError, TypeError):
            return abstain("invalid_adapter", method=self.name, declared_rules=result.trace)


class VerifiedDeclaredRules(Hybrid):
    """D1 получает объявленные операции без модели, сохраняя проверки M1."""

    name = "D1"

    def __init__(self, verifier: RuntimeVerifier):
        super().__init__(DeclaredRuleMapper(), verifier)

    def recover(self, request: RecoveryInput) -> MigrationDecision:
        decision = super().recover(request)
        trace = decision.evidence.pop("llm", None)
        if trace is not None:
            decision.evidence["declared_rules"] = trace
        if decision.evidence.get("candidate_source") == "llm":
            decision.evidence["candidate_source"] = "declared_rules"
        return decision
