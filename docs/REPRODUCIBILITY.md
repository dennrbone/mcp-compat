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
.venv/bin/ruff check src tests examples
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
It now uses the 1536-binding trusted synthetic registry; unbound M1 cases abstain.
Generated CI/p-values are diagnostic, with explicit assumptions/statuses. The
single base-tool cluster does not support a bootstrap CI. Actual tracked run:
`experiments/offline-demo-final/`; tables/PNG/SVG/LaTeX:
`experiments/analysis-offline-demo/`. Those Phase 10 artifacts used one runtime
pair; a current rerun has a different source fingerprint and runtime coverage.
The older offline-demo directory is historical 1.1 evidence; never mix versions
or source fingerprints or present these demos as the main study.

Resume uses the same command/config directory and preserves completed records.
Changing source/config/dependencies rejects resume; use a new directory. Duration
and UTC timestamps are measurements, so re-running does not promise identical
latency bytes. Dataset regeneration does promise identical bytes.

## Real providers — explicitly enabled

See [PROVIDERS.md](PROVIDERS.md) and [AGENT_TESTS.md](AGENT_TESTS.md) for the
current CodeAgent selection, installed versions and actual results.
Default CI/offline tests skip five real-model cases. A skip is NOT RUN.
An explicitly selected case fails on missing installation, credentials, quota,
timeout or invalid JSON; configuration failures are never converted into a pass.

Use the installed CLI credential store. Do not put tokens in repository files.
The real pilot uses the active frozen benchmark and its integrity checks, one
preselected case per available family/category stratum, plus the independently
bound quote/unit fixture, and B0–B3/M1/A1–A4. It has one repeat and incomplete
runtime coverage. Its descriptive results do not replace the full study. Current
revalidation and source-specific results are in [IMPROVEMENTS.md](IMPROVEMENTS.md).

Manual provider smoke in GitHub Actions requires a configured self-hosted runner
with the selected official CLI and its local authentication. Default checks run
on GitHub-hosted runners and make no model calls.
