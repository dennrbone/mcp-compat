"""Парный опыт финального допуска: один кандидат, runtime и профиль; меняется один шаг."""

import argparse
from pathlib import Path

import external_study as study
from mcp_compat.recovery import abstain, validate_candidate


def decide(case, method, runtime):
    if method not in ("FULL", "NO_FINAL"):
        raise ValueError("unknown admission ablation")
    decision = validate_candidate(case.request, case.candidate, method)
    if decision.action != "EXECUTE":
        return decision
    checker = study.verifier(case, runtime)
    checked = checker.verify(case.request, case.candidate)
    decision.evidence.update(verification=checked.model_dump(), semantic_verified=checked.passed)
    if not checked.passed:
        return abstain(checked.reason, **decision.evidence)
    decision.reasons = ["verified"]
    return (checker.admit(case.request, decision, current_state=study.current_state(case))
            if method == "FULL" else decision)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    study.METHODS = ("FULL", "NO_FINAL")
    study.STUDY_VERSION = "final-admission-ablation-1"
    study.decide = decide
    print("records", len(study.study(args.output, extra_sources=(Path(__file__),))))
