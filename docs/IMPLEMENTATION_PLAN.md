# Implementation plan — Research Spec 1.1

Baseline: `23a4846`; Phase 2 `8130d00` is an ancestor of main (verified).
Read the complete specification, master task, source and tests before editing.
Research Spec is immutable during this work. No merge into main is authorized.

| Requirement (spec section) | Phase | Module | Verification | Acceptance | Status |
|---|---|---|---|---|---|
| Research definitions, C1–C8, categories (§9–12) | 0 | RESEARCH_SPEC.md | unchanged diff | preserve definitions | COMPLETE |
| Domain, canonical JSON, Draft 2020-12 (§9,30) | 1 | domain/, schema/ | existing unit tests | 100% statements/branches | COMPLETE |
| Conservative structural diff (§10–11) | 2 | diff/ | test_diff.py | 100%, opaque retained | COMPLETE |
| 48 tools, 1920+240 cases, 8 domains (§13–16) | 3 | benchmark.py | test_benchmark.py | diversity, valid calls, deterministic freeze, integrity, isolated oracle | COMPLETE (synthetic scope) |
| B0/B3 (§17) | 4 | recovery.py | test_recovery.py | comparable traces; no semantic guesses | COMPLETE |
| Model-independent mapping (§18) | 5 | llm.py | test_llm.py | strict output, bounded retries, offline injection tests | COMPLETE |
| B1/B2, GigaChat/Qwen (§17–18) | 6 | providers.py, recovery.py | test_providers.py | documented APIs; mock integration; real opt-in only | PARTIAL: engineering complete, real smoke NOT RUN |
| M1, independent verification, gate (§10) | 7 | recovery/, verification/ | test_hybrid.py | schema-valid semantic errors blocked; no oracle access | NOT STARTED |
| MCP SDK proxy (§25,27) | 8 | mcp/ | test_mcp.py | local handshake/discovery/calls/errors/timeout | NOT STARTED |
| Frozen paired runner, metrics, A1–A4 (§19–23) | 9 | experiments/ | test_experiments.py | offline e2e, resumability, undefined denominators explicit | NOT STARTED |
| CI, paired tests, article (§22,24,26) | 10 | analysis/, docs/ | test_analysis.py | actual-run artifacts, no invented scientific claims | NOT STARTED |

## Branch dependencies

Stack (each branch starts at the previous phase's commit):
`main → phase/03-benchmark → phase/04-baselines → phase/05-llm-abstraction
→ phase/06-llm-providers → phase/07-verified-hybrid → phase/08-mcp-integration
→ phase/09-experiments → phase/10-statistics-article`.
Review/PR bases follow the same chain. No rebases, squashes or main merges.

## Cross-cutting acceptance

Run full pytest with statement/branch coverage after every phase, retain 100%
coverage policy, record actual commands/results in PHASE_REPORTS.md. Add offline
lint/types/packaging and a clean installation check. Never hide missing coverage.
Real provider quality, GPU availability, paid APIs and remote CI are independent
checks, never inferred from fake provider tests. No paid calls authorized.

## Initial environment findings

System Python is 3.11.3. Existing .venv points at a deleted temporary Python
3.11.4; restoring the interpreter is necessary before the baseline rerun.
Untracked .vscode/ and CODEX_MASTER_TASKS_03_10.md are user files, excluded from
implementation commits. Git fetch succeeded; local main equals origin/main.
