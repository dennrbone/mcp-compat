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
