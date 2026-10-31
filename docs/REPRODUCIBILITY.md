# Reproducibility

Run commands from the repository root. Python **3.11.4**, Draft **2020-12**.
The library wheel contains Python modules; frozen datasets and research artifacts
are supplied by the repository, not bundled into the wheel.

## Clean installation and checks

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.lock
.venv/bin/python -m pip install --no-deps -e .
.venv/bin/python -m pytest -q -rs --cov=mcp_compat --cov-branch --cov-report=term-missing --cov-report=xml --cov-fail-under=100
.venv/bin/ruff check src tests
.venv/bin/mypy src
.venv/bin/python -m build
```

Check the interpreter's full version before running: `python3.11` may select a
different patch release. The lock pins exact dependency versions and distribution
hashes. Phase 1–2 and all added modules retain the same 100% statement/branch
gate; no exclusions or coverage pragmas are used. Third-party SciPy/Matplotlib
imports lack complete stubs; mypy checks our source and ignores missing stubs
only for those third-party namespaces.

## Dataset replay and integrity

```bash
.venv/bin/python -c 'import json; from pathlib import Path; from mcp_compat.benchmark import generate, freeze, load; m=json.loads(Path("benchmark/manifest.json").read_bytes()); data=load(Path(m["path"]),m["digest"]); digest=freeze(generate(m["seed"]),Path("/tmp/mcp-evobench-replay"),m["seed"]); assert digest==m["digest"]; print(len(data),digest)'
```

Choose a new replay directory if it already exists: freeze is exclusive and
never overwrites. Active digest is recorded in benchmark/manifest.json; 1.2 has
48 unique old contracts and 2160 scenarios. Old freezes are retained for audit,
not main experiments. SHA-256 detects corruption with a trusted pinned digest;
it is not a digital signature.

## Offline end-to-end run

```bash
MPLCONFIGDIR=/tmp/mcp-matplotlib .venv/bin/mcp-compat-demo --output /tmp/mcp-offline-demo
MPLCONFIGDIR=/tmp/mcp-matplotlib .venv/bin/mcp-compat-analyze --run /tmp/mcp-offline-demo --output /tmp/mcp-offline-analysis --seed 42 --draws 2000
```

The demo has 45 identical frozen scenarios for nine methods, yielding 405 records.
It uses `offline-demo-no-inference`; no inference API, GPU or user data is used.
It binds one independently implemented unit/quote pair; unbound M1 cases abstain.
Generated CI/p-values are diagnostic, with explicit assumptions/statuses. The
single base-tool cluster does not support a bootstrap CI. Actual tracked run:
`experiments/offline-demo-final/`; tables/PNG/SVG/LaTeX:
`experiments/analysis-offline-demo/`. The older offline-demo directory is historical
1.1 evidence; never mix its records with 1.2 or present either as the main study.

Resume uses the same command/config directory and preserves completed records.
Changing source/config/dependencies rejects resume; use a new directory. Duration
and UTC timestamps are measurements, so re-running does not promise identical
latency bytes. Dataset regeneration does promise identical bytes.

## Real providers — opt-in, NOT RUN

Configuration is documented in PROVIDERS.md. Only a deliberate smoke opt-in can
contact a configured provider. GigaChat additionally requires explicit billing
authorization; no such authorization was given in this implementation session.
The `real_provider` tests otherwise skip with a reason. Qwen requires an existing
loopback vLLM server and pinned weights. GitHub-hosted runners have no such server
by default; the manual smoke workflow is not proof of local model availability.

The Python API `experiments.run(RunConfig(...), strategies, frozen_path, output)`
supports main experiments with injected ChatProvider/Mapper and independent
runtime verification. Set explicit actual model identifiers and trusted binding
versions before any authorized study. No runtime binder may read oracle files.

CI uses verified Node.js 24 actions:
[checkout v5.0.0](https://github.com/actions/checkout/releases/tag/v5.0.0) and
[setup-python v6.0.0](https://github.com/actions/setup-python/releases/tag/v6.0.0).
Offline tests/coverage/types/lint/build and e2e are separate from manually opted-in
provider smoke. A skipped smoke test is **NOT RUN**, even if its job exits zero.
