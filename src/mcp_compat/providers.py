"""Isolated official CLI transports; credentials stay in the installed clients."""

import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory, TemporaryFile
from typing import Mapping, Self

from pydantic import model_validator

from mcp_compat import canonical_json
from mcp_compat.llm import LLMRequest, LLMResponse, StrictModel


MODEL_ID = "gigacode/GigaCode"  # Installed CLI catalog display name: CodeAgent.


class ProviderError(RuntimeError):
    pass


class ProviderConfig(StrictModel):
    model: str = MODEL_ID
    executable: str

    @model_validator(mode="after")
    def validate_selection(self) -> Self:
        if self.model != MODEL_ID:
            raise ValueError("the installed CodeAgent model is required")
        path = Path(self.executable)
        if not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
            raise ValueError("an installed executable with an absolute path is required")
        return self


def from_env(*, environ: Mapping[str, str] | None = None) -> ProviderConfig:
    env = os.environ if environ is None else environ
    executable = env.get("GIGACODE_BIN") or shutil.which("gigacode", path=env.get("PATH", ""))
    if executable is None:
        raise ValueError("set GIGACODE_BIN to the installed CLI")
    return ProviderConfig(executable=executable)


def _parse_events(stdout: str, model: str) -> LLMResponse:
    # The installed extension CLI also emits non-JSON startup notices to stdout.
    events = [json.loads(line) for line in stdout.splitlines() if line.startswith("{")]
    if any(e["type"] not in ("step_start", "text", "reasoning", "step_finish") for e in events):
        raise ProviderError("provider_error_or_tool_event")
    starts = [e for e in events if e["type"] == "step_start"]
    finishes = [e["part"] for e in events if e["type"] == "step_finish"]
    if len(starts) != 1 or len(finishes) != 1 or finishes[0]["reason"] != "stop":
        raise ProviderError("provider_incomplete_or_multiple_steps")
    text = "".join(e["part"]["text"] for e in events if e["type"] == "text")
    if not text.strip():
        raise ProviderError("provider_empty_response")
    finish = finishes[0]
    tokens = finish.get("tokens", {})
    cache = tokens.get("cache", {})
    input_tokens = None if "input" not in tokens else tokens["input"] + cache.get("read", 0) + cache.get("write", 0)
    output_tokens = None if "output" not in tokens else tokens["output"] + tokens.get("reasoning", 0)
    if finish.get("cost", 0) != 0:
        raise ProviderError("provider_nonzero_reported_cost")
    return LLMResponse(text=text, model=model, input_tokens=input_tokens,
                       output_tokens=output_tokens, cost=finish.get("cost"))


class AgentProvider:
    def __init__(self, config: ProviderConfig):
        self.config = config

    def complete(self, request: LLMRequest, timeout: float) -> LLMResponse:
        if not 0 < timeout <= 120:
            raise ValueError("invalid provider timeout")
        config = self.config
        prefix = "KILO"
        with TemporaryDirectory(prefix="mcp-compat-agent-") as directory, TemporaryFile() as stdout:
            root = Path(directory)
            (root / "config").mkdir()
            (root / "extra").mkdir()
            agent = dict(mode="primary", prompt=request.system, temperature=0, steps=1, permission="deny")
            settings = dict(model=config.model, small_model=config.model, autoupdate=False, snapshot=False,
                share="disabled", enabled_providers=["gigacode"], permission="deny", instructions=[],
                plugin=[], mcp={}, compaction=dict(auto=False, prune=False),
                agent=dict(mcp_mapper=agent, title=dict(disable=True), summary=dict(disable=True), compaction=dict(disable=True)))
            env = os.environ.copy()
            env.update(XDG_CONFIG_HOME=str(root / "config"), NODE_TLS_REJECT_UNAUTHORIZED="1")
            env[f"{prefix}_CONFIG_DIR"] = str(root / "extra")
            env[f"{prefix}_CONFIG_CONTENT"] = canonical_json(settings)
            env[f"{prefix}_EXPERIMENTAL_OUTPUT_TOKEN_MAX"] = str(request.max_tokens)
            env[f"{prefix}_SESSION_RETRY_LIMIT"] = "0"
            for flag in ("DISABLE_AUTOUPDATE", "DISABLE_DEFAULT_PLUGINS", "DISABLE_CLAUDE_CODE",
                         "DISABLE_EXTERNAL_SKILLS", "DISABLE_PROJECT_CONFIG", "DISABLE_LSP_DOWNLOAD", "DISABLE_AUTOCOMPACT"):
                env[f"{prefix}_{flag}"] = "1"
            payload = canonical_json(dict(data=request.data, response_schema=request.response_schema))
            command = [config.executable, "run", "--pure", "--log-level", "ERROR", "--model", config.model,
                       "--agent", "mcp_mapper", "--format", "json", "--title", "mcp-compat", request.system + "\n" + payload]
            try:
                result = subprocess.run(command, cwd=root, env=env, stdin=subprocess.DEVNULL,
                    stdout=stdout, stderr=subprocess.DEVNULL, timeout=timeout, check=False)
                if result.returncode:
                    raise ProviderError("provider_cli_failed")
                if stdout.tell() > 1048576:
                    raise ProviderError("provider_output_limit")
                stdout.seek(0)
                return _parse_events(stdout.read().decode("utf-8"), config.model)
            except subprocess.TimeoutExpired:
                raise ProviderError("provider_timeout") from None
            except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError):
                raise ProviderError("provider_unavailable_or_invalid") from None
