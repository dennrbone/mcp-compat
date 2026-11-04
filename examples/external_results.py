"""Аудит реальных трасс и кластерный анализ; серверы/модели не вызываются."""

import argparse
import csv
from itertools import product
import json
from pathlib import Path
import random

import numpy as np
from scipy.stats import beta

from external_study import DATA, DIGEST, METHODS, ROOT, native_arguments, read_completed
from mcp_compat import SchemaDiffEngine, ToolCall, canonical_bytes
from mcp_compat.analysis import RATES, bootstrap_ci, clustered_recovery_comparison, paired
from mcp_compat.experiments import metrics, summaries
from mcp_compat.external import load_gold, load_inputs


def require(condition, message):
    if not condition:
        raise ValueError(message)


def audit(directory):
    records = read_completed(directory)
    methods = json.loads((directory/"manifest.json").read_bytes())["methods"]
    require(summaries(records)==json.loads((directory/"summary.json").read_bytes()),"saved summary mismatch")
    cases = load_inputs(DATA,DIGEST)
    gold = load_gold(DATA,DIGEST)
    indexed = {(r.scenario_id,r.method):r for r in records}
    events = [json.loads(p.read_bytes()) for p in sorted(directory.glob("rpc-*.json"))]
    evaluation = iter(e for e in events if e["visible"] is False)
    for case in cases:
        label = gold[case.case_id]
        old = next(evaluation)
        require(old["case_id"] == case.case_id and old["era"] == "old","old trace identity")
        observed = {k:old["full_observation"][k] for k in ("result","state")}
        require(canonical_bytes(observed)==canonical_bytes(label["expected"]),"independent old gold mismatch")
        for method in methods:
            r = indexed[case.case_id,method]
            saved=json.loads((directory/f"decision-{method}-{case.case_id}.json").read_bytes())
            require(r.decision.model_dump()==saved["decision"],"decision mismatch")
            require(r.recovery==case.request.model_dump(),"recovery input mismatch")
            require((r.ground_truth,r.recoverable)==(label["ground_truth"],label["recoverable"]),"label mismatch")
            candidate=r.decision.adapted_call
            if candidate is None and "candidate" in r.decision.evidence:
                candidate=ToolCall.model_validate(r.decision.evidence["candidate"])
            valid=None
            if candidate is not None:
                try:
                    candidate.validate_against(case.request.new_contract)
                    valid=True
                except ValueError:
                    valid=False
            require(r.schema_valid is valid,"schema score mismatch")
            semantic = None
            if r.decision.action == "EXECUTE":
                semantic = True
                for _ in range(2):
                    event = next(evaluation)
                    require(event["case_id"]==case.case_id and event["era"]=="new","new trace identity")
                    require(event["arguments"]==native_arguments(case,r.decision.adapted_call.arguments),"evaluated different candidate")
                    observed = {k:event["full_observation"][k] for k in ("result","state")}
                    if canonical_bytes(observed) != canonical_bytes(label["expected"]):
                        semantic = False
                        break
            require(r.semantic_equivalent is semantic,"independent semantic score mismatch")
    require(next(evaluation,None) is None,"unaccounted evaluator observations")
    return cases,records,events


