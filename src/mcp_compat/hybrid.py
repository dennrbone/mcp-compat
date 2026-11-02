"""Verified recovery with a declarative adapter and independently bound runtimes."""

from copy import deepcopy
from hashlib import sha256
import json
import math
from time import monotonic
from typing import Any, Callable, Literal, Protocol

from pydantic import BaseModel, Field

from mcp_compat import MigrationDecision, SchemaDiffEngine, ToolCall, ToolContract, canonical_bytes
from mcp_compat.benchmark import RecoveryInput
from mcp_compat.diff.engine import _path
from mcp_compat.llm import Operation, SemanticMapper
from mcp_compat.recovery import RuleBased, abstain, validate_candidate


class Verification(BaseModel):
    passed: bool
    reason: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class RuntimeVerifier(Protocol):
    def verify(self, request: RecoveryInput, call: ToolCall) -> Verification: ...


def digest(contract: ToolContract) -> str:
    return sha256(canonical_bytes(contract.model_dump())).hexdigest()


def normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: normalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize(item) for item in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


class SandboxVerifier:
    """Callbacks are trusted local tool implementations, never benchmark oracles."""

    def __init__(self, old: ToolContract, new: ToolContract,
                 old_impl: Callable[[dict, dict], Any], new_impl: Callable[[dict, dict], Any],
                 *, side_effects: bool = False, initial: dict | None = None,
                 timeout: float = 1, clock: Callable[[], float] = monotonic):
        self.bindings = digest(old), digest(new)
        self.old_impl, self.new_impl = old_impl, new_impl
        self.side_effects, self.initial = side_effects, deepcopy(initial or {})
        self.timeout, self.clock = timeout, clock

    def verify(self, request: RecoveryInput, call: ToolCall) -> Verification:
        if self.bindings != (digest(request.old_contract), digest(request.new_contract)):
            return Verification(passed=False, reason="unbound_runtime")
        started = self.clock()
        try:
            request.old_call.validate_against(request.old_contract)
            call.validate_against(request.new_contract)
            left, right = deepcopy(self.initial), deepcopy(self.initial)
            old_result = self.old_impl(deepcopy(request.old_call.arguments), left)
            new_result = self.new_impl(deepcopy(call.arguments), right)
            if self.clock() - started > self.timeout:
                return Verification(passed=False, reason="verification_timeout")
            before, after = (left, right) if self.side_effects else (old_result, new_result)
            json.dumps([before, after], allow_nan=False)
            before, after = normalize(before), normalize(after)
            passed = canonical_bytes(before) == canonical_bytes(after)
            return Verification(passed=passed, reason="equivalent" if passed else "semantic_mismatch",
                evidence=dict(old_outcome=sha256(canonical_bytes(before)).hexdigest(),
                              new_outcome=sha256(canonical_bytes(after)).hexdigest()))
        except Exception:
            return Verification(passed=False, reason="verification_error")


class RuntimeRegistry:
    """Only application-registered, digest-bound implementations may execute."""

    def __init__(self, verifiers: list[SandboxVerifier]):
        self.bindings: dict[tuple[str,str], SandboxVerifier] = {}
        for verifier in verifiers:
            if verifier.bindings in self.bindings:
                raise ValueError("duplicate runtime binding")
            self.bindings[verifier.bindings] = verifier

    def verify(self, request: RecoveryInput, call: ToolCall) -> Verification:
        verifier = self.bindings.get((digest(request.old_contract),digest(request.new_contract)))
        if verifier is None:
            return Verification(passed=False,reason="unbound_runtime")
        return verifier.verify(request,call)


def _read(arguments: dict, path: list[str]) -> Any:
    value: Any = arguments
    for key in path:
        value = value[key]
    return deepcopy(value)


def adapt(request: RecoveryInput, operations: list[Operation]) -> ToolCall:
    """All reads use the original call; overlapping writes and cycles are rejected."""
    paths = [tuple(op.target) for op in operations]
    for i, target in enumerate(paths):
        for other in paths[i + 1:]:
            if target[:len(other)] == other or other[:len(target)] == target:
                raise ValueError("overlapping adapter targets")
    for op in operations:
        if op.source is not None:
            for other_op in operations:
                if other_op is not op and tuple(op.source) == tuple(other_op.target):
                    raise ValueError("cyclic or dependent mapping")
    args = deepcopy(request.old_call.arguments)
    for op in operations:
        value = op.value if op.source is None else _read(request.old_call.arguments, op.source)
        if op.op in ("scale", "string"):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("conversion requires finite number")
            if op.op == "scale":
                assert op.factor is not None
                value = value * op.factor
            else:
                value = str(value)
        elif op.op == "wrap":
            value = [value]
        elif op.op == "enum":
            if not isinstance(value, str):
                raise ValueError("enum conversion requires a string")
            assert op.values is not None
            value = op.values[value]
        if op.op == "move" and op.source != op.target:
            assert op.source is not None
            parent = args
            for key in op.source[:-1]:
                parent = parent[key]
            del parent[op.source[-1]]
        parent = args
        for key in op.target[:-1]:
            parent = parent.setdefault(key, {})
        parent[op.target[-1]] = deepcopy(value)
    return ToolCall(tool_name=request.new_contract.name, arguments=args)


