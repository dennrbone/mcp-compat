"""Доверенные локальные прикладные API; эталоны оценки сюда не передаются."""

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from mcp_compat import ToolContract
from mcp_compat.hybrid import RuntimeRegistry, SandboxVerifier

VERSION = "compat-case-study-1.0"
VARIANTS = (
    "optional",
    "tool",
    "rename",
    "nested",
    "encoding",
    "enum",
    "removed",
    "semantic",
)


@dataclass(frozen=True)
class API:
    fields: dict[str, str]
    rename: tuple[str, str]
    numeric: str
    critical: str
    mode: str
    modes: tuple[str, str]
    aliases: tuple[str, str]
    description: str
    effect: bool = False
    array: bool = False


APIS = {
    "documents_words": API(
        dict(content="string", minimum_length="integer", style="string"),
        ("content", "text"),
        "minimum_length",
        "content",
        "style",
        ("all", "distinct"),
        ("every", "unique"),
        "Подсчитывает слова с ограничением минимальной длины.",
    ),
    "documents_find": API(
        dict(query="string", limit="integer", match="string"),
        ("query", "search_term"),
        "limit",
        "query",
        "match",
        ("prefix", "contains"),
        ("starts_with", "substring"),
        "Ищет названия документов в локальном каталоге.",
        array=True,
    ),
    "calendar_duration": API(
        dict(start_minute="integer", length="integer", display="string"),
        ("start_minute", "begin_minute"),
        "length",
        "start_minute",
        "display",
        ("short", "full"),
        ("brief", "verbose"),
        "Рассчитывает конец временного интервала в минутах.",
    ),
    "calendar_room": API(
        dict(room="string", seats="integer", mode="string"),
        ("room", "room_id"),
        "seats",
        "room",
        "mode",
        ("strict", "partial"),
        ("exact", "up_to_capacity"),
        "Проверяет вместимость переговорной комнаты.",
        array=True,
    ),
    "inventory_reserve": API(
        dict(sku="string", quantity="integer", fulfillment="string"),
        ("sku", "item_id"),
        "quantity",
        "sku",
        "fulfillment",
        ("ship", "pickup"),
        ("delivery", "collection"),
        "Резервирует товар в локальном состоянии склада.",
        effect=True,
    ),
    "inventory_restock": API(
        dict(sku="string", quantity="integer", reason="string"),
        ("quantity", "units"),
        "quantity",
        "quantity",
        "reason",
        ("return", "delivery"),
        ("returned", "received"),
        "Пополняет локальный склад и журнал поступлений.",
        effect=True,
        array=True,
    ),
    "messaging_enqueue": API(
        dict(recipient="string", body="string", priority="integer", channel="string"),
        ("recipient", "receiver"),
        "priority",
        "body",
        "channel",
        ("direct", "digest"),
        ("immediate", "batch"),
        "Помещает сообщение в локальную очередь.",
        effect=True,
    ),
    "messaging_revoke": API(
        dict(message_id="string", revision="integer", mode="string"),
        ("message_id", "id"),
        "revision",
        "message_id",
        "mode",
        ("soft", "hard"),
        ("mark", "remove"),
        "Отзывает сообщение в локальном хранилище.",
        effect=True,
        array=True,
    ),
    "analytics_score": API(
        dict(signal="integer", weight="integer", policy="string"),
        ("signal", "reading"),
        "weight",
        "signal",
        "policy",
        ("linear", "squared"),
        ("identity", "square"),
        "Рассчитывает взвешенную оценку сигнала.",
    ),
    "analytics_buckets": API(
        dict(samples="array", cutoff="integer", side="string"),
        ("cutoff", "threshold"),
        "cutoff",
        "samples",
        "side",
        ("above", "below"),
        ("greater", "less"),
        "Подсчитывает элементы массива по отношению к порогу.",
        array=True,
    ),
    "booking_quote": API(
        dict(nights="integer", guests="integer", plan="string"),
        ("guests", "occupants"),
        "guests",
        "nights",
        "plan",
        ("standard", "flexible"),
        ("basic", "refundable"),
        "Рассчитывает стоимость условного бронирования.",
    ),
    "booking_cancel": API(
        dict(reservation_id="string", fee="integer", notify="string"),
        ("reservation_id", "booking_id"),
        "fee",
        "fee",
        "notify",
        ("silent", "email"),
        ("none", "mail"),
        "Отменяет условную бронь в локальном состоянии.",
        effect=True,
        array=True,
    ),
}


def contract(application: str, version: str = "old") -> ToolContract:
    spec = APIS[application]
    if version not in ("old", *VARIANTS):
        raise ValueError("unknown API version")
    props: dict[str, Any] = {
        key: dict(type=value) for key, value in spec.fields.items()
    }
    for node in props.values():
        if node["type"] == "array":
            node["items"] = {"type": "integer"}
    props[spec.mode]["enum"] = list(spec.modes)
    schema: dict[str, Any] = dict(type="object", properties=props, required=list(props))
    name = application
    if version == "optional":
        props["trace_label"] = {"type": "string"}
    elif version in ("tool", "semantic"):
        name += "_v2" if version == "tool" else "_revised"
    elif version == "rename":
        old, new = spec.rename
        props[new] = props.pop(old)
        schema["required"] = [new if key == old else key for key in schema["required"]]
    elif version == "nested":
        schema = dict(
            type="object", properties=dict(payload=schema), required=["payload"]
        )
    elif version == "encoding":
        props[spec.numeric] = (
            dict(type="array", items={"type": "integer"})
            if spec.array
            else {"type": "string"}
        )
    elif version == "enum":
        props[spec.mode]["enum"] = list(spec.aliases)
    elif version == "removed":
        props.pop(spec.critical)
        schema["required"].remove(spec.critical)
    return ToolContract(
        name=name,
        description=spec.description,
        input_schema=schema,
        output_schema={"type": "object"},
        metadata={"study": VERSION},
    )


