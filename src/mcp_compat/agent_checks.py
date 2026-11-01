"""Real CLI smoke and a stratified pilot; never a full scientific study."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any

from mcp_compat import canonical_bytes
from mcp_compat.benchmark import load
from mcp_compat.domain.scenarios import EvolutionScenario
from mcp_compat.experiments import RunConfig, recovery_methods, run
from mcp_compat.llm import LLMRequest, Mapper, Proposal, SYSTEM_PROMPT
from mcp_compat.providers import AgentProvider, MODEL_ID, ProviderConfig, ProviderError, from_env


PROBE_PROMPT = SYSTEM_PROMPT + ' This is a connectivity probe: return only {"action":"ABSTAIN"}, without Markdown.'


def pilot_ids(scenarios: list[EvolutionScenario], seed: int = 42) -> list[str]:
    groups: dict[tuple[str, str], str] = {}
    ranked = sorted(scenarios, key=lambda s: sha256(f"{seed}:{s.scenario_id}".encode()).hexdigest())
    for scenario in ranked:
        groups.setdefault((scenario.mutation_family, scenario.ground_truth), scenario.scenario_id)
    # Include the independently bound runtime fixture; never bind the private oracle.
    return sorted(set(groups.values()) | {"commerce-0-C8-0"})


def cli_version(config: ProviderConfig) -> str:
    result = subprocess.run([config.executable, "--version"], capture_output=True, text=True,
                            timeout=10, check=True, env={**os.environ, 'NODE_TLS_REJECT_UNAUTHORIZED':'1'})
    versions = [line.strip() for line in result.stdout.splitlines() if re.fullmatch(r"\d+\.\d+\.\d+", line.strip())]
    if len(versions) != 1:
        raise ProviderError("provider_version_unavailable")
    return versions[0]


def agent_cli(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--index", type=Path, default=Path("benchmark/manifest.json"))
    args = parser.parse_args(argv)
    report: dict[str, Any] = dict(scope="strict_json_smoke", provider="gigacode", model=MODEL_ID, status="FAIL")
    try:
        config = from_env()
        report["cli_version"] = cli_version(config)
        client = AgentProvider(config)
        response = client.complete(LLMRequest(system=PROBE_PROMPT, data={}, response_schema=Proposal.model_json_schema()), 120)
        report["response"] = response.model_dump()
        if Proposal.model_validate_json(response.text).action != "ABSTAIN":
            raise ProviderError("probe_expected_abstain")
        report["status"] = "PASS"
    except Exception as exc:
        report["error_type"] = type(exc).__name__
        report["reason"] = str(exc) if isinstance(exc, ProviderError) else "configuration_or_response_invalid"
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / "smoke.json").open("xb") as handle:
        handle.write(canonical_bytes(report))
    print(json.dumps(report))
    if report["status"] != "PASS":
        raise SystemExit(1)
    if args.pilot:
        index = json.loads(args.index.read_bytes())
        benchmark = Path(index["path"])
        scenarios = load(benchmark, index["digest"])
        run_config = RunConfig(kind="pilot", benchmark_digest=index["digest"], scenario_ids=pilot_ids(scenarios),
            model_versions={"gigacode":config.model, "cli":str(report["cli_version"])}, interval_seconds=1)
        mapper = Mapper(client, attempts=1, timeout=120)
        records = run(run_config, recovery_methods(mapper), benchmark, args.output / "pilot")
        print(f"REAL PILOT ONLY: {len(records)} decisions; one repeat; runtime binding limited to one contract pair")
