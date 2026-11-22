"""Парная проверка propertyNames и patternProperties в strict и compat."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Callable

from hybrid_study import provider
from mcp_compat import ToolCall, ToolContract, canonical_bytes
from mcp_compat.benchmark import RecoveryInput
from mcp_compat.hybrid import Hybrid
from mcp_compat.llm import Mapper
from mcp_compat.verification import EvidenceVerifier, ObservationProfile


@dataclass(frozen=True)
class Case:
    name: str
    keyword: str
    request: RecoveryInput
    old: Callable[[dict, dict], object]
    new: Callable[[dict, dict], object]
    state_components: tuple[str, ...]
    recoverable: bool
    handlers: tuple[str, str]


def synthetic_cases():
    def case(name, keyword, arguments, new_rule, *, old_rule=None, outcome="equal",
             old_key=None, new_key=None, wrap=False, recoverable=True):
        def contract(rule):
            return ToolContract(name="record_measurement", input_schema={
                "type": "object", "required": ["data"],
                "properties": {"data": {"type": "object", **rule}},
            })

        def observe(key, unwrap=False, diff="equal"):
            def call(args, state):
                data = args["data"]
                if key is not None:
                    result = data[key]
                    if unwrap:
                        result = result[0]
                else:
                    result = data
                state["records"] = 2 if diff == "state" else 1
                return {"measurement": result, "status": "changed" if diff == "result" else "ok"}
            return call

        old, new = contract(old_rule or {}), contract(new_rule)
        request = RecoveryInput(old_contract=old, new_contract=new,
                                old_call=ToolCall(tool_name=old.name, arguments={"data": arguments}))
        return Case(name, keyword, request, observe(old_key), observe(new_key, wrap, outcome),
                    ("records",), recoverable, ("before:" + name, "after:" + name))

    names = {"propertyNames": {"pattern": "^[a-z][a-z0-9_]*$"}}
    counts = {"patternProperties": {"^m_[0-9]+$": {"type": "integer"}}, "additionalProperties": False}
    return [
        case("names_keep", "propertyNames", {"rack_12": 3}, names),
        case("names_rename", "propertyNames", {"rack_code": "T2"}, {
            "properties": {"rack_code_v2": {"type": "string", "description": "Same rack code previously provided as rack_code"}},
            "propertyNames": {"enum": ["rack_code_v2"]}, "required": ["rack_code_v2"],
        }, old_key="rack_code", new_key="rack_code_v2"),
        case("names_reject", "propertyNames", {"Invalid!": 3}, names, recoverable=False),
        case("names_changed_result", "propertyNames", {"rack_12": 3}, names, outcome="result", recoverable=False),
        case("patterns_keep", "patternProperties", {"m_42": 7}, counts),
        case("patterns_wrap", "patternProperties", {"slot_7": "gold"}, {
            "patternProperties": {"^slot_[0-9]+$": {"type": "array", "items": {"type": "string"}}},
            "additionalProperties": False,
        }, old_rule={"patternProperties": {"^slot_[0-9]+$": {"type": "string"}}},
            old_key="slot_7", new_key="slot_7", wrap=True),
        case("patterns_reject", "patternProperties", {"m_42": "unknown"}, counts, recoverable=False),
        case("patterns_changed_state", "patternProperties", {"m_42": 7}, counts, outcome="state", recoverable=False),
    ]


def observed(implementation, arguments):
    state = {}
    result = implementation(deepcopy(arguments), state)
    return canonical_bytes({"result": result, "state": state})


def run_case(case, mode, mapper=None):
    request = case.request.model_copy(deep=True)
    checker = EvidenceVerifier(request.old_contract, request.new_contract, case.old, case.new,
        profile=ObservationProfile(name=case.name, state_components=case.state_components,
            complete=True, closed_environment=True, deterministic=True, unambiguous=True),
        handler_ids=case.handlers, timeout=60)
    decision = Hybrid(mapper, checker, mode=mode, current_state=dict).recover(request)
    llm = decision.evidence.get("llm", {})
    equal = None
    if decision.adapted_call is not None:
        assert decision.evidence["admission"]["passed"]
        observations = {
            observed(implementation, call.arguments)
            for _ in range(2)
            for implementation, call in ((case.old, request.old_call), (case.new, decision.adapted_call))
        }
        equal = len(observations) == 1
    return {
        "case": case.name, "keyword": case.keyword, "action": decision.action, "reason": decision.reasons[0],
        "recoverable": case.recoverable, "confirmed": equal, "source": decision.evidence.get("candidate_source"),
        "requests": llm.get("calls", 0), "responses": len(llm.get("responses", [])),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=("synthetic", "published"), required=True)
    parser.add_argument("--provider", choices=("none", "terra", "codeagent"), default="none")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.dataset == "published":
        from published_schema_keywords import published_cases
        cases = published_cases()
    else:
        cases = synthetic_cases()
    if args.provider == "none":
        mapper, model, cli = None, None, None
    else:
        client, model, cli = provider(args.provider)
        mapper = Mapper(client, attempts=2, timeout=120)
    rows = {}
    for mode in ("strict", "compat"):
        with ThreadPoolExecutor(max_workers=3) as pool:
            rows[mode] = list(pool.map(lambda case: run_case(case, mode, mapper), cases))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(
        {"dataset": args.dataset, "provider": args.provider, "model": model, "cli": cli, "rows": rows},
        ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