def rate_contrast(records, a, b, metric, *, seed=42, draws=2000):
    """Парный cluster bootstrap и точная перестановка целых источников, максимум 16."""
    if metric not in ("CRR","UHR","FBR") or draws < 1:
        raise ValueError("invalid contrast configuration")
    if metric == "CRR":
        return clustered_recovery_comparison(records,a,b,seed=seed,draws=draws)
    left,right = paired(records,a,b)
    groups = {}
    for x,y in zip(left,right):
        groups.setdefault(x.base_tool,[]).append((x,y))
    units = list(groups.values())
    def statistic(pairs):
        x,y = [metrics(list(rows))[metric]["value"] for rows in zip(*pairs)]
        return None if x is None or y is None else x-y
    point = statistic(list(zip(left,right)))
    result = dict(difference=point,low=None,high=None,pvalue=None,clusters=len(units),
        confidence=.95,seed=seed,draws=draws,undefined_resamples=0,undefined_permutations=0,
        assumption="exchangeable method labels within entire source clusters; exploratory")
    if point is None or len(units)<2:
        return dict(result,status="undefined_metric" if point is None else "insufficient_clusters")
    if len(units)>16:
        raise ValueError("external exact contrast supports at most 16 clusters")
    rng = random.Random(seed)
    values = [statistic([pair for unit in rng.choices(units,k=len(units)) for pair in unit]) for _ in range(draws)]
    result["undefined_resamples"] = sum(v is None for v in values)
    if not result["undefined_resamples"]:
        low,high = np.quantile(values,[.025,.975])
        result.update(low=float(low),high=float(high))
    extreme = 0
    for signs in product((False,True),repeat=len(units)):
        value = statistic([(y,x) if swap else (x,y) for unit,swap in zip(units,signs) for x,y in unit])
        if value is None:
            result["undefined_permutations"] += 1
        elif abs(value) >= abs(point)-1e-12:
            extreme += 1
    if not result["undefined_permutations"]:
        result["pvalue"] = extreme/(2**len(units))
    return dict(result,status="computed" if not result["undefined_resamples"] and not result["undefined_permutations"] else "partly_undefined")


def source_error_bound(records):
    executed = [r for r in records if r.decision.action == "EXECUTE"]
    sources = {r.base_tool for r in executed}
    errors = {r.base_tool for r in executed if r.semantic_equivalent is not True}
    n,k = len(sources),len(errors)
    upper = None if not n else 1. if k==n else float(beta.ppf(.95,k+1,n-k))
    return dict(event="at least one unsafe execution in an executing source cluster",sources=n,
        error_sources=k,upper_95_one_sided=upper,method="Clopper-Pearson under iid source-event model",
        unconditional_population_UHR_upper=1.,
        limitation="purposive sources and shared mutations do not establish iid or a population sampling model; this is not a per-call UHR bound")


def family(case):
    # В raw V1 C1 использован и для четырёх benign-контролей Calculator; не считаем их rename.
    return "CONTROL" if case.kind=="historical" and case.request.old_contract.name==case.request.new_contract.name else case.family


