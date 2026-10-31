"""Opt-in GigaChat and loopback Qwen/vLLM transports; never log credentials."""

import os
from typing import Literal, Mapping, Self
from urllib.parse import urlsplit

import httpx
from pydantic import Field, SecretStr, model_validator

from mcp_compat import canonical_json
from mcp_compat.llm import LLMRequest, LLMResponse, StrictModel


class ProviderError(RuntimeError):
    pass


class ProviderConfig(StrictModel):
    provider: Literal["gigachat", "qwen"]
    endpoint: str
    model: str = Field(min_length=1)
    token: SecretStr | None = Field(default=None, repr=False)
    allow_paid: bool = False

    @model_validator(mode="after")
    def validate_endpoint(self) -> Self:
        url = urlsplit(self.endpoint)
        if url.username or url.password or url.query or url.fragment or not self.model.strip():
            raise ValueError("invalid provider configuration")
        if self.provider == "qwen":
            if url.hostname not in ("127.0.0.1", "localhost", "::1") or url.scheme not in ("http", "https") or url.path != "/v1/chat/completions":
                raise ValueError("Qwen requires a local vLLM chat endpoint")
        elif url.scheme != "https" or (url.hostname, url.path) not in (
            ("api.giga.chat", "/v1/chat/completions"),
            ("gigachat.devices.sberbank.ru", "/api/v1/chat/completions"),
        ) or self.token is None or not self.token.get_secret_value().strip():
            raise ValueError("GigaChat requires a documented TLS endpoint and access token")
        return self


def from_env(provider: Literal["gigachat", "qwen"], *, allow_paid: bool = False,
             environ: Mapping[str, str] | None = None) -> ProviderConfig:
    env = os.environ if environ is None else environ
    prefix = provider.upper()
    token = env.get(f"{prefix}_ACCESS_TOKEN")
    return ProviderConfig(provider=provider, endpoint=env[f"{prefix}_ENDPOINT"],
        model=env[f"{prefix}_MODEL"], token=None if token is None else SecretStr(token), allow_paid=allow_paid)


class ChatProvider:
    def __init__(self, config: ProviderConfig, http: httpx.Client | None = None):
        self.config = config
        self.http = http or httpx.Client(follow_redirects=False, trust_env=False)

    def close(self) -> None:
        self.http.close()

    def complete(self, request: LLMRequest, timeout: float) -> LLMResponse:
        config = self.config
        if config.provider == "gigachat" and not config.allow_paid:
            raise PermissionError("paid provider calls require explicit authorization")
        headers = {"Content-Type": "application/json"}
        if config.token is not None:
            headers["Authorization"] = f"Bearer {config.token.get_secret_value()}"
        payload = dict(model=config.model, temperature=0, max_tokens=request.max_tokens,
            messages=[dict(role="system", content=request.system),
                dict(role="user", content=canonical_json(dict(data=request.data, response_schema=request.response_schema)))])
        if config.provider == "qwen":
            payload["response_format"] = {"type": "json_object"}
        try:
            with self.http.stream("POST", config.endpoint, json=payload, headers=headers, timeout=timeout, follow_redirects=False) as response:
                response.raise_for_status()
                content = bytearray()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > 1048576:
                        raise ValueError("response limit")
                data = httpx.Response(200, content=bytes(content)).json()
            usage = data.get("usage", {})
            return LLMResponse(text=data["choices"][0]["message"]["content"],
                model=data.get("model", config.model), input_tokens=usage.get("prompt_tokens"),
                output_tokens=usage.get("completion_tokens"))
        except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError):
            raise ProviderError("provider_unavailable_or_invalid") from None
