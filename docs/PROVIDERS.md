# Provider configuration and validation status

Documentation checked 2026-10-31 (not model execution):

- [GigaChat REST reference](https://developers.sber.ru/docs/ru/gigachat/api/reference/rest/gigachat-api)
  and [chat endpoint](https://developers.sber.ru/docs/ru/gigachat/api/reference/rest/post-chat).
  Current documented endpoint: `https://api.giga.chat/v1/chat/completions`;
  legacy `https://gigachat.devices.sberbank.ru/api/v1/chat/completions` remains
  documented. Supply an already obtained access token; no implicit OAuth or billing.
- [Qwen vLLM deployment](https://qwen.readthedocs.io/en/stable/deployment/vllm.html)
  describes local OpenAI-compatible chat serving. Configure a loopback
  `/v1/chat/completions` endpoint for your actual deployment.

Set `<PROVIDER>_ENDPOINT`, `<PROVIDER>_MODEL`, and (GigaChat required)
`<PROVIDER>_ACCESS_TOKEN`; prefixes are GIGACHAT or QWEN. Never place real values
in tracked configuration. `from_env` has no model or endpoint guesses.
GigaChat additionally requires `allow_paid=True` at the explicit launch boundary
after user authorization. Permission to push Git branches is not billing consent.

HTTP implementation: httpx **0.28.1**; redirects disabled; TLS verification on;
environment proxy credentials ignored; no authentication text in error traces.
The optional `llm` extra installs the transport. Call `close()` after use.
Input/output tokens come from provider usage; missing usage/cost stays unknown.
Model name/revision returned by the server is recorded. An alias alone does not
prove immutable model weights; record serving image, weight digest, quantization
and hardware in the experimental configuration before real experiments.

Model versions/weights, credentials, GigaChat smoke, Qwen smoke, GPU/resource
availability and quality comparison: **NOT RUN / NOT PROVIDED**. All current
transport tests use httpx.MockTransport with explicit fake model names.
