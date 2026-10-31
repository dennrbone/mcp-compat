# Implementation notes

## Phase 1 and Research Spec 1.1

Phase 1 deferred `MigrationDecision` because the original spec named it without
fields or invariants. Spec 1.1 section 10.1 now defines it; Phase 2 implements
that model without consuming benchmark oracle data or making decisions.
The former version mismatch is resolved: main at `6a8f3a3` includes both Phase 1
and the user's Research Spec 1.1 update. The complete specification was read
before implementation. Research definitions, C1–C8, metrics and benchmark design
are unchanged.

## Phase 2 public API and serialization

`SchemaDiffEngine.compare(old_contract, new_contract) -> SchemaDiff` compares
versions of one scenario. It never builds an adapter or decides EXECUTE/ABSTAIN.
`ContractChange` carries family, subtype, path, old/new values and details.
`SchemaDiff.opaque` contains typed `OpaqueChange` records (path, reason, old/new
values) for unsupported or uninterpreted constructs; these are not assigned
invented C1–C8 classifications. `is_complete` is false whenever opaque is nonempty.
`has_changes` means classified changes or different opaque values; an identical
unsupported schema can therefore have `has_changes=False, is_complete=False`.
Consumers must check completeness separately. Added/removed properties carry
the entire resolved subtree, without claiming to interpret its internals.

All models support Pydantic JSON round trips. Use
`canonical_bytes(diff.model_dump(mode="json"))` for deterministic output.
Comparisons copy values and do not mutate contracts. Changes sort by
`(family, path, subtype)`; opaque records sort by `(path, reason)`.
Type strings become sorted type lists, required lists are sorted, and enum
lists sort by canonical JSON. Enum comparison preserves JSON boolean/number
identity. Numeric lexical equivalence such as `1` versus `1.0` is not normalized;
this is a structural diff, not a general JSON Schema equivalence prover.

Paths start with `input`, `output`, `name`, `description` or `metadata`.
Identifier segments use dots: `input.properties.quantity`. Other segments use
JSON-quoted brackets: `input.properties["a.b"]`. Array element schemas use
`.items`; required membership uses `.required.<name>`. These are schema paths,
not instance paths or JSON Pointers. Rename details include `new_path`.

## C1–C8 conventions and limits

- C1: direct tool rename, since the caller supplies versions of one scenario.
  Parameter rename requires the same local `$ref`, unique among all siblings on
  each side, an unchanged resolved schema and unchanged required membership.
  This is reference identity evidence only, not proof of equivalent behavior.
  Identical inline schemas, matching descriptions and similar names never
  establish identity. Changed or ambiguous references yield add/remove events.
- C2: optional property added/removed.
- C3: required property added and required membership changed in either direction.
- C4: required property removed, without a duplicate C2 removal.
- C5: primitive/array type, explicit nullable union and format changes.
- C6: enum expansion, contraction, replacement or enum constraint added/removed.
  No enum value rename inference.
- C7: a type change involving object is structural (including object/array).
  Nesting and flattening use primitive property add/remove events; no cross-path
  move correspondence is asserted. Nested properties and array items recurse.
- C8: only changes to the explicit `semantic_unit` key in `ToolContract.metadata`
  or at a compared schema node. Benchmark producers should use unit strings,
  e.g. `RUB` and `kopecks`. Presence changes are reported as marker changes;
  null represents an absent marker. This reports evidence, not a conversion
  factor, a safe adaptation, or a decision. Other metadata remains opaque.

## Local reference resolution

The isolated resolver accepts acyclic `#/$defs/...` references within the current
input/output schema document, including nested pointer segments and JSON Pointer
`~0`/`~1` escapes. It traverses properties and items, follows reference chains and
compares resolved schemas at use sites. Unused definitions are intentionally
ignored: changes to an unreferenced definition do not alter the compared schema
at any use site. Definition-only rewrites with identical resolved schemas also
produce no event.

