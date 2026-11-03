"""Отдельный A–E опыт: реальные изолированные MCP-вызовы, без LLM/эталона в методе."""

import argparse
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from importlib.metadata import version
import json
from pathlib import Path
import platform
import re
from time import perf_counter

from external_runtime import ROOT, execute, isolation_check
from mcp_compat import ToolCall, canonical_bytes
from mcp_compat.experiments import Record, _atomic, summaries
from mcp_compat.external import load_gold, load_inputs
from mcp_compat.hybrid import Hybrid, SandboxVerifier
from mcp_compat.recovery import abstain, validate_candidate
from mcp_compat.verification import EvidenceVerifier, fingerprint

DATA = ROOT/"benchmark/external-mcp"
DIGEST = "6ab2bfb7da1687012c70a8acac5254f571381af8cd03d0911d393ba41e010b8f"
METHODS = ("A", "B", "C", "D", "E", "M1_old", "M1_new")
STUDY_VERSION = "external-admission-2"


def current_state(case):
    state = deepcopy(case.initial)
    if case.alteration == "toctou":
        if case.project == "fs":
            state["files"]["data.txt"] += "changed after preview\n"
        elif case.project == "sqlite":
            state["rows"][0]["qty"] += 1
        else:
            state["changed_after_check"] = True
    return state


def native_arguments(case, arguments):
    arguments = deepcopy(arguments)
    field = case.request.old_contract.input_schema["required"][0]
    if case.alteration == "nested":
        return arguments["payload"]
    if case.alteration == "encoding":
        if len(arguments[field]) != 1:
            raise ValueError("singleton encoding required")
        arguments[field] = arguments[field][0]
    if case.alteration == "optional":
        arguments.pop("trace", None)
    if case.alteration == "removed":
        arguments[field] = dict(fs="other.txt", sqlite="SELECT qty FROM items WHERE id=2", calculator="0")[case.project]
    return arguments


def change_result(result, alteration):
    result = deepcopy(result)
    if isinstance(result, list):
        node = result[0]
        key = "text" if "text" in node else next(iter(node))
    else:
        node, key = result, "result"
    value = node[key]
    if alteration == "lossy":
        if isinstance(value, str):
            node[key] = value[:1]
        else:
            node.pop(key)
    elif alteration == "unit" and isinstance(value, (int, float)):
        node[key] = value * 1000
    else:
        node[key] = value + "::" + alteration if isinstance(value, str) else value + 1
    return result


class Runtime:
    """Привязка к source+wrapper; эта часть не получает gold.json."""

    def __init__(self, output, call=None):
        self.output, self.call = output, execute if call is None else call
        ids = sorted(int(p.stem[4:]) for p in output.glob("rpc-*.json"))
        if ids != list(range(1,len(ids)+1)):
            raise ValueError("incomplete runtime history")
        self.counter = len(ids)

    def implementation(self, case, era, *, visible=True):
        trial = 0

        def invoke(arguments, state):
            nonlocal trial
            native = native_arguments(case, arguments) if era == "new" else deepcopy(arguments)
            name = case.request.old_contract.name
            if era == "new":
                name = "read_text_file" if case.project == "fs" else name.replace("-", "_")
            self.counter += 1
            event = dict(project=case.project, era=era, tool=name, arguments=native,
                         initial=deepcopy(state), case_id=case.case_id, visible=visible)
            started = perf_counter()
            try:
                observed = self.call(case.project, era, tool=name, arguments=native, state=state)
                event["source_observation"] = deepcopy(observed)
                if case.project == "calculator":
                    observed["state"] = deepcopy(state)
                if era == "new":
                    if case.alteration in ("unit", "result_changed", "lossy", "default_changed"):
                        observed["result"] = change_result(observed["result"], case.alteration)
                    if case.alteration == "nondeterministic" and trial % 2:
                        observed["result"] = change_result(observed["result"], "alternate")
                    if case.alteration in ("hidden_state", "external", "ambiguous"):
                        observed["state"]["unobserved_effect"] = case.alteration
                event["full_observation"] = deepcopy(observed)
                if visible:
                    observed["state"].pop("unobserved_effect", None)
                event["visible_observation"] = deepcopy(observed)
                state.clear()
                state.update(observed["state"])
                trial += 1
                return observed["result"]
            except Exception as error:
                event["error_type"] = type(error).__name__
                raise
            finally:
                event["seconds"] = perf_counter() - started
                _atomic(self.output/f"rpc-{self.counter:05}.json", event)
        return invoke


