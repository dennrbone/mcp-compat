"""Frozen paired runs, durable resume, exact metric denominators, offline demo."""

import argparse
from datetime import datetime, timezone
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import platform
import re
from statistics import mean
from time import perf_counter, sleep
from typing import Any, Literal

from pydantic import Field, model_validator

from mcp_compat import MigrationDecision, ToolCall, canonical_bytes
from mcp_compat.benchmark import VERSION, equivalent, load, recovery_input
from mcp_compat.domain.scenarios import GroundTruth, MutationFamily
from mcp_compat.hybrid import Hybrid, RuntimeVerifier
from mcp_compat.llm import LLMRequest, LLMResponse, Mapper, PROMPT_VERSION, StrictModel
from mcp_compat.recovery import LLMBaseline, NoRecovery, RuleBased, Strategy, abstain
from mcp_compat.runtime_fixtures import fixture_verifier


class RunConfig(StrictModel):
    kind: Literal["offline_demo", "pilot", "main"]
    seed: int = 42
    benchmark_digest: str
    repeats: int = Field(default=1, ge=1)
    scenario_ids: list[str] | None = None
    model_versions: dict[str, str] = {}
    generation_parameters: dict[str, int | float | str] = {"temperature": 0, "max_tokens": 2048}
    interval_seconds: float = Field(default=0, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def fixed_generation(self):
        if self.generation_parameters != {"temperature":0,"max_tokens":2048}:
            raise ValueError("unsupported generation parameters; current transports use temperature=0, max_tokens=2048")
        return self


class Record(StrictModel):
    scenario_id: str
    method: str
    repeat: int
    mutation_family: MutationFamily
    ground_truth: GroundTruth
    recoverable: bool
    base_tool: str
    composed: bool
    decision: MigrationDecision
    schema_valid: bool | None
    semantic_equivalent: bool | None
    latency: float
    calls: int | None
    input_tokens: int | None
    output_tokens: int | None
    cost: float | None
    validation_stages: int
    recovery: dict[str, Any]


def _rate(numerator: int, denominator: int) -> dict:
    return dict(value=None if denominator == 0 else numerator / denominator,
                numerator=numerator, denominator=denominator)


def metrics(records: list[Record]) -> dict:
    recoverable = [r for r in records if r.recoverable]
    executed = [r for r in records if r.decision.action == "EXECUTE"]
    must = [r for r in records if r.ground_truth == "MUST_ABSTAIN"]
    generated = [r for r in records if r.schema_valid is not None]
    def total(field: str):
        values = [getattr(r, field) for r in records]
        return None if any(v is None for v in values) else sum(values)
    return dict(
        CRR=_rate(sum(r.decision.action == "EXECUTE" and r.semantic_equivalent is True for r in recoverable),len(recoverable)),
        UHR=_rate(sum(r.semantic_equivalent is not True for r in executed),len(executed)),
        FBR=_rate(sum(r.decision.action == "ABSTAIN" for r in recoverable),len(recoverable)),
        AbstentionAccuracy=_rate(sum(r.decision.action == "ABSTAIN" for r in must),len(must)),
        SchemaValidityRate=_rate(sum(r.schema_valid is True for r in generated),len(generated)),
        SemanticEquivalenceRate=_rate(sum(r.semantic_equivalent is True for r in executed),len(executed)),
        latency_mean=None if not records else mean(r.latency for r in records),
        calls=total("calls"), input_tokens=total("input_tokens"),
        output_tokens=total("output_tokens"), cost=total("cost"),
        validation_stages=sum(r.validation_stages for r in records), samples=len(records),
    )


def summaries(records: list[Record]) -> dict:
    return {method: dict(overall=metrics(rows),
        families={f"C{i}":metrics([r for r in rows if r.mutation_family == f"C{i}"]) for i in range(1,9)},
        categories={cat:metrics([r for r in rows if r.ground_truth == cat]) for cat in ("SAFE_AUTO","CONDITIONAL","MUST_ABSTAIN")})
        for method in sorted({r.method for r in records})
        for rows in [[r for r in records if r.method == method]]}


def _atomic(path: Path, value: Any) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(canonical_bytes(value))
    temporary.replace(path)


def run(config: RunConfig, strategies: list[Strategy], benchmark: Path, output: Path) -> list[Record]:
    names = [s.name for s in strategies]
    if not names or len(names) != len(set(names)) or any(not re.fullmatch(r"[A-Za-z0-9_-]+",n) for n in names):
        raise ValueError("invalid or duplicate methods")
    if config.kind != "offline_demo" and not config.model_versions:
        raise ValueError("main experiment requires explicit model versions")
    benchmark_manifest = json.loads((benchmark/"manifest.json").read_bytes())
    if config.kind == "main" and benchmark_manifest["version"] != VERSION:
        raise ValueError("retired benchmark cannot be used for a main experiment")
    scenarios = load(benchmark,config.benchmark_digest)
    if config.scenario_ids is not None:
        selected = set(config.scenario_ids)
        scenarios = [s for s in scenarios if s.scenario_id in selected]
        if len(scenarios) != len(config.scenario_ids):
            raise ValueError("unknown or duplicate scenario selection")
    if not scenarios:
        raise ValueError("empty experiment")
    dependencies: dict[str, str | None] = {}
    for package in ("mcp-compat","pydantic","jsonschema","httpx","mcp"):
        try:
            dependencies[package] = version(package)
        except PackageNotFoundError:
            dependencies[package] = None
    source = sha256(b"".join(p.read_bytes() for p in sorted(Path(__file__).parent.rglob("*.py")))).hexdigest()
    identity = dict(config=config.model_dump(),methods=names,prompt_version=PROMPT_VERSION,benchmark_version=benchmark_manifest["version"],
                    source_digest=source,python=platform.python_version(),dependencies=dependencies,
                    mapper_limits={s.name:dict(attempts=m.attempts,timeout=m.timeout,backoff=m.backoff)
                        for s in strategies if isinstance(m:=getattr(s,"mapper",None),Mapper)})
    fingerprint = sha256(canonical_bytes(identity)).hexdigest()
    output.mkdir(parents=True,exist_ok=True)
    manifest_path = output/"manifest.json"
    if manifest_path.exists():
        if json.loads(manifest_path.read_bytes())["fingerprint"] != fingerprint:
            raise ValueError("resume configuration mismatch")
    else:
        if any(output.iterdir()):
            raise ValueError("nonempty output without manifest")
        _atomic(manifest_path,dict(identity, fingerprint=fingerprint, created_at=datetime.now(timezone.utc).isoformat()))
    digests_path = output/"result-digests.json"
    prior_digests = json.loads(digests_path.read_bytes()) if digests_path.exists() else {}
    records = []
    for repeat in range(config.repeats):
        for scenario in scenarios:
            for strategy in strategies:
                path = output/f"{repeat}-{strategy.name}-{scenario.scenario_id}.json"
                key = path.stem
                if path.exists():
                    record = Record.model_validate_json(path.read_bytes())
                    if key in prior_digests and sha256(canonical_bytes(record.model_dump())).hexdigest() != prior_digests[key]:
                        raise ValueError("corrupt resume record digest")
                    if (record.scenario_id,record.method,record.repeat) != (scenario.scenario_id,strategy.name,repeat):
                        raise ValueError("corrupt resume record")
                    records.append(record)
                    continue
                if key in prior_digests:
                    raise ValueError("missing completed record")
                request = recovery_input(scenario)
                started = perf_counter()
                try:
                    decision = strategy.recover(request.model_copy(deep=True))
                except Exception as exc:
                    decision = abstain("strategy_error",error_type=type(exc).__name__,usage_unknown=True)
                latency = perf_counter() - started
                candidate = decision.adapted_call
                valid = None
                if candidate is None and "candidate" in decision.evidence:
                    try:
                        candidate = ToolCall.model_validate(decision.evidence["candidate"])
                    except ValueError:
                        valid = False
                if candidate is not None:
                    try:
                        candidate.validate_against(scenario.new_contract)
                        valid = True
                    except ValueError:
                        valid = False
                semantic = None
                if decision.action == "EXECUTE":
                    assert decision.adapted_call is not None
                    semantic = equivalent(scenario,decision.adapted_call)
                trace = decision.evidence.get("llm", {})
                calls, responses = trace.get("calls",0), trace.get("responses",[])
                if decision.evidence.get("usage_unknown"):
                    calls = None
                def usage(field):
                    if calls is None:
                        return None
                    if not calls:
                        return 0
                    return None if len(responses) != calls or any(r.get(field) is None for r in responses) else sum(r[field] for r in responses)
                record = Record(scenario_id=scenario.scenario_id,method=strategy.name,repeat=repeat,
                    mutation_family=scenario.mutation_family,ground_truth=scenario.ground_truth,
                    recoverable=scenario.metadata["recoverable"],base_tool=scenario.metadata["base_tool"],
                    composed=scenario.metadata["composed"],decision=decision,schema_valid=valid,
                    semantic_equivalent=semantic,latency=latency,calls=calls,input_tokens=usage("input_tokens"),
                    output_tokens=usage("output_tokens"),cost=usage("cost"),
                    validation_stages=int(valid is not None)+decision.evidence.get("verification_attempts", int("verification" in decision.evidence)),
                    recovery=request.model_dump())
                _atomic(path,record.model_dump(mode="json"))
                records.append(record)
                if config.interval_seconds:
                    sleep(config.interval_seconds)
    _atomic(output/"summary.json",summaries(records))
    _atomic(output/"result-digests.json",{f"{r.repeat}-{r.method}-{r.scenario_id}":sha256(canonical_bytes(r.model_dump())).hexdigest() for r in records})
    return records


class OfflineClient:
    """Protocol demo, no model inference and no oracle access."""

    def complete(self, request: LLMRequest, timeout: float) -> LLMResponse:
        proposal = {"action":"ABSTAIN"}
        if request.data["purpose"] == "mapping":
            proposal = dict(action="EXECUTE",operations=request.data["context"].get("rules",[]))
        return LLMResponse(text=json.dumps(proposal),model="offline-demo-no-inference",
                           input_tokens=0,output_tokens=0,cost=0.)


def recovery_methods(mapper: Mapper, verifier: RuntimeVerifier | None = None) -> list[Strategy]:
    if verifier is None:
        verifier = fixture_verifier()
    ablations: list[Literal["A1","A2","A3","A4"]] = ["A1","A2","A3","A4"]
    return [NoRecovery(),LLMBaseline("B1",mapper),LLMBaseline("B2",mapper),RuleBased(),Hybrid(mapper,verifier),
            *[Hybrid(mapper,verifier,ablation=a) for a in ablations]]


def offline_methods() -> list[Strategy]:
    return recovery_methods(Mapper(OfflineClient(),attempts=1))


def demo_cli(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Offline engineering demo; not a scientific experiment")
    parser.add_argument("--index",type=Path,default=Path("benchmark/manifest.json"))
    parser.add_argument("--output",type=Path,default=Path("experiments/offline-demo"))
    args = parser.parse_args(argv)
    index = json.loads(args.index.read_bytes())
    scenarios = load(Path(index["path"]),index["digest"])
    ids = [s.scenario_id for s in scenarios if s.metadata["base_tool"] == "commerce_quote"]
    config = RunConfig(kind="offline_demo",benchmark_digest=index["digest"],scenario_ids=ids,
        model_versions={"fake":"offline-demo-no-inference"})
    records = run(config,offline_methods(),Path(index["path"]),args.output)
    print(f"OFFLINE DEMO ONLY: {len(records)} records; no real LLM inference")
