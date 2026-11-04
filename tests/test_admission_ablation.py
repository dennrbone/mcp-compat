from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
from admission_ablation import decide
import external_study as study
from mcp_compat.external import load_inputs
from test_external_study import fake_source


def test_final_admission_is_the_only_change_and_gold_is_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(study, "load_gold", lambda *a: pytest.fail("gold is evaluator-only"))
    runtime = study.Runtime(tmp_path, call=fake_source)
    cases = load_inputs(study.DATA, study.DIGEST)
    for project in ("fs", "sqlite", "calculator"):
        stale = next(c for c in cases if c.project == project and c.alteration == "toctou")
        full, preview = (decide(stale, m, runtime) for m in ("FULL", "NO_FINAL"))
        assert full.action == "ABSTAIN" and full.reasons == ["state_changed"]
        assert preview.action == "EXECUTE" and preview.adapted_call == stale.candidate
        for alteration in ("none", "required", "hidden_state", "nondeterministic"):
            case = next(c for c in cases if c.project == project and c.alteration == alteration)
            a, b = (decide(case, m, runtime) for m in ("FULL", "NO_FINAL"))
            assert a.action == b.action
    with pytest.raises(ValueError, match="unknown"):
        decide(stale, "unknown", runtime)
