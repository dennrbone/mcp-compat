"""Tool contract domain model."""

from typing import Any

from jsonschema.exceptions import SchemaError
from pydantic import BaseModel, Field, field_validator

from mcp_compat.schema.validator import validate_schema


class ToolContract(BaseModel):
    """A tool name and its JSON Schema Draft 2020-12 contract."""

    name: str = Field(min_length=1)
    description: str | None = None
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def reject_blank_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be blank")
        return value

    @field_validator("input_schema")
    @classmethod
    def validate_input_schema(cls, value: dict[str, Any]) -> dict[str, Any]:
        try:
            validate_schema(value)
        except SchemaError as error:
            raise ValueError(f"input_schema is invalid: {error.message}") from error
        if value.get("type") != "object":
            raise ValueError("input_schema root must have type 'object'")
        return value

    @field_validator("output_schema")
    @classmethod
    def validate_output_schema(
        cls, value: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        if value is not None:
            try:
                validate_schema(value)
            except SchemaError as error:
                raise ValueError(f"output_schema is invalid: {error.message}") from error
        return value
