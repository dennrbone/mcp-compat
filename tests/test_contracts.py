import pytest
from pydantic import ValidationError

from mcp_compat import ToolContract


def input_schema() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$defs": {"positiveInteger": {"type": "integer", "minimum": 1}},
        "type": "object",
        "properties": {
            "quantity": {"$ref": "#/$defs/positiveInteger"},
            "destination": {
                "oneOf": [
                    {"type": "string", "minLength": 1},
                    {
                        "type": "object",
                        "properties": {"warehouse_id": {"type": "integer"}},
                        "required": ["warehouse_id"],
                    },
                ]
            },
        },
        "required": ["quantity"],
        "additionalProperties": False,
    }


def test_valid_tool_contract() -> None:
    contract = ToolContract(name="reserve_stock", input_schema=input_schema())

    assert contract.description is None
    assert contract.output_schema is None
    assert contract.metadata == {}


@pytest.mark.parametrize("name", ["", "   "])
def test_empty_tool_name_is_rejected(name: str) -> None:
    with pytest.raises(ValidationError):
        ToolContract(name=name, input_schema=input_schema())


def test_invalid_input_schema_is_rejected() -> None:
    with pytest.raises(ValidationError, match="input_schema is invalid"):
        ToolContract(name="broken", input_schema={"type": "not-a-json-type"})


def test_non_object_input_schema_is_rejected() -> None:
    with pytest.raises(ValidationError, match="root must have type 'object'"):
        ToolContract(name="broken", input_schema={"type": "array"})


def test_legacy_draft_seven_contract_checks_arguments() -> None:
    from mcp_compat import SchemaDiffEngine, ToolCall, ToolCallValidationError

    schema = {"$schema": "http://json-schema.org/draft-07/schema#",
              "properties": {"point": {"items": [{"type": "integer"}], "additionalItems": False}}}
    raw = dict(name="legacy", input_schema=schema)
    with pytest.raises(ValidationError, match="root must have type 'object'"):
        ToolContract.model_validate(raw)
    contract = ToolContract.from_legacy(raw)
    assert contract.input_schema == {**schema, "type": "object"} and "type" not in schema
    ToolCall(tool_name="legacy", arguments={"point": [1]}).validate_against(contract)
    with pytest.raises(ToolCallValidationError):
        ToolCall(tool_name="legacy", arguments={"point": [1, 2]}).validate_against(contract)
    with pytest.raises(ValidationError, match="unsupported JSON Schema dialect"):
        ToolContract.from_legacy(dict(name="legacy", input_schema={"$schema": "urn:unknown"}))
    assert not SchemaDiffEngine.compare(contract, contract).is_complete


def test_valid_output_schema() -> None:
    contract = ToolContract(
        name="reserve_stock",
        input_schema=input_schema(),
        output_schema={
            "$defs": {"id": {"type": "string"}},
            "$ref": "#/$defs/id",
        },
    )

    assert contract.output_schema == {
        "$defs": {"id": {"type": "string"}},
        "$ref": "#/$defs/id",
    }


def test_invalid_output_schema_is_rejected() -> None:
    with pytest.raises(ValidationError, match="output_schema is invalid"):
        ToolContract(
            name="broken",
            input_schema=input_schema(),
            output_schema={"type": "not-a-json-type"},
        )
