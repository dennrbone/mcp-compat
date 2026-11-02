from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

from mcp_compat.benchmark import freeze
from mcp_compat.case_study import generate
from mcp_compat.case_study_runtime import VERSION
from mcp_compat.declared_rules import DeclaredRules
from mcp_compat.experiments import RunConfig, run


def test_publication_validation_detects_plausible_but_wrong_results(tmp_path,monkeypatch):
    spec = spec_from_file_location('validation',Path(__file__).resolve().parents[1]/'examples/validate_publication_run.py')
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    data,output = tmp_path/'data',tmp_path/'output'
    digest = freeze(generate(with_rules=True)[:8],data,42,version=VERSION)
    run(RunConfig(kind='deterministic',benchmark_digest=digest),[DeclaredRules()],data,output)
    assert module.validate(output,data)['records'] == 8
    manifest,rows = module.read_results(output)
    monkeypatch.setattr(module,'read_results',lambda p:(manifest,rows[:-1]))
    with pytest.raises(AssertionError,match='matrix'):
        module.validate(output,data)
    monkeypatch.setattr(module,'read_results',lambda p:(manifest,rows))
    rows[0].recoverable = not rows[0].recoverable
    with pytest.raises(AssertionError,match='label'):
        module.validate(output,data)
    rows[0].recoverable = not rows[0].recoverable
    original_input = rows[0].recovery
    rows[0].recovery = {}
    with pytest.raises(AssertionError,match='input'):
        module.validate(output,data)
    rows[0].recovery = original_input
    original_semantic = rows[0].semantic_equivalent
    rows[0].semantic_equivalent = None
    with pytest.raises(AssertionError,match='evaluation'):
        module.validate(output,data)
    rows[0].semantic_equivalent = original_semantic
    (output/'summary.json').write_text('{}')
    with pytest.raises(AssertionError,match='summary'):
        module.validate(output,data)
