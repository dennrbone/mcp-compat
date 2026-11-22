"""Compare Hybrid modes with a provider inside the mapping stage."""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess

from codex_transport import CodexClient, MODEL as TERRA_MODEL
from external_200_dataset import read
from external_runtime import isolation_check
import external_study as external
from mcp_compat import MigrationDecision, canonical_bytes
from mcp_compat.agent_checks import cli_version
from mcp_compat.benchmark import RecoveryMode
from mcp_compat.experiments import _atomic
from mcp_compat.hybrid import Hybrid
from mcp_compat.llm import Mapper, PROMPT_VERSION
from mcp_compat.providers import AgentProvider, from_env
from mcp_compat.verification import fingerprint


class BoundedRuntime(external.Runtime):
    """Constrain probes to the shared test workload."""

    def __init__(self, output):
        super().__init__(output)
        self.blocked = 0

    def implementation(self, case, era, *, visible=True):
        invoke = super().implementation(case, era, visible=visible)
        if era == "old":
            return invoke

        def bounded(arguments, state):
            try:
                native = external.native_arguments(case, arguments)
                if case.project == "fs":
                    allowed = (native.get("path") in case.initial["files"]
                               and native.keys() <= {"path", "head", "tail"}
                               and all(type(native[key]) in (int, float) and 0 <= native[key] <= 32
                                       for key in native.keys() & {"head", "tail"}))
                else:
                    allowed = native in (case.request.old_call.arguments,
                                         external.native_arguments(case, case.candidate.arguments))
            except (KeyError, TypeError, ValueError):
                allowed = False
            if not allowed:
                self.blocked += 1
                raise ValueError("call outside the fixed experiment workload")
            return invoke(arguments, state)

        return bounded


def provider(name):
    if name == "codeagent":
        config = from_env()
        return AgentProvider(config), config.model, cli_version(config)
    executable = shutil.which("codex")
    if executable is None:
        raise ValueError("Codex CLI not found")
    version = subprocess.run([executable, "--version"], check=True, text=True,
                             capture_output=True, timeout=20).stdout.strip()
    return CodexClient(executable), TERRA_MODEL, version


def trace_count(record):
    traces = []
    while record is not None:
        traces.append(record["decision"]["evidence"].get("llm", {}))
        record = record.get("previous")
    return sum(t.get("calls", 0) for t in traces), sum(len(t.get("responses", [])) for t in traces)


def needs_retry(record):
    trace = record["decision"]["evidence"].get("llm", {})
    return trace.get("last_error_type") == "ProviderError" and trace.get("parse_status") != "parsed"


def study(dataset, provider_name, mode, output, workers, retry):
    client, model, version = provider(provider_name)
    mapper = Mapper(client, attempts=2, timeout=120)
    output.mkdir(parents=True, exist_ok=True)
    if dataset == "external":
        data_digest, cases = read("public.json")
        keys = {c.case_id: c for c in cases}
    else:
        import historical_mcp
        historical_mcp.check_installation()
        keys = historical_mcp.cases()
        data_digest = fingerprint(keys)

    manifest = dict(dataset=dataset, inputs=data_digest, provider=provider_name, model=model, cli=version,
                    mode=mode, scope="hybrid-mapping", prompt_version=PROMPT_VERSION,
                    attempts=mapper.attempts, timeout=mapper.timeout)
    path = output / "manifest.json"
    if path.exists():
        assert json.loads(path.read_bytes()) == manifest, "run identity changed"
    else:
        assert not any(output.iterdir()), "choose an empty output directory"
        _atomic(path, manifest)
    _atomic(output / "isolation.json", isolation_check())

    def decide(case_id):
        case = keys[case_id]
        folder = output / case_id
        folder.mkdir(exist_ok=True)
        path = folder / "decision.json"
        previous = json.loads(path.read_bytes()) if path.exists() else None
        if previous is not None and (not retry or not needs_retry(previous)):
            return previous
        if dataset == "historical":
            result = historical_mcp.decide(case, mapper, mode, folder)
        else:
            runtime = BoundedRuntime(folder)
            checker = external.verifier(case, runtime)
            engine = Hybrid(mapper, checker, mode=mode, current_state=lambda: external.current_state(case))
            decision = engine.recover(case.request.model_copy(deep=True))
            result = dict(decision=decision.model_dump(mode="json"), blocked_probes=runtime.blocked)
        result["case"] = case_id
        if previous is not None:
            result["previous"] = previous
        _atomic(path, result)
        return result

    records = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(decide, case_id) for case_id in keys]
        for future in as_completed(futures):
            records.append(future.result())
            if len(records) % 10 == 0 or len(records) == len(keys):
                print(dataset, provider_name, mode, "decisions", len(records), "/", len(keys), flush=True)
    assert len({r["case"] for r in records}) == len(keys)

    gold = None
    if dataset == "external":
        gold_digest, gold = read("gold.json")
        assert gold_digest == data_digest and set(gold) == set(keys)

    def score(record):
        decision = MigrationDecision.model_validate(record["decision"])
        case_id = record["case"]
        case = keys[case_id]
        calls, responses = trace_count(record)
        if decision.action == "EXECUTE":
            assert decision.evidence["admission"]["passed"]
        if dataset == "historical":
            equivalent = historical_mcp.evaluate(case, decision, output / case_id)
            recoverable = None
        else:
            runtime = BoundedRuntime(output / case_id)
            expected = gold[case_id]["expected"]
            observed = deepcopy(case.initial)
            old_result = runtime.implementation(case, "old", visible=False)(case.request.old_call.arguments, observed)
            assert canonical_bytes(dict(result=old_result, state=observed)) == canonical_bytes(expected)
            equivalent = external.evaluate(case, decision, expected, runtime)
            recoverable = gold[case_id]["recoverable"]
        result = dict(case=case_id, action=decision.action, reason=decision.reasons[0],
                      llm_calls=calls, llm_responses=responses, equivalent=equivalent, recoverable=recoverable,
                      blocked_probes=record.get("blocked_probes", 0), unavailable=needs_retry(record))
        _atomic(output / case_id / "score.json", result)
        return result

    with ThreadPoolExecutor(max_workers=workers) as pool:
        scores = list(pool.map(score, records))
    admitted = [row for row in scores if row["action"] == "EXECUTE"]
    summary = dict(**manifest, cases=len(scores),
        llm_cases=sum(row["llm_calls"] > 0 for row in scores),
        llm_calls=sum(row["llm_calls"] for row in scores),
        llm_responses=sum(row["llm_responses"] for row in scores),
        unavailable=sum(row["unavailable"] for row in scores), admitted=len(admitted),
        confirmed=sum(row["equivalent"] is True for row in admitted),
        recovered=sum(row["equivalent"] is True and row["recoverable"] is True for row in admitted) if gold else None,
        recoverable=sum(case["recoverable"] for case in gold.values()) if gold else None,
        wrong=sum(row["equivalent"] is False for row in admitted),
        unscored=sum(row["equivalent"] is None for row in admitted),
        blocked_probes=sum(row["blocked_probes"] for row in scores),
        reasons=Counter(row["reason"] for row in scores))
    _atomic(output / "summary.json", summary)
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=("external", "historical"), required=True)
    parser.add_argument("--provider", choices=("codeagent", "terra"), required=True)
    parser.add_argument("--hybrid-mode", type=RecoveryMode, choices=list(RecoveryMode), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, choices=range(1, 9), default=4)
    parser.add_argument("--retry-unavailable", action="store_true")
    args = parser.parse_args()
    study(args.dataset, args.provider, args.hybrid_mode, args.output, args.workers, args.retry_unavailable)
