"""Проверка полного опыта Terra и сравнение с историческим CodeAgent."""

from pathlib import Path

from publication_results import repeated_outcomes
from replay_candidate_verification import replay
from validate_publication_run import validate

from mcp_compat import canonical_bytes
from mcp_compat.analysis import clustered_recovery_comparison, read_results
from mcp_compat.case_study_runtime import registry
from mcp_compat.experiments import summaries


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
        output = root/'analysis'/regime
        output.mkdir(parents=True, exist_ok=True)
        (output/'comparison.json').write_bytes(canonical_bytes(result))
        print(regime, 'полная матрица и сравнение проверены', flush=True)
