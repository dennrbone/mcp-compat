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
- Engineering adapter/tests COMPLETE; real provider smoke in the original configuration and model-quality
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
  the full corpus. No fake run is presented as a result about real models.

## Phase 10 — analysis, article and final engineering audit

- `analysis.py`, `test_analysis.py`, opt-in provider smoke, fixed dependency
  lock, Node 24 workflows, experiment protocol, reproduction/status docs and
  article draft with explicit missing-experiment placeholders.
- Hand-checked exact McNemar (.125 for four discordant successes) and Wilcoxon
  (.25 for three distinct positive differences) fixtures PASS. Clustered 95%
  bootstrap, missing pairs/strata, seed stability, integrity and actual tables,
  family/category/ablation summaries and PNG/SVG/LaTeX tests PASS.
- New negative tests exposed nonfinite JSON, optional note oracle loss and
  inconsistent old base contracts. Active **evobench-1.2** fixes these, preserves
  48/1920/240 and retires (without overwriting) old data. Full seeded replay PASS.
- Risk gate checks each unit marker and requires evidence for literal values.
- Final source + separate installed-wheel suites: **233 passed, 2 real-provider
  skips, 100% statements/branches** (1433 statements / 546 branches; missing empty).
  Ruff PASS, mypy PASS (19 modules), sdist/wheel PASS, workflow YAML PASS.
- Actual final offline demo: **405 records** at `experiments/offline-demo-final/`;
  diagnostics at `experiments/analysis-offline-demo/`. One base-tool cluster means
  no bootstrap CI; Wilcoxon remains withheld without confirmed symmetry.
- Remote API inspection found Phase 3–5 PASS, Phase 6–9 FAIL due omitted optional
  dependencies in their historical CI. A separate worktree propagates the fixes
  without changing main or rewriting history. Final runs recorded separately.
- Branch `phase/10-statistics-article`, base initial Phase 9 `c162472`.
- Engineering artifacts COMPLETE; scientific Phase 10 PARTIAL (real study not run).

Final CI follow-up: authenticated API confirms **PASS for Phase 3–10** after
repairing omitted LLM/MCP extras in historical workflows. Feature-only merges
preserve complete stacked ancestry; main stays `23a4846`. Final code run
41198274481 at `c07ab3aa` passed tests and offline-e2e, while provider-smoke was
skipped. Exact commits/runs and initial failures are retained in CI_FOLLOWUP.md
and validation/ci.json. Final installed-wheel gate also passed **233 + 2 skips,
100% statements/branches**. No missing lines or branches; no failing/xfail tests.

## Phase 11 — GigaCode CodeAgent and portable MCP connection

- Branch `phase/11-agent-provider-tests`, based on Phase 10 `e10c7729`.
- Replaced the former transports with installed GigaCode CLI 26.10.76, CodeAgent
  (`gigacode/GigaCode`). Removed retired provider mentions from current files;
  research definitions stay fixed, model-selection amendment is Spec 1.2.
- Kept the generic LLMClient injection, added standard MCP stdio serving and a
  runnable provider-independent decision endpoint. No global agent config edited.
- Full source and installed-wheel gates: **254 passed, 2 opt-in skips; 100%
  statements/branches** (1525 / 560). Ruff PASS; mypy PASS (20 modules); dependency
  consistency, sdist/wheel/source equality, workflow YAML and offline e2e PASS.
- Actual CodeAgent checks: **2 real pytest cases PASS**, including the agent
  invoking our MCP tool. Earlier non-JSON output failed; prompt/harness changes
  are explicit (`mapping-1.1`). No fenced response is silently accepted.
- Stratified real pilot COMPLETED: 18 cases, 162 decisions, 94 wrapper calls.
  **79 replies failed strict parsing; M1 abstained in all 18 cases**. Integration
  checks passing does not establish recovery effectiveness. Details and observed
  rates are in AGENT_TESTS.md. Main repeated two-family study remains NOT RUN.
- Actual artifact inspection exposed trailing N/A labels outside plot limits.
  Regression initially FAIL; bounded axes fix and final rendering/tests PASS.
- Code commits: `d1752b0f` (pilot implementation), `6a60e0ee` (plot fix).
  Push rejected by automatic approval review: prior authorization covers Phase
  3–10 only. Phase 11 remote CI NOT RUN pending explicit publication approval.
- Task/prompt Markdown remains local/untracked. No merge into main.

## Phase 12 — validated model protocol

