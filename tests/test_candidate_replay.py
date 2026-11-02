from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from mcp_compat.benchmark import generate
from mcp_compat.experiments import _evaluate
from mcp_compat.hybrid import Verification
from mcp_compat.recovery import NoRecovery


def test_same_candidate_control_preserves_usage_and_rejections():
    spec = spec_from_file_location('replay',Path(__file__).resolve().parents[1]/'examples/replay_candidate_verification.py')
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    row = _evaluate(generate(42)[5],NoRecovery(),0,0)
    row.method = 'B2'
    row.calls, row.input_tokens, row.cost = 1,None,None
    original = row.model_dump()
    class Verifier:
        def __init__(self,passed):
            self.passed=passed
        def verify(self,request,call):
            assert request.model_dump() == row.recovery and call == row.decision.adapted_call
            return Verification(passed=self.passed,reason='checked')
    kept,details = module.replay([row],Verifier(True))
    assert len(kept) == 1 and kept[0].decision.adapted_call == row.decision.adapted_call
    assert kept[0].decision.evidence['candidate_replay_verification']['passed']
    assert kept[0].calls == 1 and kept[0].input_tokens is None and kept[0].cost is None
    assert details['incremental_model_calls'] == 0
    rejected,_ = module.replay([row],Verifier(False))
    assert rejected[0].decision.action == 'ABSTAIN' and rejected[0].semantic_equivalent is None
    assert row.model_dump() == original
    row.decision = rejected[0].decision
    assert module.replay([row],Verifier(True))[0][0].decision.action == 'ABSTAIN'
    row.method = 'M1'
    assert module.replay([row],Verifier(True))[0] == []
