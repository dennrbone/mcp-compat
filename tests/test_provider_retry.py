from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from hashlib import sha256
import json
import sys
from types import SimpleNamespace

import pytest

from mcp_compat import MigrationDecision, ToolCall, canonical_bytes
from mcp_compat.analysis import read_results
from mcp_compat.experiments import Record, _atomic, summaries


@pytest.fixture
def retry(monkeypatch):
    examples = Path(__file__).resolve().parents[1]/'examples'
    monkeypatch.syspath_prepend(str(examples))
    spec = spec_from_file_location('terra_provider_retry', examples/'terra_provider_retry.py')
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def row(parsed=False, execute=False, recoverable=True):
    trace = dict(parse_status='parsed' if parsed else 'invalid_or_unavailable', calls=1,
        requests=[{'data':{'purpose':'mapping'}}], responses=[{'text':'new'}] if parsed else [],
        parse_errors=[] if parsed else [{'error_type':'ProviderError'}])
    decision = MigrationDecision(action='EXECUTE' if execute else 'ABSTAIN',
        adapted_call=ToolCall(tool_name='t',arguments={}) if execute else None,
        evidence={'llm':trace})
    return Record(scenario_id='s',method='M1',repeat=2,mutation_family='C3',
        ground_truth='CONDITIONAL' if recoverable else 'MUST_ABSTAIN',recoverable=recoverable,
        base_tool='t',composed=False,decision=decision,schema_valid=True if execute else None,
        semantic_equivalent=recoverable if execute else None,latency=2.,calls=1,
        input_tokens=10 if parsed else None,output_tokens=3 if parsed else None,cost=None,
        validation_stages=int(execute),recovery={'same':'input'})


def test_retry_targets_only_unparsed_provider_failures(retry):
    assert retry.provider_failure(row())
    assert retry.provider_failure(row(recoverable=False))
    parsed = row(parsed=True)
    parsed.decision.evidence['llm']['parse_errors'] = [{'error_type':'ProviderError'}]
    assert not retry.provider_failure(parsed)  # Уже разобранный отказ модели не заменяется.
    failed = row()
    failed.decision.evidence['llm']['parse_errors'] = [{'error_type':'ValueError'}]
    assert not retry.provider_failure(failed)
    failed.decision.evidence['llm']['parse_errors'].insert(0, {'error_type':'ProviderError'})
    assert not retry.provider_failure(failed)  # Последний ответ уже дошёл, но нарушил протокол.
    assert not retry.provider_failure(row(parsed=True,execute=True))


def test_retry_replaces_outcome_preserves_all_attempts_and_unknown_usage(retry):
    old, fresh = row(), row(parsed=True,execute=True)
    snapshots = old.model_dump(), fresh.model_dump()
    result = retry.combine(old, fresh, 'selection', 'old-byte-hash')
    assert result.decision.action == 'EXECUTE' and result.semantic_equivalent is True
    assert result.repeat == 2 and result.calls == 2 and result.latency == 4
    assert result.input_tokens is result.output_tokens is result.cost is None
    trace = result.decision.evidence['llm']
    assert trace['parse_status'] == 'parsed' and trace['calls'] == 2
    assert len(trace['requests']) == 2 and len(trace['responses']) == 1
    assert trace['parse_errors'] == [{'error_type':'ProviderError'}]
    assert result.decision.evidence['provider_retry']['fresh_usage']['input_tokens'] == 10
    assert (old.model_dump(),fresh.model_dump()) == snapshots


def test_retry_does_not_select_only_improvements(retry):
    old, fresh = row(recoverable=False), row(parsed=True,execute=True,recoverable=False)
    result = retry.combine(old, fresh, 's', 'h')
    assert result.decision.action == 'EXECUTE' and result.semantic_equivalent is False
    failed_again = retry.combine(row(), row(), 's', 'h')
    assert failed_again.decision.action == 'ABSTAIN' and failed_again.calls == 2
    assert len(failed_again.decision.evidence['llm']['parse_errors']) == 2


def test_retry_rejects_identity_and_eligibility_changes(retry):
    fresh = row(parsed=True,execute=True)
    fresh.repeat = 0
    with pytest.raises(ValueError,match='identity'):
        retry.combine(row(),fresh,'s','h')
    with pytest.raises(ValueError,match='eligibility'):
        retry.combine(row(parsed=True),row(parsed=True),'s','h')
    old, fresh = row(), row(parsed=True,execute=True)
    old.calls = None
    assert retry.combine(old,fresh,'s','h').calls is None


