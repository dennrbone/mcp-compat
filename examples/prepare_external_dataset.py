"""Однократная фиксация внешних контрактов и отдельно заданных эталонов."""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from mcp_compat import ToolCall, ToolContract, canonical_bytes
from mcp_compat.benchmark import RecoveryInput
from mcp_compat.external import ExternalCase, VERSION
from mcp_compat.verification import ObservationProfile, fingerprint

ROOT = Path(__file__).resolve().parents[1]/"benchmark/external-mcp"
ROWS = [dict(id=1, name="alpha", qty=5), dict(id=2, name="beta", qty=9)]
FILES = {"data.txt": "alpha\nbeta\ngamma\n", "other.txt": "delta\n"}


def contract(project, era, name):
    catalog = json.loads((ROOT/"catalogs"/f"{project}-{era}.json").read_bytes())
    tool = next(t for t in catalog["tools"] if t["name"] == name)
    return ToolContract(name=tool["name"], description=tool.get("description"),
                        input_schema=tool["inputSchema"], output_schema=tool.get("outputSchema"))


def prepare():
    if (ROOT/"manifest.json").exists():
        raise FileExistsError("dataset is frozen; create a new dataset version")
    cases, gold = [], {}

    def add(project, index, old_name, new_name, args, expected, initial, *, alteration="none", family="C1"):
        old, new = contract(project, "old", old_name), contract(project, "new", new_name)
        candidate = deepcopy(args)
        complete = alteration not in ("hidden_state", "external", "ambiguous")
        profile = ObservationProfile(name="external-closed-1", state_components=tuple(initial),
            complete=complete, closed_environment=alteration != "external",
            deterministic=alteration != "nondeterministic", unambiguous=alteration != "ambiguous")
        field = old.input_schema["required"][0]
        if alteration == "tool_alias":
            new.name += "_alias"
        elif alteration == "optional":
            new.input_schema["properties"]["trace"] = {"type": "string"}
        elif alteration == "required":
            new.input_schema["properties"]["region"] = {"type": "string"}
            new.input_schema["required"].append("region")
        elif alteration == "removed":
            new.input_schema["properties"].pop(field)
            new.input_schema["required"].remove(field)
            candidate.pop(field)
        elif alteration == "encoding":
            new.input_schema["properties"][field] = dict(type="array", items={"type": "string"})
            candidate[field] = [candidate[field]]
        elif alteration == "enum":
            wrong = dict(fs="other.txt", sqlite="SELECT qty FROM items WHERE id=2", calculator="1")[project]
            new.input_schema["properties"][field]["enum"] = [candidate[field], wrong]
            candidate[field] = wrong
        elif alteration == "nested":
            new.input_schema = dict(type="object", properties=dict(payload=new.input_schema), required=["payload"])
            candidate = dict(payload=candidate)
        elif alteration == "opaque":
            new.input_schema["oneOf"] = [{"required": [field]}, {"required": ["unknown"]}]
        # Поведенческие вмешательства заданы отдельно от исторических версий.
        recoverable = alteration in ("none", "tool_alias", "optional", "encoding", "enum", "nested", "opaque")
        case_id = f"{project}-{index:02}-{alteration}"
        case = ExternalCase(case_id=case_id, project=project,
            kind="historical" if alteration == "none" else "constructed", family=family,
            request=RecoveryInput(old_contract=old, new_contract=new,
                old_call=ToolCall(tool_name=old.name, arguments=args)),
            candidate=ToolCall(tool_name=new.name, arguments=candidate), initial=initial,
            alteration=alteration, profile=profile)
        cases.append(case.model_dump(mode="json"))
        gold[case_id] = dict(recoverable=recoverable,
            ground_truth="CONDITIONAL" if recoverable else "MUST_ABSTAIN",
            expected=expected, confidence="high_within_fixed_fixture",
            basis="source review and explicitly written fixture; no independent second human review")

    historical = {
        "fs": [
            ("read_file", "read_text_file", dict(path="data.txt"), [dict(type="text", text=FILES["data.txt"])]),
            ("read_file", "read_text_file", dict(path="other.txt"), [dict(type="text", text="delta\n")]),
            ("read_file", "read_text_file", dict(path="data.txt", head=1), [dict(type="text", text="alpha")]),
            ("read_file", "read_text_file", dict(path="data.txt", tail=2), [dict(type="text", text="gamma\n")]),
        ],
        "sqlite": [
            ("read-query", "read_query", dict(query="SELECT qty FROM items WHERE id=1"), [dict(qty=5)]),
            ("read-query", "read_query", dict(query="SELECT name FROM items WHERE id=2"), [dict(name="beta")]),
            ("write-query", "write_query", dict(query="UPDATE items SET qty=qty-2 WHERE id=1"), [dict(affected_rows=1)]),
            ("write-query", "write_query", dict(query="DELETE FROM items WHERE id=2"), [dict(affected_rows=1)]),
        ],
        "calculator": [
            ("calculate", "calculate", dict(expression="2.5 + 3.25"), dict(result="5.75")),
            ("calculate", "calculate", dict(expression="3 * 4"), dict(result="12")),
            ("calculate", "calculate", dict(expression="7 // 2"), dict(result="3")),
            ("calculate", "calculate", dict(expression="2 ^ 3"), dict(result="8")),
        ],
    }
    variants = [("tool_alias", "C1"), ("optional", "C2"), ("required", "C3"),
                ("removed", "C4"), ("encoding", "C5"), ("enum", "C6"), ("nested", "C7"),
                ("unit", "C8"), ("result_changed", "C8"), ("hidden_state", "C8"),
                ("external", "C8"), ("nondeterministic", "C8"), ("toctou", "C8"),
                ("opaque", "C7"), ("ambiguous", "C8"), ("lossy", "C5"), ("default_changed", "C8")]
    for project, examples in historical.items():
        initial = dict(files=FILES) if project == "fs" else dict(rows=ROWS) if project == "sqlite" else {}
        for index, (old_name, new_name, args, result) in enumerate(examples):
            after = deepcopy(initial)
            if project == "sqlite" and index == 2:
                after["rows"][0]["qty"] = 3
            if project == "sqlite" and index == 3:
                after["rows"].pop()
            add(project, index, old_name, new_name, args, dict(result=result, state=after), deepcopy(initial))
        old_name, new_name, args, result = examples[0]
        for index, (alteration, family) in enumerate(variants, 4):
            add(project, index, old_name, new_name, deepcopy(args),
                dict(result=deepcopy(result), state=deepcopy(initial)), deepcopy(initial),
                alteration=alteration, family=family)
    (ROOT/"public.json").write_bytes(canonical_bytes(cases))
    (ROOT/"gold.json").write_bytes(canonical_bytes(gold))
    files = {str(p.relative_to(ROOT)):sha256(p.read_bytes()).hexdigest()
             for p in sorted(ROOT.rglob("*")) if p.is_file()}
    manifest = dict(version=VERSION, count=len(cases), files=files,
        historical_count=12, constructed_count=len(cases)-12,
        candidate_source="manual source-based proposals, no LLM, no benchmark oracle",
        gold_source="explicit source-reviewed expected outcomes, separate evaluator file")
    manifest["digest"] = fingerprint(manifest)
    (ROOT/"manifest.json").write_bytes(canonical_bytes(manifest))
    print(manifest["digest"], len(cases))


if __name__ == "__main__":
    prepare()
