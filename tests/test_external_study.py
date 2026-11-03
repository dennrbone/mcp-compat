from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"examples"))
import external_study as study
from mcp_compat import canonical_bytes
from mcp_compat.external import load_inputs


def fake_source(project, era, *, tool, arguments, state):
    """Явная offline fixture для runner-тестов; не доказательство работы чужого сервера."""
    state = deepcopy(state)
    if project == "calculator":
        values = {"2.5+3.25":"5.75","3*4":"12","7//2":"3","2^3":"8","0":"0","1":"1"}
        result = dict(result=values[arguments["expression"].replace(" ","")])
    elif project == "fs":
        text = state["files"][arguments["path"]]
        if "head" in arguments:
            text = "\n".join(text.split("\n")[:arguments["head"]])
        if "tail" in arguments:
            text = "\n".join(text.split("\n")[-arguments["tail"]:])
        result = [dict(type="text",text=text)]
    else:
        query = arguments["query"]
        if query.startswith("UPDATE"):
            state["rows"][0]["qty"] -= 2
            result = [dict(affected_rows=1)]
        elif query.startswith("DELETE"):
            state["rows"].pop()
            result = [dict(affected_rows=1)]
        else:
            key = "name" if "SELECT name" in query else "qty"
            index = 1 if "id=2" in query else 0
            result = [{key:state["rows"][index][key]}]
    return dict(result=result,state=state)


def case(alteration):
    return next(c for c in load_inputs(study.DATA,study.DIGEST) if c.project == "sqlite" and c.alteration == alteration)


def test_identical_candidates_isolate_behavior_and_completeness(tmp_path,monkeypatch):
    monkeypatch.setattr(study,"load_gold",lambda *a:pytest.fail("method must not read gold"))
    runtime = study.Runtime(tmp_path,call=fake_source)
    c = case("result_changed")
    assert study.decide(c,"A",runtime).action == "EXECUTE"
    assert study.decide(c,"C",runtime).action == "EXECUTE"
    for method in ("B","D","E","M1_new"):
        assert study.decide(c,method,runtime).action == "ABSTAIN"
    assert study.decide(c,"M1_old",runtime).action == "EXECUTE"
    c = case("hidden_state")
    assert study.decide(c,"D",runtime).action == "EXECUTE"
    assert study.decide(c,"B",runtime).reasons == ["incomplete_observation_profile"]
    c = case("nondeterministic")
    assert study.decide(c,"D",runtime).reasons == ["nondeterministic_observation"]
    c = case("toctou")
    assert study.decide(c,"B",runtime).reasons == ["state_changed"]
    assert study.decide(c,"A",runtime).action == "EXECUTE"


def test_complete_runner_resume_never_rewrites_or_reexecutes(tmp_path,monkeypatch):
    monkeypatch.setattr(study,"execute",fake_source)
    monkeypatch.setattr(study,"isolation_check",lambda:{"test_fixture_only":True})
    records = study.study(tmp_path)
    assert len(records) == 63*7
    assert all(r.calls == 0 for r in records)
    row = next(r for r in records if r.method == "M1_new" and r.scenario_id == "sqlite-07-removed")
    assert row.validation_stages == 1
    before = {p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in tmp_path.glob("*.json")}
    def forbidden(*a,**k):
        pytest.fail("completed run must not execute or rewrite")
    monkeypatch.setattr(study,"execute",forbidden)
    monkeypatch.setattr(study,"isolation_check",forbidden)
    assert study.study(tmp_path) == study.read_completed(tmp_path)
    assert before == {p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in tmp_path.glob("*.json")}
    name = next(n for n in before if n.startswith("decision-"))
    (tmp_path/name).write_bytes(canonical_bytes({"tampered":True}))
    with pytest.raises(ValueError,match="integrity"):
        study.read_completed(tmp_path)


def test_runtime_history_has_no_holes_and_decoder_rejects_multiple_values(tmp_path):
    (tmp_path/"rpc-00002.json").write_text("{}")
    with pytest.raises(ValueError,match="history"):
        study.Runtime(tmp_path,call=fake_source)
    c = case("encoding")
    with pytest.raises(ValueError,match="singleton"):
        study.native_arguments(c,{"query":["a","b"]})
    manifest = tmp_path/"manifest.json"
    manifest.write_text(json.dumps({"fingerprint":"wrong"}))
    with pytest.raises(ValueError,match="requires new"):
        study.study(tmp_path)


def test_constructed_unit_output_is_finite_and_not_a_wrapper_exception():
    assert study.change_result({"result":"5.75"},"unit") == {"result":"5.75::unit"}
    assert study.change_result([{"qty":5}],"unit") == [{"qty":5000}]


def test_full_hybrid_must_check_current_state_before_admission(tmp_path):
    runtime = study.Runtime(tmp_path,call=fake_source)
    c = case("toctou")
    decision = study.decide(c,"M1_new",runtime)
    assert decision.action == "ABSTAIN" and decision.reasons == ["state_changed"]


def test_all_valid_pinned_candidates_have_executable_fixture_wrappers(tmp_path):
    from mcp_compat import ToolCallValidationError
    runtime = study.Runtime(tmp_path,call=fake_source)
    for c in load_inputs(study.DATA,study.DIGEST):
        try:
            c.candidate.validate_against(c.request.new_contract)
        except ToolCallValidationError:
            continue
        state = deepcopy(c.initial)
        result = runtime.implementation(c,"new",visible=False)(c.candidate.arguments,state)
        canonical_bytes(dict(result=result,state=state))