@pytest.fixture
def prepared_runs(retry, tmp_path, monkeypatch):
    monkeypatch.setattr(retry, 'ROOT', tmp_path)
    monkeypatch.setattr(retry, 'EXPECTED_RECORDS', 2)
    originals = {}
    for regime in ('with-rules', 'without-rules'):
        directory = tmp_path/'runs'/regime
        directory.mkdir(parents=True)
        rows = [row(), row(parsed=True,execute=True)]
        rows[1].scenario_id = 'untargeted'
        names = [f'{r.repeat}-{r.method}-{r.scenario_id}' for r in rows]
        for name, record in zip(names, rows):
            _atomic(directory/(name+'.json'), record.model_dump(mode='json'))
        _atomic(directory/'result-digests.json', {n:sha256(canonical_bytes(r.model_dump())).hexdigest() for n,r in zip(names,rows)})
        _atomic(directory/'summary.json', summaries(rows))
        manifest = dict(config={'benchmark_digest':'test'},source_digest=retry.SOURCE,created_at='original')
        manifest['fingerprint'] = sha256(canonical_bytes({k:v for k,v in manifest.items() if k!='created_at'})).hexdigest()
        _atomic(directory/'manifest.json', manifest)
        originals[regime] = {p.name:p.read_bytes() for p in directory.glob('*.json')}
    monkeypatch.setattr(retry, 'load', lambda *args:[SimpleNamespace(scenario_id='s')])
    calls = []
    def evaluate(scenario, method, repeat, interval):
        calls.append((scenario.scenario_id, method.name, repeat))
        return row(parsed=True,execute=True)
    monkeypatch.setattr(retry, '_evaluate', evaluate)
    return retry, tmp_path, originals, calls


def test_retry_atomically_overwrites_only_targeted_rows_and_resumes_without_queries(prepared_runs):
    retry, tmp_path, originals, calls = prepared_runs
    plan = retry.execute(sys.executable)
    assert plan['status'] == 'complete' and len(plan['completed']) == len(calls) == 2
    for regime in originals:
        directory = tmp_path/'runs'/regime
        manifest, rows = read_results(directory)
        assert manifest['provider_retry_policy']['resolved_passes_per_target'] == 1
        assert all(r.decision.action=='EXECUTE' for r in rows)
        assert (directory/'2-M1-untargeted.json').read_bytes() == originals[regime]['2-M1-untargeted.json']
        assert (tmp_path/'before-provider-retry'/regime/'2-M1-s.json').read_bytes() == originals[regime]['2-M1-s.json']
        from terra_results import read_before_retry
        _, before = read_before_retry(directory, tmp_path/'before-provider-retry'/regime)
        assert sum(r.decision.action=='EXECUTE' for r in before) == 1
    # Эмулируется остановка после атомарной записи, до обновления журнала.
    plan['status'], plan['completed'] = 'in_progress', {}
    _atomic(tmp_path/'provider-retry-plan.json', plan)
    assert retry.execute(sys.executable)['status'] == 'complete' and len(calls) == 2
    assert retry.execute(sys.executable)['status'] == 'complete' and len(calls) == 2
    path = tmp_path/'runs/with-rules/2-M1-s.json'
    payload = json.loads(path.read_bytes())
    payload['latency'] = 99
    _atomic(path, payload)
    with pytest.raises(ValueError,match='hash mismatch'):
        retry.execute(sys.executable)


def test_retry_stops_on_unavailable_provider_and_keeps_cumulative_attempts(prepared_runs, monkeypatch):
    retry, tmp_path, _, calls = prepared_runs
    def evaluate(scenario, method, repeat, interval):
        calls.append(scenario.scenario_id)
        return row()
    monkeypatch.setattr(retry, '_evaluate', evaluate)
    from mcp_compat.providers import ProviderError
    with pytest.raises(ProviderError,match='stopped'):
        retry.execute(sys.executable)
    plan = json.loads((tmp_path/'provider-retry-plan.json').read_bytes())
    assert plan['status'] == 'in_progress' and not plan['completed']
    assert len(plan['unavailable']) == len(calls) == 2
    assert len(plan['transport_stops']) == 1
    monkeypatch.setattr(retry, '_evaluate', lambda *args:row(parsed=True,execute=True))
    result = retry.execute(sys.executable)
    assert result['status'] == 'complete' and not result['unavailable']
    _, rows = read_results(tmp_path/'runs/with-rules')
    replaced = next(r for r in rows if r.scenario_id == 's')
    assert replaced.calls == 3 and replaced.decision.evidence['llm']['calls'] == 3
    assert replaced.decision.evidence['provider_retry']['retry_evaluations'] == 2
    assert len(replaced.decision.evidence['llm']['parse_errors']) == 2
