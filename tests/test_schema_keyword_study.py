import json
import os
from pathlib import Path
import sys

import pytest

from mcp_compat.llm import Mapper
from test_llm import FakeClient
from mcp_compat import SchemaDiffEngine, ToolCall, ToolCallValidationError, ToolContract
from mcp_compat.benchmark import RecoveryInput
from mcp_compat.hybrid import Hybrid
from mcp_compat.verification import EvidenceVerifier, ObservationProfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
from schema_keyword_study import run_case, synthetic_cases
from published_schema_keywords import CATALOGS, VERSIONS, published_cases, published_inputs


@pytest.mark.parametrize("case", synthetic_cases(), ids=lambda case: case.name)
def test_keyword_cases_require_schema_and_behavior(case):
    strict = run_case(case, "strict")
    assert strict["action"] == "ABSTAIN" and strict["reason"] == "opaque"
    baseline = run_case(case, "compat")
    mapping = {
        "names_rename": dict(op="move", source=["data", "rack_code"], target=["data", "rack_code_v2"]),
        "patterns_wrap": dict(op="wrap", source=["data", "slot_7"], target=["data", "slot_7"]),
    }
    if case.name in mapping:
        assert baseline["reason"] == "schema_invalid"
        response = json.dumps({"action": "EXECUTE", "operations": [mapping[case.name]]})
        result = run_case(case, "compat", Mapper(FakeClient(response), attempts=1))
        assert result["source"] == "llm" and result["confirmed"] is True
    elif case.recoverable:
        assert baseline["confirmed"] is True and baseline["source"] == "verified_identity"
    else:
        assert baseline["action"] == "ABSTAIN"
        assert baseline["reason"] == ("schema_invalid" if case.name.endswith("_reject") else "semantic_mismatch")


def test_keyword_does_not_override_explicit_unit_rule():
    case = next(case for case in synthetic_cases() if case.name == "patterns_keep")
    case.request.old_contract.metadata["semantic_unit"] = "seconds"
    case.request.new_contract.metadata["semantic_unit"] = "milliseconds"
    assert run_case(case, "compat")["reason"] == "mapper_unavailable"


@pytest.mark.parametrize("entry", list(published_inputs(json.loads(CATALOGS.read_bytes()))),
                         ids=lambda entry: entry[0])
def test_published_inputs_use_original_catalog_constraints(entry):
    name, _, keyword, request, _, handlers = entry
    diff = SchemaDiffEngine.compare(request.old_contract, request.new_contract, extended=True)
    assert any(c.path.endswith("." + keyword) for c in diff.opaque)
    assert len(handlers) == 2
    for contract in (request.old_contract, request.new_contract):
        if name in {"parse_closed_schema", "users_invalid_weight"}:
            with pytest.raises(ToolCallValidationError):
                request.old_call.validate_against(contract)
        else:
            request.old_call.validate_against(contract)


def test_published_docx_footnotes_keep_resource_scope_guard():
    catalogs = json.loads(CATALOGS.read_bytes())["docx"]
    before, after = [catalogs[v]["tool"] for v in VERSIONS["docx"]]
    assert '"patternProperties"' not in json.dumps(before["inputSchema"])
    assert '"patternProperties"' in json.dumps(after["inputSchema"])
    old, new = (ToolContract(name=t["name"], input_schema=t["inputSchema"]) for t in (before, after))
    seed = RecoveryInput(old_contract=old, new_contract=new,
                         old_call=ToolCall(tool_name=old.name, arguments={"json": {
                             "meta": {"title": "Контроль"}, "content": [],
                         }}))
    seed.old_call.validate_against(old)
    client = FakeClient('{"action":"ABSTAIN"}')
    def skipped(arguments, state):
        pytest.fail("При неподдерживаемом $id пробы запрещены")

    checker = EvidenceVerifier(old, new, skipped, skipped,
        profile=ObservationProfile(name="DOCX"),
        handler_ids=tuple(catalogs[v]["integrity"] for v in VERSIONS["docx"]))
    for mode in ("strict", "compat"):
        engine = Hybrid(Mapper(client, attempts=1), checker, mode=mode, current_state=dict)
        result = engine.recover(seed)
        assert result.reasons == ["opaque"]
        assert any("$id resource scopes" in item["reason"] for item in result.evidence["diff"]["opaque"])
    assert not client.requests


@pytest.mark.skipif(os.environ.get("MCP_COMPAT_RUN_PUBLISHED_KEYWORDS") != "1",
                    reason="Требуется локальная установка опубликованных серверов")
def test_published_keyword_calls():
    cases = published_cases()
    assert len(cases) == 6
    for case in cases:
        assert run_case(case, "strict")["action"] == "ABSTAIN"
        row = run_case(case, "compat")
        assert (row["action"] == "EXECUTE") == case.recoverable
        if case.recoverable:
            assert row["confirmed"] is True
