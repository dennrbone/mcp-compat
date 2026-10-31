from copy import deepcopy
import random

import pytest

from mcp_compat import ToolCall, ToolContract
from mcp_compat.benchmark import RecoveryInput, _case, recovery_input
from mcp_compat.recovery import NoRecovery, RuleBased


def case(family, variant):
    return _case('commerce', 'order', 2, family, variant, random.Random(42))


@pytest.mark.parametrize('family,variant,action', [
    ('C1',0,'EXECUTE'), ('C1',1,'ABSTAIN'), ('C1',4,'ABSTAIN'),
    ('C2',0,'EXECUTE'), ('C2',1,'ABSTAIN'), ('C2',2,'ABSTAIN'),
    ('C3',2,'EXECUTE'), ('C3',3,'ABSTAIN'), ('C3',1,'ABSTAIN'),
    ('C4',1,'ABSTAIN'), ('C5',0,'ABSTAIN'),
    ('C6',0,'ABSTAIN'), ('C6',1,'EXECUTE'), ('C6',2,'EXECUTE'),
    ('C6',3,'ABSTAIN'), ('C6',4,'ABSTAIN'), ('C7',0,'ABSTAIN'), ('C8',0,'ABSTAIN'),
])
def test_rule_based_limits(family, variant, action):
    request = recovery_input(case(family,variant))
    snapshot = deepcopy(request)
    decision = RuleBased().recover(request)
    assert decision.action == action
    assert request == snapshot
    if decision.action == 'EXECUTE':
        decision.adapted_call.validate_against(request.new_contract)
        assert decision.evidence['semantic_verified'] is False
    else:
        assert decision.adapted_call is None


def test_no_recovery_reports_original_attempt():
    request = recovery_input(case('C1',0))
    decision = NoRecovery().recover(request)
    assert decision.reasons == ['schema_invalid']
    assert decision.evidence['candidate'] == request.old_call.model_dump()
    request = recovery_input(case('C8',0))
    assert NoRecovery().recover(request).action == 'EXECUTE'
    # Explicitly a weak baseline: schema-valid units are NOT semantic evidence.
    assert NoRecovery().recover(request).evidence['semantic_verified'] is False


def test_opaque_identity_and_required_to_optional():
    contract = ToolContract(name='t',input_schema={'type':'object','properties':{'a.b':{'type':'integer'}},'required':['a.b']})
    request = RecoveryInput(old_contract=contract, new_contract=deepcopy(contract), old_call=ToolCall(tool_name='t',arguments={'a.b':2}))
    assert RuleBased().recover(request).action == 'EXECUTE'
    request.new_contract.input_schema['required'] = []
    assert RuleBased().recover(request).action == 'ABSTAIN'
    request.new_contract.input_schema['additionalProperties'] = False
    assert RuleBased().recover(request).reasons == ['opaque']


def test_enum_removed_current_value_is_invalid():
    request = recovery_input(case('C6',2))
    request.old_call.arguments['mode'] = 'standard'
    assert RuleBased().recover(request).reasons == ['schema_invalid']
