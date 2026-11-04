"""Общие знаменатели кандидатов и отдельная оценка парной абляции; без новых вызовов."""

import argparse
import csv
from itertools import product
import json
from pathlib import Path
import random

import numpy as np

from external_results import audit, require
from external_study import ROOT
from mcp_compat import canonical_bytes
from mcp_compat.experiments import metrics


def rate(numerator, denominator):
    return dict(numerator=numerator, denominator=denominator,
                value=numerator / denominator if denominator else None)


def confusion(acceptable, accepted):
    require(acceptable.keys() == accepted.keys(), "different candidate populations")
    tp = sum(acceptable[k] and accepted[k] for k in acceptable)
    fp = sum(not acceptable[k] and accepted[k] for k in acceptable)
    fn = sum(acceptable[k] and not accepted[k] for k in acceptable)
    tn = len(acceptable) - tp - fp - fn
    return dict(TP=tp, FP=fp, FN=fn, TN=tn, FAR=rate(fp, fp + tn),
                candidate_false_block_rate=rate(fn, fn + tp))


def far_contrast(rows, *, seed=42, draws=2000):
    """Отдельный FAR имеет общий фиксированный знаменатель, в отличие от UHR."""
    require(draws > 0, "positive bootstrap draws required")
    grouped = {}
    for row in rows:
        if not row["acceptable"]:
            grouped.setdefault(row["source"], []).append(int(row["a"]) - int(row["b"]))
    units = [(sum(values), len(values)) for values in grouped.values()]
    require(len(units) <= 16, "at most 16 exact clusters")
    denominator = sum(n for _, n in units)
    point = sum(d for d, _ in units) / denominator if denominator else None
    result = dict(difference=point, low=None, high=None, pvalue=None, clusters=len(units),
                  negatives=denominator, seed=seed, draws=draws, confidence=.95,
                  assumption="exploratory; exchangeable whole-cluster method labels, not established by purposive sampling")
    if len(units) < 2:
        return dict(result, status="undefined" if not denominator else "insufficient_clusters")
    rng = random.Random(seed)
    samples = [rng.choices(units, k=len(units)) for _ in range(draws)]
    values = [sum(d for d, _ in sample) / sum(n for _, n in sample) for sample in samples]
    low, high = np.quantile(values, [.025, .975])
    extreme = sum(abs(sum(sign * unit[0] for sign, unit in zip(signs, units)) / denominator)
                  >= abs(point) - 1e-12 for signs in product((-1, 1), repeat=len(units)))
    return dict(result, low=float(low), high=float(high), pvalue=extreme / 2**len(units), status="computed")


def paired_matrix(left, right, selected):
    return {f"{a}_{b}": sum(left[k] == a and right[k] == b for k in selected)
            for a in (False, True) for b in (False, True)}


def analyze(baseline, ablation, output):
    cases, old_records, old_events = audit(baseline)
    new_cases, records, events = audit(ablation)
    require(cases == new_cases, "different frozen cases")
    old = {(r.scenario_id, r.method): r for r in old_records}
    new = {(r.scenario_id, r.method): r for r in records}
    require({r.method for r in records} == {"FULL", "NO_FINAL"}, "wrong ablation methods")
    acceptable = {}
    for case in cases:
        reference = old[case.case_id, "C"]
        if reference.decision.action == "EXECUTE":
            require(reference.decision.adapted_call == case.candidate, "C evaluated different candidate")
            require(reference.semantic_equivalent is not None, "C semantic oracle unavailable")
            acceptable[case.case_id] = reference.semantic_equivalent
        else:
            require(reference.schema_valid is False, "unexecuted candidate oracle is unknown")
            acceptable[case.case_id] = False
    methods = {m: {c.case_id: old[c.case_id, m] for c in cases} for m in ("A", "B", "C", "D", "E")}
    methods.update({m: {c.case_id: new[c.case_id, m] for c in cases} for m in ("FULL", "NO_FINAL")})
    accepted = {m: {k: r.decision.action == "EXECUTE" for k, r in rows.items()} for m, rows in methods.items()}
    for method, rows in methods.items():
        for case in cases:
            row = rows[case.case_id]
            if row.decision.action == "EXECUTE":
                require(row.decision.adapted_call == case.candidate, "methods do not share candidate")
                require(row.semantic_equivalent is acceptable[case.case_id], "candidate evaluator disagreement")
    summary = {m: dict(classification=confusion(acceptable, accepted[m]), historical_metrics=metrics(list(rows.values())))
               for m, rows in methods.items()}
    contrasts = {}
    for a, b in (("B", "A"), ("B", "C"), ("B", "D"), ("FULL", "NO_FINAL")):
        rows = [dict(source=c.project, acceptable=acceptable[c.case_id],
                     a=accepted[a][c.case_id], b=accepted[b][c.case_id]) for c in cases]
        lineage = [dict(row, source="official" if row["source"] in ("fs", "sqlite") else "independent") for row in rows]
        contrasts[a + "-" + b] = dict(repository=far_contrast(rows), lineage=far_contrast(lineage),
            leave_one_out={s: far_contrast([r for r in rows if r["source"] != s]) for s in ("fs", "sqlite", "calculator")},
            all_decisions=paired_matrix(accepted[a], accepted[b], acceptable),
            unacceptable_only=paired_matrix(accepted[a], accepted[b], [k for k, v in acceptable.items() if not v]))
    result = dict(candidate_population=dict(cases=len(cases), acceptable=sum(acceptable.values()),
                    unacceptable=sum(not value for value in acceptable.values()),
                    oracle="V2 C evaluator traces after all decisions, or invalid input schema; distinct from scenario recoverability"),
                  manifests=dict(baseline=json.loads((baseline/"manifest.json").read_bytes()),
                                 ablation=json.loads((ablation/"manifest.json").read_bytes())),
                  summary=summary, contrasts=contrasts,
                  source_calls=dict(baseline=len(old_events), ablation=len(events)),
                  source_errors=sum("error_type" in e for e in events),
                  scope="V2 A-E and new FULL/NO_FINAL remain separate experiments; no pooling or generator comparison")
    require(not output.exists(), "preserve previous analysis")
    output.mkdir(parents=True)
    (output/"analysis.json").write_bytes(canonical_bytes(result))
    with (output/"candidate-decisions.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["case_id", "source", "kind", "alteration", "acceptable_candidate", *methods])
        for c in cases:
            writer.writerow([c.case_id, c.project, c.kind, c.alteration, acceptable[c.case_id],
                             *(accepted[m][c.case_id] for m in methods)])
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, default=ROOT/"experiments/external-admission-2026-11-04-v2")
    parser.add_argument("--ablation", type=Path, default=ROOT/"experiments/final-admission-ablation-2026-11-05")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.baseline, args.ablation, args.output)
    print(json.dumps(result["candidate_population"], ensure_ascii=False))
