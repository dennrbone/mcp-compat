"""Отдельное сравнение Terra на неизменённых прикладных сценариях Phase 18."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from pydantic import model_validator

from codex_transport import CodexClient, MODEL, PARAMETERS
from mcp_compat.case_study_runtime import registry
from mcp_compat.declared_rules import DeclaredRules, VerifiedDeclaredRules
from mcp_compat.experiments import RunConfig, run
from mcp_compat.hybrid import Hybrid
from mcp_compat.llm import Mapper
from mcp_compat.recovery import LLMBaseline, RuleBased


class TerraRunConfig(RunConfig):
    @model_validator(mode='after')
    def fixed_generation(self):
        if self.generation_parameters != PARAMETERS:
            raise ValueError('unsupported Terra generation parameters')
        return self


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--pilot', action='store_true')
    args = parser.parse_args()
    client = CodexClient(args.executable)
    version = subprocess.run([args.executable, '--version'], text=True, capture_output=True,
                             timeout=30, check=True).stdout.strip()
    mapper = Mapper(client, attempts=2, timeout=120)
    verifier = registry()
    methods = [RuleBased(), DeclaredRules(), VerifiedDeclaredRules(verifier),
               LLMBaseline('B2', mapper), Hybrid(mapper, verifier)]
    root = Path('experiments/publication-2026-11-03/case-study/data')
    helper_digest = sha256(Path(__file__).read_bytes()+Path(__file__).with_name('codex_transport.py').read_bytes()).hexdigest()
    for regime in ('with-rules', 'without-rules'):
        data = root/regime
        manifest = json.loads((data/'manifest.json').read_bytes())
        selected = None
        if args.pilot:
            # Первый инструмент и первый профиль выбраны до ответов модели.
            selected = sorted(k for k in manifest['files'] if k.startswith('documents_words-0-'))
            assert len(selected) == 8
        config = TerraRunConfig(kind='pilot' if args.pilot else 'main',
            benchmark_digest=manifest['digest'], repeats=1 if args.pilot else 3,
            workers=4, interval_seconds=1, scenario_ids=selected,
            generation_parameters=PARAMETERS,
            model_versions=dict(model=MODEL, cli=version, helper_sha256=helper_digest))
        records = run(config, methods, data, args.output/regime)
        assert len(records) == (40 if args.pilot else 2880)
        print(f'{regime}: сохранено {len(records)} решений', flush=True)
