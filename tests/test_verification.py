from copy import deepcopy

import pytest

from mcp_compat import ToolCall, ToolContract
from mcp_compat.benchmark import RecoveryInput
from mcp_compat.hybrid import Hybrid, SandboxVerifier, digest
from mcp_compat.verification import EvidenceVerifier, ObservationProfile, fingerprint


def setup_verifier(old_impl=lambda a, s: a, new_impl=lambda a, s: a, **kwargs):
    contract = ToolContract(name="t", input_schema={"type": "object"},
                            output_schema={"type": "object"})
    request = RecoveryInput(old_contract=contract, new_contract=contract.model_copy(deep=True),
                            old_call=ToolCall(tool_name="t", arguments={"x": 2}))
    profile = ObservationProfile(name="test-1", complete=True, closed_environment=True,
                                 deterministic=True, unambiguous=True,
                                 state_components=("audit",))
    verifier = EvidenceVerifier(contract, contract, old_impl, new_impl,
        profile=kwargs.pop("profile", profile), handler_ids=kwargs.pop("handler_ids", ("old-v1", "new-v1")),
        **kwargs)
    return request, request.old_call.model_copy(deep=True), verifier


def test_repeatable_witness_independent_replay_and_hybrid():
    request, call, verifier = setup_verifier(initial={"audit": []})
    snapshot = deepcopy(request)
    result = verifier.verify(request, call)
    assert result.passed and result.reason == "equivalent"
    witness = result.evidence["witness"]
    assert result.evidence["witness_sha256"] == fingerprint(witness)
    assert verifier.replay(witness, request, call, current_state={"audit": []}).passed
    assert Hybrid(verifier=verifier).recover(request).action == "EXECUTE"
    assert request == snapshot and verifier.initial == {"audit": []}
    assert not {"oracle", "ground_truth", "scenario_id"}.intersection(witness)
    for key in ("original", "candidate", "initial", "handlers", "version", "profile", "checks", "action"):
        changed = deepcopy(witness)
        changed[key] = "tampered"
        assert verifier.replay(changed, request, call, current_state={"audit": []}).reason == "witness_mismatch"
    call.arguments["x"] = 3
    assert verifier.replay(witness, request, call, current_state={"audit": []}).reason == "witness_mismatch"
    assert verifier.replay(witness, request, call, current_state={"audit": [1]}).reason == "state_changed"
    request.new_contract.description = "changed"
    assert verifier.verify(request, call).reason == "unbound_runtime"


@pytest.mark.parametrize("missing", ["complete", "closed_environment", "deterministic", "unambiguous"])
def test_unknown_assumptions_refuse_without_running(missing):
    def forbidden(a, s):
        pytest.fail("incomplete profile must not execute callbacks")
    profile = ObservationProfile(name="p", **{k: k != missing for k in (
        "complete", "closed_environment", "deterministic", "unambiguous")})
    r, c, v = setup_verifier(forbidden, forbidden, profile=profile)
    assert v.verify(r, c).reason == "incomplete_observation_profile"


def test_result_and_state_are_both_observed_regression():
    r, c, v = setup_verifier(new_impl=lambda a, s: {"wrong": 1}, initial={"audit": []})
    legacy = SandboxVerifier(r.old_contract, r.new_contract, v.old_impl, v.new_impl,
                             side_effects=True, initial=v.initial)
    assert legacy.verify(r, c).passed
    assert v.verify(r, c).reason == "semantic_mismatch"

    def mutate(a, s):
        s["audit"] = ["changed"]
        return a
    r, c, v = setup_verifier(new_impl=mutate)
    assert SandboxVerifier(r.old_contract, r.new_contract, v.old_impl, mutate).verify(r, c).passed
    assert v.verify(r, c).reason == "semantic_mismatch"
    v.profile = v.profile.model_copy(update={"state_components": ()})
    assert v.verify(r, c).reason == "unobserved_state"


def test_invalid_inputs_outputs_finite_json_and_missing_schema():
    r, c, v = setup_verifier()
    c.tool_name = "other"
    assert v.verify(r, c).reason == "verification_error"
    c.tool_name = "t"
    r.old_call.tool_name = "other"
    assert v.verify(r, c).reason == "verification_error"
    r, c, v = setup_verifier(new_impl=lambda a, s: 1)
    assert v.verify(r, c).reason == "verification_error"
    r, c, v = setup_verifier(new_impl=lambda a, s: float("nan"))
    assert v.verify(r, c).reason == "verification_error"
    r, c, v = setup_verifier(new_impl=lambda a, s: {"x": 2.0})
    r.old_contract.output_schema = r.new_contract.output_schema = None
    v.bindings = tuple(digest(x) for x in (r.old_contract, r.new_contract))
    result = v.verify(r, c)
    assert result.passed
    assert result.evidence["witness"]["checks"]["outputs"] == ["finite_json_only"] * 2


def test_nondeterminism_error_and_elapsed_timeout():
    counter = iter([1, 2])
    r, c, v = setup_verifier(new_impl=lambda a, s: {"x": next(counter)})
    assert v.verify(r, c).reason == "nondeterministic_observation"
    ticks = iter([0, 2])
    r, c, v = setup_verifier(clock=lambda: next(ticks))
    assert v.verify(r, c).reason == "verification_timeout"
    def fail(a, s):
        raise RuntimeError("private details")
    r, c, v = setup_verifier(new_impl=fail)
    assert v.verify(r, c).reason == "verification_error"
    for arguments in ({"timeout": 0}, {"handler_ids": ("a",)}, {"handler_ids": ("", "a")}):
        with pytest.raises(ValueError):
            setup_verifier(**arguments)


def test_unsupported_semantic_diff_remains_opaque():
    r, _, v = setup_verifier()
    r.new_contract.input_schema["oneOf"] = [{"required": ["x"]}]
    assert Hybrid(verifier=v).recover(r).reasons == ["opaque"]


def test_replay_rejects_non_json_and_timeout_must_be_finite():
    r, c, v = setup_verifier()
    witness = v.verify(r, c).evidence["witness"]
    assert v.replay(witness, r, c, current_state={"audit": float("nan")}).reason == "verification_error"
    witness["unexpected"] = object()
    assert v.replay(witness, r, c, current_state={}).reason == "verification_error"
    for timeout in (float("nan"), float("inf")):
        with pytest.raises(ValueError):
            setup_verifier(timeout=timeout)
