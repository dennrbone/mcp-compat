from copy import deepcopy
from hashlib import sha256
import json

import pytest

from mcp_compat import canonical_bytes
from mcp_compat.analysis import analysis_cli, artifacts, bootstrap_ci, mcnemar, paired, read_results, wilcoxon_paired
from test_experiments import row


def test_hand_computed_mcnemar():
    result = mcnemar([True]*4,[False]*4)
    assert result['b'] == 4 and result['c'] == 0 and result['pvalue'] == .125
    assert mcnemar([True,False],[False,True])['pvalue'] == 1.
    assert mcnemar([True],[True])['pvalue'] == 1.
    assert mcnemar([],[])['pvalue'] is None
    for a,b in [([True],[]),([1],[False])]:
        with pytest.raises(ValueError):
            mcnemar(a,b)


def test_hand_computed_wilcoxon_and_assumptions():
    result = wilcoxon_paired([1.,2.,3.],[0.,0.,0.],symmetry_confirmed=True)
    assert result['statistic'] == 0 and result['pvalue'] == .25
    assert wilcoxon_paired([1.],[1.],symmetry_confirmed=True)['pvalue'] == 1.
    assert wilcoxon_paired([1.],[0.])['pvalue'] is None
    assert wilcoxon_paired([],[])['status'] == 'empty_pairs'
    for a,b in [([1.],[]),([float('nan')],[1.]),([None],[1.])]:
        with pytest.raises(ValueError):
            wilcoxon_paired(a,b,symmetry_confirmed=True)


def test_bootstrap_seed_units_undefined_and_manual_bounds():
    a,b = row(),row(False,semantic=None,valid=None)
    a.base_tool,b.base_tool = 'a','b'
    result = bootstrap_ci([a,b],draws=128)
    assert result['point'] == .5 and result['low'] == 0 and result['high'] == 1
    assert result == bootstrap_ci([a,b],draws=128)
    assert result['units'] == 2 and result['confidence'] == .95
    b.base_tool = 'a'
    assert bootstrap_ci([a,b],draws=10)['status'] == 'insufficient_units'
    assert bootstrap_ci([a,b],draws=128,cluster=False)['low'] == 0
    b.base_tool = 'b'
    b.recoverable = False
    assert bootstrap_ci([a,b],draws=128)['status'] == 'undefined_resamples'
    assert bootstrap_ci([],draws=8)['status'] == 'undefined_metric'
    for kwargs in [dict(metric='invented'),dict(draws=0)]:
        with pytest.raises(ValueError):
            bootstrap_ci([a],**kwargs)


def test_pairing_does_not_silently_drop_missing_runs():
    a,b = row(),row()
    b.method = 'M1'
    assert paired([b,a],'B0','M1') == ([a],[b])
    for rows in ([a],[a,a,b]):
        with pytest.raises(ValueError):
            paired(rows,'B0','M1')
    b.ground_truth = 'SAFE_AUTO'
    with pytest.raises(ValueError,match='labels'):
        paired([a,b],'B0','M1')


def save(directory,rows,kind='offline_demo'):
    directory.mkdir()
    identity = dict(config=dict(kind=kind))
    manifest = dict(identity,fingerprint=sha256(canonical_bytes(identity)).hexdigest(),created_at='unit-test')
    (directory/'manifest.json').write_bytes(canonical_bytes(manifest))
    hashes = {}
    for r in rows:
        key = f'{r.repeat}-{r.method}-{r.scenario_id}'
        data = canonical_bytes(r.model_dump())
        (directory/f'{key}.json').write_bytes(data)
        hashes[key] = sha256(data).hexdigest()
    (directory/'result-digests.json').write_bytes(canonical_bytes(hashes))


@pytest.mark.parametrize('mode', ['manifest','hash','path','identity','empty'])
def test_result_integrity(tmp_path,mode):
    directory = tmp_path/'run'
    save(directory,[row()])
    hashes_path = directory/'result-digests.json'
    hashes = json.loads(hashes_path.read_bytes())
    key = next(iter(hashes))
    if mode == 'manifest':
        path = directory/'manifest.json'
        m = json.loads(path.read_bytes())
        m['config']['kind'] = 'main'
        path.write_bytes(canonical_bytes(m))
    elif mode == 'hash':
        hashes[key] = 'bad'
    elif mode == 'path':
        hashes['../secret'] = hashes.pop(key)
    elif mode == 'identity':
        payload = json.loads((directory/f'{key}.json').read_bytes())
        payload['method'] = 'other'
        data = canonical_bytes(payload)
        (directory/f'{key}.json').write_bytes(data)
        hashes[key] = sha256(data).hexdigest()
    else:
        hashes = {}
    hashes_path.write_bytes(canonical_bytes(hashes))
    with pytest.raises(ValueError):
        read_results(directory)


def test_artifacts_come_from_actual_records_and_cli(tmp_path,capsys):
    rows = []
    for method in ('B0','B1','B2','B3','M1','A1','A2','A3','A4'):
        for i in range(2):
            r = row(semantic=method=='M1')
            r.method,r.scenario_id,r.base_tool = method,str(i),str(i)
            rows.append(r)
    rows[0].input_tokens = None
    directory = tmp_path/'run'
    save(directory,rows)
    out = tmp_path/'analysis'
    result = artifacts(directory,out,draws=8)
    assert 'OFFLINE DEMO ONLY' in result['label']
    assert result['summary']['M1']['overall']['CRR']['value'] == 1.
    assert result['comparisons']['B0']['continuous']['input_tokens']['status'] == 'unknown_measurements'
    assert result['comparisons']['B0']['continuous']['latency']['pvalue'] is None
    for name in ('rates.png','rates.svg','summary.tex','summary.csv','families.csv','categories.csv','ablations.csv','analysis.json'):
        assert (out/name).stat().st_size > 0
    analysis_cli(['--run',str(directory),'--output',str(out),'--draws','8'])
    assert 'OFFLINE DEMO ONLY' in capsys.readouterr().out
    minimal = tmp_path/'minimal'
    minimal_row = deepcopy(rows[0])
    minimal_row.recoverable = False
    minimal_row.ground_truth = 'MUST_ABSTAIN'
    save(minimal,[minimal_row],kind='main')
    result = artifacts(minimal,tmp_path/'minimal-analysis',draws=8)
    assert result['comparisons']['B0']['status'] == 'missing_methods'
    assert not (tmp_path/'minimal-analysis'/'ablations.csv').exists()


def test_trailing_undefined_rate_label_remains_inside_plot(tmp_path,monkeypatch):
    import matplotlib.pyplot as plt
    figures=[]
    original=plt.subplots
    def capture(*args,**kwargs):
        figure,axes=original(*args,**kwargs)
        figures.append(figure)
        return figure,axes
    monkeypatch.setattr(plt,'subplots',capture)
    baseline,hybrid=row(),row(False,semantic=None,valid=None)
    baseline.method,hybrid.method='B0','M1'
    directory=tmp_path/'run'
    save(directory,[baseline,hybrid],kind='pilot')
    artifacts(directory,tmp_path/'analysis',draws=8)
    axis=figures[0].axes[1]
    label=next(text for text in axis.texts if text.get_text()=='N/A')
    left,right=axis.get_xlim()
    assert left < label.get_position()[0] < right
