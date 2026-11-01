# Experiment protocol — Research Spec 1.1

Status: engineering implementation and offline demo only. H1–H4 are **NOT
TESTED**. Nothing in this document establishes a benefit of the selected real models or M1.
The Research Spec, definitions, categories, C1–C8 and metric formulas are unchanged.

## Frozen inputs

Active generator/dataset version: **evobench-1.2**, seed **42**. Digest:
`ef002e38917804b246bdd0d9a5c104160f89b76a4f15de34499c5dcb2b2ce8de`.
48 distinct old ToolContracts across 8 domains; 1920 base mutations (40 subtypes)
and 240 C1+C8 composed cases. The 40 mutation patterns repeat across tool clusters;
2160 cases are not 2160 independent business applications. The models are small
synthetic calculations and state transitions, not real payments/messages/bookings.
Retired 1.0/1.1 freezes are historical engineering artifacts, excluded from main
runs. Corrections changed dataset version; no frozen files were overwritten.

The data plane consists of old/new contracts, old call and allowlisted public
context. Ground truth, recoverability, ids and oracle programs are evaluator-only.
Public rules are explicit synthetic environment knowledge, not inferred truth.
Runtime verification binds independently authored implementations to contract
digests. An unavailable runtime always causes M1 abstention; the benchmark oracle
is never supplied in its place. The shipped demo binds one quote/unit pair.

## Planned main study — NOT RUN

1. Record exact CodeAgent model identifiers, CLI versions, provider revisions when exposed,
   quantization, hardware, endpoint identity and authorized budget. Model aliases
   alone are insufficient version evidence. Credentials remain outside manifests.
2. Freeze independent runtime bindings and mapper/provider configuration before
   examining test-oracle scores. Additional runtime coverage is an explicit
   experimental condition, not an oracle shortcut. Missing bindings stay visible.
3. Use all 2160 identical ids for B0/B1/B2/B3/M1 and A1–A4. Run each LLM family
   separately with the same dataset, sample selection and prompt version.
4. Use temperature 0 and 2048 maximum output tokens (the implemented fixed
   transport configuration). Save 3 repetitions for inference variability; seed
   42 selects data, and does not promise deterministic provider inference.
5. A smaller variability subset, if needed for budget, is selected by seed and
   stratified by family/category/domain before results are viewed; its exact ids
   and repetitions go in RunConfig. It is reported separately from the main run.
6. Save every decision, proposed candidate, response, adapter, validation,
   evaluator outcome, duration and provider usage. A source/config change creates
   a new run directory. Interrupted cases resume without replacing completed data.
7. Do not tune prompts/rules on frozen test-oracle scores. Any later benchmark
   correction gets a new version, with the previous run retained and retired.

No full main study or paid request has been performed. Current real CLI smoke
and pilot evidence is recorded in AGENT_TESTS.md. Provider versions/quotas and
broader independent runtime bindings still limit the full comparison. Git push
authorization does not authorize inference charges.

## Metrics and denominators

All rates include numerator and denominator. Zero denominators produce JSON null.

| Metric | Numerator | Denominator |
|---|---|---|
| CRR | recoverable EXECUTE with equivalent outcome | recoverable scenarios |
| UHR | EXECUTE with non-equivalent outcome (including invalid calls) | all EXECUTE decisions |
| FBR | recoverable ABSTAIN | recoverable scenarios |
| Abstention Accuracy | MUST_ABSTAIN correctly blocked | MUST_ABSTAIN scenarios |
| Schema Validity | schema-valid final candidates | final proposed candidates |
| Semantic Equivalence | equivalent executed calls | all executed calls |

Final candidates include B0's unchanged attempt, but exclude decisions without a
candidate. CONDITIONAL counts according to explicit recoverability. An unsafe
EXECUTE is not a false block. Missing tokens/cost remain null; no LLM calls have
known zero use. Repeats are attempts, paired by (scenario_id, repeat). C1–C8 use
the primary mutation family; composed cases retain their composed flag and use
C8 as primary, without double-counting secondary C1. Categories are separate.
Operational metrics include measured latency, calls, token/cost totals and
validation-stage counts. Working UHR thresholds 1% and 2% remain sensitivity
criteria, not established safety guarantees; undefined UHR proves no bound.

## Analysis and assumptions

95% percentile bootstrap resamples base-tool clusters, retaining their cases and
repeats together. One-cluster data does not produce a confidence interval.
Undefined resample denominators suppress the interval and are counted explicitly.
Family-specific intervals and family/category/ablation tables are generated.
McNemar uses the exact two-sided conditional binomial test on discordant pairs;
missing or duplicate pairs are errors. Within-tool dependence means unadjusted
scenario-level McNemar values are diagnostic, requiring sensitivity review.
Wilcoxon is withheld unless symmetry of paired differences is explicitly
confirmed, and requires complete finite paired data. Main interpretation must
address dependence, repeated measurements and multiplicity before confirming H1–H4.

Formula/API references: [SciPy binomtest](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.binomtest.html)
and [SciPy Wilcoxon](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.wilcoxon.html).
The actual installed SciPy version is pinned in requirements.lock; online stable
documentation can describe a newer release. Tests check hand-computed examples.

Offline artifact tables/plots are engineering diagnostics with a fake provider;
their numbers and p-values are not evidence about real LLM quality or hypotheses.
