"""JSON Schema Draft 2020-12 validation."""

from typing import Any
from datetime import datetime
import re

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry
from referencing.exceptions import Unresolvable

from mcp_compat.schema.canonical import canonical_json


FORMATS = FormatChecker(formats=["date"])


@FORMATS.checks("date-time", raises=ValueError)
def _date_time(value: Any) -> bool:
    if not isinstance(value,str):
        return True
    # shortcut: leap seconds are rejected until trusted runtimes support them.
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-5][0-9](?:\.[0-9]+)?(?:[Zz]|[+-][0-9]{2}:[0-5][0-9])",value):
        return False
    return datetime.fromisoformat(value.upper()).utcoffset() is not None


def validate_schema(schema: dict[str, Any]) -> None:
    """Raise ``SchemaError`` unless schema is valid Draft 2020-12 JSON Schema."""
    Draft202012Validator.check_schema(schema)


def validate_instance(instance: object, schema: dict[str, Any]) -> None:
    """Raise ``ValidationError`` unless instance satisfies the given schema."""
    try:
        canonical_json(instance)
        Draft202012Validator(schema, registry=Registry(), format_checker=FORMATS).validate(instance)
    except (Unresolvable, RecursionError) as error:
        raise ValueError("unresolvable or cyclic schema reference") from error
