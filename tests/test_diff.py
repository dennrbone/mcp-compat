from copy import deepcopy

import pytest

from mcp_compat import SchemaDiff, SchemaDiffEngine, ToolContract, canonical_bytes


def contract(properties=None, required=None, **schema):
    return ToolContract(name='t', input_schema=dict(type='object', properties=properties or {}, required=required or [], **schema))


def compare(old, new):
    return SchemaDiffEngine.compare(old, new)


def signatures(diff):
    return [(c.family, c.subtype, c.path) for c in diff.changes]


def test_no_changes_and_serialization():
    old = contract({'a': {'type': ['string', 'null'], 'enum': ['b', 'a', None]}})
    new = contract({'a': {'enum': [None, 'a', 'b'], 'type': ['null', 'string']}})
    diff = compare(old, new)
    assert diff.changes == [] and not diff.has_changes and diff.is_complete
    assert canonical_bytes(diff.model_dump()) == canonical_bytes(compare(old, new).model_dump())
    assert SchemaDiff.model_validate_json(diff.model_dump_json()) == diff
    assert not compare(contract({'a': {'type': 'string'}}), contract({'a': {'type': ['string']}})).has_changes


def test_tool_rename():
    old = contract()
    assert signatures(compare(old, old.model_copy(update={'name': 'next'}))) == [('C1', 'tool_renamed', 'name')]


@pytest.mark.parametrize('old,new,family,subtype', [
    (contract(), contract({'x': {}}), 'C2', 'parameter_added'),
    (contract({'x': {}}), contract(), 'C2', 'parameter_removed'),
    (contract(), contract({'x': {}}, ['x']), 'C3', 'parameter_added'),
    (contract({'x': {}}, ['x']), contract(), 'C4', 'parameter_removed'),
    (contract({'x': {}}), contract({'x': {}}, ['x']), 'C3', 'required_changed'),
    (contract({'x': {}}, ['x']), contract({'x': {}}), 'C3', 'required_changed'),
    (contract(), contract(required=['unlisted']), 'C3', 'required_changed'),
])
def test_parameter_evolution(old, new, family, subtype):
    diff = compare(old, new)
    assert len(diff.changes) == 1
    assert (diff.changes[0].family, diff.changes[0].subtype) == (family, subtype)
    assert diff.has_changes


@pytest.mark.parametrize('old,new,family,subtype', [
    ({'type':'integer'}, {'type':'string'}, 'C5', 'type_changed'),
    ({'type':'string'}, {'type':['string','null']}, 'C5', 'nullable_changed'),
    ({'type':['string','null']}, {'type':'string'}, 'C5', 'nullable_changed'),
    ({'format':'date'}, {'format':'date-time'}, 'C5', 'format_changed'),
    ({'type':'string'}, {'type':'array'}, 'C5', 'type_changed'),
    ({'type':'array'}, {'type':'string'}, 'C5', 'type_changed'),
    ({'type':'object'}, {'type':'string'}, 'C7', 'type_changed'),
    ({'type':'array'}, {'type':'object'}, 'C7', 'type_changed'),
    ({'enum':['a']}, {'enum':['a','b']}, 'C6', 'enum_values_added'),
    ({'enum':['a','b']}, {'enum':['a']}, 'C6', 'enum_values_removed'),
    ({'enum':['a']}, {'enum':['b']}, 'C6', 'enum_changed'),
    ({}, {'enum':['b']}, 'C6', 'enum_changed'),
    ({'enum':['b']}, {}, 'C6', 'enum_changed'),
    ({'semantic_unit':'RUB'}, {'semantic_unit':'kopecks'}, 'C8', 'semantic_unit_changed'),
])
def test_leaf_changes(old, new, family, subtype):
    diff = compare(contract({'x': old}), contract({'x': new}))
    assert len(diff.changes) == 1
    assert (diff.changes[0].family, diff.changes[0].subtype) == (family, subtype)
    assert diff.is_complete


