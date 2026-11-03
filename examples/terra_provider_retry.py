"""Перезапись только провайдерных отказов по явному указанию автора."""

import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import shutil

from codex_transport import CodexClient
from mcp_compat import canonical_bytes
from mcp_compat.analysis import read_results
from mcp_compat.benchmark import load
from mcp_compat.case_study_runtime import registry
from mcp_compat.experiments import Record, _atomic, _evaluate, summaries
from mcp_compat.hybrid import Hybrid
from mcp_compat.llm import Mapper
from mcp_compat.providers import ProviderError
from mcp_compat.recovery import LLMBaseline

ROOT = Path('experiments/terra-2026-11-03')
SOURCE = 'ccd2591e512801b45a81d0a1c426c802a5b380ec680ae03c13c2fd31efd24397'
EXPECTED_RECORDS = 2880


def provider_failure(record):
    trace = record.decision.evidence.get('llm', {})
    errors = trace.get('parse_errors', [])
    return (record.decision.action == 'ABSTAIN' and trace.get('parse_status') != 'parsed'
            and bool(errors) and errors[-1]['error_type'] == 'ProviderError')


def combine(previous, fresh, selection_digest, previous_hash):
    fields = ('scenario_id', 'method', 'repeat', 'ground_truth', 'mutation_family',
              'recoverable', 'base_tool', 'composed', 'recovery')
    if any(getattr(previous, f) != getattr(fresh, f) for f in fields) or not provider_failure(previous):
        raise ValueError('replacement identity or eligibility mismatch')
    result = fresh.model_copy(deep=True)
    old_trace = previous.decision.evidence.get('llm', {})
    new_trace = result.decision.evidence.setdefault('llm', {})
    for field in ('requests', 'responses', 'parse_errors'):
        new_trace[field] = deepcopy(old_trace.get(field, []))+new_trace.get(field, [])
    new_trace['calls'] = old_trace.get('calls', 0)+new_trace.get('calls', 0)
    result.decision.evidence['provider_retry'] = dict(
        selection_digest=selection_digest, previous_byte_hash=previous_hash,
        retry_evaluations=previous.decision.evidence.get('provider_retry', {}).get('retry_evaluations', 0)+1,
        applied_at_utc=datetime.now(timezone.utc).isoformat(),
        original_reasons=previous.decision.reasons, prior_calls=previous.calls,
        extra_calls=fresh.calls, fresh_usage={k:getattr(fresh, k) for k in ('input_tokens', 'output_tokens', 'cost')},
        latency_scope='sum of original and retry components, not live end-to-end elapsed time')
    for field in ('calls', 'input_tokens', 'output_tokens', 'cost'):
        old, new = getattr(previous, field), getattr(fresh, field)
        setattr(result, field, None if old is None or new is None else old+new)
    result.latency += previous.latency
    result.validation_stages += previous.validation_stages
    return result


