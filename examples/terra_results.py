"""Проверка полного опыта Terra и сравнение с историческим CodeAgent."""

from pathlib import Path
from hashlib import sha256
import json

from publication_results import repeated_outcomes
from replay_candidate_verification import replay
from validate_publication_run import validate

from mcp_compat import canonical_bytes
from mcp_compat.analysis import clustered_recovery_comparison, read_results
from mcp_compat.case_study_runtime import registry
from mcp_compat.experiments import Record, summaries


def read_before_retry(directory, backup):
    manifest = json.loads((backup/'manifest.json').read_bytes())
    identity = {k:v for k,v in manifest.items() if k not in ('created_at', 'fingerprint')}
    assert sha256(canonical_bytes(identity)).hexdigest() == manifest['fingerprint']
    digests = json.loads((backup/'result-digests.json').read_bytes())
    rows = []
    for key, expected in digests.items():
        path = backup/(key+'.json')
        record = Record.model_validate_json((path if path.exists() else directory/path.name).read_bytes())
        assert key == f'{record.repeat}-{record.method}-{record.scenario_id}'
        assert sha256(canonical_bytes(record.model_dump())).hexdigest() == expected
        rows.append(record)
    return manifest, rows


if __name__ == '__main__':
    root = Path('experiments/terra-2026-11-03')
    original = Path('experiments/publication-2026-11-03/case-study')
    for regime in ('with-rules', 'without-rules'):
        models = {}
        integrity = {}
        manifests = {}
        repetitions = {}
        replay_details = {}
        for model, directory in [('CodeAgent', original/'runs'/regime), ('Terra', root/'runs'/regime)]:
            integrity[model] = validate(directory, original/'data'/regime)
            manifest, records = read_results(directory)
            assert len(records) == 2880 and manifest['config']['repeats'] == 3
            manifests[model] = manifest
            repetitions[model] = repeated_outcomes(records)
            derived, details = replay(records, registry())
            models[model] = records+derived
            replay_details[model] = details
        assert manifests['CodeAgent']['source_digest'] == manifests['Terra']['source_digest']
        assert manifests['Terra']['source_digest'] == 'ccd2591e512801b45a81d0a1c426c802a5b380ec680ae03c13c2fd31efd24397'
        combined = [r.model_copy(update={'method':model+'_'+r.method})
                    for model, rows in models.items() for r in rows]
        comparisons = {method:{cluster:clustered_recovery_comparison(combined, 'Terra_'+method,
                        'CodeAgent_'+method, cluster_by=cluster) for cluster in ('base_tool', 'domain')}
                       for method in ('M1', 'B2', 'B2V')}
        result = dict(integrity=integrity, manifests=manifests,
            summary={model:summaries(rows) for model, rows in models.items()},
            repeated_outcomes=repetitions, replay=replay_details, comparisons=comparisons,
            scope='historical comparison of model+client pipelines; generation settings and network conditions differ',
            replay_scope='same candidates; verifier only, not full M1; component latency, not live E2E')
        backup = root/'before-provider-retry'/regime
        if (backup/'manifest.json').exists():
            original_manifest, original_records = read_before_retry(root/'runs'/regime, backup)
            original_replay, _ = replay(original_records, registry())
            before = original_records+original_replay
            paired_before = [r.model_copy(update={'method':model+'_'+r.method})
                             for model, rows in [('CodeAgent', models['CodeAgent']), ('Terra', before)] for r in rows]
            result['before_provider_retry'] = dict(manifest=original_manifest, summary=summaries(before),
                comparisons={method:clustered_recovery_comparison(paired_before, 'Terra_'+method, 'CodeAgent_'+method)
                             for method in ('M1', 'B2', 'B2V')},
                scope='original Terra answers restored by original hashes; extra provider retry applied only to final Terra matrix')
        output = root/'analysis'/regime
        output.mkdir(parents=True, exist_ok=True)
        (output/'comparison.json').write_bytes(canonical_bytes(result))
        print(regime, 'полная матрица и сравнение проверены', flush=True)
