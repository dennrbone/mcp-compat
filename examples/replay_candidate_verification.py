"""Повторная проверка тех же кандидатов B2 без новых обращений к модели."""

import argparse
from collections import Counter
from copy import deepcopy
from pathlib import Path
from time import perf_counter

from mcp_compat import canonical_bytes
from mcp_compat.analysis import read_results
from mcp_compat.benchmark import RecoveryInput
from mcp_compat.experiments import metrics
from mcp_compat.hybrid import RuntimeVerifier
from mcp_compat.recovery import abstain


def replay(records, verifier: RuntimeVerifier):
    result = []
    reasons: Counter[str] = Counter()
    verification_seconds = 0.
    for record in records:
        if record.method != 'B2':
            continue
        candidate = record.decision.adapted_call
        decision = record.decision.model_copy(deep=True)
        started = perf_counter()
        if decision.action == 'EXECUTE':
            request = RecoveryInput.model_validate(record.recovery)
            verdict = verifier.verify(request,candidate)
            reasons[verdict.reason] += 1
            if not verdict.passed:
                decision = abstain(verdict.reason,verification=verdict.model_dump())
            else:
                decision.evidence['candidate_replay_verification'] = verdict.model_dump()
        elapsed = perf_counter() - started
        verification_seconds += elapsed
        updated = record.model_copy(update=dict(method='B2V',decision=decision,
            semantic_equivalent=record.semantic_equivalent if decision.action == 'EXECUTE' else None,
            validation_stages=record.validation_stages+int(candidate is not None),latency=record.latency+elapsed))
        result.append(updated)
    return result,dict(verification_seconds=verification_seconds,reasons=dict(reasons),
                       incremental_model_calls=0,candidate_generation_usage='inherited_from_B2_not_additional_requests',
                       latency_scope='sum_of_recorded_generation_and_later_replay_not_observed_end_to_end')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    manifest,records = read_results(args.run)
    if manifest['benchmark_version'] == 'compat-case-study-1.0':
        from mcp_compat.case_study_runtime import registry
        verifier = registry()
    else:
        from mcp_compat.runtime_fixtures import fixture_verifier
        verifier = fixture_verifier()
    rows,details = replay(records,verifier)
    payload = dict(source_run=str(args.run),source_manifest=deepcopy(manifest),
                   scope='same_candidate_verifier_only_not_full_M1',details=details,
                   metrics=metrics(rows),decisions=[dict(source_record=f'{r.repeat}-B2-{r.scenario_id}',
                       action=r.decision.action,reasons=r.decision.reasons,
                       semantic_equivalent=r.semantic_equivalent) for r in rows])
    with args.output.open('xb') as stream:
        stream.write(canonical_bytes(payload))