class Hybrid:
    name = "M1"

    def __init__(self, mapper: SemanticMapper | None = None, verifier: RuntimeVerifier | None = None,
                 *, ablation: Literal["A1", "A2", "A3", "A4"] | None = None):
        self.mapper, self.verifier, self.ablation = mapper, verifier, ablation
        if ablation is not None:
            self.name = ablation

    def recover(self, request: RecoveryInput) -> MigrationDecision:
        stages: dict[str, Any] = {"method": self.name}
        try:
            request.old_call.validate_against(request.old_contract)
            diff = SchemaDiffEngine.compare(request.old_contract, request.new_contract)
            stages["diff"] = diff.model_dump()
            if not diff.is_complete:
                return abstain("opaque", **stages)
            stages["candidates"] = sorted(set(request.old_contract.input_schema.get("properties", {})) & set(request.new_contract.input_schema.get("properties", {})))
            operations = []
            deterministic = RuleBased().recover(request)
            if deterministic.action == "EXECUTE" and self.ablation != "A2":
                call = deterministic.adapted_call
                assert call is not None
            else:
                if self.ablation == "A3":
                    return abstain("no_deterministic_candidate", **stages)
                if self.mapper is None:
                    return abstain("mapper_unavailable", **stages)
                mapping = self.mapper.propose_mapping(request)
                stages["llm"] = mapping.trace
                if mapping.proposal is None or mapping.proposal.action != "EXECUTE":
                    return abstain("mapping_abstain", **stages)
                operations = mapping.proposal.operations
                stages["adapter"] = [op.model_dump(exclude_unset=True) for op in operations]
                call = adapt(request, operations)
            decision = validate_candidate(request, call, self.name)
            stages.update(decision.evidence)
            if decision.action != "EXECUTE":
                return abstain("schema_invalid", **stages)
            verification = Verification(passed=False, reason="verifier_unavailable")
            if self.ablation != "A1" and self.verifier is not None:
                verification = self.verifier.verify(request, call)
            stages["verification"] = verification.model_dump()
            if self.ablation != "A4":
                if self.ablation != "A1" and not verification.passed:
                    return abstain(verification.reason, **stages)
                public = [Operation.model_validate(rule) for rule in request.context.get("rules", [])]
                for op in operations:
                    if op.op == "set" and op not in public:
                        schema = request.new_contract.input_schema
                        for segment in op.target:
                            schema = schema["properties"][segment]
                        if "default" not in schema or canonical_bytes(schema["default"]) != canonical_bytes(op.value):
                            return abstain("literal_value_unproven", **stages)
                unit_changes = [c for c in diff.changes if c.family == "C8"]
                if unit_changes or any(op.op == "scale" for op in operations):
                    allowed: dict[tuple[Any, Any], int] = {("RUB", "kopecks"):100, ("seconds", "milliseconds"):1000}
                    proven: set[str] = set()
                    for op in operations:
                        if op.op == "scale":
                            if op not in public:
                                return abstain("unit_rule_missing", **stages)
                            old_node,new_node = request.old_contract.input_schema,request.new_contract.input_schema
                            old_path,new_path = "input","input"
                            assert op.source is not None
                            for segment in op.source:
                                old_node = old_node["properties"][segment]
                                old_path = _path(old_path+".properties",segment)
                            for segment in op.target:
                                new_node = new_node["properties"][segment]
                                new_path = _path(new_path+".properties",segment)
                            pairs = [(request.old_contract.metadata.get("semantic_unit"),request.new_contract.metadata.get("semantic_unit")),
                                     (old_node.get("semantic_unit"),new_node.get("semantic_unit"))]
                            if not any(allowed.get(pair) == op.factor for pair in pairs):
                                return abstain("unit_rule_missing", **stages)
                            for change in unit_changes:
                                if allowed.get((change.old_value,change.new_value)) == op.factor and change.path in ("metadata.semantic_unit",old_path+".semantic_unit",new_path+".semantic_unit"):
                                    proven.add(change.path)
                    if any(change.path not in proven for change in unit_changes):
                        return abstain("unit_rule_missing", **stages)
                    stages["unit_rules_proven"] = sorted(proven)
            decision.evidence.update(stages, semantic_verified=verification.passed)
            decision.reasons = ["verified" if verification.passed else "ablation_unverified"]
            return decision
        except Exception as exc:
            return abstain("pipeline_error", **stages, error_type=type(exc).__name__)
