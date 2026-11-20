"""Проверка версии установленного клиента CodeAgent."""

import os
import re
import subprocess

from mcp_compat.providers import ProviderConfig, ProviderError


def cli_version(config: ProviderConfig) -> str:
    result = subprocess.run([config.executable, "--version"], capture_output=True, text=True,
                            timeout=10, check=True, env={**os.environ, 'NODE_TLS_REJECT_UNAUTHORIZED':'1'})
    versions = [line.strip() for line in result.stdout.splitlines() if re.fullmatch(r"\d+\.\d+\.\d+", line.strip())]
    if len(versions) != 1:
        raise ProviderError("provider_version_unavailable")
    return versions[0]
