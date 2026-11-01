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
| Default suite, Python 3.11.4 | 254 passed, 2 opt-in skips |
| Statements / branches | 1525 / 560; 100%, no missing lines or branches |
| Separate installed-wheel suite | 254 passed, 2 skips; 100% |
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

Current pilot: **COMPLETED**, with **162 decisions** over **18 cases**, 16 base
tools and all eight mutation families. Selection covered every available
family/category stratum plus the bound quote/unit fixture before scores were
viewed. Nine methods, one repeat. The runner recorded **94 wrapper calls**,
575769 input tokens and 56330 output tokens; reported cost 0 (not a billing audit).
Preflight/MCP smokes and the interrupted run are separate from these totals.

**Recovery effectiveness is not established.** Of 94 mapping invocations,
**79 failed strict proposal parsing**: 61 JSONDecodeError, 12 ValidationError,
6 ValueError. Common outputs included Markdown fences or an incorrect proposal
shape. They were rejected, not repaired or called successes. M1 executed **zero**
calls and abstained on all 18 cases: CRR 0/10, FBR 10/10, UHR undefined because
there were no executions. Runtime verification is bound to only one contract
pair. These limitations prevent a claim about the intended method's effectiveness.

Descriptive observed rates (numerator/denominator):

| Method | CRR | UHR | FBR |
| --- | --- | --- | --- |
| B0 | 3/10 | 5/8 | 5/10 |
| B1 | 3/10 | 5/8 | 5/10 |
| B2 | 2/10 | 1/3 | 8/10 |
| B3 | 2/10 | 0/2 | 8/10 |
| M1 | 0/10 | undefined (0 executions) | 10/10 |
| A1 | 2/10 | 0/2 | 8/10 |
| A2 | 0/10 | undefined (0 executions) | 10/10 |
| A3 | 0/10 | undefined (0 executions) | 10/10 |
| A4 | 2/10 | 1/3 | 8/10 |

Full responses, decisions and integrity digests are under `codeagent/pilot/`.
`codeagent/analysis/` contains actual CSV/LaTeX/PNG/SVG output. Its statistics are
diagnostic on this small, one-repeat pilot; Wilcoxon remains withheld without
confirmed symmetry. No significance or superiority claim is made.

The pilot source fingerprint resolves to engineering commit `d1752b0f`; rendering
corrections after that run do not change its decisions or immutable data manifest.

The full two-family, 2160-case, repeated scientific study remains NOT RUN.
No superiority claim or H1–H4 conclusion follows from a short integration pilot.

The plot's trailing undefined-rate annotation originally fell outside its axes.
A regression test failed before a one-line axis-limit fix; final PNG inspection
and source/wheel test gates passed. Pilot decisions and hashes were preserved.

Phase 11 push was rejected by automatic approval review because previous origin
authorization covers Phase 3–10 only. Remote Phase 11 CI: NOT RUN. No merge into
main was performed. Current commits and results are available locally for review.
