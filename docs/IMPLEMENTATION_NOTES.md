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
