from datetime import timedelta
import json

import anyio
from mcp import types
from mcp.shared.memory import create_connected_server_and_client_session as connected
import pytest

from mcp_compat import ToolContract
from mcp_compat.hybrid import Hybrid
from mcp_compat.mcp_integration import make_proxy, make_server
from mcp_compat.recovery import NoRecovery
from test_hybrid import mapper, unit_request, verifier


def contract():
    return ToolContract(name='echo',input_schema={'type':'object','properties':{'x':{'type':'integer'}},'required':['x']},output_schema={'type':'object','properties':{'x':{'type':'integer'}},'required':['x']})


async def echo(a,s):
    s['calls'] = s.get('calls',0) + 1
    return a


def test_handshake_discovery_validation_and_isolated_calls():
    async def run():
        c = contract()
        state = {}
        async with connected(make_server(c,echo,state)) as client:
            await client.send_ping()
            tools = (await client.list_tools()).tools
            assert len(tools) == 1 and tools[0].inputSchema == c.input_schema
            assert tools[0].outputSchema == c.output_schema
            result = await client.call_tool('echo',{'x':3})
            assert not result.isError and result.structuredContent == {'x':3}
            for name,args in [('echo',{}),('echo',{'x':'bad'}),('missing',{'x':1})]:
                result = await client.call_tool(name,args)
                assert result.isError
            assert state == {'calls':1}
    anyio.run(run)


@pytest.mark.parametrize('behavior', ['raise','invalid_output','not_object','nonfinite','native_error'])
def test_server_failures(behavior):
    async def implementation(a,s):
        if behavior == 'raise':
            raise RuntimeError('SECRET')
        if behavior == 'invalid_output':
            return {'x':'bad'}
        if behavior == 'not_object':
            return []
        if behavior == 'nonfinite':
            return {'x':float('nan')}
        return types.CallToolResult(isError=True,content=[])
    async def run():
        async with connected(make_server(contract(),implementation)) as client:
            result = await client.call_tool('echo',{'x':1})
            assert result.isError and 'SECRET' not in str(result)
    anyio.run(run)


def test_v1_v2_proxy_verified_unit_conversion():
    async def run():
        r = unit_request()
        async def old(a,s):
            return {'value':a['value']}
        async def new(a,s):
            return {'value':a['value']//100}
        async with connected(make_server(r.old_contract,old)) as v1:
            expected = await v1.call_tool('t',{'value':2})
        async with connected(make_server(r.new_contract,new)) as v2:
            engine = Hybrid(mapper(r.context['rules']),verifier(r))
            async with connected(make_proxy(r.old_contract,r.new_contract,v2,engine,context=r.context)) as proxy:
                result = await proxy.call_tool('t',{'value':2})
                assert not result.isError and result.structuredContent == expected.structuredContent
            async with connected(make_proxy(r.old_contract,r.new_contract,v2,Hybrid())) as proxy:
                result = await proxy.call_tool('t',{'value':2})
                assert result.isError
                assert json.loads(result.content[0].text)['reasons'] == ['migration_abstain']
    anyio.run(run)


def test_proxy_errors_timeout_and_disconnect():
    async def run():
        c = contract()
        for mode in ('failure','slow','unstructured'):
            async def implementation(a,s):
                if mode == 'slow':
                    await anyio.sleep(.2)
                if mode == 'unstructured':
                    return types.CallToolResult(content=[types.TextContent(type='text',text='ok')])
                raise ValueError('private')
            remote_contract = c.model_copy(update={'output_schema':None})
            async with connected(make_server(remote_contract,implementation)) as upstream:
                async with connected(make_proxy(c,c,upstream,NoRecovery(),timeout=.05),read_timeout_seconds=timedelta(seconds=2)) as proxy:
                    result = await proxy.call_tool('echo',{'x':1})
                    assert result.isError
                    assert json.loads(result.content[0].text)['reasons'][0] in ('upstream_error','proxy_timeout','upstream_unavailable')
        async with connected(make_server(c,echo)) as upstream:
            pass
        async with connected(make_proxy(c,c,upstream,NoRecovery())) as proxy:
            result = await proxy.call_tool('echo',{'x':1})
            assert result.isError
            assert json.loads(result.content[0].text)['reasons'] == ['upstream_unavailable']
    anyio.run(run)


def test_fixture_configuration_errors():
    with pytest.raises(ValueError,match='tool name'):
        make_server(contract().model_copy(update={'name':'bad name'}),echo)
    with pytest.raises(ValueError,match='positive'):
        make_proxy(contract(),contract(),None,NoRecovery(),timeout=0)


def test_stdio_server_lifecycle(monkeypatch):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from mcp_compat.mcp_integration import serve_stdio

    calls=[]
    @asynccontextmanager
    async def streams():
        yield 'reader','writer'
    async def run(*args):
        calls.append(args)
    monkeypatch.setattr('mcp_compat.mcp_integration.stdio_server',streams)
    server=SimpleNamespace(run=run,create_initialization_options=lambda:'options')
    anyio.run(serve_stdio,server)
    assert calls == [('reader','writer','options')]


def test_model_independent_stdio_example():
    from pathlib import Path
    import sys
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp_compat.benchmark import RecoveryInput
    from mcp_compat import ToolCall

    async def run():
        entry=Path(__file__).resolve().parents[1]/'examples/mcp_server.py'
        parameters=StdioServerParameters(command=sys.executable,args=[str(entry)])
        with anyio.fail_after(10):
            async with stdio_client(parameters) as streams:
                async with ClientSession(*streams) as client:
                    await client.initialize()
                    await client.send_ping()
                    assert [t.name for t in (await client.list_tools()).tools] == ['check_migration']
                    c=contract()
                    request=RecoveryInput(old_contract=c,new_contract=c,old_call=ToolCall(tool_name='echo',arguments={'x':3}))
                    result=await client.call_tool('check_migration',request.model_dump(mode='json'))
                    assert not result.isError
                    assert result.structuredContent['action'] == 'ABSTAIN'
                    assert 'verifier_unavailable' in result.structuredContent['reasons']
                    invalid=await client.call_tool('check_migration',{})
                    assert invalid.isError
    anyio.run(run)
