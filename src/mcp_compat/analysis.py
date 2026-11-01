"""Reproducible statistics and figures; never infer model quality from a demo."""

import argparse
import csv
from hashlib import sha256
import json
import math
from pathlib import Path
import random
from typing import Any

import numpy as np
from scipy.stats import binomtest, wilcoxon

from mcp_compat import canonical_bytes
from mcp_compat.experiments import Record, metrics, summaries

RATES = ("CRR", "UHR", "FBR", "AbstentionAccuracy", "SchemaValidityRate", "SemanticEquivalenceRate")


def bootstrap_ci(records: list[Record], metric: str = "CRR", *, seed: int = 42,
                 draws: int = 2000, cluster: bool = True) -> dict:
    if metric not in RATES or draws < 1:
        raise ValueError("invalid bootstrap configuration")
    point = metrics(records)[metric]["value"]
    groups: dict[str, list[Record]] = {}
    for i, record in enumerate(records):
        groups.setdefault(record.base_tool if cluster else str(i), []).append(record)
    result = dict(point=point, low=None, high=None, confidence=.95, seed=seed,
                  draws=draws, units=len(groups), undefined_resamples=0)
    if point is None:
        return dict(result,status="undefined_metric")
    if len(groups) < 2:
        return dict(result,status="insufficient_units")
    rng = random.Random(seed)
    units = list(groups.values())
    samples = []
    for _ in range(draws):
        sample = [row for group in rng.choices(units,k=len(units)) for row in group]
        value = metrics(sample)[metric]["value"]
        if value is None:
            result["undefined_resamples"] += 1
        else:
            samples.append(value)
    if result["undefined_resamples"]:
        return dict(result,status="undefined_resamples")
    low, high = np.quantile(samples,[.025,.975],method="linear")
    return dict(result,low=float(low),high=float(high),status="computed")


def mcnemar(a: list[bool], b: list[bool]) -> dict:
    if len(a) != len(b) or any(type(v) is not bool for v in a+b):
        raise ValueError("McNemar requires matched binary observations")
    if not a:
        return dict(n=0,b=0,c=0,pvalue=None,status="empty_pairs")
    discordant_b = sum(x and not y for x,y in zip(a,b))
    discordant_c = sum(y and not x for x,y in zip(a,b))
    n = discordant_b + discordant_c
    pvalue = 1. if n == 0 else float(binomtest(discordant_b,n,.5,alternative="two-sided").pvalue)
    return dict(n=len(a),b=discordant_b,c=discordant_c,pvalue=pvalue,method="exact_binomial",status="computed")


def wilcoxon_paired(a: list[float], b: list[float], *, symmetry_confirmed: bool = False) -> dict:
    if len(a) != len(b) or any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in a+b):
        raise ValueError("Wilcoxon requires matched finite observations")
    if not a or not symmetry_confirmed:
        return dict(n=len(a),statistic=None,pvalue=None,status="empty_pairs" if not a else "symmetry_not_confirmed")
    if all(x == y for x,y in zip(a,b)):
        return dict(n=len(a),statistic=0.,pvalue=1.,status="all_zero_differences")
    result = wilcoxon(a,b,zero_method="wilcox",correction=False,alternative="two-sided",method="auto")
    return dict(n=len(a),statistic=float(result.statistic),pvalue=float(result.pvalue),status="computed_scipy_auto")


def paired(records: list[Record], method_a: str, method_b: str) -> tuple[list[Record],list[Record]]:
    def index(method):
        rows = [r for r in records if r.method == method]
        keys = {(r.scenario_id,r.repeat):r for r in rows}
        if len(keys) != len(rows):
            raise ValueError("duplicate paired observation")
        return keys
    a,b = index(method_a), index(method_b)
    if not a or a.keys() != b.keys():
        raise ValueError("missing paired observations")
    keys = sorted(a)
    left,right = [a[k] for k in keys],[b[k] for k in keys]
    if any((x.ground_truth,x.recoverable,x.base_tool) != (y.ground_truth,y.recoverable,y.base_tool) for x,y in zip(left,right)):
        raise ValueError("paired labels differ")
    return left,right


