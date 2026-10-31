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
