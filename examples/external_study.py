"""Изолированные вызовы и независимая оценка набора из 200 сценариев."""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter

from external_runtime import ROOT, execute
from mcp_compat import canonical_bytes
from mcp_compat.experiments import _atomic
from mcp_compat.verification import EvidenceVerifier, fingerprint

DATA = ROOT/"benchmark/external-mcp"
DIGEST = "6ab2bfb7da1687012c70a8acac5254f571381af8cd03d0911d393ba41e010b8f"


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


def verifier(case, runtime):
    old = runtime.implementation(case, "old")
    new = runtime.implementation(case, "new")
    provenance = json.loads((DATA/"provenance.json").read_bytes())[case.project]
    wrapper = sha256(Path(__file__).read_bytes()).hexdigest()
    binding = dict(wrapper=wrapper, alteration=case.alteration, native_tool=case.request.old_contract.name)
    return EvidenceVerifier(case.request.old_contract, case.request.new_contract, old, new,
        profile=case.profile,
        handler_ids=tuple(fingerprint(dict(binding,source=provenance[era+"_commit"])) for era in ("old","new")),
        initial=case.initial, timeout=120)


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
