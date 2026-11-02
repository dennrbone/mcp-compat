"""Trusted synthetic implementations; no evaluator, scenario labels or oracle views."""

from dataclasses import dataclass
from functools import partial
from typing import Any

from mcp_compat import ToolContract
from mcp_compat.hybrid import RuntimeRegistry, SandboxVerifier

# This business ABI is authored independently of the benchmark's interpreter.
TOOLS = {
    "commerce": ("quote", "discount", "order", "return", "cancel", "receipt"),
    "inventory": ("count", "capacity", "reserve", "release", "move", "audit"),
    "calendar": (
        "duration",
        "availability",
        "schedule",
        "reschedule",
        "delete",
        "agenda",
    ),
    "documents": ("word_count", "size", "create", "append", "archive", "search"),
    "messaging": ("length", "quota", "enqueue", "deliver", "revoke", "history"),
    "booking": ("price", "vacancies", "book", "extend", "cancel", "itinerary"),
    "analytics": ("sum", "mean", "record", "aggregate", "purge", "report"),
    "finance": ("balance", "tax", "credit", "debit", "reverse", "ledger"),
}


@dataclass(frozen=True)
class Version:
    contract: ToolContract
    layout: str = "flat"
    unit: str = "original"


def base_contract(domain: str, operation: str) -> ToolContract:
    return ToolContract(
        name=f"{domain}_{operation}",
        description=f"Synthetic {domain} {operation}; isolated state only.",
        input_schema=dict(
            type="object",
            properties=dict(
                value={"type": ["integer", "number", "null"], "semantic_unit": "RUB"},
                target={"type": "string"},
                mode={"type": "string", "enum": ["standard", "express"]},
                note={"type": "string"},
                notify={"type": "boolean"},
                legacy={"type": "boolean"},
                date={"type": "string", "format": "date"},
                duration={"type": "integer", "semantic_unit": "seconds"},
            ),
            required=["value", "target", "mode", "notify", "legacy"],
        ),
    )


def versions(old: ToolContract, domain: str) -> list[Version]:
    result = [Version(old)]

    def fresh() -> ToolContract:
        return old.model_copy(deep=True)

    def rename(fields: dict[str, str], layout: str) -> None:
        c = fresh()
        for source, target in fields.items():
            c.input_schema["properties"][target] = c.input_schema["properties"].pop(
                source
            )
            c.input_schema["required"] = [
                target if k == source else k for k in c.input_schema["required"]
            ]
        result.append(Version(c, layout))

    c = fresh()
    c.name += "_v2"
    result.append(Version(c))
    rename({"value": "amount"}, "amount")
    rename({"target": "entity_id"}, "entity")
    rename({"value": "amount", "target": "entity_id"}, "both")
    for schema in (
        {"type": "string"},
        {"type": ["string", "null"]},
        {"type": "string", "default": "local"},
    ):
        c = fresh()
        c.input_schema["properties"]["tag"] = schema
        result.append(Version(c))
    c = fresh()
    c.input_schema["properties"].pop("note")
    result.append(Version(c))
    for default in (True, False):
        c = fresh()
        c.input_schema["properties"]["region"] = {
            "type": "string",
            **({"default": domain} if default else {}),
        }
        c.input_schema["required"].append("region")
        result.append(Version(c))
    c = fresh()
    c.input_schema["required"].append("note")
    result.append(Version(c))
    for removed in ("legacy", "notify", "target", "mode", "value"):
        c = fresh()
        c.input_schema["properties"].pop(removed)
        c.input_schema["required"].remove(removed)
        result.append(Version(c))
    c = fresh()
    c.input_schema["properties"]["value"] = {"type": "integer"}
    result.append(Version(c))
    c = fresh()
    c.input_schema["properties"]["date"]["format"] = "date-time"
    result.append(Version(c))
    for options in (
        ["standard", "priority"],
        ["standard", "express", "economy"],
        ["express"],
        ["delivery"],
        ["express_air", "express_road"],
    ):
        c = fresh()
        c.input_schema["properties"]["mode"]["enum"] = options
        result.append(Version(c))
    for field in ("value", "target"):
        c = fresh()
        node = c.input_schema["properties"].pop(field)
        c.input_schema["properties"]["payload"] = dict(
            type="object", properties={field: node}, required=[field]
        )
        c.input_schema["required"] = [
            "payload" if k == field else k for k in c.input_schema["required"]
        ]
        result.append(Version(c, "nested_" + field))
    c = fresh()
    c.input_schema = dict(
        type="object",
        properties={"payload": old.model_copy(deep=True).input_schema},
        required=["payload"],
    )
    result.append(Version(c, "wrapped"))
    c = fresh()
    for field in ("value", "target"):
        c.input_schema["properties"].pop(field)
        c.input_schema["required"].remove(field)
    c.input_schema["properties"]["packed"] = {"type": "string"}
    c.input_schema["required"].append("packed")
    result.append(Version(c, "packed"))
    for field, unit, meaning in (
        ("value", "kopecks", "currency"),
        ("duration", "milliseconds", "time"),
    ):
        for composed in (False, True):
            c = fresh()
            c.input_schema["properties"][field]["semantic_unit"] = unit
            if composed:
                c.name += "_next"
            result.append(Version(c, unit=meaning))
    # String/array encodings share contract hashes with distinct implementations.
    # shortcut: bind these only when a trusted implementation revision disambiguates them.
    return result


