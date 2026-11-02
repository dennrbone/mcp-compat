from copy import deepcopy
import json
from pathlib import Path

import pytest

from mcp_compat import ToolCall
from mcp_compat.benchmark import equivalent, load, recovery_input
from mcp_compat.experiments import OfflineClient
from mcp_compat.hybrid import Hybrid, RuntimeRegistry, SandboxVerifier, digest
from mcp_compat.llm import Mapper
from mcp_compat.runtime_fixtures import base_contract, fixture_verifier


@pytest.fixture(scope="module")
def corpus():
    index = json.loads(Path("benchmark/manifest.json").read_bytes())
    return load(Path(index["path"]), index["digest"])


@pytest.fixture(scope="module")
def registry():
    return fixture_verifier()


def test_full_corpus_correct_calls_and_side_effects_are_verified(corpus, registry):
    counts = {"verified": 0, "unbound": 0, "must_abstain": 0}
    for scenario in corpus:
        request = recovery_input(scenario)
        if not scenario.metadata["recoverable"]:
            counts["must_abstain"] += 1
            continue
        call = ToolCall.model_validate(scenario.oracle["expected_call"])
        result = registry.verify(request, call)
        if result.reason == "unbound_runtime":
            assert scenario.mutation_subtype in (
                "integer_string",
                "number_decimal_string",
                "scalar_array",
                "split_value",
            )
            counts["unbound"] += 1
        else:
            assert result.passed, (scenario.scenario_id, result)
            counts["verified"] += 1
    assert counts == dict(verified=1056, unbound=192, must_abstain=912)
    assert len(registry.bindings) > 1000


def test_full_corpus_hybrid_has_no_unsafe_execution_with_declared_rule_client(
    corpus, registry
):
    engine = Hybrid(Mapper(OfflineClient(), attempts=1), registry)
    executed = 0
    for scenario in corpus:
        decision = engine.recover(recovery_input(scenario))
        if decision.action == "EXECUTE":
            assert equivalent(scenario, decision.adapted_call), scenario.scenario_id
            assert decision.evidence["verification"]["passed"]
            executed += 1
    assert executed == 1056


def test_schema_equivalence_does_not_identify_an_implementation(corpus, registry):
    pairs = [
        ("commerce-0-C5-0", "commerce-0-C5-3"),
        ("commerce-0-C5-1", "commerce-0-C7-3"),
    ]
    by_id = {s.scenario_id: s for s in corpus}
    for first, second in pairs:
        a, b = by_id[first], by_id[second]
        assert digest(a.new_contract) == digest(b.new_contract)
        call = ToolCall.model_validate(a.oracle["expected_call"])
        assert registry.verify(recovery_input(a), call).reason == "unbound_runtime"


def test_registry_is_bound_and_never_calls_evaluator(corpus, registry, monkeypatch):
    scenario = next(s for s in corpus if s.scenario_id == "finance-2-C8-0")
    request = recovery_input(scenario)
    call = ToolCall.model_validate(scenario.oracle["expected_call"])

    def forbidden(*args, **kwargs):
        raise AssertionError("evaluator leaked into runtime verification")

    for name in ("simulate", "equivalent", "_view"):
        monkeypatch.setattr("mcp_compat.benchmark." + name, forbidden)
    assert registry.verify(request, call).passed
    request.new_contract.metadata["untrusted"] = "changed"
    assert registry.verify(request, call).reason == "unbound_runtime"
    assert RuntimeRegistry([]).verify(request, call).reason == "unbound_runtime"


def test_schema_invalid_calls_never_reach_runtime():
    contract = base_contract("commerce", "quote")
    called = []

    def implementation(arguments, state):
        called.append(arguments)
        return arguments

    v = SandboxVerifier(contract, contract, implementation, implementation)
    with pytest.raises(ValueError, match="duplicate"):
        RuntimeRegistry([v, v])
    from mcp_compat.benchmark import RecoveryInput

    good = dict(
        value=2, target="id", mode="express", notify=True, legacy=True, duration=60
    )
    request = RecoveryInput(
        old_contract=contract,
        new_contract=contract,
        old_call=ToolCall(tool_name=contract.name, arguments=good),
    )
    assert (
        v.verify(request, ToolCall(tool_name="wrong", arguments=good)).reason
        == "verification_error"
    )
    assert not called
    request.old_call.arguments["value"] = "invalid"
    assert (
        v.verify(request, ToolCall(tool_name=contract.name, arguments=good)).reason
        == "verification_error"
    )
    assert not called


def test_changed_numeric_and_side_effect_inputs_cannot_pass(corpus, registry):
    cases = [
        s
        for s in corpus
        if s.metadata["recoverable"]
        and (digest(s.old_contract), digest(s.new_contract)) in registry.bindings
    ]
    for scenario in cases:
        call = ToolCall.model_validate(scenario.oracle["expected_call"])
        changed = deepcopy(call.arguments)
        node = changed if "duration" in changed else changed["payload"]
        node["duration"] += 1
        wrong = ToolCall(tool_name=call.tool_name, arguments=changed)
        assert not equivalent(scenario, wrong)
        assert not registry.verify(recovery_input(scenario), wrong).passed, (
            scenario.scenario_id
        )


def test_experiment_methods_accept_application_supplied_registry(corpus):
    from mcp_compat.experiments import recovery_methods
    scenario=next(s for s in corpus if s.scenario_id=='commerce-0-C1-0')
    methods=recovery_methods(Mapper(OfflineClient()),RuntimeRegistry([]))
    m1=next(m for m in methods if m.name=='M1')
    assert m1.recover(recovery_input(scenario)).reasons==['unbound_runtime']


def test_trusted_packed_implementation_checks_actual_decoded_values(corpus,registry):
    scenario=next(s for s in corpus if s.scenario_id=='commerce-0-C7-4')
    request=recovery_input(scenario)
    arguments=deepcopy(request.old_call.arguments)
    value=arguments.pop('value')
    target=arguments.pop('target')
    arguments['packed']=f'{target}|{value}'
    correct=ToolCall(tool_name=request.new_contract.name,arguments=arguments)
    assert registry.verify(request,correct).passed
    arguments['packed']=f'other-target|{value}'
    assert not registry.verify(request,ToolCall(tool_name=correct.tool_name,arguments=arguments)).passed
    arguments['packed']='invalid'
    assert registry.verify(request,ToolCall(tool_name=correct.tool_name,arguments=arguments)).reason=='verification_error'
