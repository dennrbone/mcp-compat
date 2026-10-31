# Phase reports

All local tests use Python 3.11.4. PASS applies only to the recorded checks.
No paid requests or main merges are authorized. CI is separate from local tests.

## Baseline / Phase 0–2

- Branch baseline: `main`, `23a4846`; fetched origin agrees.
- Phase 2 ancestor check: PASS (`8130d00`).
- Full existing suite: **79 passed**, **100% statements and branches**.
- Command: `.venv/bin/python -m pytest -q --cov=mcp_compat --cov-branch --cov-report=term-missing --cov-fail-under=100`.
- Restored deleted temporary interpreter; system Python 3.11.3 was not used.

## Phase 3 — benchmark

- `benchmark.py`, `test_benchmark.py`, plan, packaging/development configuration.
- 48 named tools, 8 domains, 40 mutation subtypes, 1920 base + 240 composed.
- RecoveryInput excludes evaluation labels/oracle; mutation rules are explicit
  public simulator metadata, not proof of safe execution.
- Full suite before property checks: **92 passed; 100% statements/branches**.
- Final checks and frozen digest recorded below when executed.
- Tools share an interpreter, with domain-specific pure calculations and
  create/update/remove state transitions. They are deliberately simplified
  business models. The 40 mutation patterns are reused across 48 tool clusters;
  no empirical independence claim is made.
- No model quality or external system was tested.

Final Phase 3 gate: **94 passed, 100% statements/branches**, no missing lines or
branches; Ruff PASS; mypy PASS (12 modules). Hypothesis seed/mutation tests PASS.
Frozen data: `benchmark/scenarios/evobench-1.0/`, seed 42, digest
`f34cacc1ebaf53fb6313bb61ee496192575e5e37c0d1d46efc231a52c7b8458c`.
Development provisional datasets were moved to /tmp before the final freeze;
no experiment was run against them. Phase 3 COMPLETE (synthetic scope).

## Phase 4 — B0/B3

- `recovery.py`, `test_recovery.py`, validator/call regression fixes and tests.
- Pre-fix regression: 2 FAIL (external reference retrieval; recursion escape).
- Final full suite: **118 passed; 100% statements/branches**, no missing lines
  or branches. Ruff PASS; mypy PASS (13 modules).
- B3 is intentionally conservative; candidate schema validity is separate from
  semantic equivalence. No implicit rename/enum/unit/side-effect inference.
- Branch `phase/04-baselines`, depends on Phase 3 `c207c03`.
- Phase 3 push BLOCKED by automatic approval review (destination authorization);
  publication approval pending, local work continues. Phase 4 COMPLETE.

Publication update: user explicitly authorized this origin; prompt Markdown audit
PASS. Phase 3/4 push PASS. Master task and .vscode remain untracked.

## Phase 5 — model abstraction

- `llm.py`, `test_llm.py`: strict proposals/opcodes, injected provider, versioned
  source-code prompt, duplicate/nonfinite/extra-key rejection, limits/deadlines,
  bounded retry/backoff, stable failure traces and malicious-description tests.
- **149 passed; 100% statements/branches**, no missing lines/branches.
- Ruff PASS; mypy PASS (14 modules). Entire suite offline.
- Branch `phase/05-llm-abstraction`, base Phase 4 `8bfd3d9`.
- Fake responses test the interface only. Model quality: NOT RUN.
- Phase 5 COMPLETE. Next: provider transports and B1/B2.

## Phase 6 — providers and B1/B2

- `providers.py`, B1/B2 in `recovery.py`, mock transport/integration tests,
  `PROVIDERS.md`, optional pinned httpx transport dependency.
- **171 passed; 100% statements/branches**, no missing lines/branches;
  Ruff PASS; mypy PASS (15 modules).
- Official API/deployment documentation checked; versions/credentials are
  explicit configuration. Redirects blocked; credential-bearing errors sanitized.
- Branch `phase/06-llm-providers`, base Phase 5 `df623c6`; Phase 5 push PASS.
- Engineering adapter/tests COMPLETE; real GigaChat/Qwen smoke and model-quality
  experiment **NOT RUN** (no credentials/weights/paid authorization). Phase 6
  overall **PARTIAL**; this does not block independent offline phases.

## Phase 7 — Verified Hybrid

- `hybrid.py`, `test_hybrid.py`, operation serialization round-trip regression.
- Independent runtime binding; finite normalized outputs; isolated state;
  unit rules; controlled adapter; A1–A4; fail-closed complete stage traces.
- Oracle regression initially FAIL (region ignored); generator correction
  creates **evobench-1.1**, preserving retired 1.0. Main/model experiments NOT RUN.
- Full suite **192 passed; 100% statements/branches**, no missing lines/branches;
  Ruff PASS; mypy PASS (16 modules).
- Branch `phase/07-verified-hybrid`, base Phase 6 `6b92869`; Phase 6 push PASS.
- Phase 7 COMPLETE for injected trusted runtimes. Absent runtime bindings cause
  abstention; benchmark evaluator is never substituted for runtime verification.

## Phase 8 — official MCP integration

- `mcp_integration.py`, `test_mcp.py`, `MCP_INTEGRATION.md`; SDK **1.30.0**.
- 9 actual in-memory MCP integration tests PASS: handshake, discovery, schemas,
  v1/v2, proxy adaptation/abstention, invalid payloads/output, server failures,
  timeout and disconnect. No external services or user data.
- Full suite **201 passed; 100% statements/branches**, no missing lines/branches;
  Ruff PASS; mypy PASS (17 modules).
- Branch `phase/08-mcp-integration`, base Phase 7 `abfcc50`; Phase 7 push PASS.
- Phase 8 COMPLETE for isolated local transport; production deployment excluded.

## Phase 9 — runner and offline demo

- `experiments.py`, `test_experiments.py`, console entry point, actual demo
  artifacts in `experiments/offline-demo/` (45 frozen cases × 9 methods = **405**
  records). This run uses **no real inference** and is not a scientific study.
- B0/B1/B2/B3/M1 and A1–A4 use identical ids and dataset digest. One manually
  authored runtime pair demonstrates positive M1 verification without oracle access.
- Resume, interruption, corruption, selection, missing usage, metric formulas,
  empty strata, pacing and e2e demo tests PASS.
- Full suite **215 passed; 100% statements/branches**, no missing lines/branches;
  Ruff PASS; mypy PASS (18 modules).
- Branch `phase/09-experiments`, base Phase 8 `f66141e`; Phase 8 push PASS.
- Engineering COMPLETE. Main two-provider study/repeated real inference NOT RUN;
  phase overall PARTIAL pending resources and independently bound runtimes for
  the full corpus. No fake run is presented as a result about GigaChat or Qwen.
