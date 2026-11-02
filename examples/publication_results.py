"""Производный анализ только завершённых условий прикладного исследования."""

import argparse
from collections import Counter, defaultdict
from pathlib import Path

from mcp_compat import canonical_bytes
from mcp_compat.analysis import artifacts, clustered_recovery_comparison, read_results
from mcp_compat.experiments import metrics, summaries


def repeated_outcomes(records):
    result = {}
    for method in sorted({r.method for r in records}):
        rows = [r for r in records if r.method == method]
        cases = defaultdict(list)
        for r in rows:
            cases[r.scenario_id].append(r)
        correct = Counter(sum(r.decision.action == 'EXECUTE' and r.semantic_equivalent is True for r in group)
                          for group in cases.values() if group[0].recoverable)
        traces = [r.decision.evidence['llm'] for r in rows if 'llm' in r.decision.evidence]
        result[method] = dict(
            per_repeat={str(repeat):metrics([r for r in rows if r.repeat == repeat]) for repeat in sorted({r.repeat for r in rows})},
            recoverable_cases_by_correct_repeat_count={str(k):v for k,v in sorted(correct.items())},
            unique_cases=len(cases), action_disagreements=sum(len({r.decision.action for r in group}) > 1 for group in cases.values()),
            mapping_decisions=len(traces),parsed_mappings=sum(t.get('parse_status') == 'parsed' for t in traces),
            terminal_unparsed=sum(t.get('parse_status') != 'parsed' for t in traces),
            responses_received=sum(len(t.get('responses',[])) for t in traces),
            attempt_errors=dict(Counter(e['error_type'] for t in traces for e in t.get('parse_errors',[]))),
            records_with_unknown_usage=sum(any(getattr(r,k) is None for k in ('calls','input_tokens','output_tokens','cost')) for r in rows))
    return result


if __name__ == '__main__':
    from replay_candidate_verification import replay
    from validate_publication_run import validate
    from mcp_compat.case_study_runtime import registry

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--regime',choices=('with-rules','without-rules'))
    args = parser.parse_args()
    root = Path('experiments/publication-2026-11-03/case-study')
    for regime in [args.regime] if args.regime else ('with-rules','without-rules'):
        directory = root/'runs'/regime
        integrity = validate(directory,root/'data'/regime)
        manifest,records = read_results(directory)
        artifacts(directory,root/'analysis'/regime,seed=42,draws=2000)
        replayed,details = replay(records,registry())
        result = dict(source_manifest=manifest,integrity=integrity,repeated_outcomes=repeated_outcomes(records),
                      replay=dict(scope='same_B2_candidates_verifier_only_not_full_M1',details=details,summary=summaries(replayed),
                                  comparison=clustered_recovery_comparison(records+replayed,'M1','B2V'),
                                  comparison_by_domain=clustered_recovery_comparison(records+replayed,'M1','B2V',cluster_by='domain')))
        (root/'analysis'/regime/'repeated-and-replay.json').write_bytes(canonical_bytes(result))
        print(regime,'проверено и проанализировано:',len(records),'решений',flush=True)