No external fetching occurs. External/anchor/recursive references, missing or
non-schema targets, `$id` resource scopes and `$ref` siblings (except `$defs`)
produce an opaque record for the affected input/output document. Percent-encoded
pointer fragments are not decoded; missing literal targets are opaque.
Combinators (`oneOf`, `anyOf`, `allOf`, etc.), conditional/dependent schemas,
additional/pattern properties, numeric/string constraints and other unhandled
keywords remain opaque, even when unchanged. Boolean schemas compare identically
without events; changes involving them are opaque. Annotation/dialect changes,
unknown metadata and output schema presence changes are opaque. This intentionally
small resolver is not a universal JSON Schema resolver.

## Ambiguities and deferred semantic work

The spec does not define structural evidence for parameter identity. The narrow
reference-identity rule above is an implementation convention; it adds no new
scientific equivalence criterion. Cross-object moves, semantic renames such as
`quantity -> amount`, enum rename/merge/split, unit conversions, split/merge of
parameters and side-effect interpretation are deferred to the Semantic Mapper.

C4 mentions previously used fields, but compare receives no ToolCall and cannot
know which optional fields were used. The explicit Phase 2 rule therefore assigns
optional removal to C2 and required removal to C4. Required-to-optional is C3 as
explicitly requested, though the spec's C3 subtype list names only the opposite
direction. The remaining “v1.0” wording in section 10.1 is a version-label
inconsistency; the v1.1 header and defined EXECUTE/ABSTAIN invariants are used.
No scientific interpretation has been added for these ambiguities.

Semantic matching, adapter generation, benchmark generation, MCP transport and
LLM integration are not implemented. No dependencies or Hypothesis were added.
Tests are offline; Python installation and Git operations may require network.

## Phase 3 conventions

`RecoveryInput` is a separate strict boundary model. Only old/new contracts,
old call and `metadata.public_context` reach strategies; labels, ids, expected
calls and oracle programs do not. Public mutation rules are explicit knowledge
provided by the synthetic environment. They are untrusted proposals until a
separate runtime verifier validates them. Evaluator views are private decoders,
not runtime verification inputs. Missing defaults are constants only in the
simulated implementation, never guessed by recovery.

The corpus includes all three categories; recoverability means a safe solution
exists with the allowed context. `MUST_ABSTAIN` expresses insufficient permitted
information, even if a lucky guess happens to match a hidden implementation.
Five C8 mutations combine with tool rename for each base tool (240 composed).
The synthetic tools share an interpreter with domain-specific pure calculations
(quotes, capacities, durations, text counts, quotas, prices, aggregates, taxes)
and record creation/update/removal plus event logs for side effects. Canonical
intent is retained alongside computed outputs to make lost user intent visible.
These are simplified business models, not production implementations. Mutation
patterns repeat across tool clusters; analysis must not claim 2160 independent
business tasks merely from the corpus size.

Frozen datasets use exclusive creation plus per-file SHA-256 and a pinned
manifest digest supplied by the caller. Hashes detect corruption, not a trusted
signature. Regenerate into a new directory; never edit a frozen dataset.

## Phase 4

B0 attempts the original name and arguments against the new contract, preserving
the failed candidate and error in evidence. B3 changes only the supplied tool
name, accepts optional additions, enum expansion/contraction (subject to actual
validation), and optional→required when the call already supplies the value.
It refuses removals, value conversions, field renames, units and opaque schemas.
All strategies return MigrationDecision with stable reasons and machine-readable
candidate/schema evidence. Baseline execution does not assert semantic proof.

Regression tests exposed two Phase 1 validation defects before fixing them:
jsonschema's default registry could retrieve external references, and cyclic
references escaped as RecursionError. Validation now uses a non-fetching registry
and wraps unresolved/cyclic references as domain errors. No resolver expansion
or change to structural opaque behavior was made.

## Phase 5

`SemanticMapper`/`LLMClient` protocols are injected; Mapper uses versioned prompts
in Python source (no prompt Markdown is committed). Tool names/descriptions,
errors and context are JSON data under a fixed system instruction. This limits
instruction confusion but does not claim that prompt wording defeats injection;
typed proposals, independent validation and runtime verification are required.
Strict JSON rejects extra/duplicate keys, code fields, non-finite numbers and
unbounded operations. The six-opcode language cannot execute Python. Retries
are limited to three attempts under a shared deadline; transport implementations
must honor each supplied timeout. Errors retain type only, not credential text.
Offline fake tests prove protocol/safety behavior, not real model quality.

