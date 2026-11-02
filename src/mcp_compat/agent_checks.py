"""Real CLI smoke, a stratified pilot, or a resumable full CodeAgent benchmark."""

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
from mcp_compat.llm import LLMRequest, Mapper, parse_proposal, response_schema, SYSTEM_PROMPT
from mcp_compat.providers import AgentProvider, MODEL_ID, ProviderConfig, ProviderError, from_env
from mcp_compat.runtime_fixtures import fixture_verifier


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
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--pilot", action="store_true")
    mode.add_argument("--full", action="store_true")
    parser.add_argument("--workers", type=int, choices=range(1,9), default=1)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--index", type=Path, default=Path("benchmark/manifest.json"))
    args = parser.parse_args(argv)
    if args.resume and not (args.full or args.pilot):
        parser.error("--resume requires --full or --pilot")
    args.output.mkdir(parents=True, exist_ok=True)
    if args.resume:
        report = json.loads((args.output / "smoke.json").read_bytes())
        config = from_env()
        if report["status"] != "PASS" or report["cli_version"] != cli_version(config):
            raise ValueError("resume requires a passed smoke with the same CLI version")
    else:
        report = smoke(args.output)
        config = from_env()
    if args.pilot or args.full:
        index = json.loads(args.index.read_bytes())
        benchmark = Path(index["path"])
        scenarios = load(benchmark, index["digest"])
        run_config = RunConfig(kind="main" if args.full else "pilot", benchmark_digest=index["digest"],
            scenario_ids=None if args.full else pilot_ids(scenarios), workers=args.workers,
            model_versions={"gigacode":config.model, "cli":str(report["cli_version"])}, interval_seconds=1)
        mapper = Mapper(AgentProvider(config), attempts=2, timeout=120)
        verifier = fixture_verifier()
        methods = recovery_methods(mapper,verifier)
        print(f"REAL {'FULL BENCHMARK' if args.full else 'PILOT'}: {len(scenarios) if args.full else len(run_config.scenario_ids or [])} scenarios; {len(methods)} methods; one repeat; {args.workers} workers", flush=True)
        records = run(run_config, methods, benchmark, args.output / run_config.kind)
        print(f"COMPLETED: {len(records)} decisions; one repeat; {len(verifier.bindings)} trusted synthetic runtime bindings", flush=True)


def smoke(output: Path) -> dict[str, Any]:
    if (output / "smoke.json").exists():
        raise FileExistsError("smoke evidence already exists; use the runner API to resume its pilot")
    report: dict[str, Any] = dict(scope="strict_json_smoke", provider="gigacode", model=MODEL_ID, status="FAIL")
    try:
        config = from_env()
        report["cli_version"] = cli_version(config)
        client = AgentProvider(config)
        response = client.complete(LLMRequest(system=PROBE_PROMPT, data={}, response_schema=response_schema("mapping")), 120)
        report["response"] = response.model_dump()
        if parse_proposal(response.text,"mapping")[0].action != "ABSTAIN":
            raise ProviderError("probe_expected_abstain")
        report["status"] = "PASS"
    except Exception as exc:
        report["error_type"] = type(exc).__name__
        report["reason"] = str(exc) if isinstance(exc, ProviderError) else "configuration_or_response_invalid"
    with (output / "smoke.json").open("xb") as handle:
        handle.write(canonical_bytes(report))
    print(json.dumps(report))
    if report["status"] != "PASS":
        raise SystemExit(1)
    return report