def analyze(directory, output, *, draws=2000):
    cases,records,events = audit(directory)
    require(not output.exists(),"analysis output already exists; keep prior artifacts")
    output.mkdir(parents=True)
    lookup = {c.case_id:c for c in cases}
    supported = {c.case_id for c in cases if SchemaDiffEngine.compare(c.request.old_contract,c.request.new_contract).is_complete}
    strata = {"all":records,"historical":[r for r in records if lookup[r.scenario_id].kind=="historical"],
        "constructed":[r for r in records if lookup[r.scenario_id].kind=="constructed"],
        "historical_renames":[r for r in records if lookup[r.scenario_id].kind=="historical" and family(lookup[r.scenario_id])!="CONTROL"],
        "benign_controls":[r for r in records if family(lookup[r.scenario_id])=="CONTROL"],
        "supported_diff":[r for r in records if r.scenario_id in supported],
        "actual_source_writes":[r for r in records if lookup[r.scenario_id].request.old_contract.name=="write-query"],
        "constructed_state_changes":[r for r in records if lookup[r.scenario_id].alteration in ("hidden_state","external","ambiguous","toctou")]}
    strata.update({"source_"+s:[r for r in records if r.base_tool==s] for s in ("fs","sqlite","calculator")})
    strata.update({"family_"+f:[r for r in records if family(lookup[r.scenario_id])==f] for f in [*(f"C{i}" for i in range(1,9)),"CONTROL"]})
    summary = {name:{method:metrics([r for r in rows if r.method==method]) for method in METHODS} for name,rows in strata.items()}
    contrasts = {}
    pairs = (("B","A"),("B","C"),("B","D"),("M1_new","M1_old"))
    lineage = [r.model_copy(update={"base_tool":"official" if r.base_tool in ("fs","sqlite") else "independent"}) for r in records]
    for a,b in pairs:
        contrasts[a+"-"+b] = {group:{metric:rate_contrast(rows,a,b,metric,draws=draws) for metric in ("CRR","UHR","FBR")}
            for group,rows in [("repository",records),("lineage",lineage)]}
        contrasts[a+"-"+b]["leave_one_source_out"] = {source:{metric:rate_contrast([r for r in records if r.base_tool!=source],a,b,metric,draws=draws)
            for metric in ("CRR","UHR","FBR")} for source in ("fs","sqlite","calculator")}
    intervals = {method:{metric:bootstrap_ci([r for r in records if r.method==method],metric,draws=draws) for metric in RATES} for method in METHODS}
    bounds = {method:source_error_bound([r for r in records if r.method==method]) for method in METHODS}
    decisions = [json.loads(p.read_bytes()) for p in directory.glob("decision-*.json")]
    operational = {method:dict(preview_source_invocations=sum(d["source_calls"] for d in decisions if d["method"]==method),
        median_seconds=float(np.median([r.latency for r in records if r.method==method])),
        p95_seconds=float(np.quantile([r.latency for r in records if r.method==method],.95))) for method in METHODS}
    result = dict(run_manifest=json.loads((directory/"manifest.json").read_bytes()),
        summary=summary,intervals=intervals,contrasts=contrasts,source_error_bounds=bounds,
        operational=operational,source_invocations=len(events),source_errors=sum("error_type" in e for e in events),
        validation=dict(status="PASS",full_matrix=len(records),independent_trace_recalculation=True),
        preparation=dict(source_pairs=3,repositories=3,independent_lineages=2,manual_cases=63,human_hours=None,
                         reason="manual effort not measured prospectively"),
        limitations=["Only three purposive repositories and two lineages; shared constructed patterns.",
            "A-E use supplied candidates; full M1 has no mapper. Do not rank generators from these results.",
            "Completeness declarations are supplied, not automatically inferred.",
            "V1 and V2 change both admission and TOCTOU environment; compare methods within each run.",
            "Historical Calculator cases are benign controls; raw family C1 retained but excluded from rename strata.",
            "Latency includes process startup and extra probes; order fixed; no causal speed inference."])
    (output/"analysis.json").write_bytes(canonical_bytes(result))
    with (output/"metrics.csv").open("w",newline="",encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["stratum","method","metric","numerator","denominator","value"])
        for stratum,methods in summary.items():
            for method,values in methods.items():
                for metric in RATES:
                    rate=values[metric]
                    writer.writerow([stratum,method,metric,rate["numerator"],rate["denominator"],rate["value"]])
    plot(result,output)
    return result


def plot(result,output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    with matplotlib.rc_context({"svg.hashsalt":"external-admission"}):
        fig,axes = plt.subplots(2,2,figsize=(12,7),constrained_layout=True)
        for row,stratum in enumerate(("historical","constructed")):
            for column,metric in enumerate(("CRR","UHR")):
                axis=axes[row,column]
                rates=[result["summary"][stratum][m][metric] for m in METHODS]
                axis.bar(METHODS,[np.nan if r["value"] is None else r["value"] for r in rates],color="#486f99" if column==0 else "#b35151")
                axis.set_ylim(0,1.15)
                axis.set_title(("Исторические пары" if row==0 else "Искусственные изменения")+" — "+metric)
                axis.tick_params(axis="x",labelrotation=25)
                for i,rate in enumerate(rates):
                    axis.text(i,.03 if rate["value"] is None else rate["value"]+.025,
                        "N/A" if rate["value"] is None else f'{rate["numerator"]}/{rate["denominator"]}',ha="center",fontsize=9)
        fig.savefig(output/"external-rates.png",dpi=160,metadata={"Software":"mcp-compat"})
        fig.savefig(output/"external-rates.svg",metadata={"Date":None})
        plt.close(fig)


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--run",type=Path,default=ROOT/"experiments/external-admission-2026-11-04-v2")
    parser.add_argument("--output",type=Path,default=ROOT/"experiments/external-analysis-2026-11-04-v2")
    args=parser.parse_args()
    result=analyze(args.run,args.output)
    print("validated",result["validation"]["full_matrix"],"records")
