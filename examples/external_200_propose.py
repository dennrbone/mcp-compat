"""Collect one traceable direct proposal per case from the requested real provider."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
from time import perf_counter

from codex_transport import MODEL, CodexClient
from external_200_dataset import read
from mcp_compat.agent_checks import cli_version
from mcp_compat.experiments import _atomic
from mcp_compat.llm import Mapper
from mcp_compat.providers import AgentProvider, from_env
from mcp_compat.verification import fingerprint


def collect(provider, output, workers, retry_provider_errors):
    digest, cases = read("public.json")
    if provider == "codeagent":
        config = from_env()
        client = AgentProvider(config)
        model, version = config.model, cli_version(config)
    else:
        executable = shutil.which("codex")
        if executable is None:
            raise ValueError("Codex CLI unavailable")
        client = CodexClient(executable)
        model = MODEL
        version = subprocess.run([executable, "--version"], text=True, capture_output=True,
                                 timeout=25, check=True).stdout.strip()
    mapper = Mapper(client, attempts=2, timeout=120)
    manifest = dict(dataset=digest, provider=provider, model=model, cli_version=version, purpose="B2",
                    mapper_attempts=2, timeout_seconds=120, workers=workers,
                    runner=sha256(Path(__file__).read_bytes()).hexdigest())
    output.mkdir(parents=True, exist_ok=True)
    manifest_file = output / "manifest.json"
    if manifest_file.exists():
        if json.loads(manifest_file.read_bytes()) != manifest:
            raise ValueError("provider or benchmark differs from saved run")
    else:
        _atomic(manifest_file, manifest)

    def propose(case):
        path = output / f"{case.case_id}.json"
        request = case.request.model_copy(deep=True)
        request_id = fingerprint(request.model_dump())
        previous = None
        if path.exists():
            previous = json.loads(path.read_bytes())
            assert previous["request"] == request_id
            if not (retry_provider_errors and previous["mapping"]["proposal"] is None
                    and previous["mapping"]["trace"].get("last_error_type") == "ProviderError"
                    and "initial_attempt" not in previous):
                return previous
        start = perf_counter()
        mapping = mapper.propose_mapping(request, purpose="B2")
        record = dict(case_id=case.case_id, request=request_id, mapping=mapping.model_dump(),
                      seconds=perf_counter() - start)
        if previous is not None:
            record["initial_attempt"] = previous
        _atomic(path, record)
        return record

    total = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, record in enumerate(pool.map(propose, cases), start=1):
            total += record["mapping"]["proposal"] is not None
            if i % 10 == 0 or i == len(cases):
                print(f"{provider}: {i}/{len(cases)} stored, {total} parsed", flush=True)
    assert len(list(output.glob("*.json"))) == len(cases) + 1


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("provider", choices=("codeagent", "terra"))
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--workers", type=int, choices=range(1, 9), default=4)
    p.add_argument("--retry-provider-errors", action="store_true")
    args = p.parse_args()
    collect(args.provider, args.output, args.workers, args.retry_provider_errors)
