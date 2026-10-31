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