User explicitly approved pushes to origin, then excluded Markdown prompts.
Phase 3/4 were audited and pushed successfully; master-task Markdown remains
untracked. Documentation contains design/results, not model prompt text.

## Phase 7 — verification and benchmark correction

The adapter evaluates six typed opcodes, reading only original arguments;
overlapping targets, dependencies/cycles and invalid conversions fail closed.
M1 records diff, candidates, mapping, adapter, schema validation, verification
and gate reasons. An opaque diff always abstains. C8 additionally requires an
explicit matching public scale rule and a recognized exact integer unit factor.
Missing/negative verifier evidence, mapping errors and ambiguity never execute.

SandboxVerifier binds independently supplied trusted implementations to both
contract digests. It compares normalized pure results or isolated final states
from equivalent initial states. It has no EvolutionScenario/oracle argument.
An outcome match concerns this call, not a universal equivalence proof. Preview
callbacks must be trusted local bounded operations: elapsed-time checks detect
overruns after return, not preempt arbitrary Python code. Remote/hostile callbacks
are outside this implementation's trust boundary.

A1 skips verification (but retains unit/risk rules); A2 bypasses structural
candidate reuse; A3 forbids the mapper; A4 removes final evidence/risk gating.
These intentionally weakened methods are research ablations, not safe defaults.

A new hand-checked test demonstrated an oracle bug: a changed required `region`
was ignored in evobench-1.0. New required context and ambiguous `source` are now
semantically observable. The old frozen dataset is preserved, not overwritten;
generator evobench-1.1 is a new freeze of the same 48/1920/240 design. Version 1.0
is retired and must not be used in scientific experiments. No scientific/model
experiment preceded this correction. No settings were tuned to oracle scores.

## Phase 9 — metrics and reproducibility conventions

Runner uses exactly one pinned frozen dataset and identical selected ids for
all methods/repeats. Manifest records UTC start time, source digest, Python and
dependency versions, seed, sample ids, prompt version, model identifiers and
generation settings. The supported generation configuration is fixed at
temperature 0 / 2048 maximum output tokens, matching actual transports; other
parameters are rejected rather than merely logged without applying them.
Seed concerns dataset generation/selection; deterministic model inference is
not asserted. Per-case pacing and bounded mapper retry/backoff limit requests.

Results use atomically replaced per-case JSON files. Interrupted runs retain
completed cases; resumes reject configuration/identity mismatch and validate
record keys and completed-result hashes. Existing results are never silently
rerun after deletion/corruption. A source change requires a new run directory.
Source manifests fingerprint package implementation, not external custom
callbacks; external runtime/model serving versions must be pinned by operators.

Research Spec gives formulas for CRR/UHR/FBR but describes the other denominator
choices in prose. Conventions: Abstention Accuracy denominator is MUST_ABSTAIN;
Schema Validity denominator is final proposed candidates (B0 includes its raw
attempt), excluding decisions with no candidate; Semantic Equivalence denominator
is EXECUTE decisions. A schema-invalid EXECUTE is unsafe. Recoverable CONDITIONAL
cases count with SAFE_AUTO in CRR/FBR, per explicit scenario recoverability.
Rates expose numerator/denominator, with null for zero denominator. Missing
provider usage/cost is null, not zero; zero calls have known zero token/cost use.
Unexpected strategy errors mark operational use unknown. Family/category empty
strata remain explicit. Repeats count attempts and are paired by (id, repeat).

Offline demo uses an explicitly named fake provider, public rules and a single
independently authored commerce quote/unit runtime binding. Other M1 runtime
pairs are unbound and abstain. No oracle is injected into recovery. This is an
engineering exercise, not a benchmark of model quality. Full main runs require
real model versions and separately supplied trusted runtime bindings. Two-provider
variability experiments are NOT RUN, and cannot be inferred from this demo.
