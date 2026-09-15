"""Tool call domain model and contract validation."""

from typing import Any

from jsonschema.exceptions import ValidationError
from pydantic import BaseModel, Field, field_validator

from mcp_compat.domain.contracts import ToolContract
from mcp_compat.schema.validator import validate_instance


class ToolCallValidationError(ValueError):
    """Raised when a tool call does not satisfy its contract."""


class ToolCall(BaseModel):
    """A named tool invocation with JSON-object arguments."""

    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any]

    @field_validator("tool_name")
    @classmethod
    def reject_blank_tool_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("tool_name must not be blank")
        return value

    def validate_against(self, contract: ToolContract) -> None:
        """Validate the tool name and arguments, raising a domain error on failure."""
        if self.tool_name != contract.name:
            raise ToolCallValidationError(
                f"tool name mismatch: expected {contract.name!r}, got {self.tool_name!r}"
            )
        try:
            validate_instance(self.arguments, contract.input_schema)
        except ValidationError as error:
            path = ".".join(map(str, error.absolute_path)) or "<root>"
            raise ToolCallValidationError(
                f"arguments are invalid at {path}: {error.message}"
            ) from error