def read_results(directory: Path) -> tuple[dict,list[Record]]:
    manifest = json.loads((directory/"manifest.json").read_bytes())
    identity = {key:value for key,value in manifest.items() if key not in ("fingerprint","created_at")}
    if sha256(canonical_bytes(identity)).hexdigest() != manifest["fingerprint"]:
        raise ValueError("run manifest integrity failure")
    digests = json.loads((directory/"result-digests.json").read_bytes())
    records = []
    for key, digest in sorted(digests.items()):
        if not key or any(character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-" for character in key):
            raise ValueError("invalid result path")
        record = Record.model_validate_json((directory/f"{key}.json").read_bytes())
        if sha256(canonical_bytes(record.model_dump())).hexdigest() != digest:
            raise ValueError("result integrity failure")
        if key != f"{record.repeat}-{record.method}-{record.scenario_id}":
            raise ValueError("result identity mismatch")
        records.append(record)
    if not records:
        raise ValueError("empty results")
    return manifest,records


def _table(path: Path, rows: list[dict]) -> None:
    with path.open("w",newline="",encoding="utf-8") as stream:
        writer = csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def artifacts(directory: Path, output: Path, *, seed: int = 42, draws: int = 2000) -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    manifest,records = read_results(directory)
    output.mkdir(parents=True,exist_ok=True)
    grouped = summaries(records)
    rows, family_rows, category_rows = [], [], []
    intervals = {}
    for method,summary in grouped.items():
        selected = [r for r in records if r.method == method]
        intervals[method] = dict(overall={metric:bootstrap_ci(selected,metric,seed=seed,draws=draws) for metric in RATES},families={})
        rows.append(dict(method=method,samples=summary["overall"]["samples"],**{m:summary["overall"][m]["value"] for m in RATES},
                         **{m:summary["overall"][m] for m in ("latency_mean","calls","input_tokens","output_tokens","cost","validation_stages")}))
        for family,values in summary["families"].items():
            family_rows.append(dict(method=method,family=family,samples=values["samples"],**{m:values[m]["value"] for m in RATES}))
            family_data = [r for r in selected if r.mutation_family == family]
            intervals[method]["families"][family] = {metric:bootstrap_ci(family_data,metric,seed=seed,draws=draws) for metric in RATES}
        for category,values in summary["categories"].items():
            category_rows.append(dict(method=method,category=category,samples=values["samples"],**{m:values[m]["value"] for m in RATES}))
    comparisons: dict[str, Any] = {}
    for baseline in ("B0","B1","B2","B3"):
        if "M1" not in grouped or baseline not in grouped:
            comparisons[baseline] = dict(status="missing_methods")
            continue
        a,b = paired(records,"M1",baseline)
        recoverable = [(x,y) for x,y in zip(a,b) if x.recoverable]
        comparisons[baseline] = dict(
            recovery_mcnemar=mcnemar([x.decision.action == "EXECUTE" and x.semantic_equivalent is True for x,y in recoverable],
                                     [y.decision.action == "EXECUTE" and y.semantic_equivalent is True for x,y in recoverable]),
            continuous={},
        )
        for field in ("latency","calls","input_tokens","output_tokens","cost"):
            left,right = [getattr(r,field) for r in a],[getattr(r,field) for r in b]
            comparisons[baseline]["continuous"][field] = dict(status="unknown_measurements",pvalue=None) if any(v is None for v in left+right) else wilcoxon_paired(left,right)
    labels = {"offline_demo":"OFFLINE DEMO ONLY — no model inference", "pilot":"REAL PILOT — one repeat; limited runtime bindings"}
    label = labels.get(manifest["config"]["kind"], "Experiment results — assumptions require review")
    result = dict(label=label,seed=seed,draws=draws,bootstrap_unit="base_tool",summary=grouped,
                  intervals=intervals,comparisons=comparisons,
                  limitations=["Scenario pairs within a base tool are dependent; unadjusted McNemar is diagnostic.",
                               "Wilcoxon withheld without confirmed symmetry; repeats are not independent samples."])
    (output/"analysis.json").write_bytes(canonical_bytes(result))
    _table(output/"summary.csv",rows)
    _table(output/"families.csv",family_rows)
    _table(output/"categories.csv",category_rows)
    ablations = [row for row in rows if row["method"] in ("M1","A1","A2","A3","A4")]
    if ablations:
        _table(output/"ablations.csv",ablations)
    lines = ["% " + label,"\\begin{tabular}{lrrr}","Method & CRR & UHR & FBR \\\\"]
    for row in rows:
        values = ["--" if row[m] is None else f"{row[m]:.4f}" for m in ("CRR","UHR","FBR")]
        lines.append(row["method"].replace("_","\\_") + " & " + " & ".join(values) + " \\\\")
    lines.append("\\end{tabular}")
    (output/"summary.tex").write_text("\n".join(lines)+"\n",encoding="utf-8")
    with matplotlib.rc_context({"svg.hashsalt":"mcp-compat"}):
        figure,axes = plt.subplots(1,3,figsize=(12,4),constrained_layout=True)
        for axis,metric in zip(axes,("CRR","UHR","FBR")):
            axis.bar([row["method"] for row in rows],[np.nan if row[metric] is None else row[metric] for row in rows],color="#486f99")
            axis.set_title(metric)
            axis.set_ylim(0,1)
            axis.set_xlim(-.5,len(rows)-.5)
            axis.tick_params(axis="x",labelrotation=45)
            axis.set_ylabel("Rate")
            for index,row in enumerate(rows):
                if row[metric] is None:
                    axis.text(index,.03,"N/A",ha="center",va="bottom",fontsize=8)
        figure.suptitle(label,fontsize=11)
        figure.savefig(output/"rates.png",dpi=160,metadata={"Software":"mcp-compat"})
        figure.savefig(output/"rates.svg",metadata={"Date":None})
        plt.close(figure)
    return result


def analysis_cli(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Analyze actual runner results; report assumptions explicitly")
    parser.add_argument("--run",type=Path,default=Path("experiments/offline-demo"))
    parser.add_argument("--output",type=Path,default=Path("experiments/analysis-offline-demo"))
    parser.add_argument("--seed",type=int,default=42)
    parser.add_argument("--draws",type=int,default=2000)
    args = parser.parse_args(argv)
    result = artifacts(args.run,args.output,seed=args.seed,draws=args.draws)
    print(result["label"])
