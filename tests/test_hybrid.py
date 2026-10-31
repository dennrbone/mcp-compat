from copy import deepcopy
import json

import pytest

from mcp_compat import ToolCall, ToolContract
from mcp_compat.benchmark import RecoveryInput
from mcp_compat.hybrid import Hybrid, SandboxVerifier, adapt, normalize
from mcp_compat.llm import Mapper, Operation
from test_llm import FakeClient


def unit_request():
    old = ToolContract(name='t',input_schema={'type':'object','properties':{'value':{'type':'integer'}},'required':['value']}, metadata={'semantic_unit':'RUB'})
    new = old.model_copy(deep=True)
    new.metadata['semantic_unit'] = 'kopecks'
    return RecoveryInput(old_contract=old,new_contract=new,old_call=ToolCall(tool_name='t',arguments={'value':2}),context={'rules':[dict(op='scale',source=['value'],target=['value'],factor=100)]})


def mapper(ops):
    return Mapper(FakeClient(json.dumps(dict(action='EXECUTE',operations=ops))),attempts=1)


def verifier(r):
    return SandboxVerifier(r.old_contract,r.new_contract,lambda a,s:a['value'],lambda a,s:a['value']/100)


def test_unit_mapping_and_no_oracle():
    r = unit_request()
    snapshot = deepcopy(r)
    decision = Hybrid(mapper(r.context['rules']),verifier(r)).recover(r)
    assert decision.action == 'EXECUTE' and decision.adapted_call.arguments['value'] == 200
    assert decision.evidence['semantic_verified'] and r == snapshot
    assert 'oracle' not in json.dumps(decision.model_dump())
    wrong = Hybrid(mapper([]),verifier(r)).recover(r)
    assert wrong.reasons == ['semantic_mismatch'] and wrong.adapted_call is None


def test_verification_and_explicit_unit_rule_required():
    r = unit_request()
    assert Hybrid(mapper(r.context['rules'])).recover(r).reasons == ['verifier_unavailable']
    engine = Hybrid(mapper(r.context['rules']),verifier(r))
    r.context = {}
    assert engine.recover(r).reasons == ['unit_rule_missing']
    r.new_contract.metadata['semantic_unit'] = 'unknown'
    assert Hybrid(mapper([]),SandboxVerifier(r.old_contract,r.new_contract,lambda a,s:1,lambda a,s:1)).recover(r).reasons == ['unit_rule_missing']


def test_all_ablations():
    r = unit_request()
    assert Hybrid(mapper([]),verifier(r),ablation='A1').recover(r).reasons == ['unit_rule_missing']
    assert Hybrid(mapper(r.context['rules']),ablation='A1').recover(r).action == 'EXECUTE'
    assert Hybrid(mapper([]),verifier(r),ablation='A4').recover(r).action == 'EXECUTE'
    assert Hybrid(ablation='A3').recover(r).reasons == ['no_deterministic_candidate']
    same = r.model_copy(deep=True)
    same.new_contract = same.old_contract.model_copy(deep=True)
    v = SandboxVerifier(same.old_contract,same.new_contract,lambda a,s:a,lambda a,s:a)
    assert Hybrid(verifier=v).recover(same).action == 'EXECUTE'
    assert Hybrid(mapper([]),v,ablation='A2').recover(same).action == 'EXECUTE'


def test_pipeline_safe_failures():
    r = unit_request()
    assert Hybrid().recover(r).reasons == ['mapper_unavailable']
    assert Hybrid(Mapper(FakeClient('bad'),attempts=1)).recover(r).reasons == ['mapping_abstain']
    wrong = [dict(op='set',target=['value'],value='bad')]
    assert Hybrid(mapper(wrong),verifier(r)).recover(r).reasons == ['schema_invalid']
    r.new_contract.input_schema['additionalProperties'] = False
    assert Hybrid().recover(r).reasons == ['opaque']
    r.old_call.tool_name = 'wrong'
    assert Hybrid().recover(r).reasons == ['pipeline_error']


def test_sandbox_state_binding_error_timeout_and_finite():
    r = unit_request()
    call = ToolCall(tool_name='t',arguments={'value':200})
    def old(a,s):
        s['balance'] += a['value']
    def new(a,s):
        s['balance'] += a['value']/100
    initial = {'balance':1}
    v = SandboxVerifier(r.old_contract,r.new_contract,old,new,side_effects=True,initial=initial)
    assert v.verify(r,call).passed and initial == {'balance':1}
    changed = deepcopy(r)
    changed.new_contract.name = 'other'
    assert v.verify(changed,call).reason == 'unbound_runtime'
    def fail(a,s):
        raise TimeoutError('private')
    assert SandboxVerifier(r.old_contract,r.new_contract,fail,new).verify(r,call).reason == 'verification_error'
    times = iter([0,2])
    v = SandboxVerifier(r.old_contract,r.new_contract,old,new,initial=initial,clock=lambda:next(times))
    assert v.verify(r,call).reason == 'verification_timeout'
    v = SandboxVerifier(r.old_contract,r.new_contract,lambda a,s:float('nan'),lambda a,s:float('nan'))
    assert v.verify(r,call).reason == 'verification_error'
    assert normalize([{'a':1.0,'b':True},1.25,None]) == [{'a':1,'b':True},1.25,None]
    assert type(normalize(True)) is bool


@pytest.mark.parametrize('ops,args,expected', [
    ([dict(op='move',source=['a.b'],target=['payload','x'])],{'a.b':2},{'payload':{'x':2}}),
    ([dict(op='move',source=['payload','x'],target=['a'])],{'payload':{'x':2}},{'payload':{},'a':2}),
    ([dict(op='move',source=['x'],target=['x'])],{'x':2},{'x':2}),
    ([dict(op='string',source=['x'],target=['x'])],{'x':2},{'x':'2'}),
    ([dict(op='wrap',source=['x'],target=['x'])],{'x':2},{'x':[2]}),
    ([dict(op='enum',source=['x'],target=['x'],values={'a':'b'})],{'x':'a'},{'x':'b'}),
    ([dict(op='set',target=['x'],value=3)],{}, {'x':3}),
])
def test_adapter_opcodes(ops,args,expected):
    r = unit_request()
    r.old_call.arguments = args
    assert adapt(r,[Operation.model_validate(op) for op in ops]).arguments == expected
    assert r.old_call.arguments == args


@pytest.mark.parametrize('ops,args', [
    ([dict(op='set',target=['x'],value=1),dict(op='set',target=['x'],value=2)],{}),
    ([dict(op='set',target=['x'],value=1),dict(op='set',target=['x','y'],value=2)],{}),
    ([dict(op='set',target=['x','y'],value=1),dict(op='set',target=['x'],value=2)],{}),
    ([dict(op='move',source=['x'],target=['y']),dict(op='move',source=['y'],target=['x'])],{'x':1,'y':2}),
    ([dict(op='scale',source=['x'],target=['x'],factor=100)],{'x':True}),
    ([dict(op='scale',source=['x'],target=['x'],factor=100)],{'x':'2'}),
    ([dict(op='scale',source=['x'],target=['x'],factor=100)],{'x':float('inf')}),
    ([dict(op='enum',source=['x'],target=['x'],values={'a':'b'})],{'x':1}),
])
def test_bad_adapters(ops,args):
    r = unit_request()
    r.old_call.arguments = args
    with pytest.raises(ValueError):
        adapt(r,[Operation.model_validate(op) for op in ops])