def _business(domain: str, operation: int, record: dict, state: dict) -> dict:
    table = state.setdefault(domain, {})
    target, value, note = record["target"], record["value"] or 0, record["note"]
    if operation in (0, 1, 5):
        computations = {
            "commerce": (
                value * (2 if record["mode"] == "express" else 1),
                value * 0.9,
                {"total": value, "customer": target},
            ),
            "inventory": (
                table.get(target, {}).get("units", 0),
                100 - value,
                {"stock": table, "count": len(table)},
            ),
            "calendar": (value * 60, target not in table, sorted(table)),
            "documents": (
                len(note.split()),
                len(note.encode()),
                [key for key in table if target in key],
            ),
            "messaging": (len(note), 1000 - value, state.get("events", [])),
            "booking": (
                value * 150,
                50 - len(table),
                {"guest": target, "bookings": table},
            ),
            "analytics": (
                value,
                value / max(len(table), 1),
                {"samples": len(table), "sum": value},
            ),
            "finance": (
                table.get(target, {}).get("balance", 0),
                value * 0.2,
                {"account": target, "entries": state.get("events", [])},
            ),
        }
        return dict(
            arguments=record, result=computations[domain][(0, 1, 5).index(operation)]
        )
    if operation == 2:
        table[target] = dict(units=value, balance=value, record=record)
    elif operation == 3:
        previous = table.get(target, {}).get("balance", 0)
        table[target] = dict(units=value, balance=previous - value, record=record)
    else:
        table.pop(target, None)
    state.setdefault("events", []).append(dict(operation=operation, record=record))
    return dict(applied=True)


def _legacy(domain: str, operation: int, a: dict, state: dict) -> dict:
    record = dict(
        value=a["value"],
        target=a["target"],
        mode=a["mode"],
        notify=a["notify"],
        note=a.get("note", ""),
        date=a.get("date", ""),
        duration=a["duration"],
        region=domain,
    )
    return _business(domain, operation, record, state)


def _modern(
    domain: str, operation: int, version: Version, arguments: dict, state: dict
) -> dict:
    a = arguments["payload"] if version.layout == "wrapped" else arguments
    schema = version.contract.input_schema
    properties = (
        schema["properties"]["payload"]["properties"]
        if version.layout == "wrapped"
        else schema["properties"]
    )
    value: Any = 0
    target = "unknown"
    if version.layout == "packed":
        target, raw = a["packed"].rsplit("|", 1)
        value = int(raw)
    else:
        if version.layout == "nested_value":
            value = a["payload"]["value"]
        elif version.layout in ("amount", "both"):
            value = a["amount"]
        elif "value" in properties:
            value = a["value"]
        if version.layout == "nested_target":
            target = a["payload"]["target"]
        elif version.layout in ("entity", "both"):
            target = a["entity_id"]
        elif "target" in properties:
            target = a["target"]
    if version.unit == "currency":
        value /= 100
    duration = a["duration"] / 1000 if version.unit == "time" else a["duration"]
    mode = a["mode"] if "mode" in properties else "standard"
    if mode == "priority":
        mode = "express"
    record = dict(
        value=value,
        target=target,
        mode=mode,
        notify=a["notify"] if "notify" in properties else False,
        note=a.get("note", "") if "note" in properties else "",
        date=a.get("date", ""),
        duration=duration,
        region=a["region"] if "region" in properties else domain,
    )
    return _business(domain, operation, record, state)


def fixture_verifier() -> RuntimeRegistry:
    verifiers = []
    for domain, operations in TOOLS.items():
        for index, operation in enumerate(operations):
            old = base_contract(domain, operation)
            for version in versions(old, domain):
                verifiers.append(
                    SandboxVerifier(
                        old,
                        version.contract,
                        partial(_legacy, domain, index),
                        partial(_modern, domain, index, version),
                        side_effects=index in (2, 3, 4),
                    )
                )
    return RuntimeRegistry(verifiers)
