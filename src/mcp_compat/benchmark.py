"""Seeded synthetic corpus. Evaluation data never belongs in RecoveryInput."""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import random
import re
from typing import Any

from pydantic import BaseModel, ConfigDict

from mcp_compat import EvolutionScenario, ToolCall, ToolContract, canonical_bytes
from mcp_compat.domain.scenarios import GroundTruth, MutationFamily

VERSION = "evobench-1.2"
DOMAINS = {
    "commerce": ("quote", "discount", "order", "return", "cancel", "receipt"),
    "inventory": ("count", "capacity", "reserve", "release", "move", "audit"),
    "calendar": ("duration", "availability", "schedule", "reschedule", "delete", "agenda"),
    "documents": ("word_count", "size", "create", "append", "archive", "search"),
    "messaging": ("length", "quota", "enqueue", "deliver", "revoke", "history"),
    "booking": ("price", "vacancies", "book", "extend", "cancel", "itinerary"),
    "analytics": ("sum", "mean", "record", "aggregate", "purge", "report"),
    "finance": ("balance", "tax", "credit", "debit", "reverse", "ledger"),
}
SUBTYPES: dict[MutationFamily, tuple[str, ...]] = {
    "C1": ("tool_rename", "value_rename", "target_rename", "two_renames", "ambiguous_rename"),
    "C2": ("optional_added", "unused_removed", "used_removed", "optional_nullable", "optional_default"),
    "C3": ("required_default", "required_unknown", "optional_required_present", "optional_required_missing", "required_derived"),
    "C4": ("required_redundant_removed", "notification_removed", "target_removed", "mode_removed", "value_removed"),
    "C5": ("integer_string", "scalar_array", "nullable_removed", "number_decimal_string", "format_changed"),
    "C6": ("enum_rename", "enum_add", "enum_remove_unused", "enum_merge", "enum_split"),
    "C7": ("nest_value", "nest_target", "wrap", "split_value", "merge_target_value"),
    "C8": ("rub_kopecks", "seconds_milliseconds", "gross_net_unknown", "delete_deactivate", "changed_notification"),
}


class RecoveryInput(BaseModel):
    """Only observable contracts/call and separately allowlisted context."""

    model_config = ConfigDict(extra="forbid")
    old_contract: ToolContract
    new_contract: ToolContract
    old_call: ToolCall
    context: dict[str, Any] = {}


def recovery_input(scenario: EvolutionScenario) -> RecoveryInput:
    return RecoveryInput(
        old_contract=scenario.old_contract.model_copy(deep=True),
        new_contract=scenario.new_contract.model_copy(deep=True),
        old_call=scenario.old_call.model_copy(deep=True),
        context=deepcopy(scenario.metadata.get("public_context", {})),
    )


def _schema(properties: dict, required: list[str]) -> dict:
    return dict(type="object", properties=properties, required=required)


