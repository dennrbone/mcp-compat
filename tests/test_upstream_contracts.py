"""Regression cases from the published servers' recorded MCP catalogs."""

from collections import Counter
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from mcp_compat import SchemaDiffEngine, ToolContract

FIXTURE = Path(__file__).parent / 'fixtures/upstream-catalogs.json'
DATA = json.loads(FIXTURE.read_bytes())
ANNOTATIONS = {'$schema', '$comment', 'title', 'description', 'examples', 'example',
               'deprecated', 'readOnly', 'writeOnly'}
SCHEMA_MAPS = {'properties', 'patternProperties', '$defs', 'definitions', 'dependentSchemas'}
SCHEMA_VALUES = {'items', 'additionalProperties', 'additionalItems', 'not', 'if', 'then', 'else',
                 'contains', 'propertyNames', 'unevaluatedItems', 'unevaluatedProperties'}
SCHEMA_LISTS = {'allOf', 'anyOf', 'oneOf', 'prefixItems'}


def validation_shape(schema):
    if not isinstance(schema, dict):
        return schema
    result = {}
    for key, value in schema.items():
        if key in ANNOTATIONS:
            continue
        if key in SCHEMA_MAPS:
            value = {name: validation_shape(nested) for name, nested in value.items()}
        elif key in SCHEMA_VALUES:
            value = validation_shape(value)
        elif key in SCHEMA_LISTS:
            value = [validation_shape(item) for item in value]
        elif key in ('required', 'enum', 'type') and isinstance(value, list):
            value = sorted(value, key=lambda item: json.dumps(item, sort_keys=True))
        result[key] = value
    return result


def contract(tool):
    return ToolContract(name=tool['name'], description=tool.get('description'),
                        input_schema=tool['inputSchema'], output_schema=tool.get('outputSchema'))


@pytest.mark.parametrize('change', DATA['changes'], ids=lambda change: change['id'])
def test_published_tool_contract_change(change):
    before, after = (DATA['releases'][change[version]]['tools'][change['tool']]
                     for version in ('before', 'after'))
    assert before['name'] == after['name'] == change['tool']
    observed = [field for field in ('inputSchema', 'outputSchema')
                if validation_shape(before.get(field)) != validation_shape(after.get(field))]
    assert observed == change['fields']
    unsupported = [tool for tool in (before, after) if tool['inputSchema'].get('type') != 'object']
    if unsupported:
        assert change['analysis'] == 'invalid_input_root'
        for tool in unsupported:
            with pytest.raises(ValidationError, match="root must have type 'object'"):
                contract(tool)
        return
    difference = SchemaDiffEngine.compare(contract(before), contract(after))
    assert change['analysis'] == ('complete' if difference.is_complete else 'opaque')
    assert difference.has_changes
    for field in observed:
        prefix = 'input' if field == 'inputSchema' else 'output'
        assert any((x.path == prefix or x.path.startswith(prefix+'.') or x.path.startswith(prefix+'['))
                   and x.old_value != x.new_value for x in (*difference.changes, *difference.opaque))


def test_published_catalog_provenance_and_coverage():
    counts = Counter()
    for change in DATA['changes']:
        old, new = (DATA['releases'][change[version]] for version in ('before', 'after'))
        assert old['provenance']['package'] == new['provenance']['package']
        assert old['provenance']['dist.integrity'] != new['provenance']['dist.integrity']
        assert old['provenance']['dist.tarball'].startswith('https://registry.npmjs.org/')
        assert new['provenance']['dist.tarball'].startswith('https://registry.npmjs.org/')
        counts[change['id']] += 1
    assert len(counts) >= 50 and set(counts.values()) == {1}


@pytest.mark.parametrize(
    ('project', 'before', 'after', 'index', 'expected'),
    [
        ('filesystem', '2025.8.21', '2.3.0', 0, {'content': 'alpha\nbeta\ngamma\n'}),
        ('filesystem', '2025.8.21', '2.3.0', 1, {'content': 'alpha'}),
        ('filesystem', '2025.8.21', '2.3.0', 2, {'content': 'alpha'}),
        ('filesystem', '2025.8.21', '2.3.0', 3, {'content': '[FILE] sample.txt'}),
        ('memory', '2025.8.4', '2.1.1', 0, {'entities': [], 'relations': []}),
    ],
)
def test_published_structured_output_probes(project, before, after, index, expected):
    old, new = (DATA['releases'][f'{project}@{version}']['probes'][index] for version in (before, after))
    assert old['arguments'] == new['arguments'] and old['tool'] == new['tool']
    assert old['result']['isError'] is new['result']['isError'] is False
    assert 'structuredContent' not in old['result']
    assert new['result']['structuredContent'] == expected
    assert old['result']['content'] == new['result']['content']
    schema = DATA['releases'][f'{project}@{after}']['tools'][new['tool']]['outputSchema']
    from mcp_compat.schema import validate_instance
    validate_instance(expected, schema)
