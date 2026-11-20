import subprocess
import sys
from types import SimpleNamespace

import pytest

from mcp_compat.agent_checks import cli_version
from mcp_compat.providers import ProviderConfig, ProviderError


def test_cli_version(monkeypatch):
    config=ProviderConfig(executable=sys.executable)
    monkeypatch.setattr(subprocess,'run',lambda *a,**kw:SimpleNamespace(stdout='notice\n26.10.76\n'))
    assert cli_version(config) == '26.10.76'
    monkeypatch.setattr(subprocess,'run',lambda *a,**kw:SimpleNamespace(stdout='missing'))
    with pytest.raises(ProviderError,match='version'):
        cli_version(config)