def verifier(case, runtime, *, legacy=False, profile=None):
    old = runtime.implementation(case, "old")
    new = runtime.implementation(case, "new")
    if legacy:
        return SandboxVerifier(case.request.old_contract, case.request.new_contract, old, new,
            side_effects=case.project == "sqlite", initial=case.initial, timeout=120)
    provenance = json.loads((DATA/"provenance.json").read_bytes())[case.project]
    wrapper = sha256(Path(__file__).read_bytes()).hexdigest()
    binding = dict(wrapper=wrapper, alteration=case.alteration, native_tool=case.request.old_contract.name)
    return EvidenceVerifier(case.request.old_contract, case.request.new_contract, old, new,
        profile=case.profile if profile is None else profile,
        handler_ids=tuple(fingerprint(dict(binding,source=provenance[era+"_commit"])) for era in ("old","new")),
        initial=case.initial, timeout=120)


def decide(case, method, runtime):
    if method.startswith("M1_"):
        checker = verifier(case, runtime, legacy=method == "M1_old")
        strategy = Hybrid(verifier=checker)
        strategy.name = method
        decision = strategy.recover(case.request.model_copy(deep=True))
        return checker.admit(case.request,decision,current_state=current_state(case)) if method == "M1_new" else decision
    decision = validate_candidate(case.request, case.candidate, method)
    if decision.action != "EXECUTE" or method == "C":
        return decision
    profile = case.profile
    if method == "D":
        profile = profile.model_copy(update=dict(complete=True, closed_environment=True,
                                                 deterministic=True, unambiguous=True))
    if method == "E":
        profile = profile.model_copy(update=dict(complete=False))
    checker = verifier(case, runtime, legacy=method == "A", profile=profile)
    checked = checker.verify(case.request, case.candidate)
    decision.evidence.update(verification=checked.model_dump(), semantic_verified=checked.passed)
    if not checked.passed:
        return abstain(checked.reason, **decision.evidence)
    decision.reasons = ["verified"]
    return checker.admit(case.request,decision,current_state=current_state(case)) if method in ("B","D") else decision


def evaluate(case, decision, expected, runtime):
    if decision.action != "EXECUTE":
        return None
    implementation = runtime.implementation(case,"new",visible=False)
    for _ in range(2):
        state = current_state(case)
        try:
            result = implementation(decision.adapted_call.arguments,state)
            if canonical_bytes(dict(result=result,state=state)) != canonical_bytes(expected):
                return False
        except Exception:
            return False
    return True