def execute(executable):
    backup = ROOT/'before-provider-retry'
    plan_path = ROOT/'provider-retry-plan.json'
    if not plan_path.exists():
        selection, manifests = {}, {}
        for regime in ('with-rules', 'without-rules'):
            directory = ROOT/'runs'/regime
            manifest, records = read_results(directory)
            if len(records) != EXPECTED_RECORDS or manifest['source_digest'] != SOURCE:
                raise ValueError('complete frozen main run required before replacement')
            manifests[regime] = manifest
            target = backup/regime
            target.mkdir(parents=True, exist_ok=True)
            for name in ('manifest.json', 'summary.json', 'result-digests.json'):
                if (target/name).exists():
                    if (target/name).read_bytes() != (directory/name).read_bytes():
                        raise ValueError('existing original backup differs')
                else:
                    shutil.copyfile(directory/name, target/name)
            for row in records:
                if provider_failure(row):
                    name = f'{row.repeat}-{row.method}-{row.scenario_id}.json'
                    data = (directory/name).read_bytes()
                    if (target/name).exists() and (target/name).read_bytes() != data:
                        raise ValueError('existing record backup differs')
                    (target/name).write_bytes(data)
                    selection[regime+'/'+name] = sha256(data).hexdigest()
        digest = sha256(canonical_bytes(selection)).hexdigest()
        plan = dict(selection=selection, selection_digest=digest, original_manifests=manifests,
                    resolved_passes_per_target=1, attempts_per_pass=2, timeout=120, workers=4,
                    stop_on_terminal_provider_failure=True,
                    script_sha256=sha256(Path(__file__).read_bytes()).hexdigest(), completed={}, status='in_progress')
        _atomic(plan_path, plan)
    plan = json.loads(plan_path.read_bytes())
    if plan['script_sha256'] != sha256(Path(__file__).read_bytes()).hexdigest():
        raise ValueError('retry script changed since selection')
    if plan['status'] == 'complete':
        if any(sha256((ROOT/'runs'/key).read_bytes()).hexdigest() != expected
               for key, expected in plan['completed'].items()):
            raise ValueError('completed replacement hash mismatch')
        return plan
    mapper = Mapper(CodexClient(executable), attempts=2, timeout=120)
    methods = dict(B2=LLMBaseline('B2', mapper), M1=Hybrid(mapper, registry()))
    cases = {regime:{s.scenario_id:s for s in load(
        Path('experiments/publication-2026-11-03/case-study/data')/regime,
        manifest['config']['benchmark_digest'])} for regime, manifest in plan['original_manifests'].items()}
    jobs = []
    for key, expected in plan['selection'].items():
        path = ROOT/'runs'/key
        original_bytes = (backup/key).read_bytes()
        if sha256(original_bytes).hexdigest() != expected:
            raise ValueError('original backup hash mismatch')
        previous = Record.model_validate_json(original_bytes)
        current = Record.model_validate_json(path.read_bytes())
        marker = current.decision.evidence.get('provider_retry', {})
        known = plan['completed'].get(key) or plan.get('unavailable', {}).get(key)
        if known and sha256(path.read_bytes()).hexdigest() != known:
            raise ValueError('record changed after saved retry')
        if sha256(path.read_bytes()).hexdigest() == expected:
            jobs.append((key, previous))
        elif marker.get('selection_digest') == plan['selection_digest'] and marker.get('previous_byte_hash') == expected:
            if provider_failure(current):
                jobs.append((key, current))
            else:
                plan['completed'][key] = sha256(path.read_bytes()).hexdigest()
                plan.get('unavailable', {}).pop(key, None)
        else:
            raise ValueError('record changed outside the registered replacement')
    _atomic(plan_path, plan)
    with ThreadPoolExecutor(max_workers=4) as executor:
        pending, running = iter(jobs), {}
        exhausted, halted = False, False
        while running or not exhausted:
            while len(running) < 4 and not exhausted:
                job = next(pending, None)
                if job is None:
                    exhausted = True
                else:
                    key, previous = job
                    regime = key.split('/')[0]
                    future = executor.submit(_evaluate, cases[regime][previous.scenario_id], methods[previous.method], previous.repeat, 1)
                    running[future] = (key, previous)
            if not running:
                break
            done, _ = wait(running, return_when=FIRST_COMPLETED)
            for future in done:
                key, previous = running.pop(future)
                result = combine(previous, future.result(), plan['selection_digest'], plan['selection'][key])
                path = ROOT/'runs'/key
                _atomic(path, result.model_dump(mode='json'))
                if provider_failure(result):
                    plan.setdefault('unavailable', {})[key] = sha256(path.read_bytes()).hexdigest()
                    exhausted, halted = True, True
                else:
                    plan['completed'][key] = sha256(path.read_bytes()).hexdigest()
                    plan.get('unavailable', {}).pop(key, None)
                _atomic(plan_path, plan)
    if halted:
        plan.setdefault('transport_stops', []).append(dict(at_utc=datetime.now(timezone.utc).isoformat(),
                                                         unresolved=list(plan.get('unavailable', {}))))
        _atomic(plan_path, plan)
        raise ProviderError('provider retry stopped after unavailable response; restore access before resuming')
    for regime, original in plan['original_manifests'].items():
        directory = ROOT/'runs'/regime
        digests = json.loads((backup/regime/'result-digests.json').read_bytes())
        rows = [Record.model_validate_json((directory/(key+'.json')).read_bytes()) for key in digests]
        for key, row in zip(digests, rows):
            if regime+'/'+key+'.json' not in plan['selection'] and sha256(canonical_bytes(row.model_dump())).hexdigest() != digests[key]:
                raise ValueError('untargeted record changed')
        _atomic(directory/'summary.json', summaries(rows))
        _atomic(directory/'result-digests.json', {f'{r.repeat}-{r.method}-{r.scenario_id}':sha256(canonical_bytes(r.model_dump())).hexdigest() for r in rows})
        manifest = deepcopy(original)
        manifest.pop('fingerprint')
        manifest['provider_retry_policy'] = dict(original_fingerprint=original['fingerprint'],
            selection_digest=plan['selection_digest'], script_sha256=plan['script_sha256'],
            resolved_passes_per_target=1, attempts_per_pass=2, source_backup=str(backup/regime),
            stop_on_terminal_provider_failure=True, transport_stops=len(plan.get('transport_stops', [])),
            calls_scope='all original and retry CLI invocations; unknown usage remains unknown',
            latency_scope='mixed original measurements and summed retry components; no causal latency comparison')
        identity = {k:v for k,v in manifest.items() if k != 'created_at'}
        manifest['fingerprint'] = sha256(canonical_bytes(identity)).hexdigest()
        _atomic(directory/'manifest.json', manifest)
    plan['status'] = 'complete'
    plan['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
    _atomic(plan_path, plan)
    return plan


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', required=True)
    args = parser.parse_args()
    import mcp_compat.experiments as engine
    digest = sha256(b''.join(p.read_bytes() for p in sorted(Path(engine.__file__).parent.rglob('*.py')))).hexdigest()
    if digest != SOURCE:
        raise ValueError('use the frozen phase18-fda30006 PYTHONPATH')
    result = execute(args.executable)
    print('Перезаписано провайдерных отказов:', len(result['completed']), 'из', len(result['selection']))
