"""Real inference is opt-in and is never part of the offline quality evidence."""

import os

import pytest

from mcp_compat.llm import LLMRequest, Proposal
from mcp_compat.providers import ChatProvider, from_env


@pytest.mark.real_provider
@pytest.mark.parametrize('provider',['qwen','gigachat'])
def test_real_provider_smoke(provider):
    if os.environ.get('MCP_COMPAT_RUN_PROVIDER_SMOKE') != '1' or os.environ.get('MCP_COMPAT_SMOKE_PROVIDER') != provider:
        pytest.skip('real provider not explicitly enabled')
    paid = os.environ.get('MCP_COMPAT_ALLOW_PAID') == '1'
    if provider == 'gigachat' and not paid:
        pytest.skip('paid inference not authorized')
    required = [f'{provider.upper()}_ENDPOINT',f'{provider.upper()}_MODEL']
    if provider == 'gigachat':
        required.append('GIGACHAT_ACCESS_TOKEN')
    if any(not os.environ.get(key) for key in required):
        pytest.skip('required provider configuration missing')
    config = from_env(provider,allow_paid=paid)
    client = ChatProvider(config)
    try:
        response = client.complete(LLMRequest(system='Return only a JSON object with action ABSTAIN.',data={},response_schema=Proposal.model_json_schema()),20)
        assert Proposal.model_validate_json(response.text).action == 'ABSTAIN'
    finally:
        client.close()
