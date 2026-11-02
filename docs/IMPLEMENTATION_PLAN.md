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
| B1/B2, CLI providers (CodeAgent) (§17–18) | 6 | providers.py, recovery.py | test_providers.py | documented APIs; mock integration; real opt-in only | COMPLETE для CodeAgent: CLI, mapping и шесть реальных проверок прошли; H3 не исследована |
| M1, independent verification, gate (§10) | 7 | hybrid.py | test_hybrid.py | schema-valid semantic errors blocked; no oracle access | COMPLETE (injected trusted runtimes) |
| MCP SDK proxy (§25,27) | 8 | mcp_integration.py | test_mcp.py | local handshake/discovery/calls/errors/timeout | COMPLETE (local in-memory) |
| Frozen paired runner, metrics, A1–A4 (§19–23) | 9 | experiments.py | test_experiments.py | offline e2e, resumability, undefined denominators explicit | PARTIAL к исходному плану: 19440 решений старого набора и 5760 прикладных получены; несколько семейств не исследованы |
| CI, paired tests, article (§22,24,26) | 10 | analysis.py, docs/ | test_analysis.py | actual-run artifacts, no invented scientific claims | PARTIAL к исходному плану: реальные таблицы, кластерный анализ и рукопись готовы; обобщение H1–H4 не подтверждено |

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


## Дополнения по Research Spec 1.4

| Требование | Фаза | Модуль/артефакт | Проверка | Результат |
|---|---|---|---|---|
| Контроль готовых операций | 17 | declared_rules.py | test_declared_rules.py, 4320 решений | COMPLETE |
| Парный кластерный анализ | 17 | analysis.py | test_analysis.py, группы инструментов/областей | COMPLETE |
| Новый прикладной набор и независимые эталоны | 18 | case_study.py, case_study_runtime.py | test_case_study.py, 192 SDK-сценария | COMPLETE |
| Два условия и три повтора CodeAgent | 18 | publication_case_study.py | 5760 записей, хеши и полные матрицы | COMPLETE |
| Проверка тех же кандидатов и повторяемость | 18 | publication_results.py, replay_candidate_verification.py | три отдельные регрессии, без новых LLM-запросов | COMPLETE |
| Негативный путь D0 | 19 | declared_rules.py | FAIL до, PASS после, 1152 прежних решения совпали | COMPLETE |
| Русская рукопись и первичная литература | 19 | ARTICLE_DRAFT.md, LITERATURE_REVIEW.md | реальные числа, 14 источников, ограничения | COMPLETE в формате авторского черновика |

Стек продолжен через Phase 11–19. `main` не изменена. Текущие подтверждения
и исходные коммиты опыта приведены в RESULTS_STATUS.md и validation/.
