import pytest
from pydantic import ValidationError

from mcp_compat import EvolutionScenario, ToolCall, ToolContract, canonical_json


def make_scenario(**changes: str) -> EvolutionScenario:
    contract = ToolContract(
        name="reserve_stock",
        input_schema={
            "type": "object",
            "properties": {"quantity": {"type": "integer"}},
            "required": ["quantity"],
        },
    )
    values = {
        "scenario_id": "c1-rename-001",
        "old_contract": contract,
        "new_contract": contract,
        "old_call": ToolCall(tool_name="reserve_stock", arguments={"quantity": 2}),
        "ground_truth": "SAFE_AUTO",
        "mutation_family": "C1",
        "mutation_subtype": "rename_parameter",
        "oracle": {"expected": {"amount": 2}},
    }
    values.update(changes)
    return EvolutionScenario.model_validate(values)


def test_valid_evolution_scenario() -> None:
    scenario = make_scenario()

    assert scenario.ground_truth == "SAFE_AUTO"
    assert scenario.mutation_family == "C1"
    assert scenario.metadata == {}


def test_invalid_ground_truth() -> None:
    with pytest.raises(ValidationError):
        make_scenario(ground_truth="UNSAFE")


def test_invalid_mutation_family() -> None:
    with pytest.raises(ValidationError):
        make_scenario(mutation_family="C9")


@pytest.mark.parametrize(
    "model",
    [
        ToolContract(name="tool", input_schema={"type": "object"}),
        ToolCall(tool_name="tool", arguments={"value": "данные"}),
        make_scenario(),
    ],
)
def test_json_round_trip(model: object) -> None:
    restored = type(model).model_validate_json(model.model_dump_json())

    assert restored == model
    assert canonical_json(restored.model_dump(mode="json")) == canonical_json(
        model.model_dump(mode="json")
    )
