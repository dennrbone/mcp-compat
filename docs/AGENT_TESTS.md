# GigaCode validation — 2026-11-01

Only the installed GigaCode CodeAgent is used for current real tests. The actual
CLI catalog ID is `gigacode/GigaCode`, version 26.10.76. Its hidden model revision
is unknown. The selected client reports zero token cost.

The strict JSON smoke passed after the harness repeated the mapping instruction
in the final user message. Earlier schema-only/prose/fenced responses failed;
they are not counted as successful checks. Prompt `mapping-1.1` retains strict
JSON validation and records the change.

Confirmed checks on the final GigaCode-only source:

| Check | Result |
| --- | --- |
| Default suite, Python 3.11.4 | 253 passed, 2 opt-in skips |
| Statements / branches | 1524 / 560; 100%, no missing lines or branches |
| Separate installed-wheel suite | 253 passed, 2 skips; 100% |
| Explicit real CodeAgent pytest cases | 2 passed, no skips |
| CodeAgent → project MCP | One actual `compat_check_migration` call completed; input matched the fixture; returned ABSTAIN |
| Ruff / mypy | PASS; 20 source modules |
| sdist / wheel / source equality | PASS; stdio example included in sdist |
| Workflow YAML / dependency consistency | PASS |
| Offline runner + analysis | PASS; 405 fake-provider diagnostic records, no model claim |

Machine-readable coverage and provenance: `docs/validation/phase11.json`.
Real MCP evidence: `experiments/agent-tests-2026-11-01/codeagent/mcp-smoke.json`.

The first pilot was interrupted when the requested client configuration changed;
`experiments/agent-tests-2026-11-01/codeagent-interrupted` contains partial evidence,
not a completed study. The current run uses a new source/config fingerprint at
`experiments/agent-tests-2026-11-01/codeagent`.

Current pilot: IN PROGRESS. Its preselected 18 cases cover all available
family/category strata plus the independently bound quote/unit fixture. Nine
methods (B0–B3, M1, A1–A4), one repeat: 162 planned decisions. M1 runtime coverage
is limited to one contract pair; other pairs abstain. Final results are recorded
only after the runner completes and its integrity checks pass.

The full two-family, 2160-case, repeated scientific study remains NOT RUN.
No superiority claim or H1–H4 conclusion follows from a short integration pilot.