- Branch `phase/12-structured-mapping`; previous Phase 11 evidence preserved.
- Protocol mapping-2.0 has purpose-specific schemas and valid opcode operands,
  relative argument paths and a separate baseline candidate wire object. One
  complete JSON fence is normalized while all schema/domain checks stay active.
- Retry feedback is bounded, preserves raw responses, and records each request.
- Native structured capture was calibrated but not adopted: invalid captures and
  timeouts were observed. The installed CLI plus independent parser is retained.
- Full suite: **266 passed, 4 opt-in skips; 100% statements/branches** (1572/574).
  Ruff, mypy (20 modules) and dependency consistency PASS.
- **4 real CodeAgent tests PASS**, including positive mapping and B2 development
  transformations, strict smoke and actual MCP delivery. This is protocol
  evidence, not a whole-benchmark effectiveness claim. See IMPROVEMENTS.md.
- Main unchanged; no feature publication or scientific conclusion claimed.

## Phase 13 — runtime registry and evaluation validation

- Branch `phase/13-runtime-registry`; 1536 digest-bound synthetic runtime pairs,
  48 tools, separate implementations and isolated state. Evaluator functions
  are forbidden during verifier execution; unknown/colliding implementations
  remain unbound. Application-supplied registries are supported.
- Full 2160-case audit with a declared-rule fake client: 1056 correct recoveries,
  0 unsafe executions; 192 recoverable ambiguous encodings remain unsupported,
  912 MUST_ABSTAIN cases blocked. This is not a model experiment.
- Corrected missing date-time validation after a failing regression. Spec 1.3
  records the validation profile; frozen benchmark data/labels unchanged.
- **285 passed, 5 opt-in skips; 100% statements/branches** (1730/636). Ruff PASS;
  mypy PASS (21 modules). **2 actual CodeAgent→MCP tests PASS**, including positive
  verified recovery and unknown-binding abstention.
- See IMPROVEMENTS.md and validation/phase13.json. Main unchanged; no push.

## Phase 14 — real revalidation

- Branch `phase/14-recovery-revalidation`, code `8a5a7789`; prior data preserved.
- Same paired 18 cases × 9 methods = 162 decisions: **94/94 mappings parsed**,
  95 invocations including one retried transport failure. Unknown usage remains
  null. M1: **7/10 recoveries; 0/7 unsafe executions; 8/8 required abstentions**.
- **286 passed, 5 opt-in skips, 100% statements/branches** (1732/638), source and
  installed wheel. **5 actual CodeAgent tests PASS**. Lint/types/build/dependency
  checks, YAML, offline e2e and real-result integrity PASS.
- Detailed evidence: validation/phase14.json and IMPROVEMENTS.md. No scientific
  superiority claim; main unchanged; remote CI unavailable without publication.

## Phase 15 — independently verified identity candidate

- Branch `phase/15-verified-identity`, code `25040b53`. Schema-valid unchanged
  arguments may pass the independent verifier before model mapping. Failed
  previews fall back; unit rules and ablation exclusions remain active. All
  preview attempts are counted; passing previews are reused once.
- M1-only real revalidation, same 18 IDs: **8/10 correct recoveries, 0/8 unsafe
  executions, 8/8 required abstentions**. All **14/14 model replies parsed**;
  14 invocations, no retry errors. Two earlier false blocks now pass without
  inference; one previously solved unit case was declined by the service.
- **294 passed, 5 opt-in skips; 100% statements/branches** (1749/648), source
  and clean wheel. **5 actual CodeAgent tests PASS**. Lint/types/build/package
  equality/dependencies/YAML, offline e2e/analysis and result integrity PASS.
- Prior paired data preserved; different-source runs are not pooled. Full
  scientific study remains NOT RUN. See IMPROVEMENTS.md and phase15.json.
- Main unchanged; Phase 11–15 branches remain local, task/prompt Markdown untracked.

## Phase 16 — full CodeAgent benchmark

- Branch `phase/16-full-codeagent-benchmark`; frozen experiment code `7fc2627e`.
- Added `--full`, bounded workers (1–8) and CLI resume using the existing runner,
  mapper and actual installed CodeAgent. Completed records are saved atomically;
  resume preserves them and checks the source/configuration fingerprint.
- Source and clean-wheel gates: **300 passed, 5 opt-in skips; 100% statements
  and branches** (1787/662). A deterministic small-batch regression removes a
  timing-dependent coverage gap observed in the initial clean-wheel gate.
- Full benchmark **COMPLETED**: 2160 scenarios × nine methods = 19440 decisions,
  one repeat, eight workers. All result hashes, the complete paired matrix,
  dataset labels, source fingerprint and regenerated summaries verified PASS.
