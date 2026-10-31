from copy import deepcopy
from hashlib import sha256
import json

import pytest
from hypothesis import given, settings, strategies as st
from pydantic import ValidationError

from mcp_compat import ToolCall, canonical_bytes
from mcp_compat.benchmark import (
    RecoveryInput, _case, _view, equivalent, freeze, generate, load,
    recovery_input, simulate,
)


@pytest.fixture(scope="module")
def corpus():
    return generate()


def test_corpus_validity_diversity_and_ground_truth(corpus):
    assert len(corpus) == len({s.scenario_id for s in corpus}) == 2160
    assert len({s.metadata['base_tool'] for s in corpus}) == 48
    assert len({canonical_bytes(s.old_contract.model_dump()) for s in corpus}) == 48
    assert len({s.metadata['domain'] for s in corpus}) == 8
    assert sum(s.metadata['composed'] for s in corpus) == 240
    assert {s.ground_truth for s in corpus} == {'SAFE_AUTO', 'CONDITIONAL', 'MUST_ABSTAIN'}
    assert len({(s.mutation_family, s.mutation_subtype) for s in corpus}) == 40
    for s in corpus:
        s.old_call.validate_against(s.old_contract)
        assert s.old_contract != s.new_contract
        if s.oracle['expected_call'] is not None:
            call = ToolCall.model_validate(s.oracle['expected_call'])
            assert equivalent(s, call), s.scenario_id
        else:
            assert s.ground_truth == 'MUST_ABSTAIN'
    # Seed changes values, not labels or mutation composition.
    again = generate()
    assert canonical_bytes([s.model_dump() for s in corpus]) == canonical_bytes([s.model_dump() for s in again])
    assert generate(43)[0].old_call != corpus[0].old_call


def test_recovery_boundary_has_no_labels_or_oracle(corpus):
    s = deepcopy(corpus[0])
    before = recovery_input(s)
    s.oracle = {'secret': 'poison'}
    s.ground_truth = 'MUST_ABSTAIN'
    s.metadata['arbitrary_secret'] = 'poison'
    assert recovery_input(s) == before
    before.old_call.arguments.clear()
    assert s.old_call.arguments
    with pytest.raises(ValidationError):
        RecoveryInput(**recovery_input(s).model_dump(), oracle={})


def test_roundtrip_frozen_bytes_and_corruption(tmp_path, corpus):
    a, b = tmp_path/'a', tmp_path/'b'
    subset = corpus[:12]
    digest = freeze(subset, a, 42)
    assert freeze(subset, b, 42) == digest
    assert sorted(load(a, digest), key=lambda s:s.scenario_id) == sorted(subset, key=lambda s:s.scenario_id)
    for p in a.rglob('*.json'):
        assert p.read_bytes() == (b/p.relative_to(a)).read_bytes()
    with pytest.raises(FileExistsError):
        freeze(subset, a, 42)
    with pytest.raises(ValueError, match='manifest'):
        load(a, 'bad')
    p = a/subset[0].scenario_id/'old_call.json'
    p.write_text('{}')
    with pytest.raises(ValueError, match='scenario integrity'):
        load(a, digest)


@pytest.mark.parametrize('change', ['version', 'digest', 'count', 'id', 'files', 'mismatch', 'symlink', 'seed'])
def test_manifest_validation(tmp_path, corpus, change):
    directory = tmp_path/'data'
    digest = freeze(corpus[:1], directory, 42)
    path = directory/'manifest.json'
    m = json.loads(path.read_bytes())
    sid = corpus[0].scenario_id
    if change == 'version':
        m['version'] = 'bad'
    elif change == 'digest':
        m['digest'] = 'bad'
    elif change == 'count':
        m['count'] = 2
    elif change == 'seed':
        m['seed'] = 7
    elif change == 'id':
        m['files']['../bad'] = m['files'].pop(sid)
    elif change == 'files':
        m['files'][sid]['extra'] = 'hash'
    elif change == 'mismatch':
        p = directory/sid/'metadata.json'
        metadata = json.loads(p.read_bytes())
        metadata['scenario_id'] = 'other'
        p.write_bytes(canonical_bytes(metadata))
        m['files'][sid]['metadata'] = sha256(p.read_bytes()).hexdigest()
    else:
        p = directory/sid/'old_call.json'
        moved = tmp_path/'call.json'
        p.rename(moved)
        p.symlink_to(moved)
    if change in ('id', 'files', 'mismatch', 'count'):
        digest = m['digest'] = sha256(canonical_bytes({k:v for k,v in m.items() if k != 'digest'})).hexdigest()
    path.write_bytes(canonical_bytes(m))
    with pytest.raises(ValueError):
        load(directory, digest)


@pytest.mark.parametrize('bad_id', ['../bad', 'duplicate'])
def test_freeze_invalid_ids(tmp_path, corpus, bad_id):
    s = deepcopy(corpus[0])
    if bad_id == 'duplicate':
        cases = [s, s]
    else:
        s.scenario_id = bad_id
        cases = [s]
    with pytest.raises(ValueError):
        freeze(cases, tmp_path/'data', 42)


def test_oracle_semantic_wrong_invalid_and_isolation(corpus):
    s = next(s for s in corpus if s.mutation_subtype == 'rub_kopecks')
    assert not equivalent(s, s.old_call)  # schema-valid, unit-wrong
    assert not equivalent(s, ToolCall(tool_name='wrong', arguments={}))
    assert not equivalent(s, ToolCall(tool_name=s.new_contract.name, arguments={}))
    state = {'events': []}
    assert simulate({'x': 1}, {'value': {'path':['x']}}, 2, state)['events']
    assert state == {'events': []}
    for bad in ([1,2], []):
        with pytest.raises(ValueError):
            _view({'x':bad}, {'value': {'path':['x'], 'decode':'singleton'}})
    assert _view({'x':'standard'}, {'mode': {'path':['x'], 'decode':'priority'}}) == {'mode':'standard'}
    view = {'value': {'path':['packed'], 'decode':'packed_value'}, 'target': {'path':['packed'], 'decode':'packed_target'}}
    assert _view({'packed':'abc|4'}, view) == {'value':4,'target':'abc'}
    assert _view({'x':1.25}, {'value':{'path':['x']}}) == {'value':1.25}


@given(st.integers(min_value=0, max_value=2**32), st.sampled_from(['C1','C2','C3','C4','C5','C6','C7','C8']), st.integers(0,4))
@settings(max_examples=30, deadline=None)
def test_seeded_mutations(seed, family, variant):
    import random
    a = _case('inventory', 'reserve', 2, family, variant, random.Random(seed))
    b = _case('inventory', 'reserve', 2, family, variant, random.Random(seed))
    assert canonical_bytes(a.model_dump()) == canonical_bytes(b.model_dump())
    a.old_call.validate_against(a.old_contract)


def test_required_added_value_affects_semantics():
    import random
    s = _case('commerce','order',2,'C3',0,random.Random(42))
    call = ToolCall.model_validate(s.oracle['expected_call'])
    assert equivalent(s, call)
    call.arguments['region'] = 'different-region'
    assert not equivalent(s, call)


def test_oracle_observes_new_optional_side_effects():
    import random
    s = _case('commerce','order',2,'C2',0,random.Random(42))
    call = ToolCall.model_validate(s.oracle['expected_call'])
    call.arguments['note'] = 'unrequested audit note'
    assert not equivalent(s,call)
