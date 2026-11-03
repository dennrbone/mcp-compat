from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"examples"))
from external_results import audit, family, rate_contrast, source_error_bound
from external_study import DATA,DIGEST
from mcp_compat import canonical_bytes
from mcp_compat.experiments import Record, summaries
from mcp_compat.external import load_inputs
from mcp_compat.verification import fingerprint
from test_experiments import row


def pairs(n=2):
    rows=[]
    for i in range(n):
        for method,semantic in (("B",True),("C",False)):
            r=row(semantic=semantic)
            r.method,r.scenario_id,r.base_tool=method,str(i),str(i)
            rows.append(r)
    return rows


def test_hand_checked_clustered_rate_contrasts_and_zero_bound():
    rows=pairs()
    for metric,difference in (("CRR",1.),("UHR",-1.),("FBR",0.)):
        result=rate_contrast(rows,"B","C",metric,draws=32)
        assert result["difference"]==difference and result["low"]==difference and result["high"]==difference
        assert result["pvalue"]==(.5 if difference else 1.)
        assert result==rate_contrast(rows,"B","C",metric,draws=32)
    bound=source_error_bound([r for r in rows if r.method=="B"])
    assert bound["upper_95_one_sided"]==pytest.approx(1-.05**.5)
    assert bound["unconditional_population_UHR_upper"]==1.
    assert source_error_bound([r for r in rows if r.method=="C"])["upper_95_one_sided"]==1.
    assert source_error_bound([])["upper_95_one_sided"] is None


def test_undefined_bootstrap_and_small_cluster_limits_are_reported():
    rows=pairs()
    for r in rows[2:]:
        r.decision=r.decision.model_copy(update=dict(action="ABSTAIN",adapted_call=None))
        r.semantic_equivalent=None
    result=rate_contrast(rows,"B","C","UHR",draws=128)
    assert result["undefined_resamples"]>0 and result["low"] is None
    assert result["status"]=="partly_undefined"
    assert rate_contrast(rows[2:],"B","C","UHR")["status"]=="undefined_metric"
    assert rate_contrast(pairs(1),"B","C","UHR")["status"]=="insufficient_clusters"
    for options in ({"metric":"fake"},{"metric":"FBR","draws":0}):
        with pytest.raises(ValueError):
            rate_contrast(pairs(),"B","C",**options)
    with pytest.raises(ValueError,match="16"):
        rate_contrast(pairs(17),"B","C","UHR",draws=1)


def test_benign_historical_cases_are_not_reported_as_renames():
    cases=load_inputs(DATA,DIGEST)
    controls=[c for c in cases if family(c)=="CONTROL"]
    assert len(controls)==4 and all(c.project=="calculator" and c.kind=="historical" for c in controls)
    assert sum(c.kind=="historical" and family(c)=="C1" for c in cases)==8


def test_undefined_permutations_are_not_silently_removed():
    rows=pairs()
    for i in (1,2):
        rows[i].decision=rows[i].decision.model_copy(update=dict(action="ABSTAIN",adapted_call=None))
        rows[i].semantic_equivalent=None
    result=rate_contrast(rows,"B","C","UHR",draws=32)
    assert result["undefined_permutations"]==2 and result["pvalue"] is None


@pytest.mark.parametrize("tamper",["semantic","label"])
def test_independent_trace_audit_rejects_self_consistently_rehashed_results(tmp_path,tamper):
    root=Path(__file__).resolve().parents[1]
    source=root/"experiments/external-admission-2026-11-04"
    directory=tmp_path/"run"
    shutil.copytree(source,directory)
    path=directory/"0-B-calculator-00-none.json"
    record=json.loads(path.read_bytes())
    if tamper=="semantic":
        record["semantic_equivalent"]=False
    else:
        record["ground_truth"]="MUST_ABSTAIN"
    path.write_bytes(canonical_bytes(record))
    hashes=json.loads((directory/"result-digests.json").read_bytes())
    hashes[path.stem]=fingerprint(deepcopy(record))
    (directory/"result-digests.json").write_bytes(canonical_bytes(hashes))
    rows=[Record.model_validate_json((directory/(name+".json")).read_bytes()) for name in hashes]
    (directory/"summary.json").write_bytes(canonical_bytes(summaries(rows)))
    artifact_hashes=json.loads((directory/"artifact-digests.json").read_bytes())
    for name in artifact_hashes:
        artifact_hashes[name]=sha256((directory/name).read_bytes()).hexdigest()
    (directory/"artifact-digests.json").write_bytes(canonical_bytes(artifact_hashes))
    with pytest.raises(ValueError,match="mismatch"):
        audit(directory)
