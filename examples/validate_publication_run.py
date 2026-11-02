"""Проверка полноты, меток, закрытой оценки и хешей завершённого запуска."""

import argparse
import json
from pathlib import Path

from mcp_compat import canonical_bytes
from mcp_compat.analysis import read_results
from mcp_compat.benchmark import equivalent, load, recovery_input
from mcp_compat.experiments import summaries


def validate(directory: Path, benchmark: Path) -> dict:
    manifest,records = read_results(directory)
    config = manifest['config']
    cases = {s.scenario_id:s for s in load(benchmark,config['benchmark_digest'])}
    selected = set(config['scenario_ids'] if config['scenario_ids'] is not None else cases)
    assert selected <= cases.keys(), 'unknown scenario'
    expected = {(sid,method,repeat) for sid in selected for method in manifest['methods'] for repeat in range(config['repeats'])}
    actual = {(r.scenario_id,r.method,r.repeat) for r in records}
    assert len(records) == len(expected) and actual == expected, 'incomplete or duplicate matrix'
    for r in records:
        s = cases[r.scenario_id]
        assert (r.ground_truth,r.mutation_family,r.recoverable,r.base_tool,r.composed) == (
            s.ground_truth,s.mutation_family,s.metadata['recoverable'],s.metadata['base_tool'],s.metadata['composed']), 'label mismatch'
        assert r.recovery == recovery_input(s).model_dump(), 'recovery input mismatch'
        semantic = equivalent(s,r.decision.adapted_call) if r.decision.action == 'EXECUTE' else None
        assert semantic is r.semantic_equivalent, 'evaluation mismatch'
    assert canonical_bytes(json.loads((directory/'summary.json').read_bytes())) == canonical_bytes(summaries(records)), 'summary mismatch'
    return dict(status='PASS',records=len(records),scenarios=len(selected),methods=manifest['methods'],
                repeats=config['repeats'],source_digest=manifest['source_digest'],
                benchmark_digest=config['benchmark_digest'],checks=['hashes','matrix','labels','recovery_input','semantic_evaluation','summary'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--benchmark',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    result = validate(args.run,args.benchmark)
    with args.output.open('xb') as stream:
        stream.write(canonical_bytes(result))
    print(json.dumps(result,ensure_ascii=False))
