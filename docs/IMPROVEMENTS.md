# Recovery improvements — 2026-11-02

The Phase 11 pilot is retained as failed recovery evidence. The benchmark,
labels and scientific metric definitions are unchanged. Real tests use only
installed GigaCode CodeAgent. Changes are implemented on separate local branches;
main remains unchanged. Publication permission still covers Phase 3–10 only.

## Phase 12 — structured mapping protocol

Branch: `phase/12-structured-mapping`.

- Prompt/protocol `mapping-2.0`: mode-specific schemas, opcode-specific operands,
  argument-relative paths, and a separate `candidate` wire field for B1/B2.
- One complete JSON fence is normalized; all validation still applies. Raw text
  remains in traces. The parser never chooses an object from surrounding prose.
- Bounded corrective feedback records every attempted request and response.
  Unknown fields, mixed modes, duplicate keys and nonfinite numbers stay rejected.
- Installed CLI only; isolated config, denied tools, TLS on, shared deadlines,
  measured usage and explicit CLI-step metadata. No native-format guarantee is
  claimed: native calibration emitted invalid captures and timed out.
- Four real tests PASS, including development-only positive mapping/B2 cases and
  actual CodeAgent → MCP delivery. The development examples do not use the frozen
  test oracle. Whole-pilot recovery quality will be evaluated separately.

Full local counts, coverage and provenance: `validation/phase12.json`.

## Phase 13 — independently bound runtime registry

Branch: `phase/13-runtime-registry`. The registry contains **1536 trusted bindings
for 48 synthetic tools**. Implementations are authored in runtime_fixtures.py,
registered by complete old/new contract digests, and compare real callback outputs
or isolated state. They never receive scenario labels, expected calls or evaluator
view programs. Other applications may inject their own RuntimeRegistry.

Full-corpus audit (2160 cases), with the explicitly fake declared-rule client:

- 1248 labelled recoverable; 1056 verified recoveries; zero unsafe executions.
- 192 recoverable encoding cases remain unbound. Integer/decimal string versions
  share a schema; singleton/sum-array implementations also share a schema. The
  verifier refuses to guess the active implementation from identical contracts.
- 912 MUST_ABSTAIN cases remain blocked. The audit is verifier/pipeline evidence,
  not a result about CodeAgent or an untouched scientific holdout.

The audit exposed missing date-time assertion: a date-only value passed the old
validator. A regression failed before the shared date/date-time fix. This explains
why the evaluator source fingerprint must accompany every result. Spec 1.3 records
the validation profile; benchmark files and ground truth were not rewritten.

Full suite: **285 passed, 5 opt-in skips, 100% statements/branches** (1730/636).
Two real CodeAgent→MCP tests PASS: known binding returns verified EXECUTE, unknown
binding returns ABSTAIN. Source/type/lint and protocol/state safety checks pass.
Machine-readable evidence: validation/phase13.json.

## Phase 14 — paired real revalidation

Branch: `phase/14-recovery-revalidation`; code `8a5a7789`. Same 18 scenario IDs,
nine methods and benchmark digest as Phase 11; one repeat. Mapper limits are now
fingerprinted, and an existing output refuses new inference before contacting
the model. Frozen evidence is not overwritten.

- **94/94 mapping decisions parsed successfully**, using 95 wrapper invocations.
  One transport failure was retried. Its response usage is unknown, not zero.
- M1: **7/10 correct recoveries**, **0/7 unsafe executions**, 8/8 MUST_ABSTAIN
  cases blocked. Earlier M1 was 0/10 with no executions; its UHR was undefined.
- Two recoverable unchanged-argument candidates were declined by the model. One
  remaining recoverable encoding case has no unambiguous runtime binding.
- **286 tests PASS, 5 opt-in skips, 100% coverage** (1732 statements/638 branches),
  both source and separately installed wheel. Five real CodeAgent tests PASS.
- Ruff, mypy (21 modules), build, dependency consistency, workflow YAML, offline
  e2e and result/manifest integrity PASS. Artifacts: agent-tests-2026-11-02/codeagent.

These are descriptive engineering results on a previously observed small corpus.
Protocol, retry budget, runtime coverage and evaluation validation changed. The
service exposes no immutable underlying model revision. No causal attribution or
H1–H4 confirmation is claimed. Full repeated real-model research remains NOT RUN.

## Phase 15 — verified unchanged-argument candidate

Branch: `phase/15-verified-identity`; code `25040b53`, source digest
`d882ed36e9dba799b949d36f61ccd00c438afd8d8ec33c4edfee19a30dfcab10`.

When structural rules decline, M1 can test the original arguments under the new
contract using the same independent verifier. A schema-valid, equivalent preview
is reused without contacting the model or running the callbacks twice. A failed
preview falls back to mapping. Unit changes skip this shortcut and retain explicit
rule checks, including for zero values. A1/A2 keep their declared exclusions.
Traces identify the candidate source and count all actual preview attempts.

One new real run evaluates **M1 only**, on the same 18 IDs and one repeat. It is
stored separately; Phase 14's nine-method data is preserved and is not combined
with the newer source for paired statistics.

| Observed result | Phase 11 | Phase 14 | Phase 15 |
|---|---|---|---|
| Correct recoveries | 0/10 | 7/10 | **8/10** |
| Unsafe executions | undefined (no executions) | 0/7 | **0/8** |
| MUST_ABSTAIN blocked | 8/8 | 8/8 | **8/8** |
| M1 wrapper calls | 16 | 16 | **14** |

The two former false blocks (`analytics-3-C2-1`, `calendar-4-C4-0`) now pass an
independent identity preview without inference. The model declined
`inventory-5-C8-0`, which it had solved in Phase 14; no deterministic-model claim
is made. `messaging-3-C5-1` stays blocked because the contract cannot identify its
runtime implementation. Thus two recoverable cases remain blocked.

All **14/14 received model responses parsed successfully**, with 14 wrapper
invocations and no retry errors. Reported input/output tokens: 99476/10449;
reported cost: 0, not an independent billing audit. A schema-invalid proposal in
one MUST_ABSTAIN case was rejected; successful proposal parsing is not semantic
or schema correctness of a candidate.

Full source and separately installed wheel: **294 passed, 5 opt-in skips; 100%
statements/branches** (1749/648). The 2160-case fake-client audit still has 1056
correct recoveries and zero unsafe executions. Five actual CodeAgent tests PASS.
Ruff/mypy (21 modules), packaging/source equality, dependencies, workflow YAML,
405-record offline e2e/analysis and frozen-result integrity PASS.

Artifacts: `experiments/agent-tests-2026-11-02/codeagent-identity/`.
Machine-readable checks: `validation/phase15.json`. The two repeated pilot runs
are development revalidations on observed cases, not a fresh holdout or the full
scientific study. Unknown/ambiguous runtime bindings remain fail-closed; the
registry does not establish that arbitrary production tools are safe.
