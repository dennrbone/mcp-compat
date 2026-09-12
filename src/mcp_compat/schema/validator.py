"""JSON Schema Draft 2020-12 validation."""

from typing import Any

from jsonschema import Draft202012Validator


def validate_schema(schema: dict[str, Any]) -> None:
    """Raise ``SchemaError`` unless schema is valid Draft 2020-12 JSON Schema."""
    Draft202012Validator.check_schema(schema)


def validate_instance(instance: object, schema: dict[str, Any]) -> None:
    """Raise ``ValidationError`` unless instance satisfies the given schema."""
    Draft202012Validator(schema).validate(instance)
