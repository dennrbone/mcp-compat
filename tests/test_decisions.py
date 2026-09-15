import pytest
from pydantic import ValidationError

from mcp_compat import MigrationDecision, ToolCall


@pytest.mark.parametrize('action,call', [('EXECUTE', ToolCall(tool_name='t', arguments={})), ('ABSTAIN', None)])
def test_decision_round_trip(action, call):
    decision = MigrationDecision(action=action, adapted_call=call, reasons=['schema_valid'], evidence={'valid': True})
    assert MigrationDecision.model_validate_json(decision.model_dump_json()) == decision
    assert decision.metadata == {}


@pytest.mark.parametrize('kwargs', [dict(action='EXECUTE'), dict(action='ABSTAIN', adapted_call=ToolCall(tool_name='t', arguments={})), dict(action='RETRY')])
def test_invalid_decision(kwargs):
    with pytest.raises(ValidationError):
        MigrationDecision(**kwargs)