def _case(domain: str, operation: str, index: int, family: MutationFamily, variant: int, rng: random.Random) -> EvolutionScenario:
    value = rng.randint(2, 90)
    target = f"{domain}-{rng.randrange(100000):05}"
    props = {"value": {"type": ["integer", "number", "null"],"semantic_unit":"RUB"}, "target": {"type": "string"},
             "mode": {"type": "string", "enum": ["standard", "express"]},
             "note": {"type": "string"}, "notify": {"type": "boolean"},
             "legacy": {"type":"boolean"}, "date":{"type":"string","format":"date"},
             "duration":{"type":"integer","semantic_unit":"seconds"}}
    args: dict[str, Any] = dict(value=value, target=target, mode="express", notify=True, legacy=True, duration=value+60)
    old = ToolContract(name=f"{domain}_{operation}", description=f"Synthetic {domain} {operation}; isolated state only.",
                       input_schema=_schema(props, ["value", "target", "mode", "notify", "legacy"]))
    new = old.model_copy(deep=True)
    p = new.input_schema["properties"]
    required = new.input_schema["required"]
    expected: Any = deepcopy(args)
    old_view: dict[str, Any] = {key: {"path": [key]} for key in args}
    old_view.pop("legacy")
    old_view.update(note={"path":["note"],"default":""},date={"path":["date"],"default":""},
                    region={"constant":domain},source={"constant":"private-source"})
    new_view = deepcopy(old_view)
    truth: GroundTruth = "CONDITIONAL"
    rules: list[dict] = []

    def rename(source: str, dest: str) -> None:
        p[dest] = p.pop(source)
        required[required.index(source)] = dest
        expected[dest] = expected.pop(source)
        new_view[source] = {"path": [dest]}
        rules.append(dict(op="move", source=[source], target=[dest]))

    def remove(key: str, default: Any) -> None:
        p.pop(key)
        if key in required:
            required.remove(key)
        expected.pop(key, None)
        new_view[key] = {"constant": default}

    if family == "C1":
        if variant == 0:
            new.name += "_v2"
        elif variant == 1:
            rename("value", "amount")
        elif variant == 2:
            rename("target", "entity_id")
        elif variant == 3:
            rename("value", "amount")
            rename("target", "entity_id")
        else:
            rename("target", "destination")
            p["source"] = {"type": "string"}
            required.append("source")
            new_view["source"] = {"path": ["source"]}
            truth = "MUST_ABSTAIN"
    elif family == "C2":
        truth = "SAFE_AUTO"
        if variant in (0, 3, 4):
            p["tag"] = {"type": ["string", "null"] if variant == 3 else "string"}
            if variant == 4:
                p["tag"]["default"] = "local"
        else:
            if variant == 2:
                args["note"] = expected["note"] = "retain this audit note"
                old_view["note"] = {"path": ["note"]}
                truth = "MUST_ABSTAIN"
            remove("note", "")
    elif family == "C3":
        if variant in (0, 1, 4):
            p["region"] = {"type": "string"}
            required.append("region")
            new_view["region"] = {"path": ["region"]}
            if variant == 0:
                old_view["region"] = {"constant": domain}
                p["region"]["default"] = domain
                expected["region"] = domain
                rules.append(dict(op="set", target=["region"], value=domain))
            elif variant == 4:
                old_view["region"] = {"constant": domain}
                expected["region"] = domain
                rules.append(dict(op="set", target=["region"], value=domain))
            else:
                old_view["region"] = {"constant": domain}
                truth = "MUST_ABSTAIN"
        else:
            required.append("note")
            new_view["note"] = {"path": ["note"]}
            if variant == 2:
                args["note"] = expected["note"] = "explicit note"
                old_view["note"] = new_view["note"] = {"path": ["note"]}
            else:
                truth = "MUST_ABSTAIN"
    elif family == "C4":
        if variant == 0:
            p.pop("legacy")
            required.remove("legacy")
            expected.pop("legacy")
        else:
            key = ("notify", "target", "mode", "value")[variant - 1]
            remove(key, {"notify": False, "target": "unknown", "mode": "standard", "value": 0}[key])
            truth = "MUST_ABSTAIN"
    elif family == "C5":
        if variant in (0, 3):
            p["value"] = {"type": "string"}
            expected["value"] = str(value)
            new_view["value"]["decode"] = "integer"
            rules.append(dict(op="string", source=["value"], target=["value"]))
            if variant == 3:
                args["value"] = value + .25
                expected["value"] = str(args["value"])
                new_view["value"]["decode"] = "decimal"
        elif variant == 1:
            p["value"] = {"type": "array", "items": {"type": "integer"}}
            expected["value"] = [value]
            new_view["value"]["decode"] = "singleton"
            rules.append(dict(op="wrap", source=["value"], target=["value"]))
        elif variant == 2:
            p["value"] = {"type":"integer"}
            args["value"] = None
            truth = "MUST_ABSTAIN"
        else:
            args["date"] = "2026-01-01"
            p["date"]["format"] = "date-time"
            truth = "MUST_ABSTAIN"
    elif family == "C6":
        if variant == 0:
            p["mode"]["enum"] = ["standard", "priority"]
            expected["mode"] = "priority"
            new_view["mode"]["decode"] = "priority"
            rules.append(dict(op="enum", source=["mode"], target=["mode"], values={"express": "priority", "standard": "standard"}))
        elif variant == 1:
            p["mode"]["enum"].append("economy")
            truth = "SAFE_AUTO"
        elif variant == 2:
            p["mode"]["enum"] = ["express"]
            truth = "SAFE_AUTO"
        else:
            p["mode"]["enum"] = ["delivery"] if variant == 3 else ["express_air", "express_road"]
            truth = "MUST_ABSTAIN"
    elif family == "C7":
        if variant in (0, 1):
            key = "value" if variant == 0 else "target"
            p["payload"] = _schema({key: p.pop(key)}, [key])
            required[required.index(key)] = "payload"
            expected["payload"] = {key: expected.pop(key)}
            new_view[key] = {"path": ["payload", key]}
            rules.append(dict(op="move", source=[key], target=["payload", key]))
        elif variant == 2:
            new.input_schema = _schema({"payload": deepcopy(old.input_schema)}, ["payload"])
            expected = {"payload": expected}
            for spec in new_view.values():
                if "path" in spec:
                    spec["path"].insert(0,"payload")
            for key in args:
                rules.append(dict(op="move", source=[key], target=["payload", key]))
        elif variant == 3:
            p["value"] = {"type": "array", "items": {"type": "integer"}}
            expected["value"] = [value // 2, value - value // 2]
            new_view["value"]["decode"] = "sum"
            rules.append(dict(op="wrap", source=["value"], target=["value"]))
        else:
            remove("value", 0)
            remove("target", "")
            p["packed"] = {"type": "string"}
            required.append("packed")
            expected["packed"] = f"{target}|{value}"
            new_view["value"] = {"path": ["packed"], "decode": "packed_value"}
            new_view["target"] = {"path": ["packed"], "decode": "packed_target"}
            truth = "MUST_ABSTAIN"
    else:
        if variant < 2:
            factor = 100 if variant == 0 else 1000
            key = "value" if variant == 0 else "duration"
            p[key]["semantic_unit"] = "kopecks" if variant == 0 else "milliseconds"
            expected[key] = args[key] * factor
            new_view[key]["divisor"] = factor
            rules.append(dict(op="scale", source=[key], target=[key], factor=factor))
        else:
            new.metadata["semantic_unit"] = ("net", "deactivated", "silent")[variant-2]
            truth = "MUST_ABSTAIN"
            new_view["notify"] = {"constant": False}
    if truth == "MUST_ABSTAIN":
        expected = None
        rules = []
    old_call = ToolCall(tool_name=old.name, arguments=args)
    old_call.validate_against(old)
    expected_call = None if expected is None else ToolCall(tool_name=new.name, arguments=expected)
    if expected_call is not None:
        expected_call.validate_against(new)
    return EvolutionScenario(
        scenario_id=f"{domain}-{index}-{family}-{variant}", old_contract=old, new_contract=new,
        old_call=old_call, mutation_family=family, mutation_subtype=SUBTYPES[family][variant],
        ground_truth=truth, oracle=dict(old_view=old_view, new_view=new_view, operation=index, domain=domain,
            expected_call=None if expected_call is None else expected_call.model_dump()),
        metadata=dict(domain=domain, base_tool=old.name, composed=False,
            recoverable=truth != "MUST_ABSTAIN", public_context={"rules": rules}),
    )


def generate(seed: int = 42) -> list[EvolutionScenario]:
    rng = random.Random(seed)
    scenarios = []
    for domain, operations in DOMAINS.items():
        for index, operation in enumerate(operations):
            for family in SUBTYPES:
                for variant in range(5):
                    scenarios.append(_case(domain, operation, index, family, variant, rng))
            for variant in range(5):
                s = _case(domain, operation, index, "C8", variant, rng)
                s.scenario_id += "-composed"
                s.new_contract.name += "_next"
                if s.oracle["expected_call"] is not None:
                    s.oracle["expected_call"]["tool_name"] = s.new_contract.name
                s.metadata.update(composed=True, families=["C1", "C8"])
                scenarios.append(s)
    return scenarios


def _view(arguments: dict, view: dict) -> dict:
    result = {}
    for key, spec in view.items():
        if "constant" in spec:
            value = spec["constant"]
        else:
            value = arguments
            for segment in spec["path"]:
                if segment not in value and "default" in spec:
                    value = spec["default"]
                    break
                value = value[segment]
        decode = spec.get("decode")
        if decode == "integer":
            value = int(value)
        elif decode == "decimal":
            value = float(value)
        elif decode == "singleton":
            if len(value) != 1:
                raise ValueError("expected singleton")
            value = value[0]
        elif decode == "sum":
            value = sum(value)
        elif decode == "priority":
            value = "express" if value == "priority" else value
        elif decode == "packed_value":
            value = int(value.rsplit("|", 1)[1])
        elif decode == "packed_target":
            value = value.rsplit("|", 1)[0]
        if "divisor" in spec:
            value /= spec["divisor"]
        result[key] = value
    # Equal JSON numbers normalize to the same representation, independently of schema validation.
    for key,value in result.items():
        if isinstance(value, float) and value.is_integer():
            result[key] = int(value)
    return result


def simulate(arguments: dict, view: dict, operation: int, initial: dict, domain: str = "commerce") -> dict:
    """Six toy operations per domain; never perform network or external writes."""
    record = _view(arguments, view)
    state = deepcopy(initial)
    value, target = record.get("value") or 0, record.get("target", "")
    note = record.get("note", "")
    records = state.setdefault(domain, {})
    if operation in (0, 1, 5):
        results = {
            "commerce": (value * (2 if record.get("mode") == "express" else 1), value * .9, {"total": value, "customer": target}),
            "inventory": (records.get(target, {}).get("units", 0), 100 - value, {"stock": records, "count": len(records)}),
            "calendar": (value * 60, target not in records, sorted(records)),
            "documents": (len(note.split()), len(note.encode("utf-8")), [k for k in records if target in k]),
            "messaging": (len(note), 1000 - value, state.get("events", [])),
            "booking": (value * 150, 50 - len(records), {"guest": target, "bookings": records}),
            "analytics": (value, value / max(len(records), 1), {"samples": len(records), "sum": value}),
            "finance": (records.get(target, {}).get("balance", 0), value * .2, {"account": target, "entries": state.get("events", [])}),
        }
        return {"intent": record, "result": results[domain][(0, 1, 5).index(operation)]}
    if operation == 2:
        records[target] = {"units": value, "balance": value, "record": record}
    elif operation == 3:
        previous = records.get(target, {}).get("balance", 0)
        records[target] = {"units": value, "balance": previous - value, "record": record}
    else:
        records.pop(target, None)
    state.setdefault("events", []).append({"operation": operation, "record": record})
    return state


def equivalent(scenario: EvolutionScenario, call: ToolCall) -> bool:
    """Evaluator-only oracle; called after a strategy's decision."""
    try:
        call.validate_against(scenario.new_contract)
        o = scenario.oracle
        before = simulate(scenario.old_call.arguments, o["old_view"], o["operation"], {}, o["domain"])
        after = simulate(call.arguments, o["new_view"], o["operation"], {}, o["domain"])
        return canonical_bytes(before) == canonical_bytes(after)
    except (ValueError, KeyError, TypeError, IndexError):
        return False


def freeze(scenarios: list[EvolutionScenario], directory: Path, seed: int) -> str:
    """Exclusive creation: never overwrite a frozen benchmark."""
    directory.mkdir(parents=True, exist_ok=False)
    hashes: dict[str, dict[str, str]] = {}
    for s in scenarios:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", s.scenario_id) or s.scenario_id in hashes:
            raise ValueError("invalid or duplicate scenario id")
        folder = directory / s.scenario_id
        folder.mkdir()
        payloads = {"old_tool": s.old_contract.model_dump(), "new_tool": s.new_contract.model_dump(),
                    "old_call": s.old_call.model_dump(), "oracle": s.oracle,
                    "metadata": dict(s.metadata, scenario_id=s.scenario_id, ground_truth=s.ground_truth,
                                     mutation_family=s.mutation_family, mutation_subtype=s.mutation_subtype)}
        hashes[s.scenario_id] = {}
        for name, payload in payloads.items():
            data = canonical_bytes(payload)
            (folder / f"{name}.json").write_bytes(data)
            hashes[s.scenario_id][name] = sha256(data).hexdigest()
    manifest = dict(version=VERSION, seed=seed, count=len(scenarios), files=hashes)
    digest = sha256(canonical_bytes(manifest)).hexdigest()
    manifest["digest"] = digest
    (directory / "manifest.json").write_bytes(canonical_bytes(manifest))
    return digest


def load(directory: Path, expected_digest: str) -> list[EvolutionScenario]:
    manifest = json.loads((directory / "manifest.json").read_bytes())
    hashes = manifest["files"]
    content = {key: value for key, value in manifest.items() if key != "digest"}
    if manifest["version"] not in ("evobench-1.0", "evobench-1.1", VERSION) or sha256(canonical_bytes(content)).hexdigest() != expected_digest or manifest["digest"] != expected_digest:
        raise ValueError("manifest integrity failure")
    scenarios = []
    for sid, files in sorted(hashes.items()):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", sid):
            raise ValueError("invalid scenario id")
        payloads = {}
        if set(files) != {"old_tool", "new_tool", "old_call", "oracle", "metadata"}:
            raise ValueError("invalid file set")
        for name, digest in files.items():
            path = directory / sid / f"{name}.json"
            data = path.read_bytes()
            if path.is_symlink() or path.parent.is_symlink() or sha256(data).hexdigest() != digest:
                raise ValueError("scenario integrity failure")
            payloads[name] = json.loads(data)
        m = payloads["metadata"]
        s = EvolutionScenario(scenario_id=m.pop("scenario_id"), ground_truth=m.pop("ground_truth"),
            mutation_family=m.pop("mutation_family"), mutation_subtype=m.pop("mutation_subtype"),
            metadata=m, old_contract=payloads["old_tool"], new_contract=payloads["new_tool"],
            old_call=payloads["old_call"], oracle=payloads["oracle"])
        if s.scenario_id != sid:
            raise ValueError("scenario id mismatch")
        s.old_call.validate_against(s.old_contract)
        scenarios.append(s)
    if len(scenarios) != manifest["count"]:
        raise ValueError("scenario count mismatch")
    return scenarios
