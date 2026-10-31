# Verified CI follow-up

Authenticated GitHub Actions inspection found Phase 3–5 passing and Phase 6–9
failing. Phase 6 run 41194486471 failed collecting test_providers.py with
`ModuleNotFoundError: No module named 'httpx'`: CI installed dev but omitted the
declared llm extra. This is a CI configuration defect, not a provider result.

Phase 6 CI now installs `[dev,llm]` and uses verified Node.js 24 actions
checkout 5.0.0 / setup-python 6.0.0. Local branch rerun: **171 passed, 100%
statements/branches**. The correction is propagated forward through feature
branches with ordinary merges, preserving history; main is untouched.

Phase 7 inherited the correction; local rerun **192 passed, 100% coverage**.
Phase 8 additionally installs the official MCP SDK extra, required by its actual
protocol integration tests. Its earlier dev-only workflow omitted that extra.
Phase 8 local rerun: **201 passed, 100% statements/branches**. Phase 6 repaired
remote run 41197661102: **success**, confirmed through authenticated Actions API.

## Final verification

Phase 9 inherited both dependency fixes; its local rerun passed **215 tests,
100% statements/branches**. Phase 10 retained its full hash-locked workflow when
merging the repaired parent history. Only feature branches were merged; all
eight phase branches still form an ancestor chain. Main remains `23a4846`.

Authenticated remote verification (2026-10-31):

| Phase | Verified commit | Actions run | Result |
|---|---|---|---|
| 3 | c207c038 | [41194215386](https://github.com/dennrbone/mcp-compat/actions/runs/41194215386) | PASS |
| 4 | 8bfd3d9b | [41194215348](https://github.com/dennrbone/mcp-compat/actions/runs/41194215348) | PASS |
| 5 | df623c67 | [41194349085](https://github.com/dennrbone/mcp-compat/actions/runs/41194349085) | PASS |
| 6 | 615c09fe | [41197661102](https://github.com/dennrbone/mcp-compat/actions/runs/41197661102) | PASS after fix |
| 7 | 5cdc371d | [41197886071](https://github.com/dennrbone/mcp-compat/actions/runs/41197886071) | PASS after fix |
| 8 | 33405564 | [41197886122](https://github.com/dennrbone/mcp-compat/actions/runs/41197886122) | PASS after fix |
| 9 | 2bbbc2bf | [41198395050](https://github.com/dennrbone/mcp-compat/actions/runs/41198395050) | PASS after fix |
| 10 | c07ab3aa | [41198274481](https://github.com/dennrbone/mcp-compat/actions/runs/41198274481) | PASS |

These are verified code commits; subsequent documentation-only status commits
may have additional runs. Historical failing runs remain visible for audit.
Phase 10 tests and offline-e2e jobs passed; provider-smoke was **skipped**, correctly
remaining NOT RUN. Nothing here claims a real provider/model experiment.