- M1: **1001/1248 correct recoveries (80.2%), 0/1001 unsafe executions,
  912/912 required abstentions**. Its 247 false blocks include all 192 ambiguous
  runtime signatures; supported-only recovery is 1001/1056 (94.8%), a diagnostic
  subset rather than a replacement for the primary denominator.
- Recorded 11731 wrapper invocations; 10303/10896 mapping decisions parsed.
  593 ended without a usable parsed proposal. ProviderError dominates attempted
  errors; missing usage stays unknown. No failed case was replaced or omitted.
- Finished 2026-11-02 23:37:43 Asia/Omsk; observed wall time about 10 h 27 min.
  Raw evidence: `experiments/full-codeagent-2026-11-02/`. This is a complete
  single-model, single-repeat benchmark; the planned repeated study remains open.
- See IMPROVEMENTS.md and validation/phase16.json. Main unchanged; no push or
  remote CI. Removed background helper code was not part of this experiment.


## Phase 17 — контроль источника правил и кластерная статистика

- Ветка `phase/17-publication-methodology`, код эксперимента `65d8c760`.
- Исходные 19440 решений сохранены. Дополнительно получены 4320 настоящих
  детерминированных решений D0/D1 на тех же 2160 случаях, без вызовов модели.
- D0: CRR 1248/1248, UHR 528/1776; D1: CRR 1056/1248 (84,6%), UHR 0/1056,
  обязательный отказ 912/912. M1 уступил D1 на 55 случаев, или 4,41 п.п.
- Парный кластерный bootstrap по 48 инструментам: 95% ДИ разности M1−D1
  от −5,85 до −3,13 п.п. Перестановка знака целого кластера: p=0,0001;
  чувствительность по восьми областям: p=0,0078125. Обменность меток методов
  внутри кластера — допущение теста; анализ добавлен после исходного прогона.
- При готовых точных операциях модель не улучшила восстановление. Это
  ограничивает научный вывод и прямо учитывается в статье.
- Полные проверки исходников и отдельно установленного wheel: **311 passed,
  5 opt-in skipped; 100% строк и ветвей** (1874 / 688). Ruff, mypy, сборка и
  согласованность зависимостей прошли. Новых запросов CodeAgent в этой фазе нет.
- Совпадение общих модулей с Phase 16 подтверждено в `shared-core-proof.json`;
  сравнение задержки последовательного контроля с восемью CLI workers исключено.
- Phase 11–16 успешно отправлены в origin; все шесть удалённых CI прошли.
  `main` не изменена. Файлы Markdown с промптами не отправлены.

## Phase 18 — независимая прикладная проверка, запуск продолжается

- Ветка `phase/18-independent-case-study`, заморозка кода и данных `fda30006`.
- 12 новых локальных API, шесть областей, 192 сценария, 96 однозначных пар
  обработчиков. Эталоны заданы отдельно вручную. Эти приложения независимы
  от старого генератора, но подготовлены тем же автором и не являются
  внешней слепой репликацией.
- Два замороженных условия доступности правил, пять методов и три повтора:
  5760 запланированных решений. Код/данные отправлены в origin до просмотра
  результатов. Source digest: `ccd2591e512801b45a81d0a1c426c802a5b380ec680ae03c13c2fd31efd24397`.
- Предварительные полные проверки исходников и отдельного wheel: **315 passed,
  5 opt-in skipped; 100% строк и ветвей** (2064 / 784). Ruff/mypy, зависимости,
  сборка, совпадение wheel с исходниками прошли.
- Все 192 случая прошли через официальный MCP SDK и proxy без модели;
  правильное поведение и отсутствие исполнения при отказе проверены.
- Удалённый CI для `fda30006` прошёл: Actions 41511930652. CI Phase 17
  `48bb2707` также прошёл: 41511178264. Это не модельные тесты в Actions.
- Реальный CodeAgent запущен по зафиксированному протоколу, но итоговые
  результаты пока не проверены: **RUNNING / NOT YET VALIDATED**.


Контрольная точка Phase 18: после 1118 сохранённых решений появился сетевой
HTTP 503 и повторяющиеся ProviderError. Запросы остановлены, байтовые хеши
записаны; незаписанное использование запросов в работе остаётся неизвестным.
Пользователь восстановил соединение. GitHub HTTP 200, отдельная проба CodeAgent
PASS и совпадение 1118 хешей подтверждены перед продолжением. Код и параметры
сохранились. Ошибочные завершённые решения не заменяются. Это описание
прерывания, а не итоговая оценка качества нового опыта.
