import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from mcp_compat.llm import LLMRequest, Mapper
from mcp_compat.providers import AgentProvider, MODEL_ID, ProviderConfig, ProviderError, from_env
from mcp_compat.recovery import LLMBaseline
from test_llm import FakeClient, request


def config(**kwargs):
    return ProviderConfig(**dict(executable=sys.executable) | kwargs)


def events(text='{"action":"ABSTAIN"}', **finish):
    return [dict(type='step_start',part={}),dict(type='reasoning',part={}),
            dict(type='text',part=dict(text=text)),
            dict(type='step_finish',part=dict(reason='stop',**finish))]


def mock_cli(monkeypatch, payload, code=0):
    def invoke(command, **kwargs):
        kwargs['stdout'].write(payload)
        return SimpleNamespace(returncode=code)
    monkeypatch.setattr(subprocess, 'run', invoke)


def test_cli_isolation_and_usage(monkeypatch):
    c = config()
    def invoke(command, **kwargs):
        prefix = 'KILO'
        env = kwargs['env']
        settings = json.loads(env[prefix+'_CONFIG_CONTENT'])
        assert settings['model'] == settings['small_model'] == c.model
        assert settings['enabled_providers'] == ['gigacode']
        assert settings['permission'] == settings['agent']['mcp_mapper']['permission'] == 'deny'
        assert settings['agent']['mcp_mapper']['prompt'] == 'fixed'
        assert settings['agent']['mcp_mapper']['steps'] == 1
        assert settings['agent']['title']['disable'] and settings['plugin'] == []
        assert settings['instructions'] == [] and settings['mcp'] == {}
        assert env['NODE_TLS_REJECT_UNAUTHORIZED'] == '1'
        assert env[prefix+'_EXPERIMENTAL_OUTPUT_TOKEN_MAX'] == '2048'
        assert env[prefix+'_DISABLE_EXTERNAL_SKILLS'] == '1'
        assert env[prefix+'_DISABLE_PROJECT_CONFIG'] == '1'
        assert Path(env['XDG_CONFIG_HOME']).is_dir()
        assert Path(env[prefix+'_CONFIG_DIR']).is_dir()
        assert kwargs['cwd'] != Path.cwd() and kwargs['timeout'] == 2
        assert kwargs['stdin'] == subprocess.DEVNULL and kwargs['stderr'] == subprocess.DEVNULL
        assert command[0] == sys.executable and '--pure' in command and '--title' in command
        assert command[command.index('--model')+1] == c.model
        assert command[-1].startswith('fixed\n')
        assert json.loads(command[-1].split('\n',1)[1]) == dict(data={},response_schema={})
        response = events(tokens=dict(input=3,output=4,reasoning=2,cache=dict(read=5,write=1)),cost=0)
        kwargs['stdout'].write(('startup notice\n'+'\n'.join(json.dumps(e) for e in response)).encode())
        return SimpleNamespace(returncode=0)
    monkeypatch.setenv('NODE_TLS_REJECT_UNAUTHORIZED','0')
    monkeypatch.setattr(subprocess,'run',invoke)
    response = AgentProvider(c).complete(LLMRequest(system='fixed',data={},response_schema={}),2)
    assert response.model == c.model and response.input_tokens == 9 and response.output_tokens == 6
    assert response.cost == 0


@pytest.mark.parametrize('bad', [
    [], [dict(type='error',error='SECRET')], [dict(type='tool_use',part={})],
    events()[:-1], events()+events(),
    [dict(type='step_start'),dict(type='step_finish',part=dict(reason='length'))],
    events('  '), events(cost=1), [dict(type='text')],
    events(tokens=dict(input='invalid')), events(tokens=None),
    events(tokens=dict(output=-1)), events(cost=None),
])
def test_bad_events_fail_closed(monkeypatch,bad):
    mock_cli(monkeypatch,'\n'.join(json.dumps(e) for e in bad).encode())
    with pytest.raises(ProviderError) as exc:
        AgentProvider(config()).complete(LLMRequest(system='s',data={},response_schema={}),1)
    assert 'SECRET' not in str(exc.value)


