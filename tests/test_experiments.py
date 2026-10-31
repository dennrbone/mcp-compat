from importlib.metadata import PackageNotFoundError
import json
import random

import pytest
from pydantic import ValidationError

from mcp_compat import MigrationDecision, ToolCall, canonical_bytes
from mcp_compat.benchmark import _case, freeze
from mcp_compat.experiments import Record, RunConfig, demo_cli, metrics, run, summaries
from mcp_compat.llm import Mapper
from mcp_compat.recovery import LLMBaseline, NoRecovery, RuleBased, abstain
from test_llm import FakeClient


@pytest.fixture
def frozen(tmp_path):
    cases = [_case('commerce','quote',0,f,v,random.Random(42)) for f,v in [('C2',0),('C1',0),('C8',0),('C3',1)]]
    directory = tmp_path/'benchmark'
    digest = freeze(cases,directory,42)
    return directory,digest,cases


def row(execute=True,recoverable=True,semantic=True,valid=True):
    call = ToolCall(tool_name='t',arguments={})
    return Record(scenario_id='s',method='B0',repeat=0,mutation_family='C1',
        ground_truth='CONDITIONAL' if recoverable else 'MUST_ABSTAIN',recoverable=recoverable,
        base_tool='t',composed=False,decision=MigrationDecision(action='EXECUTE',adapted_call=call) if execute else abstain('blocked'),
        schema_valid=valid,semantic_equivalent=semantic,latency=1.,calls=0,input_tokens=0,
        output_tokens=0,cost=0.,validation_stages=1,recovery={})


def test_hand_checked_metric_denominators():
    rows = [row(),row(semantic=False),row(False,semantic=None,valid=False),row(False,False,None,None),row(True,False,False)]
    m = metrics(rows)
    assert m['CRR'] == dict(value=1/3,numerator=1,denominator=3)
    assert m['UHR']['value'] == 2/3 and m['FBR']['value'] == 1/3
    assert m['AbstentionAccuracy']['value'] == .5
    assert m['SchemaValidityRate']['value'] == .75
    assert m['SemanticEquivalenceRate']['value'] == 1/3
    assert m['latency_mean'] == 1 and m['calls'] == 0
    assert metrics([])['CRR']['value'] is None
    assert metrics([])['latency_mean'] is None
    rows[0].cost = rows[0].input_tokens = rows[0].calls = None
    assert metrics(rows)['cost'] is None and metrics(rows)['input_tokens'] is None and metrics(rows)['calls'] is None
    grouped = summaries(rows)
    assert grouped['B0']['families']['C2']['CRR']['value'] is None
    assert grouped['B0']['categories']['SAFE_AUTO']['samples'] == 0
    with pytest.raises(ValidationError,match='generation parameters'):
        RunConfig(kind='offline_demo',benchmark_digest='hash',generation_parameters={'temperature':1})


def test_paired_frozen_run_and_byte_preserving_resume(tmp_path,frozen,monkeypatch):
    directory,digest,cases = frozen
    cfg = RunConfig(kind='offline_demo',benchmark_digest=digest,repeats=2,interval_seconds=.001)
    waits = []
    monkeypatch.setattr('mcp_compat.experiments.sleep',waits.append)
    methods = [NoRecovery(),RuleBased()]
    output = tmp_path/'run'
    records = run(cfg,methods,directory,output)
    assert len(records) == 16 and len(waits) == 16
    before = {p.name:p.read_bytes() for p in output.glob('*.json')}
    resumed = run(cfg,methods,directory,output)
    assert resumed == records
    assert {p.name:p.read_bytes() for p in output.glob('*.json')} == before
    assert any(r.semantic_equivalent is False for r in records)
    cfg.seed += 1
    with pytest.raises(ValueError,match='configuration'):
        run(cfg,methods,directory,output)


@pytest.mark.parametrize('names', [[],['B0','B0'],['../bad']])
def test_bad_methods(tmp_path,frozen,names):
    directory,digest,_ = frozen
    methods = [NoRecovery() for _ in names]
    for method,name in zip(methods,names):
        method.name = name
    with pytest.raises(ValueError,match='methods'):
        run(RunConfig(kind='offline_demo',benchmark_digest=digest),methods,directory,tmp_path/'out')


@pytest.mark.parametrize('selection', [['missing'],['commerce-0-C2-0','commerce-0-C2-0'],[]])
def test_selection(tmp_path,frozen,selection):
    directory,digest,_ = frozen
    with pytest.raises(ValueError):
        run(RunConfig(kind='offline_demo',benchmark_digest=digest,scenario_ids=selection),[NoRecovery()],directory,tmp_path/'out')


