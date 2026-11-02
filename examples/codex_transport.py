"""Одноразовый текстовый транспорт Terra через авторизованный Codex CLI."""

import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory, TemporaryFile

from mcp_compat import canonical_json
from mcp_compat.llm import LLMRequest, LLMResponse
from mcp_compat.providers import ProviderError

MODEL = 'gpt-6.1-terra'
PARAMETERS = dict(reasoning_effort='low', temperature='provider_default',
                  max_tokens='provider_default', request_max_tokens_hint=2048)
DISABLED = ('shell_tool', 'unified_exec', 'apps', 'plugins', 'multi_agent',
            'multi_agent_v2', 'memories', 'browser_use', 'computer_use',
            'in_app_browser', 'image_generation', 'view_image', 'hooks', 'skill_search')


def parse_events(stdout: str) -> LLMResponse:
    events = [json.loads(line) for line in stdout.splitlines() if line.strip()]
    texts, finishes, starts, threads = [], [], 0, 0
    for event in events:
        kind = event['type']
        if kind == 'thread.started':
            threads += 1
        elif kind == 'turn.started':
            starts += 1
        elif kind == 'turn.completed':
            finishes.append(event)
        elif kind in ('item.started', 'item.updated', 'item.completed'):
            item = event['item']
            if item['type'] not in ('agent_message', 'reasoning'):
                raise ProviderError('codex_unexpected_tool_event')
            if kind == 'item.completed' and item['type'] == 'agent_message':
                texts.append(item['text'])
        else:
            raise ProviderError('codex_error_or_unknown_event')
    if threads != 1 or starts != 1 or len(finishes) != 1 or len(texts) != 1 or not texts[0].strip():
        raise ProviderError('codex_incomplete_or_multiple_responses')
    usage = finishes[0].get('usage', {})
    return LLMResponse(text=texts[0], model=MODEL,
        input_tokens=usage.get('input_tokens'), output_tokens=usage.get('output_tokens'),
        cost=None, details=dict(transport='codex-cli-json-1', parameters=PARAMETERS,
            cached_input_tokens=usage.get('cached_input_tokens'),
            reasoning_output_tokens=usage.get('reasoning_output_tokens'),
            output_token_limit_enforced=False, backend_revision='unknown'))


class CodexClient:
    def __init__(self, executable: str):
        path = Path(executable)
        if not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
            raise ValueError('absolute installed Codex executable required')
        self.executable = executable

    def complete(self, request: LLMRequest, timeout: float) -> LLMResponse:
        if not 0 < timeout <= 120:
            raise ValueError('invalid provider timeout')
        with TemporaryDirectory(prefix='mcp-compat-terra-') as directory, TemporaryFile() as stdout:
            root = Path(directory)
            instructions = root/'instructions.txt'
            instructions.write_text(request.system)
            command = [self.executable, '--no-daemon', '-a', 'never', 'exec',
                '--ignore-user-config', '--ephemeral', '--skip-git-repo-check',
                '--sandbox', 'read-only', '--model', MODEL, '--json', '--color', 'never',
                '-c', 'model_reasoning_effort="low"', '-c', 'service_tier="default"',
                '-c', 'project_doc_max_bytes=0', '-c', 'agents.enabled=false',
                '-c', 'web_search="disabled"', '-c', 'developer_instructions=""',
                '-c', 'features.skip_host_skill_discovery=true',
                '-c', 'suppress_unstable_features_warning=true',
                '-c', 'analytics.enabled=false',
                '-c', 'model_instructions_file='+json.dumps(str(instructions))]
            for feature in DISABLED:
                command.extend(['--disable', feature])
            command.append('-')
            env = os.environ.copy()
            # Используется сохранённая ChatGPT-авторизация, без подстановки API-ключа.
            for name in ('OPENAI_API_KEY', 'CODEX_API_KEY'):
                env.pop(name, None)
            payload = canonical_json(dict(data=request.data, response_schema=request.response_schema))
            prompt = request.system+'\n'+payload+'\n'+request.system
            try:
                result = subprocess.run(command, input=prompt.encode(), cwd=root, env=env,
                    stdout=stdout, stderr=subprocess.DEVNULL, timeout=timeout, check=False)
                if result.returncode:
                    raise ProviderError('codex_cli_failed')
                if stdout.tell() > 1048576:
                    raise ProviderError('codex_output_limit')
                stdout.seek(0)
                return parse_events(stdout.read().decode('utf-8'))
            except subprocess.TimeoutExpired:
                raise ProviderError('codex_timeout') from None
            except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError):
                raise ProviderError('codex_unavailable_or_invalid') from None
