from importlib.util import module_from_spec, spec_from_file_location
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from mcp_compat.llm import LLMRequest
from mcp_compat.providers import ProviderError


@pytest.fixture
def transport(monkeypatch):
    path = Path(__file__).resolve().parents[1]/'examples/codex_transport.py'
    spec = spec_from_file_location('codex_transport', path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setitem(sys.modules, 'codex_transport', module)
    return module


def events(text='{"action":"ABSTAIN"}'):
    return [dict(type='thread.started'), dict(type='turn.started'),
            dict(type='item.completed', item=dict(type='reasoning', text='')),
            dict(type='item.completed', item=dict(type='agent_message', text=text)),
            dict(type='turn.completed', usage=dict(input_tokens=12, cached_input_tokens=8, output_tokens=4))]


def test_codex_usage_is_not_double_counted(transport):
    result = transport.parse_events('\n'.join(json.dumps(e) for e in events()))
    assert result.model == 'gpt-6.1-terra'
    assert result.input_tokens == 12 and result.output_tokens == 4 and result.cost is None
    assert result.details['cached_input_tokens'] == 8
    assert result.details['output_token_limit_enforced'] is False
    rows = events()
    rows[-1].pop('usage')
    result = transport.parse_events('\n'.join(json.dumps(e) for e in rows))
    assert result.input_tokens is result.output_tokens is None


@pytest.mark.parametrize('rows', [
    [], events(''), events()[:-1], events()+[dict(type='turn.started')],
    events()+[dict(type='turn.completed')], events()+[dict(type='error')],
    events()+[dict(type='item.started', item=dict(type='command_execution'))],
    events()+[dict(type='item.completed', item=dict(type='agent_message', text='extra'))],
])
def test_codex_rejects_tools_partial_and_multiple_turns(transport, rows):
    with pytest.raises(ProviderError):
        transport.parse_events('\n'.join(json.dumps(e) for e in rows))


def test_codex_transport_isolated_and_keys_not_forwarded(transport, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'TEST_SECRET')
    monkeypatch.setenv('CODEX_API_KEY', 'TEST_SECRET')
    request = LLMRequest(system='Return JSON', data={'purpose':'mapping'}, response_schema={})
    def invoke(command, **kwargs):
        assert command[0] == sys.executable and command[1] == '--no-daemon'
        assert command[command.index('--model')+1] == transport.MODEL
        assert command[command.index('--sandbox')+1] == 'read-only'
        assert '--ignore-user-config' in command and '--ephemeral' in command
        assert '--output-schema' not in command  # Та же обычная генерация JSON, что у CodeAgent.
        assert not {'OPENAI_API_KEY', 'CODEX_API_KEY'} & kwargs['env'].keys()
        settings = [command[i+1] for i, value in enumerate(command[:-1]) if value == '-c']
        assert 'project_doc_max_bytes=0' in settings and 'agents.enabled=false' in settings
        value = next(v for v in settings if v.startswith('model_instructions_file='))
        path = Path(json.loads(value.split('=',1)[1]))
        assert path.parent == kwargs['cwd'] and path.read_text() == request.system
        assert json.loads(kwargs['input'].decode().splitlines()[1]) == dict(data=request.data, response_schema={})
        assert kwargs['timeout'] == 12
        kwargs['stdout'].write('\n'.join(json.dumps(e) for e in events()).encode())
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(subprocess, 'run', invoke)
    assert transport.CodexClient(sys.executable).complete(request, 12).text == '{"action":"ABSTAIN"}'


@pytest.mark.parametrize('failure', ['exit', 'huge', 'malformed', 'timeout', 'os'])
def test_codex_errors_are_bounded_and_sanitized(transport, monkeypatch, failure):
    def invoke(*args, **kwargs):
        if failure == 'timeout':
            raise subprocess.TimeoutExpired('TEST_SECRET', 1)
        if failure == 'os':
            raise OSError('TEST_SECRET')
        kwargs['stdout'].write(b'x'*(1048577 if failure == 'huge' else 1))
        return SimpleNamespace(returncode=int(failure == 'exit'))
    monkeypatch.setattr(subprocess, 'run', invoke)
    with pytest.raises(ProviderError) as error:
        transport.CodexClient(sys.executable).complete(LLMRequest(system='s',data={},response_schema={}), 1)
    assert 'TEST_SECRET' not in str(error.value)


def test_codex_configuration_bounds_and_honest_parameters(transport):
    for executable in ('relative', '/missing/cli', '/private/tmp'):
        with pytest.raises(ValueError):
            transport.CodexClient(executable)
    client = transport.CodexClient(sys.executable)
    for timeout in (0, -1, 121, float('nan')):
        with pytest.raises(ValueError):
            client.complete(LLMRequest(system='s',data={},response_schema={}), timeout)
    path = Path(__file__).resolve().parents[1]/'examples/terra_case_study.py'
    spec = spec_from_file_location('terra_case_study', path)
    runner = module_from_spec(spec)
    spec.loader.exec_module(runner)
    good = runner.TerraRunConfig(kind='pilot',benchmark_digest='x',generation_parameters=transport.PARAMETERS)
    assert good.generation_parameters['temperature'] == 'provider_default'
    with pytest.raises(ValidationError, match='Terra generation'):
        runner.TerraRunConfig(kind='pilot',benchmark_digest='x')


@pytest.mark.real_provider
def test_real_terra_mapping_through_business_mcp_proxy(transport):
    if os.environ.get('MCP_COMPAT_RUN_TERRA_SMOKE') != '1':
        pytest.skip('real Terra inference not explicitly enabled')
    from test_provider_smoke import _business_proxy_check
    executable = os.environ.get('MCP_COMPAT_CODEX_BIN') or shutil.which('codex')
    assert executable is not None
    _business_proxy_check(transport.CodexClient(executable),
                          os.environ.get('MCP_COMPAT_TERRA_BUSINESS_SMOKE_EVIDENCE'))
