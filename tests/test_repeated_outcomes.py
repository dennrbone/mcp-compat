from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from mcp_compat.benchmark import generate
from mcp_compat.experiments import _evaluate
from mcp_compat.recovery import NoRecovery, abstain


def test_repeat_diagnostics_keep_cases_and_failed_attempts_visible():
    spec = spec_from_file_location('repeated',Path(__file__).resolve().parents[1]/'examples/publication_results.py')
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    first = _evaluate(generate(42)[5],NoRecovery(),0,0)
    assert first.semantic_equivalent is True
    first.method = 'B2'
    second = first.model_copy(deep=True,update=dict(repeat=1,decision=abstain('timeout'),semantic_equivalent=None,cost=None))
    second.decision.evidence['llm'] = dict(calls=2,responses=[],parse_status='invalid_or_unavailable',parse_errors=[dict(error_type='ProviderError')])
    result = module.repeated_outcomes([first,second])['B2']
    assert result['unique_cases'] == 1 and result['action_disagreements'] == 1
    assert result['recoverable_cases_by_correct_repeat_count'] == {'1':1}
    assert result['per_repeat']['0']['CRR']['numerator'] == 1
    assert result['per_repeat']['1']['CRR']['numerator'] == 0
    assert result['attempt_errors'] == {'ProviderError':1} and result['records_with_unknown_usage'] == 1
    assert result['terminal_unparsed'] == 1 and result['parsed_mappings'] == 0