def test_nested_and_items():
    old = contract({'box': {'type':'object', 'properties': {'a.b': {'type':'array', 'items': {'type':'integer'}}}}})
    new = deepcopy(old)
    new.input_schema['properties']['box']['properties']['a.b']['items']['type'] = 'string'
    assert signatures(compare(old, new)) == [('C5','type_changed','input.properties.box.properties["a.b"].items.type')]
    for left, right in [({'items': {}}, {}), ({}, {'items': {}})]:
        assert not compare(contract({'a':left}), contract({'a':right})).has_changes


def test_nesting_flattening_is_primitive():
    old = contract({'quantity': {'type':'integer'}})
    new = contract({'box': {'type':'object','properties': {'quantity': {'type':'integer'}}}})
    for a,b in [(old,new),(new,old)]:
        assert sorted(c.subtype for c in compare(a,b).changes) == ['parameter_added', 'parameter_removed']
        assert not any(c.family == 'C1' for c in compare(a,b).changes)


@pytest.mark.parametrize('names', [('quantity','amount'), ('amount_rub','amount_kopecks')])
def test_no_semantic_inference(names):
    diff = compare(contract({names[0]: {'type':'integer'}}), contract({names[1]: {'type':'integer'}}))
    assert len(diff.changes) == 2
    assert {c.family for c in diff.changes} == {'C2'}


def test_refs_and_unique_rename():
    old = contract({'a': {'$ref':'#/$defs/value'}}, **{'$defs': {'value': {'type':'integer'}}})
    new = contract({'b': {'$ref':'#/$defs/value'}}, **{'$defs': {'value': {'type':'integer'}}})
    diff = compare(old, new)
    assert signatures(diff) == [('C1','parameter_renamed','input.properties.a')]
    assert diff.changes[0].details == {'new_path':'input.properties.b', 'reference':'#/$defs/value'}
    new.input_schema['properties'] = {'a': {'$ref':'#/$defs/value'}}
    new.input_schema['$defs']['value']['type'] = 'string'
    assert signatures(compare(old,new)) == [('C5','type_changed','input.properties.a.type')]
    escaped = contract({'a': {'$ref':'#/$defs/a~1b~0c'}}, **{'$defs': {'a/b~c': {'type':'integer'}}})
    assert not compare(escaped,escaped).has_changes


@pytest.mark.parametrize('mode', ['duplicate_old','duplicate_new','missing','changed','required','existing','boolean'])
def test_ambiguous_ref_not_rename(mode):
    old = contract({'a': {'$ref':'#/$defs/v'}}, **{'$defs': {'v': {'type':'string'}}})
    new = contract({'b': {'$ref':'#/$defs/v'}}, **{'$defs': {'v': {'type':'string'}}})
    if mode == 'duplicate_old':
        old.input_schema['properties']['extra'] = {'$ref':'#/$defs/v'}
    elif mode == 'duplicate_new':
        new.input_schema['properties']['extra'] = {'$ref':'#/$defs/v'}
    elif mode == 'missing':
        new.input_schema['properties']['b'] = {}
    elif mode == 'changed':
        new.input_schema['$defs']['v'] = {'type':'integer'}
    elif mode == 'required':
        new.input_schema['required'] = ['b']
    elif mode == 'existing':
        old.input_schema['properties']['b'] = {}
    else:
        old.input_schema['properties']['a'] = True
    assert not any(c.family == 'C1' for c in compare(old,new).changes)


@pytest.mark.parametrize('schema', [
    {'$id':'https://example.test/s'},
    {'$ref':'https://example.test/s'},
    {'$ref':'#/$defs/missing'},
    {'$ref':'#/$defs/x', '$defs': {'x': {'$ref':'#/$defs/x'}}},
    {'$ref':'#/$defs/x', '$defs': {'x': True}, 'title':'sibling'},
    {'$ref':'#/$defs/x/type', '$defs': {'x': {'type':'string'}}},
    {'$ref':'#/$defs/x/type/nope', '$defs': {'x': {'type':'string'}}},
])
def test_unsupported_refs(schema):
    old = contract()
    old.output_schema = schema
    diff = compare(old,old)
    assert not diff.is_complete and not diff.has_changes
    assert diff.opaque[0].reason
    new = contract()
    new.output_schema = {}
    assert compare(old,new).has_changes


