import json
import subprocess
import sys
from types import SimpleNamespace

import pytest

from mcp_compat.agent_checks import agent_cli, cli_version, pilot_ids
from mcp_compat.benchmark import generate
from mcp_compat.llm import LLMResponse
from mcp_compat.providers import ProviderConfig, ProviderError


def test_stratified_pilot_selection():
    cases=generate(42)
    ids=pilot_ids(cases)
    selected=[s for s in cases if s.scenario_id in ids]
    assert len(ids) == len(set(ids)) and 'commerce-0-C8-0' in ids
    assert {(s.mutation_family,s.ground_truth) for s in selected} == {(s.mutation_family,s.ground_truth) for s in cases}
    assert len({s.metadata['base_tool'] for s in selected}) > 8
    assert pilot_ids(list(reversed(cases))) == ids
    assert pilot_ids(cases,43) != ids


def test_cli_version(monkeypatch):
    config=ProviderConfig(executable=sys.executable)
    monkeypatch.setattr(subprocess,'run',lambda *a,**kw:SimpleNamespace(stdout='notice\n26.10.76\n'))
    assert cli_version(config) == '26.10.76'
    monkeypatch.setattr(subprocess,'run',lambda *a,**kw:SimpleNamespace(stdout='missing'))
    with pytest.raises(ProviderError,match='version'):
        cli_version(config)


@pytest.mark.parametrize('pilot',[False,True])
def test_real_cli_smoke_and_pilot_wiring(tmp_path,monkeypatch,capsys,pilot):
    output=tmp_path/'out'
    monkeypatch.setenv('GIGACODE_BIN',sys.executable)
    monkeypatch.setattr('mcp_compat.agent_checks.cli_version',lambda c:'26.10.76')
    monkeypatch.setattr('mcp_compat.agent_checks.AgentProvider.complete',lambda *a:LLMResponse(text='{"action":"ABSTAIN"}',model='gigacode/GigaCode'))
    called=[]
    def run(config,strategies,benchmark,out):
        assert config.kind == 'pilot' and config.repeats == 1
        assert config.scenario_ids == pilot_ids(generate(42))
        assert [s.name for s in strategies] == ['B0','B1','B2','B3','M1','A1','A2','A3','A4']
        assert strategies[2].mapper.client.config.model == 'gigacode/GigaCode'
        assert strategies[2].mapper.attempts == 1
        called.append(out)
        return []
    monkeypatch.setattr('mcp_compat.agent_checks.run',run)
    agent_cli(['--output',str(output)]+(['--pilot'] if pilot else []))
    assert bool(called) == pilot
    report=json.loads((output/'smoke.json').read_bytes())
    assert report['status'] == 'PASS' and report['scope'] == 'strict_json_smoke'
    assert 'PASS' in capsys.readouterr().out
    with pytest.raises(FileExistsError):
        agent_cli(['--output',str(output)])


@pytest.mark.parametrize('result',[ProviderError('provider_timeout'),LLMResponse(text='{"action":"EXECUTE","operations":[]}',model='test'),LLMResponse(text='```json\n{}\n```',model='test')])
def test_smoke_failure_is_not_success(tmp_path,monkeypatch,result):
    monkeypatch.setenv('GIGACODE_BIN',sys.executable)
    monkeypatch.setattr('mcp_compat.agent_checks.cli_version',lambda c:'26.10.76')
    def complete(*args):
        if isinstance(result,Exception):
            raise result
        return result
    monkeypatch.setattr('mcp_compat.agent_checks.AgentProvider.complete',complete)
    with pytest.raises(SystemExit) as exc:
        agent_cli(['--output',str(tmp_path),'--pilot'])
    assert exc.value.code == 1
    report=json.loads((tmp_path/'smoke.json').read_bytes())
    assert report['status'] == 'FAIL'
    assert 'SECRET' not in str(report)
