"""Воспроизводит зафиксированную прикладную проверку только через CodeAgent."""

import json
from pathlib import Path

from mcp_compat.agent_checks import cli_version
from mcp_compat.case_study_runtime import registry
from mcp_compat.declared_rules import DeclaredRules, VerifiedDeclaredRules
from mcp_compat.experiments import RunConfig, run
from mcp_compat.hybrid import Hybrid
from mcp_compat.llm import Mapper
from mcp_compat.providers import AgentProvider, from_env
from mcp_compat.recovery import LLMBaseline, RuleBased


if __name__ == "__main__":
    root = Path("experiments/publication-2026-11-03/case-study")
    provider = from_env()
    version = cli_version(provider)
    mapper = Mapper(AgentProvider(provider),attempts=2,timeout=120)
    verifier = registry()
    methods = [RuleBased(),DeclaredRules(),VerifiedDeclaredRules(verifier),
               LLMBaseline("B2",mapper),Hybrid(mapper,verifier)]
    for regime in ("with-rules","without-rules"):
        data = root/"data"/regime
        digest = json.loads((data/"manifest.json").read_bytes())["digest"]
        config = RunConfig(kind="main",benchmark_digest=digest,repeats=3,workers=4,
                           interval_seconds=1,model_versions={"gigacode":provider.model,"cli":version})
        records = run(config,methods,data,root/"runs"/regime)
        assert len(records) == 2880
        print(f"{regime}: сохранено {len(records)} решений",flush=True)
