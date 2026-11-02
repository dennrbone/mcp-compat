# Results status — 2026-11-02

## Confirmed local engineering checks

| Check | Status | Evidence |
|---|---|---|
| Full pytest, Python 3.11.4 | PASS | 294 passed, 5 real-provider skips |
| Statement + branch coverage | PASS | 1749 statements / 648 branches; 100%; no missing coverage |
| Clean wheel install, Python 3.11.4 | PASS | 294 passed, 5 skips; 100% in separate /tmp environment |
| Ruff / mypy | PASS | Source/tests/examples lint; all 21 source modules type checked |
| Packaging | PASS | sdist + wheel built; wheel Python files equal source |
| Workflow YAML | PASS | Parsed and required jobs present; remote execution is a separate check |
| Frozen benchmark replay | PASS | 2160 cases regenerated with identical pinned digest |
| Local official MCP SDK integration | PASS | handshake/discovery/v1/v2/proxy/errors/timeout/disconnect |
| Offline demo / actual diagnostic artifacts | PASS | 45 cases × 9 methods = 405 records, no inference |
| Actual CodeAgent tests | PASS | 5 passed, including positive mapping/B2 and known/unknown MCP bindings |
| Full-corpus runtime audit | PASS | Fake declared-rule client; 1056 correct recoveries, 0 unsafe, 192 unbound recoverable cases |

Historical Phase 10 evidence: `docs/validation/local.json`. Current checks:
`docs/validation/phase15.json` and [IMPROVEMENTS.md](IMPROVEMENTS.md).
Earlier failures remain in [AGENT_TESTS.md](AGENT_TESTS.md) and phase11.json.
Active benchmark: **evobench-1.2**, digest
`ef002e38917804b246bdd0d9a5c104160f89b76a4f15de34499c5dcb2b2ce8de`.
Definitions: `benchmark/definitions/tools.json` (48 distinct old contracts).
Benchmark size and scientific metric definitions are unchanged. Research Spec 1.3
records the date/date-time assertion correction; source fingerprints distinguish
evaluation versions. Frozen data and prior scores are preserved.

## Scientific/provider checks

| Check | Status | Reason |
|---|---|---|
| Current real CLI checks | PASS | installed GigaCode CodeAgent; five opt-in cases |
| Paired real pilot, Phase 14 | COMPLETED | 18 cases × 9 methods; 94/94 mappings parsed; M1 7/10 recoveries |
| M1-only real revalidation, Phase 15 | COMPLETED | Same 18 IDs; 14/14 mappings parsed; 8/10 recoveries, 0/8 unsafe |
| Full real model quality comparison | NOT RUN | Pilot checks do not establish scientific conclusions |
| Two-family primary study and LLM variability | NOT RUN | Requires actual providers and frozen runtime conditions |
| Main CRR/UHR/FBR, confidence intervals and hypothesis tests | NOT RUN | No main results exist |
| H1–H4 / superiority over baseline | NOT TESTED | Unit tests and fake responses cannot establish these |

Default offline suite: no failures or xfails.
The five cases in `tests/test_provider_smoke.py` skip by default because real
inference is explicitly opt-in. A skipped case is NOT RUN. Current real checks
and historical failures are recorded separately in [IMPROVEMENTS.md](IMPROVEMENTS.md)
and [AGENT_TESTS.md](AGENT_TESTS.md).

## Phase acceptance

| Phase | Status | Boundary |
|---|---|---|
| 0 | COMPLETE | Specification read and preserved |
| 1 | COMPLETE | Domain/schema regression gates retained; proven JSON/reference defects fixed |
| 2 | COMPLETE | Conservative diff and 100% coverage retained |
| 3 | COMPLETE | Active 1.2 freeze, diversity/integrity/replay and oracle tests |
| 4 | COMPLETE | B0/B3 and comparable traces |
| 5 | COMPLETE | Strict mapper/provider interfaces and offline safety tests |
| 6 | PARTIAL | CodeAgent protocol/B1/B2 tested; full family study NOT RUN |
| 7 | COMPLETE | Pipeline/gates tested with independently injected trusted runtimes |
| 8 | COMPLETE | Official SDK, isolated local integration |
| 9 | PARTIAL | Runner/metrics/ablations/demo complete; main study NOT RUN |
| 10 | PARTIAL | Analysis/docs/draft complete; scientific results/conclusions pending |

## GitHub Actions and Git

Authenticated GitHub API inspection confirmed initial Phase 3/4/5 CI PASS and
Phase 6/7/8/9 CI FAIL. Phase 6 logs showed missing `httpx`: the workflow omitted
the declared LLM extra. CI repair was propagated through the feature stack, adding
the MCP extra where required. **All Phase 3–10 verified code runs now PASS**;
run ids/commits are recorded in CI_FOLLOWUP.md and `docs/validation/ci.json`.
Phase 10 tests and offline-e2e PASS; provider-smoke is skipped / NOT RUN.
Local PASS is never substituted for a remote Actions result. Phase 11–15 are
locally committed; automatic approval review rejected Phase 11's push because
prior permission covers Phase 3–10 only. Phase 11–15 remote CI remains NOT RUN.

Phase branches are stacked; no merge/rebase/squash into main was performed.
Only ordinary forward propagation of CI fixes between feature branches is used.
Markdown containing prompts/master tasks and .vscode stay local/untracked.
The publication destination is the explicitly authorized existing origin.

## Remaining limits and required resources

- Synthetic functions are simplified, with repeated mutation templates and
  dependence inside tool clusters. Frozen 1.0/1.1 have documented oracle/base
  contract defects and are retired, preserved for audit, and blocked in main runs.
- The current registry supplies 1536 independently authored synthetic bindings
  across 48 tools. Identical-contract ambiguous implementations remain unbound
  (192 recoverable cases). The evaluator oracle is never used as the verifier.
- The final small pilot has two false blocks: a model abstention and an unbound
  ambiguous encoding. It is development evidence, not an untouched holdout;
  service variability is visible between runs and no safety bound is established.
- Trusted preview functions must terminate; elapsed-time checks detect overruns
  after return and do not sandbox arbitrary hostile Python.
- Main studies need pinned model/serving conditions, sufficient free-service
  quota and broader independent runtime bindings. Current authorization covers
  installed GigaCode CodeAgent only; paid inference is excluded.
- Merge into main remains subject to the user's separate permission.

Commands: REPRODUCIBILITY.md. Protocol: EXPERIMENT_PROTOCOL.md. Article structure:
ARTICLE_DRAFT.md. Per-phase changes/checks: PHASE_REPORTS.md.
