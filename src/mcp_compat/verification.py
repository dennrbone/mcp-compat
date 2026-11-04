"""Повторяемые свидетельства допуска для доверенной замкнутой среды."""

from copy import deepcopy
from hashlib import sha256
from importlib.metadata import version
from time import monotonic
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict

from mcp_compat import MigrationDecision, ToolCall, ToolContract, canonical_bytes
from mcp_compat.benchmark import RecoveryInput
from mcp_compat.hybrid import Verification, digest, normalize
from mcp_compat.schema import validate_instance

EVIDENCE_VERSION = "admission-evidence-3"
NORMALIZATION_VERSION = "json-numeric-int-1"


class ObservationProfile(BaseModel):
    """Декларации доверенного оператора, не выводимые из одной JSON Schema."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    name: str
    state_components: tuple[str, ...] = ()
    complete: bool = False
    closed_environment: bool = False
    deterministic: bool = False
    unambiguous: bool = False


def fingerprint(value: Any) -> str:
    return sha256(canonical_bytes(value)).hexdigest()


class EvidenceVerifier:
    """Сравнивает результат И состояние; callback должны быть доверенными."""

    def __init__(self, old: ToolContract, new: ToolContract,
                 old_impl: Callable[[dict, dict], Any], new_impl: Callable[[dict, dict], Any],
                 *, profile: ObservationProfile, handler_ids: tuple[str, str],
                 initial: dict | None = None, timeout: float = 1,
                 clock: Callable[[], float] = monotonic):
        if not 0 < timeout < float("inf") or len(handler_ids) != 2 or not all(handler_ids):
            raise ValueError("positive timeout and two pinned handler identifiers required")
        self.bindings = digest(old), digest(new)
        self.old_impl, self.new_impl = old_impl, new_impl
        self.profile, self.handler_ids = profile, handler_ids
        self.initial = deepcopy({} if initial is None else initial)
        self.timeout, self.clock = timeout, clock

    def verify(self, request: RecoveryInput, call: ToolCall) -> Verification:
        witness: dict[str, Any] = dict(
            version=EVIDENCE_VERSION, scope="preview", normalization=NORMALIZATION_VERSION,
            validator="jsonschema-" + version("jsonschema"),
            handlers=list(self.handler_ids), profile=self.profile.model_dump(mode="json"),
            checks={}, observations=[],
        )

        def finish(reason: str, passed: bool = False) -> Verification:
            witness.update(action="EXECUTE" if passed else "ABSTAIN", reason=reason)
            return Verification(passed=passed, reason=reason,
                                evidence=dict(witness=witness, witness_sha256=fingerprint(witness)))

        try:
            witness.update(contracts=[digest(request.old_contract), digest(request.new_contract)],
                           original=fingerprint(request.old_call.model_dump()),
                           candidate=fingerprint(call.model_dump()), initial=fingerprint(self.initial))
            if tuple(witness["contracts"]) != self.bindings:
                return finish("unbound_runtime")
            p = self.profile
            if not (p.complete and p.closed_environment and p.deterministic and p.unambiguous):
                return finish("incomplete_observation_profile")
            request.old_call.validate_against(request.old_contract)
            call.validate_against(request.new_contract)
            witness["checks"]["inputs"] = True
            witness["checks"]["outputs"] = [
                "declared_schema" if c.output_schema is not None else "finite_json_only"
                for c in (request.old_contract, request.new_contract)
            ]
            started = self.clock()
            trials = []
            for _ in range(2):
                observations = []
                for contract, implementation, arguments in (
                    (request.old_contract, self.old_impl, request.old_call.arguments),
                    (request.new_contract, self.new_impl, call.arguments),
                ):
                    state = deepcopy(self.initial)
                    result = implementation(deepcopy(arguments), state)
                    canonical_bytes([result, state])
                    if not set(state).union(self.initial).issubset(p.state_components):
                        return finish("unobserved_state")
                    if contract.output_schema is not None:
                        validate_instance(result, contract.output_schema)
                    observations.append(canonical_bytes(normalize(dict(result=result, state=state))))
                trials.append(observations)
                witness["observations"].append([sha256(value).hexdigest() for value in observations])
            if self.clock() - started > self.timeout:
                return finish("verification_timeout")
            first, second = trials
            if first != second:
                return finish("nondeterministic_observation")
            if first[0] != first[1]:
                return finish("semantic_mismatch")
            witness["checks"].update(outputs_valid=True, repeatable=True, equivalent=True)
            return finish("equivalent", True)
        except Exception:
            return finish("verification_error")

    def replay(self, witness: dict, request: RecoveryInput, call: ToolCall,
               *, current_state: dict) -> Verification:
        """Пересчитывает свидетель; не исполняет реальную операцию и не закрывает TOCTOU."""
        try:
            if fingerprint(current_state) != fingerprint(self.initial):
                return Verification(passed=False, reason="state_changed")
            verified = self.verify(request, call)
            if canonical_bytes(witness) != canonical_bytes(verified.evidence["witness"]):
                return Verification(passed=False, reason="witness_mismatch")
            return verified
        except (TypeError, ValueError):
            return Verification(passed=False, reason="verification_error")

    def admit(self, request: RecoveryInput, decision: MigrationDecision,
              *, current_state: dict) -> MigrationDecision:
        """Применяет replay к решению caller; внешний commit всё ещё должен быть атомарным."""
        if decision.action == "ABSTAIN":
            return decision
        call = decision.adapted_call
        assert call is not None
        try:
            preview = Verification.model_validate(decision.evidence["verification"])
            witness = preview.evidence["witness"]
        except (KeyError, ValueError):
            witness = None
        checked = (self.replay(witness, request, call, current_state=current_state)
                   if isinstance(witness, dict) else Verification(passed=False, reason="witness_missing"))
        evidence = deepcopy(decision.evidence)
        evidence.update(admission=checked.model_dump(), semantic_verified=checked.passed,
                        candidate=call.model_dump())
        return MigrationDecision(action="EXECUTE" if checked.passed else "ABSTAIN",
            adapted_call=call.model_copy(deep=True) if checked.passed else None,
            reasons=["verified_admission" if checked.passed else checked.reason], evidence=evidence)