def study(output):
    cases = load_inputs(DATA,DIGEST)
    output.mkdir(parents=True,exist_ok=True)
    files = list((ROOT/"src/mcp_compat").rglob("*.py")) + [Path(__file__), ROOT/"examples/external_runtime.py",ROOT/"examples/external_worker.py"]
    identity = dict(study_version=STUDY_VERSION,config=dict(kind="deterministic",benchmark_digest=DIGEST,seed=42,repeats=1,
                               scenario_ids=[c.case_id for c in cases]), methods=list(METHODS),
        benchmark_version="external-mcp-1.0", prompt_version="NO_MODEL",
        source_digest=fingerprint({str(p.relative_to(ROOT)):sha256(p.read_bytes()).hexdigest() for p in files}),
        python=platform.python_version(), dependencies={p:version(p) for p in ("mcp","pydantic","jsonschema")},
        node_dependencies=sha256((ROOT/"examples/external-filesystem/package-lock.json").read_bytes()).hexdigest(),
        interpretation="A-E: fixed candidate; M1: no mapper; evaluator requires both independent probes")
    identity["fingerprint"] = fingerprint(identity)
    manifest = output/"manifest.json"
    if manifest.exists():
        if json.loads(manifest.read_bytes())["fingerprint"] != identity["fingerprint"]:
            raise ValueError("new source/configuration requires new study directory")
        if (output/"artifact-digests.json").exists():
            return read_completed(output)
    else:
        if any(output.iterdir()):
            raise ValueError("nonempty study directory without manifest")
        _atomic(manifest,dict(identity,created_at=datetime.now(timezone.utc).isoformat()))
    _atomic(output/"isolation.json",isolation_check())
    runtime = Runtime(output)
    decisions = {}
    for case in cases:
        for method in METHODS:
            path = output/f"decision-{method}-{case.case_id}.json"
            if path.exists():
                data = json.loads(path.read_bytes())
            else:
                started = perf_counter()
                before = runtime.counter
                decision = decide(case,method,runtime)
                data = dict(case_id=case.case_id,method=method,decision=decision.model_dump(),
                            latency=perf_counter()-started,source_calls=runtime.counter-before)
                _atomic(path,data)
            decisions[case.case_id,method] = data
        print("decisions",case.case_id,flush=True)
    # Эталон впервые читается после всех решений; ни Runtime, ни decide его не получают.
    gold = load_gold(DATA,DIGEST)
    records = []
    from mcp_compat import MigrationDecision
    for case in cases:
        label = gold[case.case_id]
        # Проверка ручного эталона старого обработчика отдельно от допуска кандидата.
        state = deepcopy(case.initial)
        result = runtime.implementation(case,"old",visible=False)(case.request.old_call.arguments,state)
        if canonical_bytes(dict(result=result,state=state)) != canonical_bytes(label["expected"]):
            raise ValueError("independent gold/source disagreement; preserve this run and dataset")
        for method in METHODS:
            data = decisions[case.case_id,method]
            decision = MigrationDecision.model_validate(data["decision"])
            path = output/f"0-{method}-{case.case_id}.json"
            if path.exists():
                records.append(Record.model_validate_json(path.read_bytes()))
                continue
            candidate = decision.adapted_call
            if candidate is None and "candidate" in decision.evidence:
                candidate = ToolCall.model_validate(decision.evidence["candidate"])
            valid = None
            if candidate is not None:
                try:
                    candidate.validate_against(case.request.new_contract)
                    valid = True
                except ValueError:
                    valid = False
            equivalent = evaluate(case,decision,label["expected"],runtime)
            record = Record(scenario_id=case.case_id,method=method,repeat=0,mutation_family=case.family,
                ground_truth=label["ground_truth"],recoverable=label["recoverable"],base_tool=case.project,
                composed=False,decision=decision,schema_valid=valid,semantic_equivalent=equivalent,
                latency=data["latency"],calls=0,input_tokens=0,output_tokens=0,cost=0,
                validation_stages=int(valid is not None)+decision.evidence.get("verification_attempts",int("verification" in decision.evidence))+int("admission" in decision.evidence),
                recovery=case.request.model_dump())
            _atomic(path,record.model_dump())
            records.append(record)
    _atomic(output/"result-digests.json",{f"0-{r.method}-{r.scenario_id}":fingerprint(r.model_dump()) for r in records})
    _atomic(output/"summary.json",summaries(records))
    _atomic(output/"runtime-accounting.json",dict(source_calls=runtime.counter,model_calls=0,
        notes="attempted source tool invocations include previews and evaluator probes; each worker also initializes and lists tools, these setup RPCs are not counted; failed invocations may have unknown delivery"))
    _atomic(output/"artifact-digests.json",{p.name:sha256(p.read_bytes()).hexdigest()
        for p in sorted(output.glob("*.json")) if p.name != "artifact-digests.json"})
    return records


def read_completed(output):
    hashes = json.loads((output/"artifact-digests.json").read_bytes())
    names = {p.name for p in output.glob("*.json") if p.name != "artifact-digests.json"}
    if names != hashes.keys():
        raise ValueError("incomplete study artifact set")
    for name, expected in hashes.items():
        if not re.fullmatch(r"[A-Za-z0-9_.-]+",name) or sha256((output/name).read_bytes()).hexdigest() != expected:
            raise ValueError("study artifact integrity failure")
    manifest = json.loads((output/"manifest.json").read_bytes())
    identity = {k:v for k,v in manifest.items() if k not in ("fingerprint","created_at")}
    if fingerprint(identity) != manifest["fingerprint"]:
        raise ValueError("study manifest integrity failure")
    digests = json.loads((output/"result-digests.json").read_bytes())
    expected_keys = {f"0-{method}-{sid}" for method in manifest["methods"] for sid in manifest["config"]["scenario_ids"]}
    if set(digests) != expected_keys:
        raise ValueError("incomplete result matrix")
    records = []
    for name, expected in sorted(digests.items()):
        record = Record.model_validate_json((output/(name+".json")).read_bytes())
        if fingerprint(record.model_dump()) != expected:
            raise ValueError("result digest failure")
        records.append(record)
    return records


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,default=ROOT/"experiments/external-admission-2026-11-04-v2")
    args = parser.parse_args()
    print("records",len(study(args.output)))
