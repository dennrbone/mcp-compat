from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"examples"))
import external_study as study
from external_200_dataset import read
from mcp_compat import canonical_bytes
from mcp_compat.external import load_inputs
from mcp_compat.hybrid import Hybrid


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


def test_runtime_history_has_no_holes_and_decoder_rejects_multiple_values(tmp_path):
    (tmp_path/"rpc-00002.json").write_text("{}")
    with pytest.raises(ValueError,match="history"):
        study.Runtime(tmp_path,call=fake_source)
    c = case("encoding")
    with pytest.raises(ValueError,match="singleton"):
        study.native_arguments(c,{"query":["a","b"]})


def test_constructed_unit_output_is_finite_and_not_a_wrapper_exception():
    assert study.change_result({"result":"5.75"},"unit") == {"result":"5.75::unit"}
    assert study.change_result([{"qty":5}],"unit") == [{"qty":5000}]


def test_full_hybrid_must_check_current_state_before_admission(tmp_path):
    runtime = study.Runtime(tmp_path,call=fake_source)
    c = case("toctou")
    checker = study.verifier(c, runtime)
    decision = Hybrid(verifier=checker, current_state=lambda: study.current_state(c)).recover(c.request)
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

def test_extended_dataset_preserves_original_cases_and_has_distinct_new_inputs():
    digest, extended = read("public.json")
    oracle_digest, labels = read("gold.json")
    original = load_inputs(study.DATA, study.DIGEST)
    assert digest == oracle_digest
    assert extended[:len(original)] == original
    assert len(extended) == len(labels) == 200
    assert {case.case_id for case in extended} == set(labels)
    new_inputs = {canonical_bytes(case.request.model_dump()) for case in extended[len(original):]}
    assert len(new_inputs) == 137
    assert all(not case.request.context for case in extended)
