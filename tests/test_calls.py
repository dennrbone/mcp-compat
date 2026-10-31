import pytest
from pydantic import ValidationError

from mcp_compat import ToolCall, ToolCallValidationError, ToolContract


@pytest.fixture
def contract() -> ToolContract:
    return ToolContract(
        name="reserve_stock",
        input_schema={
            "type": "object",
            "properties": {"quantity": {"type": "integer", "minimum": 1}},
            "required": ["quantity"],
            "additionalProperties": False,
        },
    )


def test_valid_tool_call(contract: ToolContract) -> None:
    call = ToolCall(tool_name="reserve_stock", arguments={"quantity": 2})

    assert call.validate_against(contract) is None


@pytest.mark.parametrize("tool_name", ["", "\t"])
def test_blank_tool_call_name_is_rejected(tool_name: str) -> None:
    with pytest.raises(ValidationError):
        ToolCall(tool_name=tool_name, arguments={})


def test_wrong_tool_name(contract: ToolContract) -> None:
    call = ToolCall(tool_name="release_stock", arguments={"quantity": 2})

    with pytest.raises(ToolCallValidationError, match="tool name mismatch"):
        call.validate_against(contract)


def test_missing_required_argument(contract: ToolContract) -> None:
    call = ToolCall(tool_name="reserve_stock", arguments={})

    with pytest.raises(ToolCallValidationError, match=r"at <root>.*required"):
        call.validate_against(contract)


def test_wrong_argument_type(contract: ToolContract) -> None:
    call = ToolCall(tool_name="reserve_stock", arguments={"quantity": "two"})

    with pytest.raises(ToolCallValidationError, match=r"at quantity.*integer"):
        call.validate_against(contract)


def test_broken_ref_is_domain_error():
    contract = ToolContract(name='t', input_schema={'type':'object','properties':{'x':{'$ref':'#/$defs/missing'}}})
    with pytest.raises(ToolCallValidationError, match='schema reference'):
        ToolCall(tool_name='t', arguments={'x':1}).validate_against(contract)
