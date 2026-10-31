import json

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from mcp_compat.llm import LLMRequest, Mapper
from mcp_compat.providers import ChatProvider, ProviderConfig, ProviderError, from_env
from mcp_compat.recovery import LLMBaseline
from test_llm import FakeClient, request


def config(provider='qwen', **kwargs):
    data = dict(provider=provider, endpoint='http://127.0.0.1:8000/v1/chat/completions',model='explicit-test-model')
    if provider == 'gigachat':
        data.update(endpoint='https://api.giga.chat/v1/chat/completions',token=SecretStr('SECRET'))
    data.update(kwargs)
    return ProviderConfig(**data)


@pytest.mark.parametrize('provider', ['qwen','gigachat'])
def test_mock_transport_request_and_usage(provider):
    def handle(req):
        payload = json.loads(req.content)
        assert payload['model'] == 'explicit-test-model' and payload['temperature'] == 0
        assert payload['messages'][1]['role'] == 'user'
        assert ('response_format' in payload) == (provider == 'qwen')
        assert req.headers.get('Authorization') == ('Bearer SECRET' if provider == 'gigachat' else None)
        return httpx.Response(200,json={'choices':[{'message':{'content':'{"action":"ABSTAIN"}'}}], 'usage':{'prompt_tokens':3,'completion_tokens':4},'model':'test-revision'})
    c = ChatProvider(config(provider,allow_paid=True),httpx.Client(transport=httpx.MockTransport(handle)))
    response = c.complete(LLMRequest(system='fixed',data={},response_schema={}),2)
    assert response.model == 'test-revision' and response.input_tokens == 3 and response.output_tokens == 4
    assert response.cost is None and 'SECRET' not in repr(c.config)
    c.close()


@pytest.mark.parametrize('response', [httpx.Response(401,text='SECRET'),httpx.Response(302,headers={'Location':'https://evil.invalid'}),httpx.Response(200,json={}),httpx.Response(200,content=b'x'*1048577),httpx.Response(200,json={'choices':[]}),httpx.Response(200,json={'choices':[{'message':{'content':17}}]})])
def test_errors_are_sanitized(response):
    c = ChatProvider(config(),httpx.Client(transport=httpx.MockTransport(lambda req:response)))
    with pytest.raises(ProviderError) as exc:
        c.complete(LLMRequest(system='s',data={},response_schema={}),1)
    assert 'SECRET' not in str(exc.value)
    c.close()


def test_timeouts_and_paid_guard():
    def timeout(req):
        raise httpx.ReadTimeout('SECRET')
    c = ChatProvider(config(),httpx.Client(transport=httpx.MockTransport(timeout)))
    with pytest.raises(ProviderError):
        c.complete(LLMRequest(system='s',data={},response_schema={}),1)
    c.close()
    c = ChatProvider(config('gigachat'))
    with pytest.raises(PermissionError):
        c.complete(LLMRequest(system='s',data={},response_schema={}),1)
    c.close()


@pytest.mark.parametrize('provider,kwargs', [
    ('qwen',dict(endpoint='https://remote.invalid/v1/chat/completions')),
    ('qwen',dict(endpoint='ftp://localhost/v1/chat/completions')),
    ('qwen',dict(endpoint='http://localhost/wrong')),
    ('qwen',dict(endpoint='http://u:p@localhost/v1/chat/completions')),
    ('qwen',dict(endpoint='http://localhost/v1/chat/completions?key=secret')),
    ('qwen',dict(model='  ')), ('gigachat',dict(token=None)),
    ('gigachat',dict(token=SecretStr(''))), ('gigachat',dict(endpoint='http://api.giga.chat/v1/chat/completions')),
    ('gigachat',dict(endpoint='https://evil.invalid/v1/chat/completions')),
])
def test_bad_configuration(provider,kwargs):
    with pytest.raises(ValidationError):
        config(provider,**kwargs)


def test_environment_configuration(monkeypatch):
    env = dict(QWEN_ENDPOINT='http://localhost:8000/v1/chat/completions',QWEN_MODEL='explicit')
    assert from_env('qwen',environ=env).token is None
    env['QWEN_ACCESS_TOKEN'] = 'secret'
    assert from_env('qwen',environ=env).token.get_secret_value() == 'secret'
    for key,val in env.items():
        monkeypatch.setenv(key,val)
    assert from_env('qwen').model == 'explicit'
    with pytest.raises(KeyError):
        from_env('gigachat',environ={})


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


def test_usage_missing_is_unknown():
    response = {'choices':[{'message':{'content':'{"action":"ABSTAIN"}'}}]}
    c = ChatProvider(config(),httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(200,json=response))))
    result = c.complete(LLMRequest(system='s',data={},response_schema={}),1)
    assert result.model == 'explicit-test-model' and result.input_tokens is None
    c.close()
