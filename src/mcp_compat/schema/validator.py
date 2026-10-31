"""JSON Schema Draft 2020-12 validation."""

from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry
from referencing.exceptions import Unresolvable


def validate_schema(schema: dict[str, Any]) -> None:
    """Raise ``SchemaError`` unless schema is valid Draft 2020-12 JSON Schema."""
    Draft202012Validator.check_schema(schema)


def validate_instance(instance: object, schema: dict[str, Any]) -> None:
    """Raise ``ValidationError`` unless instance satisfies the given schema."""
    try:
        Draft202012Validator(schema, registry=Registry()).validate(instance)
    except (Unresolvable, RecursionError) as error:
        raise ValueError("unresolvable or cyclic schema reference") from error
