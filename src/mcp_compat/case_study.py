"""Прикладные сценарии и вручную рассчитанные эталоны; доступны только оценщику."""

from copy import deepcopy
from typing import Any

from mcp_compat import EvolutionScenario, ToolCall, canonical_bytes
from mcp_compat.case_study_runtime import (
    APIS,
    VARIANTS,
    VERSION,
    contract,
    execute,
    initial,
)
from mcp_compat.domain.scenarios import MutationFamily

# Эталоны заданы явно, а не вычислены обработчиками проверяемого API.
PROFILES: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {
    "documents_words": [
        (
            dict(content="a beta beta gamma", minimum_length=2, style="all"),
            dict(minimum_length=2, count=3, style="all"),
        ),
        (
            dict(content="one two two three", minimum_length=3, style="distinct"),
            dict(minimum_length=3, count=3, style="distinct"),
        ),
    ],
    "documents_find": [
        (
            dict(query="al", limit=2, match="prefix"),
            dict(query="al", matches=["alpha", "alphabet"]),
        ),
        (
            dict(query="am", limit=1, match="contains"),
            dict(query="am", matches=["gamma"]),
        ),
    ],
    "calendar_duration": [
        (
            dict(start_minute=600, length=90, display="short"),
            dict(start=600, end=690, label="90 min"),
        ),
        (
            dict(start_minute=720, length=45, display="full"),
            dict(start=720, end=765, label="45 minutes"),
        ),
    ],
    "calendar_room": [
        (
            dict(room="R1", seats=3, mode="strict"),
            dict(room="R1", available=True, assigned=3),
        ),
        (
            dict(room="R2", seats=8, mode="partial"),
            dict(room="R2", available=True, assigned=5),
        ),
    ],
    "inventory_reserve": [
        (
            dict(sku="A", quantity=3, fulfillment="ship"),
            dict(
                stock={"A": 17, "B": 10},
                reservations=[dict(sku="A", quantity=3, fulfillment="ship")],
            ),
        ),
        (
            dict(sku="B", quantity=4, fulfillment="pickup"),
            dict(
                stock={"A": 20, "B": 6},
                reservations=[dict(sku="B", quantity=4, fulfillment="pickup")],
            ),
        ),
    ],
    "inventory_restock": [
        (
            dict(sku="A", quantity=2, reason="return"),
            dict(
                stock={"A": 22, "B": 10},
                events=[dict(sku="A", quantity=2, reason="return")],
            ),
        ),
        (
            dict(sku="B", quantity=5, reason="delivery"),
            dict(
                stock={"A": 20, "B": 15},
                events=[dict(sku="B", quantity=5, reason="delivery")],
            ),
        ),
    ],
    "messaging_enqueue": [
        (
            dict(recipient="u1", body="ready", priority=1, channel="direct"),
            dict(
                queue=[dict(recipient="u1", body="ready", priority=1, channel="direct")]
            ),
        ),
        (
            dict(recipient="u2", body="later", priority=3, channel="digest"),
            dict(
                queue=[dict(recipient="u2", body="later", priority=3, channel="digest")]
            ),
        ),
    ],
    "messaging_revoke": [
        (
            dict(message_id="m1", revision=1, mode="soft"),
            dict(
                messages={
                    "m1": dict(revision=1, deleted=True),
                    "m2": dict(revision=2, deleted=False),
                },
                events=[dict(id="m1", revision=1, mode="soft")],
            ),
        ),
        (
            dict(message_id="m2", revision=2, mode="hard"),
            dict(
                messages={"m1": dict(revision=1, deleted=False)},
                events=[dict(id="m2", revision=2, mode="hard")],
            ),
        ),
    ],
    "analytics_score": [
        (dict(signal=3, weight=2, policy="linear"), dict(signal=3, score=6)),
        (dict(signal=4, weight=3, policy="squared"), dict(signal=4, score=48)),
    ],
    "analytics_buckets": [
        (dict(samples=[1, 5, 9], cutoff=4, side="above"), dict(cutoff=4, count=2)),
        (dict(samples=[2, 4, 8, 10], cutoff=8, side="below"), dict(cutoff=8, count=2)),
    ],
    "booking_quote": [
        (dict(nights=2, guests=1, plan="standard"), dict(nights=2, total=200)),
        (dict(nights=3, guests=2, plan="flexible"), dict(nights=3, total=620)),
    ],
    "booking_cancel": [
        (
            dict(reservation_id="r1", fee=5, notify="silent"),
            dict(
                active=["r2"],
                cancelled=[dict(reservation_id="r1", fee=5, notify="silent")],
            ),
        ),
        (
            dict(reservation_id="r2", fee=10, notify="email"),
            dict(
                active=["r1"],
                cancelled=[dict(reservation_id="r2", fee=10, notify="email")],
            ),
        ),
    ],
}


