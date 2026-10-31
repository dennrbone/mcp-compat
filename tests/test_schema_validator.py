import pytest
from jsonschema.exceptions import SchemaError, ValidationError

from mcp_compat.schema import (
    canonical_bytes,
    canonical_json,
    validate_instance,
    validate_schema,
)


def test_validate_schema_and_instance() -> None:
    schema = {"type": "integer", "minimum": 1}

    assert validate_schema(schema) is None
    assert validate_instance(1, schema) is None
    with pytest.raises(ValidationError):
        validate_instance(0, schema)


def test_validate_schema_rejects_invalid_schema() -> None:
    with pytest.raises(SchemaError):
        validate_schema({"type": "not-a-json-type"})


def test_canonical_serialization_ignores_dict_order() -> None:
    first = {"b": [2, 1], "a": {"текст": "значение", "x": True}}
    second = {"a": {"x": True, "текст": "значение"}, "b": [2, 1]}

    assert canonical_json(first) == canonical_json(second)
    assert canonical_json(first) == '{"a":{"x":true,"текст":"значение"},"b":[2,1]}'
    assert canonical_bytes(first) == canonical_json(first).encode("utf-8")


def test_external_refs_never_fetch(monkeypatch):
    requests = []
    def forbidden(request):
        requests.append(request)
        raise OSError('network must not be used')
    monkeypatch.setattr('urllib.request.urlopen', forbidden)
    with pytest.raises(ValueError, match='schema reference'):
        validate_instance(1, {'$ref':'https://example.invalid/schema'})
    assert requests == []


def test_cyclic_reference_fails_safely():
    with pytest.raises(ValueError, match='schema reference'):
        validate_instance(1, {'$ref':'#/$defs/self', '$defs': {'self':{'$ref':'#/$defs/self'}}})


@pytest.mark.parametrize('number', [float('nan'),float('inf'),-float('inf')])
def test_nonfinite_values_are_not_json(number):
    with pytest.raises(ValueError):
        canonical_json({'value':number})
    with pytest.raises(ValueError):
        validate_instance({'value':number},{'type':'object','properties':{'value':{'type':'number'}}})