@pytest.mark.parametrize('old,new', [(True,False),(True,{}),({},False)])
def test_boolean_opaque(old,new):
    diff = compare(contract({'a':old}),contract({'a':new}))
    assert diff.has_changes and not diff.is_complete
    assert not compare(contract({'a':True}), contract({'a':True})).has_changes


def test_opaque_keywords_metadata_output():
    old = contract({'a': {'oneOf':[{'type':'string'},{'type':'integer'}]}})
    assert not compare(old,old).is_complete
    assert not compare(old,old).has_changes
    new = deepcopy(old)
    new.input_schema['properties']['a']['oneOf'] = [{'type':'boolean'}]
    new.input_schema['description'] = 'updated'
    new.description = 'updated'
    new.metadata = {'semantic_unit':'RUB','other':1}
    new.output_schema = {'type':'string'}
    diff = compare(old,new)
    assert diff.has_changes and not diff.is_complete
    assert len(diff.opaque) == 5
    assert signatures(diff) == [('C8','semantic_unit_changed','metadata.semantic_unit')]
    newer = deepcopy(new)
    newer.metadata['semantic_unit'] = 'kopecks'
    assert compare(new,newer).changes[0].new_value == 'kopecks'
    assert not compare(new,new).has_changes
    assert compare(new,old).has_changes


def test_order_roundtrip_and_no_mutation():
    old = contract({'z': {'type':'integer'},'a': {'type':'string'}}, ['z'])
    new = contract({'z': {'type':'string'},'a': {'type':['string','null']},'b': {}})
    snapshot = old.model_dump_json(), new.model_dump_json()
    diff = compare(old,new)
    assert signatures(diff) == sorted(signatures(diff), key=lambda x:(x[0],x[2],x[1]))
    assert SchemaDiff.model_validate_json(diff.model_dump_json()) == diff
    assert canonical_bytes(diff.model_dump()) == canonical_bytes(compare(old,new).model_dump())
    assert snapshot == (old.model_dump_json(),new.model_dump_json())


def test_required_rename_has_no_spurious_required_events():
    old = contract({'a': {'$ref':'#/$defs/v'}}, ['a'], **{'$defs': {'v': {'type':'integer'}}})
    new = contract({'b': {'$ref':'#/$defs/v'}}, ['b'], **{'$defs': {'v': {'type':'integer'}}})
    assert signatures(compare(old,new)) == [('C1','parameter_renamed','input.properties.a')]


def test_json_boolean_is_not_number():
    diff = compare(contract({'a': {'enum':[True]}}), contract({'a': {'enum':[1]}}))
    assert signatures(diff) == [('C6','enum_changed','input.properties.a.enum')]


def test_chained_ref_array_and_output():
    old = contract(**{'$defs': {'a': {'$ref':'#/$defs/b'}, 'b': {'type':'array', 'items': {'type':'string'}}}})
    old.input_schema['properties'] = {'value': {'$ref':'#/$defs/a'}}
    old.output_schema = {'type':'object', 'properties': {'result': {'type':'string'}}}
    new = deepcopy(old)
    new.input_schema['$defs']['b']['items']['type'] = 'integer'
    new.output_schema['properties']['result']['type'] = 'integer'
    assert signatures(compare(old,new)) == [
        ('C5','type_changed','input.properties.value.items.type'),
        ('C5','type_changed','output.properties.result.type'),
    ]


def test_ref_to_boolean_and_unused_defs():
    old = contract({'a': {'$ref':'#/$defs/v'}}, **{'$defs': {'v':True, 'unused': {'type':'string'}}})
    new = deepcopy(old)
    new.input_schema['$defs']['unused'] = {'type':'integer'}
    assert not compare(old,new).has_changes
    new.input_schema['$defs']['v'] = False
    assert compare(old,new).opaque[0].path == 'input.properties.a'


def test_opaque_resolution_order_is_independent_of_property_insertion():
    old = contract({'z': {'$ref':'https://example.test/s'}, 'a': {'$ref':'#/$defs/missing'}})
    reordered = contract(dict(reversed(list(old.input_schema['properties'].items()))))
    assert canonical_bytes(compare(old, old).model_dump()) == canonical_bytes(compare(reordered, reordered).model_dump())