def generate(*, with_rules: bool) -> list[EvolutionScenario]:
    scenarios = []
    families: dict[str, MutationFamily] = dict(
        optional="C2",
        tool="C1",
        rename="C1",
        nested="C7",
        encoding="C5",
        enum="C6",
        removed="C4",
        semantic="C8",
    )
    for app, spec in APIS.items():
        for profile, (arguments, expected) in enumerate(PROFILES[app]):
            for variant in VARIANTS:
                adapted = deepcopy(arguments)
                rules: list[dict] = []
                if variant == "rename":
                    old, new = spec.rename
                    adapted[new] = adapted.pop(old)
                    rules = [dict(op="move", source=[old], target=[new])]
                elif variant == "nested":
                    adapted = dict(payload=adapted)
                    rules = [
                        dict(op="move", source=[key], target=["payload", key])
                        for key in arguments
                    ]
                elif variant == "encoding":
                    adapted[spec.numeric] = (
                        [adapted[spec.numeric]]
                        if spec.array
                        else str(adapted[spec.numeric])
                    )
                    rules = [
                        dict(
                            op="wrap" if spec.array else "string",
                            source=[spec.numeric],
                            target=[spec.numeric],
                        )
                    ]
                elif variant == "enum":
                    adapted[spec.mode] = dict(zip(spec.modes, spec.aliases))[
                        adapted[spec.mode]
                    ]
                    rules = [
                        dict(
                            op="enum",
                            source=[spec.mode],
                            target=[spec.mode],
                            values=dict(zip(spec.modes, spec.aliases)),
                        )
                    ]
                recoverable = variant not in ("removed", "semantic")
                new_contract = contract(app, variant)
                scenarios.append(
                    EvolutionScenario(
                        scenario_id=f"{app}-{profile}-{variant}",
                        old_contract=contract(app),
                        new_contract=new_contract,
                        old_call=ToolCall(tool_name=app, arguments=deepcopy(arguments)),
                        ground_truth="SAFE_AUTO"
                        if variant == "optional"
                        else "CONDITIONAL"
                        if recoverable
                        else "MUST_ABSTAIN",
                        mutation_family=families[variant],
                        mutation_subtype=variant,
                        oracle=dict(
                            expected=deepcopy(expected),
                            adapted_call=ToolCall(
                                tool_name=new_contract.name, arguments=adapted
                            ).model_dump()
                            if recoverable
                            else None,
                        ),
                        metadata=dict(
                            study=VERSION,
                            application=app,
                            api_version=variant,
                            base_tool=app,
                            composed=False,
                            recoverable=recoverable,
                            public_context=dict(rules=rules) if with_rules else {},
                        ),
                    )
                )
    return scenarios


def equivalent(scenario: EvolutionScenario, call: ToolCall) -> bool:
    try:
        call.validate_against(scenario.new_contract)
        app = scenario.metadata["application"]
        state = initial(app)
        result = execute(app, scenario.metadata["api_version"], call.arguments, state)
        observed = state if APIS[app].effect else result
        return canonical_bytes(observed) == canonical_bytes(scenario.oracle["expected"])
    except (ValueError, KeyError, TypeError, IndexError):
        return False