def test_corrupt_resume_and_interruption(tmp_path,frozen):
    directory,digest,cases = frozen
    cfg = RunConfig(kind='offline_demo',benchmark_digest=digest,scenario_ids=[s.scenario_id for s in cases])
    class Interrupted:
        name = 'B0'
        count = 0
        def recover(self,request):
            self.count += 1
            if self.count == 2:
                raise KeyboardInterrupt()
            return NoRecovery().recover(request)
    output = tmp_path/'out'
    with pytest.raises(KeyboardInterrupt):
        run(cfg,[Interrupted()],directory,output)
    assert len(list(output.glob('0-B0-*.json'))) == 1
    assert len(run(cfg,[NoRecovery()],directory,output)) == 4
    path = next(output.glob('0-B0-*.json'))
    record = json.loads(path.read_bytes())
    record['method'] = 'wrong'
    path.write_bytes(canonical_bytes(record))
    with pytest.raises(ValueError,match='corrupt resume'):
        run(cfg,[NoRecovery()],directory,output)


def test_failed_strategy_unknown_usage_and_invalid_candidate(tmp_path,frozen):
    directory,digest,_ = frozen
    class Failed:
        name = 'FAILED'
        def recover(self,request):
            raise RuntimeError('SECRET')
    class Invalid:
        name = 'INVALID'
        def recover(self,request):
            return abstain('invalid',candidate={})
    config = RunConfig(kind='offline_demo',benchmark_digest=digest)
    records = run(config,[Failed(),Invalid()],directory,tmp_path/'out')
    assert all(r.calls is None and r.cost is None for r in records if r.method == 'FAILED')
    assert all(r.schema_valid is False for r in records if r.method == 'INVALID')
    assert 'SECRET' not in str(records)


def test_llm_usage_known_and_incomplete(tmp_path,frozen):
    directory,digest,_ = frozen
    config = RunConfig(kind='offline_demo',benchmark_digest=digest,scenario_ids=['commerce-0-C2-0'])
    for label,responses in [('known',['{"action":"ABSTAIN"}']),('unknown',[TimeoutError('private'),'{"action":"ABSTAIN"}'])]:
        mapper = Mapper(FakeClient(*responses),backoff=0)
        record = run(config,[LLMBaseline('B2',mapper)],directory,tmp_path/label)[0]
        assert record.calls == (1 if label == 'known' else 2)
        assert record.cost == (0. if label == 'known' else None)


def test_offline_demo_cli(tmp_path,frozen,capsys):
    directory,digest,_ = frozen
    index = tmp_path/'index.json'
    index.write_text(json.dumps(dict(path=str(directory),digest=digest)))
    output = tmp_path/'demo'
    demo_cli(['--index',str(index),'--output',str(output)])
    assert 'OFFLINE DEMO ONLY' in capsys.readouterr().out
    assert len(list(output.glob('0-*.json'))) == 36
    m1 = Record.model_validate_json((output/'0-M1-commerce-0-C8-0.json').read_bytes())
    assert m1.decision.action == 'EXECUTE'
    assert m1.semantic_equivalent is True


def test_main_requires_models_and_optional_dependencies_are_recorded(tmp_path,frozen,monkeypatch):
    directory,digest,_ = frozen
    with pytest.raises(ValueError,match='explicit model'):
        run(RunConfig(kind='main',benchmark_digest=digest),[NoRecovery()],directory,tmp_path/'main')
    def absent(package):
        raise PackageNotFoundError(package)
    monkeypatch.setattr('mcp_compat.experiments.version',absent)
    out = tmp_path/'optional'
    cfg = RunConfig(kind='offline_demo',benchmark_digest=digest)
    run(cfg,[NoRecovery()],directory,out)
    assert json.loads((out/'manifest.json').read_bytes())['dependencies']['mcp'] is None
    path = next(out.glob('0-*.json'))
    path.unlink()
    with pytest.raises(ValueError,match='missing completed'):
        run(cfg,[NoRecovery()],directory,out)


def test_nonempty_output_and_unhashed_resume_identity(tmp_path,frozen):
    directory,digest,_ = frozen
    output = tmp_path/'out'
    output.mkdir()
    (output/'unrelated').write_text('keep')
    cfg = RunConfig(kind='offline_demo',benchmark_digest=digest)
    with pytest.raises(ValueError,match='nonempty'):
        run(cfg,[NoRecovery()],directory,output)
    output = tmp_path/'run'
    run(cfg,[NoRecovery()],directory,output)
    (output/'result-digests.json').unlink()
    path = next(output.glob('0-*.json'))
    payload = json.loads(path.read_bytes())
    payload['scenario_id'] = 'other'
    path.write_bytes(canonical_bytes(payload))
    with pytest.raises(ValueError,match='corrupt resume'):
        run(cfg,[NoRecovery()],directory,output)


def test_main_refuses_retired_benchmark(tmp_path,frozen):
    from hashlib import sha256
    directory,_,_ = frozen
    manifest_path = directory/'manifest.json'
    manifest = json.loads(manifest_path.read_bytes())
    manifest['version'] = 'evobench-1.0'
    digest = manifest['digest'] = sha256(canonical_bytes({k:v for k,v in manifest.items() if k != 'digest'})).hexdigest()
    manifest_path.write_bytes(canonical_bytes(manifest))
    cfg = RunConfig(kind='main',benchmark_digest=digest,model_versions={'test':'offline-unit-test-only'})
    with pytest.raises(ValueError,match='retired benchmark'):
        run(cfg,[NoRecovery()],directory,tmp_path/'out')
