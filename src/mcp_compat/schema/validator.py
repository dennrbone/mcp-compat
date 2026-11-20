"""Validation with the contract's declared JSON Schema dialect."""

from typing import Any
from datetime import datetime
import re

from jsonschema import Draft7Validator, Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
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


def _validator(schema: dict[str, Any]) -> type[Draft7Validator] | type[Draft202012Validator]:
    dialect = schema.get("$schema", "https://json-schema.org/draft/2020-12/schema")
    if isinstance(dialect, str):
        match dialect.removesuffix("#"):
            case "http://json-schema.org/draft-07/schema":
                return Draft7Validator
            case "https://json-schema.org/draft/2020-12/schema":
                return Draft202012Validator
    raise SchemaError("unsupported JSON Schema dialect")


def validate_schema(schema: dict[str, Any]) -> None:
    """Raise ``SchemaError`` if schema or its declared dialect is unsupported."""
    _validator(schema).check_schema(schema)


def validate_instance(instance: object, schema: dict[str, Any]) -> None:
    """Raise ``ValidationError`` unless instance satisfies the given schema."""
    try:
        canonical_json(instance)
        _validator(schema)(schema, registry=Registry(), format_checker=FORMATS).validate(instance)
    except SchemaError as error:
        raise ValueError(error.message) from error
    except (Unresolvable, RecursionError) as error:
        raise ValueError("unresolvable or cyclic schema reference") from error
