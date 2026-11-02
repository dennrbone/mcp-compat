from copy import deepcopy

import anyio
from mcp.shared.memory import create_connected_server_and_client_session as connected
import pytest

from mcp_compat import ToolCall, canonical_bytes
from mcp_compat.benchmark import equivalent, freeze, load, recovery_input
from mcp_compat.case_study import PROFILES, generate
from mcp_compat.case_study_runtime import APIS, VERSION, contract, execute, initial, registry
from mcp_compat.declared_rules import DeclaredRules, VerifiedDeclaredRules
from mcp_compat.experiments import RunConfig, run
from mcp_compat.mcp_integration import make_proxy, make_server


def test_independent_references_and_both_information_regimes(tmp_path, monkeypatch):
    scenarios = generate(with_rules=True)
    hidden = generate(with_rules=False)
    assert len(scenarios) == 192 and sum(s.metadata['recoverable'] for s in scenarios) == 144
    verifier = registry()
    assert len(verifier.bindings) == 96
    for scenario,other in zip(scenarios,hidden):
        app = scenario.metadata['application']
        before = initial(app)
        expected = execute(app,'old',scenario.old_call.arguments,before)
        assert (before if APIS[app].effect else expected) == scenario.oracle['expected']
        assert scenario.old_contract == other.old_contract and scenario.new_contract == other.new_contract
        assert scenario.old_call == other.old_call and scenario.oracle == other.oracle
        assert other.metadata['public_context'] == {}
        request = recovery_input(scenario)
        decision = VerifiedDeclaredRules(verifier).recover(request)
        if scenario.metadata['recoverable']:
            call = ToolCall.model_validate(scenario.oracle['adapted_call'])
            assert equivalent(scenario,call)
            assert verifier.verify(request,call).passed
            assert decision.action == 'EXECUTE' and equivalent(scenario,decision.adapted_call)
        else:
            call = ToolCall(tool_name=scenario.new_contract.name,arguments=scenario.old_call.arguments)
            assert not equivalent(scenario,call)
            assert not verifier.verify(request,call).passed
            assert decision.action == 'ABSTAIN'
        assert not equivalent(scenario,ToolCall(tool_name='invalid',arguments={}))
    sample = scenarios[2]
    request = recovery_input(sample)
    call = ToolCall.model_validate(sample.oracle['adapted_call'])
    def forbidden(*args,**kwargs):
        raise AssertionError('Оценщик не доступен верификатору')
    monkeypatch.setattr('mcp_compat.case_study.equivalent',forbidden)
    monkeypatch.setattr('mcp_compat.case_study.PROFILES',{})
    assert verifier.verify(request,call).passed
    data = tmp_path/'data'
    digest = freeze(scenarios,data,42,version=VERSION)
    assert load(data,digest) == sorted(scenarios,key=lambda s:s.scenario_id)
    with pytest.raises(ValueError,match='unsupported'):
        freeze([],tmp_path/'invalid',42,version='unknown')


def test_main_runner_uses_case_study_evaluator(tmp_path):
    cases = generate(with_rules=True)[:8]
    data = tmp_path/'data'
    digest = freeze(cases,data,42,version=VERSION)
    config = RunConfig(kind='main',benchmark_digest=digest,model_versions={'deterministic':'no-inference'})
    records = run(config,[DeclaredRules(),VerifiedDeclaredRules(registry())],data,tmp_path/'results')
    assert len(records) == 16 and all(r.calls == 0 for r in records)
    assert all(r.semantic_equivalent for r in records if r.decision.action == 'EXECUTE' and r.recoverable)


def test_runtime_negative_inputs_and_branch_boundaries():
    with pytest.raises(ValueError,match='version'):
        contract('documents_words','unknown')
    with pytest.raises(ValueError,match='version'):
        execute('documents_words','unknown',{}, {})
    with pytest.raises(ValueError,match='singleton'):
        execute('documents_find','encoding',dict(query='al',limit=[1,2],match='prefix'),{})
    assert execute('calendar_room','old',dict(room='missing',seats=3,mode='strict'),{})['assigned'] == 0
    for app in ('documents_words','analytics_buckets','inventory_restock'):
        args = deepcopy(PROFILES[app][0][0])
        args.pop(APIS[app].critical)
        execute(app,'removed',args,initial(app))


def test_all_cases_through_official_mcp_proxy():
    async def check():
        engine = VerifiedDeclaredRules(registry())
        for scenario in generate(with_rules=True):
            app,version = scenario.metadata['application'],scenario.metadata['api_version']
            old_state,new_state = initial(app),initial(app)
            async def old(a,s):
                return execute(app,'old',a,s)
            async def new(a,s):
                return execute(app,version,a,s)
            async with connected(make_server(scenario.old_contract,old,old_state)) as previous:
                expected = await previous.call_tool(scenario.old_contract.name,scenario.old_call.arguments)
            async with connected(make_server(scenario.new_contract,new,new_state)) as upstream:
                async with connected(make_proxy(scenario.old_contract,scenario.new_contract,upstream,engine,
                                                context=scenario.metadata['public_context'],timeout=5)) as proxy:
                    result = await proxy.call_tool(scenario.old_contract.name,scenario.old_call.arguments)
            if scenario.metadata['recoverable']:
                assert not result.isError and result.structuredContent == expected.structuredContent
                assert canonical_bytes(new_state) == canonical_bytes(old_state)
            else:
                assert result.isError and new_state == initial(app)
    anyio.run(check)