def initial(application: str) -> dict:
    if application == "inventory_reserve":
        return dict(stock={"A": 20, "B": 10}, reservations=[])
    if application == "inventory_restock":
        return dict(stock={"A": 20, "B": 10}, events=[])
    if application == "messaging_enqueue":
        return dict(queue=[])
    if application == "messaging_revoke":
        return dict(
            messages={
                "m1": dict(revision=1, deleted=False),
                "m2": dict(revision=2, deleted=False),
            },
            events=[],
        )
    if application == "booking_cancel":
        return dict(active=["r1", "r2"], cancelled=[])
    return {}


def execute(application: str, version: str, arguments: dict, state: dict) -> dict:
    spec = APIS[application]
    if version not in ("old", *VARIANTS):
        raise ValueError("unknown API version")
    a = deepcopy(arguments)
    if version == "rename":
        old, new = spec.rename
        a[old] = a.pop(new)
    elif version == "nested":
        a = a["payload"]
    elif version == "encoding":
        value = a[spec.numeric]
        if spec.array:
            if len(value) != 1:
                raise ValueError("singleton encoding required")
            value = value[0]
        a[spec.numeric] = int(value)
    elif version == "enum":
        a[spec.mode] = dict(zip(spec.aliases, spec.modes))[a[spec.mode]]
    elif version == "removed":
        kind = spec.fields[spec.critical]
        a[spec.critical] = [] if kind == "array" else 0 if kind == "integer" else ""
    result = _business(application, a, state)
    if version == "semantic":
        if spec.effect:
            state["api_audit"] = [{"revision": 2}]
        else:
            result["api_audit"] = "revision_2"
    return result


def _business(app: str, a: dict, state: dict) -> dict:
    if app == "documents_words":
        words = [
            word for word in a["content"].split() if len(word) >= a["minimum_length"]
        ]
        return dict(
            minimum_length=a["minimum_length"],
            count=len(set(words)) if a["style"] == "distinct" else len(words),
            style=a["style"],
        )
    if app == "documents_find":
        titles = ("alpha", "alphabet", "beta", "gamma", "gamma-ray")
        selected = (
            [t for t in titles if t.startswith(a["query"])]
            if a["match"] == "prefix"
            else [t for t in titles if a["query"] in t]
        )
        return dict(query=a["query"], matches=selected[: a["limit"]])
    if app == "calendar_duration":
        suffix = "min" if a["display"] == "short" else "minutes"
        return dict(
            start=a["start_minute"],
            end=a["start_minute"] + a["length"],
            label=f"{a['length']} {suffix}",
        )
    if app == "calendar_room":
        capacity = {"R1": 6, "R2": 5}.get(a["room"], 0)
        ok = capacity >= a["seats"] if a["mode"] == "strict" else capacity > 0
        assigned = (
            min(capacity, a["seats"])
            if a["mode"] == "partial"
            else a["seats"]
            if ok
            else 0
        )
        return dict(room=a["room"], available=ok, assigned=assigned)
    if app == "inventory_reserve":
        state["stock"][a["sku"]] -= a["quantity"]
        state["reservations"].append(
            dict(sku=a["sku"], quantity=a["quantity"], fulfillment=a["fulfillment"])
        )
        return dict(reserved=a["quantity"])
    if app == "inventory_restock":
        state["stock"][a["sku"]] += a["quantity"]
        state["events"].append(
            dict(sku=a["sku"], quantity=a["quantity"], reason=a["reason"])
        )
        return dict(added=a["quantity"])
    if app == "messaging_enqueue":
        state["queue"].append(
            {k: a[k] for k in ("recipient", "body", "priority", "channel")}
        )
        return dict(queued=True)
    if app == "messaging_revoke":
        message = state["messages"][a["message_id"]]
        if a["mode"] == "hard":
            del state["messages"][a["message_id"]]
        else:
            message["deleted"] = True
        state["events"].append(
            dict(id=a["message_id"], revision=a["revision"], mode=a["mode"])
        )
        return dict(revoked=True)
    if app == "analytics_score":
        value = a["signal"] if a["policy"] == "linear" else a["signal"] ** 2
        return dict(signal=a["signal"], score=value * a["weight"])
    if app == "analytics_buckets":
        count = (
            sum(x > a["cutoff"] for x in a["samples"])
            if a["side"] == "above"
            else sum(x < a["cutoff"] for x in a["samples"])
        )
        return dict(cutoff=a["cutoff"], count=count)
    if app == "booking_quote":
        return dict(
            nights=a["nights"],
            total=100 * a["nights"] * a["guests"]
            + (20 if a["plan"] == "flexible" else 0),
        )
    state["active"].remove(a["reservation_id"])
    state["cancelled"].append({k: a[k] for k in ("reservation_id", "fee", "notify")})
    return dict(cancelled=True)


def registry() -> RuntimeRegistry:
    verifiers = []
    for app, spec in APIS.items():
        for version in VARIANTS:

            def old(args, state, application=app):
                return execute(application, "old", args, state)

            def new(args, state, application=app, revision=version):
                return execute(application, revision, args, state)

            verifiers.append(
                SandboxVerifier(
                    contract(app),
                    contract(app, version),
                    old,
                    new,
                    side_effects=spec.effect,
                    initial=initial(app),
                )
            )
    return RuntimeRegistry(verifiers)
