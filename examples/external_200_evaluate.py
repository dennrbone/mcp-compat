"""Evaluate the 200-case benchmark with real sandboxed runtimes and sealed references."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import platform
from statistics import median, quantiles
from time import perf_counter

import admission_ablation
from admission_comparison import confusion, far_contrast
import external_study as old
from external_200_dataset import read
from external_runtime import isolation_check
from mcp_compat import MigrationDecision, ToolCall, canonical_bytes
from mcp_compat.experiments import Record, _atomic, metrics
from mcp_compat.llm import MappingResult
from mcp_compat.recovery import abstain, validate_candidate
from mcp_compat.verification import fingerprint

FIXED = (*old.METHODS, "FULL", "NO_FINAL")


def in_workload(case, candidate):
    """Allow only reviewed business inputs to be passed to the pinned servers."""
    args = old.native_arguments(case, candidate.arguments)
    if case.project != "fs":
        return args in (case.request.old_call.arguments, old.native_arguments(case, case.candidate.arguments))
    return (args.get("path") in case.initial["files"] and args.keys() <= {"path", "head", "tail"}
            and all(type(args[key]) in (int, float) and 0 <= args[key] <= 32
                    for key in args.keys() & {"head", "tail"}))


def generated(case, mapping, runtime, method):
    proposal = mapping.proposal
    if proposal is None or proposal.action == "ABSTAIN":
        return abstain(mapping.reason if proposal is None else "model_abstain")
    call = proposal.call
    assert call is not None
    decision = validate_candidate(case.request, call, method)
    if decision.action == "ABSTAIN":
        return decision
    try:
        allowed = in_workload(case, call)
    except (KeyError, TypeError, ValueError):
        allowed = False
    if not allowed:
        return abstain("out_of_fixture", **decision.evidence)
    if method.startswith("C_"):
        return decision
    return old.decide(case.model_copy(update={"candidate": call}), "B", runtime)


def semantic(case, decision, expected, runtime):
    result = old.evaluate(case, decision, expected, runtime)
    return result


def input_valid(case, decision):
    call = decision.adapted_call
    if call is None and "candidate" in decision.evidence:
        call = ToolCall.model_validate(decision.evidence["candidate"])
    if call is None:
        return None
    try:
        call.validate_against(case.request.new_contract)
    except ValueError:
        return False
    return True


def study(lane, output, workers, proposals):
    digest, cases = read("public.json")
    methods = FIXED if lane == "fixed" else (f"C_{lane}", f"B_{lane}")
    output.mkdir(parents=True, exist_ok=True)
    proposal_files = {}
    if lane != "fixed":
        manifest = json.loads((proposals / "manifest.json").read_bytes())
        if manifest["dataset"] != digest or manifest["provider"] != lane:
            raise ValueError("model inputs do not match the frozen benchmark")
        proposal_files = {c.case_id: (proposals / f"{c.case_id}.json").read_bytes() for c in cases}
    files = list((old.ROOT / "src/mcp_compat").rglob("*.py")) + [
        Path(__file__), Path(old.__file__), *[old.ROOT / "examples" / f for f in
        ("admission_ablation.py", "external_runtime.py", "external_worker.py")]
    ]
    identity = dict(lane=lane, data=digest, methods=methods, workers=workers, python=platform.python_version(),
                    code=fingerprint({str(p.relative_to(old.ROOT)): sha256(p.read_bytes()).hexdigest() for p in files}),
                    proposals=fingerprint({k: sha256(v).hexdigest() for k, v in proposal_files.items()}))
    identity["methods"] = list(methods)
    manifest_file = output / "manifest.json"
    if manifest_file.exists():
        if json.loads(manifest_file.read_bytes()) != identity:
            raise ValueError("saved run configuration changed")
    else:
        _atomic(manifest_file, identity)
    _atomic(output / "isolation.json", isolation_check())

    def decide_case(case):
        folder = output / case.case_id
        folder.mkdir(exist_ok=True)
        runtime = old.Runtime(folder)
        mapping = None
        proposal = None
        if proposal_files:
            proposal = json.loads(proposal_files[case.case_id])
            assert proposal["request"] == fingerprint(case.request.model_dump())
            mapping = MappingResult.model_validate(proposal["mapping"])
        for method in methods:
            path = folder / f"decision-{method}.json"
            if path.exists():
                continue
            start = perf_counter()
            before = runtime.counter
            if mapping is not None:
                decision = generated(case, mapping, runtime, method)
            elif method in ("FULL", "NO_FINAL"):
                decision = admission_ablation.decide(case, method, runtime)
            else:
                decision = old.decide(case, method, runtime)
            _atomic(path, dict(decision=decision.model_dump(), seconds=perf_counter() - start,
                               source_calls=runtime.counter - before,
                               model_seconds=0 if proposal is None else proposal["seconds"]))
        return case.case_id

    def execute(fn, stage):
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for i, result in enumerate(pool.map(fn, cases), start=1):
                if i % 10 == 0 or i == len(cases):
                    print(f"{lane} {stage}: {i}/{len(cases)} ({result})", flush=True)

    execute(decide_case, "decisions")
    gold_digest, gold = read("gold.json")
    if gold_digest != digest or set(gold) != {c.case_id for c in cases}:
        raise ValueError("reference matrix differs from case matrix")

    def evaluate_case(case):
        folder = output / case.case_id
        runtime = old.Runtime(folder)
        label = gold[case.case_id]
        state = deepcopy(case.initial)
        if not (folder / "reference.json").exists():
            args = case.request.old_call.arguments
            result = runtime.implementation(case, "old", visible=False)(args, state)
            if canonical_bytes(dict(result=result, state=state)) != canonical_bytes(label["expected"]):
                raise ValueError(f"frozen reference and pinned old server disagree: {case.case_id}")
            _atomic(folder / "reference.json", dict(result=result, state=state))
        for method in methods:
            path = folder / f"score-{method}.json"
            if path.exists():
                continue
            data = json.loads((folder / f"decision-{method}.json").read_bytes())
            decision = MigrationDecision.model_validate(data["decision"])
            equivalent = semantic(case, decision, label["expected"], runtime)
            _atomic(path, Record(scenario_id=case.case_id, method=method, repeat=0, mutation_family=case.family,
                ground_truth=label["ground_truth"], recoverable=label["recoverable"], base_tool=case.project,
                composed=False, decision=decision, schema_valid=input_valid(case, decision),
                semantic_equivalent=equivalent, latency=data["seconds"], calls=None, input_tokens=None,
                output_tokens=None, cost=None, validation_stages=int("verification" in decision.evidence)
                + int("admission" in decision.evidence), recovery=case.request.model_dump()).model_dump())
        return case.case_id

    execute(evaluate_case, "evaluation")
    records = {method: {c.case_id: Record.model_validate_json(
        (output / c.case_id / f"score-{method}.json").read_bytes()) for c in cases} for method in methods}
    events = [json.loads(p.read_bytes()) for p in output.glob("*/rpc-*.json")]
    errors = [event["case_id"] for event in events if "error_type" in event]
    if errors:
        raise ValueError(f"source errors need investigation: {errors[:12]} (total {len(errors)})")
    result = dict(dataset=digest, decisions=sum(map(len, records.values())), source_calls=len(events),
                  source_errors=len(errors), metrics={m: metrics(list(rows.values())) for m, rows in records.items()})
    result["operational"] = {}
    for method in methods:
        saved = [json.loads((output / c.case_id / f"decision-{method}.json").read_bytes()) for c in cases]
        seconds = [r["seconds"] for r in saved]
        result["operational"][method] = dict(source_calls=sum(r["source_calls"] for r in saved),
            median_seconds=median(seconds), p95_seconds=quantiles(seconds, n=100, method="inclusive")[94])
    classifications = FIXED[:5] + ("FULL", "NO_FINAL") if lane == "fixed" else methods
    structural = records["C" if lane == "fixed" else f"C_{lane}"]
    acceptable = {k: r.semantic_equivalent is True for k, r in structural.items()}
    result["classification"] = {m: confusion(acceptable, {k: r.decision.action == "EXECUTE"
        for k, r in records[m].items()}) for m in classifications}
    for method in classifications:
        for row in records[method].values():
            if row.decision.action == "EXECUTE":
                assert row.decision.adapted_call == structural[row.scenario_id].decision.adapted_call
                assert row.semantic_equivalent is acceptable[row.scenario_id]
    if lane == "fixed":
        result["contrasts"] = {}
        for a, b in (("B", "A"), ("FULL", "NO_FINAL")):
            rows = [dict(source=c.project, acceptable=acceptable[c.case_id],
                         a=records[a][c.case_id].decision.action == "EXECUTE",
                         b=records[b][c.case_id].decision.action == "EXECUTE") for c in cases]
            lineage = [dict(row, source="independent" if row["source"] == "calculator" else "official") for row in rows]
            result["contrasts"][f"{a}-{b}"] = dict(repository=far_contrast(rows), lineage=far_contrast(lineage))
    _atomic(output / "summary.json", result)
    print(lane, result["decisions"], "decisions;", result["source_calls"], "actual source calls", flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("lane", choices=("fixed", "codeagent", "terra"))
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--proposals", type=Path)
    p.add_argument("--workers", type=int, choices=range(1, 13), default=8)
    a = p.parse_args()
    if (a.lane == "fixed") == (a.proposals is not None):
        p.error("--proposals is required only for model lanes")
    study(a.lane, a.output, a.workers, a.proposals)
