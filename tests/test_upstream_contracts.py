"""Regression cases from the published servers' recorded MCP catalogs."""

from collections import Counter
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from mcp_compat import SchemaDiffEngine, ToolContract
from mcp_compat.benchmark import RecoveryInput

FIXTURE = Path(__file__).parent / 'fixtures/upstream-catalogs.json'
DATA = json.loads(FIXTURE.read_bytes())
HISTORICAL = FIXTURE.parents[2] / 'benchmark/external-mcp-historical'
ARGUMENTS = json.loads((HISTORICAL / 'arguments.json').read_bytes())
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


def catalog_contract(tool):
    return dict(name=tool['name'], description=tool.get('description'),
                input_schema=tool['inputSchema'], output_schema=tool.get('outputSchema'))


@pytest.mark.parametrize('change', DATA['changes'], ids=lambda change: change['id'])
def test_published_tool_contract_change(change):
    before, after = (DATA['releases'][change[version]]['tools'][change['tool']]
                     for version in ('before', 'after'))
    assert before['name'] == after['name'] == change['tool']
    observed = [field for field in ('inputSchema', 'outputSchema')
                if validation_shape(before.get(field)) != validation_shape(after.get(field))]
    assert observed == change['fields']
    raw = dict(old_contract=catalog_contract(before), new_contract=catalog_contract(after),
               old_call=dict(tool_name=change['tool'], arguments=ARGUMENTS[change['id']]))
    compatible = RecoveryInput.from_catalogs(raw, mode='compat')
    compatible.old_call.validate_against(compatible.old_contract)
    compatible.old_call.validate_against(compatible.new_contract)
    assert compatible.new_contract == ToolContract.model_validate(raw['new_contract'])
    if before['inputSchema'].get('type') != 'object':
        assert change['analysis'] == 'invalid_input_root'
        with pytest.raises(ValidationError, match="root must have type 'object'"):
            RecoveryInput.from_catalogs(raw, mode='strict')
        assert RecoveryInput.from_catalogs(raw, mode='strict', import_legacy=True) == compatible
        assert 'type' not in before['inputSchema']
        assert compatible.old_contract.input_schema == {**before['inputSchema'], 'type': 'object'}
    else:
        assert RecoveryInput.from_catalogs(raw, mode='strict') == compatible
    difference = SchemaDiffEngine.compare(compatible.old_contract, compatible.new_contract)
    if change['analysis'] != 'invalid_input_root':
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
    assert len(counts) == 23 and set(counts.values()) == {1}
    assert set(counts) == set(ARGUMENTS)
    for release_id, release in DATA['releases'].items():
        project, version = release_id.split('@')
        lock = json.loads((HISTORICAL / project / version / 'package-lock.json').read_bytes())
        provenance = release['provenance']
        package = lock['packages']['node_modules/' + provenance['package']]
        assert (package['version'], package['resolved'], package['integrity']) == (
            version, provenance['dist.tarball'], provenance['dist.integrity'])


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
