from copy import deepcopy
import json
from pathlib import Path

import pytest

from mcp_compat.benchmark import equivalent, load, recovery_input
from mcp_compat.declared_rules import DeclaredRuleMapper, DeclaredRules, VerifiedDeclaredRules
from mcp_compat.experiments import RunConfig, run
from mcp_compat.runtime_fixtures import fixture_verifier
from test_hybrid import unit_request, verifier


def test_declared_controls_share_validation_without_model_calls():
    request=unit_request()
    snapshot=deepcopy(request)
    for strategy in (DeclaredRules(),VerifiedDeclaredRules(verifier(request))):
        result=strategy.recover(request)
        assert result.action=='EXECUTE' and result.adapted_call.arguments=={'value':200}
        assert result.evidence['declared_rules']['calls']==0
        assert 'llm' not in result.evidence
    assert request==snapshot


@pytest.mark.parametrize('rules',[
    [{'op':'scale','source':['wrong'],'target':['value'],'factor':100}],
    [{'op':'set','target':['value'],'value':'x'*33000}],
    [{'op':'scale','source':['value'],'target':['value'],'factor':float('nan')}],
    [{'op':'move','source':['value'],'target':['value']}]*33,
])
def test_invalid_declared_rules_fail_closed(rules):
    request=unit_request()
    request.context={'rules':rules}
    assert DeclaredRuleMapper().propose_mapping(request).proposal is None
    assert DeclaredRules().recover(request).reasons==['invalid_declared_rules']
    assert VerifiedDeclaredRules(verifier(request)).recover(request).action=='ABSTAIN'


def test_schema_only_control_can_execute_a_semantically_wrong_candidate():
    request=unit_request()
    request.context={}
    assert DeclaredRules().recover(request).action=='EXECUTE'
    assert VerifiedDeclaredRules(verifier(request)).recover(request).action=='ABSTAIN'
    request.old_call.arguments['value']='bad'
    assert DeclaredRules().recover(request).reasons==['invalid_adapter']


def test_declared_control_preserves_schema_rejection():
    request=unit_request()
    request.context={'rules':[dict(op='set',target=['value'],value='bad')]}
    assert DeclaredRules().recover(request).reasons==['schema_invalid']


def test_declared_rule_target_through_scalar_abstains():
    from mcp_compat import ToolCall, ToolContract
    from mcp_compat.benchmark import RecoveryInput
    old=ToolContract(name='t',input_schema=dict(type='object',properties=dict(x={'type':'integer'},value={'type':'integer'}),required=['x','value']))
    new=ToolContract(name='t',input_schema=dict(type='object',properties=dict(x={'type':'object','properties':{'y':{'type':'object','properties':{'z':{'type':'string'}}}}},value={'type':'integer'}),required=['x','value']))
    request=RecoveryInput(old_contract=old,new_contract=new,old_call=ToolCall(tool_name='t',arguments=dict(x=3,value=7)))
    for target in (['x','y'],['x','y','z']):
        request.context=dict(rules=[dict(op='string',source=['value'],target=target)])
        snapshot=deepcopy(request)
        decision=DeclaredRules().recover(request)
        assert decision.action=='ABSTAIN' and decision.reasons==['invalid_adapter']
        assert decision.evidence['declared_rules']['calls']==0 and request==snapshot


def test_full_corpus_declared_controls_are_a_real_zero_inference_comparison(tmp_path):
    index=json.loads(Path('benchmark/manifest.json').read_bytes())
    corpus=load(Path(index['path']),index['digest'])
    engine=VerifiedDeclaredRules(fixture_verifier())
    executed=0
    for scenario in corpus:
        decision=engine.recover(recovery_input(scenario))
        assert 'llm' not in decision.evidence
        if decision.action=='EXECUTE':
            assert equivalent(scenario,decision.adapted_call)
            executed+=1
    assert executed==1056
    selected=[s.scenario_id for s in corpus[:2]]
    records=run(RunConfig(kind='deterministic',benchmark_digest=index['digest'],scenario_ids=selected),
        [DeclaredRules(),engine],Path(index['path']),tmp_path/'run')
    assert len(records)==4 and all(r.calls==r.cost==r.input_tokens==0 for r in records)