@pytest.mark.parametrize('payload,code',[(b'',1),(b'x'*1048577,0),(b'{bad',0),(b'{"type":"text","part":{"text":"\xff"}}',0)])
def test_invalid_cli_output(monkeypatch,payload,code):
    mock_cli(monkeypatch,payload,code)
    with pytest.raises(ProviderError):
        AgentProvider(config()).complete(LLMRequest(system='s',data={},response_schema={}),1)


@pytest.mark.parametrize('error',[subprocess.TimeoutExpired('SECRET',1),OSError('SECRET')])
def test_cli_errors_are_sanitized(monkeypatch,error):
    def invoke(*args,**kwargs):
        raise error
    monkeypatch.setattr(subprocess,'run',invoke)
    with pytest.raises(ProviderError) as exc:
        AgentProvider(config()).complete(LLMRequest(system='s',data={},response_schema={}),1)
    assert 'SECRET' not in str(exc.value)


@pytest.mark.parametrize('timeout',[0,-1,121,float('nan')])
def test_bad_timeout(timeout):
    with pytest.raises(ValueError):
        AgentProvider(config()).complete(LLMRequest(system='s',data={},response_schema={}),timeout)


@pytest.mark.parametrize('kwargs', [dict(model='unselected-model'),dict(model=''),
    dict(executable='relative'),dict(executable='/nonexistent/cli'),dict(executable='/tmp')])
def test_bad_configuration(kwargs):
    with pytest.raises(ValidationError):
        config(**kwargs)


def test_unexecutable_configuration(tmp_path):
    binary=tmp_path/'cli'
    binary.write_text('not executable')
    binary.chmod(0o600)
    with pytest.raises(ValidationError):
        config(executable=str(binary))


def test_environment_configuration(monkeypatch):
    env=dict(GIGACODE_BIN=sys.executable)
    assert from_env(environ=env).executable == sys.executable
    monkeypatch.setenv('GIGACODE_BIN',sys.executable)
    assert from_env().model == MODEL_ID
    env=dict(PATH=str(Path(sys.executable).parent))
    monkeypatch.setattr('shutil.which',lambda name,path:sys.executable)
    assert from_env(environ=env).executable == sys.executable
    monkeypatch.setattr('shutil.which',lambda name,path:None)
    with pytest.raises(ValueError,match='GIGACODE_BIN'):
        from_env(environ={})


def test_usage_missing_is_unknown(monkeypatch):
    mock_cli(monkeypatch,'\n'.join(json.dumps(e) for e in events()).encode())
    response=AgentProvider(config()).complete(LLMRequest(system='s',data={},response_schema={}),1)
    assert response.input_tokens is response.output_tokens is response.cost is None


def test_llm_baselines():
    with pytest.raises(ValueError):
        LLMBaseline('B9',Mapper(FakeClient()))
    r = request()
    fake = FakeClient('{"action":"EXECUTE","call":{"tool_name":"t","arguments":{}}}')
    assert LLMBaseline('B1',Mapper(fake)).recover(r).action == 'EXECUTE'
    assert not fake.requests
    r.old_call.tool_name = 'old'
    b1 = LLMBaseline('B1',Mapper(fake)).recover(r)
    assert b1.action == 'EXECUTE' and b1.evidence['initial_attempt']['action'] == 'ABSTAIN'
    assert fake.requests[0][0].data['error']
    for text in ('{"action":"ABSTAIN"}', 'malformed'):
        result = LLMBaseline('B2',Mapper(FakeClient(text),attempts=1)).recover(r)
        assert result.action == 'ABSTAIN'
    text = '{"action":"EXECUTE","call":{"tool_name":"wrong","arguments":{}}}'
    assert LLMBaseline('B2',Mapper(FakeClient(text))).recover(r).reasons == ['schema_invalid']
