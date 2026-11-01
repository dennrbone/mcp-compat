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
