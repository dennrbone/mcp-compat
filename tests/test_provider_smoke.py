"""Real CodeAgent inference is opt-in; enabled failures must fail the test."""

import os

import pytest

from mcp_compat.agent_checks import PROBE_PROMPT
from mcp_compat.llm import LLMRequest, parse_proposal, response_schema
from mcp_compat.providers import AgentProvider, from_env


@pytest.mark.real_provider
def test_real_provider_smoke():
    if os.environ.get('MCP_COMPAT_RUN_PROVIDER_SMOKE') != '1':
        pytest.skip('real CodeAgent inference not explicitly enabled')
    response=AgentProvider(from_env()).complete(LLMRequest(system=PROBE_PROMPT,
        data={},response_schema=response_schema('mapping')),120)
    assert parse_proposal(response.text,'mapping')[0].action == 'ABSTAIN'


@pytest.mark.real_provider
def test_codeagent_calls_project_mcp(tmp_path):
    if os.environ.get('MCP_COMPAT_RUN_PROVIDER_SMOKE') != '1':
        pytest.skip('real CodeAgent inference not explicitly enabled')
    import json
    from pathlib import Path
    import subprocess
    import sys
    from mcp_compat import ToolCall, ToolContract
    from mcp_compat.benchmark import RecoveryInput

    c=ToolContract(name='echo',input_schema={'type':'object','properties':{'x':{'type':'integer'}},'required':['x']})
    expected=RecoveryInput(old_contract=c,new_contract=c,old_call=ToolCall(tool_name='echo',arguments={'x':3}))
    config=from_env()
    (tmp_path/'config').mkdir()
    (tmp_path/'extra').mkdir()
    entry=Path(__file__).resolve().parents[1]/'examples/mcp_server.py'
    permissions={'*':'deny','compat_check_migration':'allow'}
    settings=dict(model=config.model,small_model=config.model,autoupdate=False,snapshot=False,share='disabled',
        permission=permissions,enabled_providers=['gigacode'],instructions=[],plugin=[],compaction=dict(auto=False,prune=False),
        mcp=dict(compat=dict(type='local',command=[sys.executable,str(entry)],enabled=True)),
        agent=dict(mcp_probe=dict(mode='primary',prompt='Call the specified MCP tool exactly once. Never use other tools.',
            temperature=0,steps=2,permission=permissions),title=dict(disable=True),summary=dict(disable=True),compaction=dict(disable=True)))
    env={**os.environ,'XDG_CONFIG_HOME':str(tmp_path/'config'),'NODE_TLS_REJECT_UNAUTHORIZED':'1',
        'KILO_CONFIG_DIR':str(tmp_path/'extra'),'KILO_CONFIG_CONTENT':json.dumps(settings),
        'KILO_EXPERIMENTAL_OUTPUT_TOKEN_MAX':'2048','KILO_SESSION_RETRY_LIMIT':'0'}
    for flag in ('DISABLE_DEFAULT_PLUGINS','DISABLE_CLAUDE_CODE','DISABLE_EXTERNAL_SKILLS','DISABLE_PROJECT_CONFIG','DISABLE_LSP_DOWNLOAD','DISABLE_AUTOCOMPACT'):
        env['KILO_'+flag]='1'
    prompt='Call compat_check_migration exactly once with this JSON input. Then report its actual action. Do not execute any business tool.\n'+expected.model_dump_json()
    result=subprocess.run([config.executable,'run','--pure','--log-level','ERROR','--model',config.model,
        '--agent','mcp_probe','--format','json','--title','mcp-compat-stdio-smoke',prompt],cwd=tmp_path,env=env,
        capture_output=True,text=True,timeout=120,check=False)
    events=[json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
    evidence=dict(scope='codeagent_to_project_mcp',model=config.model,returncode=result.returncode,events=events)
    evidence_path=os.environ.get('MCP_COMPAT_MCP_SMOKE_EVIDENCE')
    if evidence_path:
        with Path(evidence_path).open('x') as handle:
            json.dump(evidence,handle,ensure_ascii=False,indent=2)
    assert result.returncode == 0
    assert not any(e['type']=='error' for e in events)
    calls=[e['part'] for e in events if e['type']=='tool_use']
    assert len(calls) == 1 and calls[0]['tool'] == 'compat_check_migration'
    state=calls[0]['state']
    assert state['status'] == 'completed'
    assert RecoveryInput.model_validate(state['input']) == expected
    assert 'ABSTAIN' in state['output']
    finishes=[e['part'] for e in events if e['type']=='step_finish']
    assert finishes and all(p.get('cost')==0 for p in finishes)


@pytest.mark.real_provider
@pytest.mark.parametrize('purpose',['mapping','B2'])
def test_real_mapping_protocol(purpose):
    if os.environ.get('MCP_COMPAT_RUN_PROVIDER_SMOKE')!='1':
        pytest.skip('real CodeAgent inference not explicitly enabled')
    from mcp_compat import ToolCall,ToolContract
    from mcp_compat.benchmark import RecoveryInput
    from mcp_compat.hybrid import adapt
    from mcp_compat.llm import Mapper
    old=ToolContract(name='development_counter',input_schema=dict(type='object',properties=dict(quantity={'type':'integer'}),required=['quantity'],additionalProperties=False))
    new=old.model_copy(deep=True)
    new.input_schema=dict(type='object',properties=dict(count={'type':'integer'}),required=['count'],additionalProperties=False)
    request=RecoveryInput(old_contract=old,new_contract=new,old_call=ToolCall(tool_name=old.name,arguments={'quantity':7}),
        context=dict(rules=[dict(op='move',source=['quantity'],target=['count'])]))
    result=Mapper(AgentProvider(from_env()),attempts=2,timeout=120).propose_mapping(request,purpose)
    assert result.proposal is not None and result.proposal.action=='EXECUTE'
    call=adapt(request,result.proposal.operations) if purpose=='mapping' else result.proposal.call
    call.validate_against(new)
    assert call.arguments=={'count':7}
    assert result.trace['responses'][-1]['details']['transport']=='gigacode-cli-json-2'
