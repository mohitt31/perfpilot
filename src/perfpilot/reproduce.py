"""Cross-machine evidence comparison without pooling unlike experiments."""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import Field

from perfpilot.evidence.io import load_and_validate_bundle
from perfpilot.evidence.schema import CandidateResult, EvidenceBundle, StrictModel


class ReproductionOutcome(StrEnum):
    INCOMPARABLE = "incomparable"
    NO_SHARED_CANDIDATE = "no_shared_candidate"
    CONSISTENT_SIGNAL = "consistent_signal"
    CONFLICTING_SIGNAL = "conflicting_signal"
    INCONCLUSIVE = "inconclusive"


class CandidateComparison(StrictModel):
    patch_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    first_candidate_id: str
    second_candidate_id: str
    first_decision: str
    second_decision: str
    first_effect_fraction: float | None
    second_effect_fraction: float | None
    first_confidence_interval: tuple[float, float] | None
    second_confidence_interval: tuple[float, float] | None
    confidence_intervals_overlap: bool | None
    signal: Literal["consistent", "conflicting", "inconclusive"]


class ReproductionReport(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    first_run_id: str
    second_run_id: str
    outcome: ReproductionOutcome
    same_repository_commit: bool
    same_benchmark_policy: bool
    same_machine: bool
    machine_differences: tuple[str, ...]
    candidates: tuple[CandidateComparison, ...]
    limitations: tuple[str, ...] = Field(min_length=1)


def _artifact_hashes(bundle: EvidenceBundle) -> dict[str, str]:
    return {artifact.artifact_id: artifact.sha256 for artifact in bundle.artifacts}


def _candidates_by_patch(bundle: EvidenceBundle) -> dict[str, CandidateResult]:
    hashes = _artifact_hashes(bundle)
    return {hashes[item.patch_artifact_id]: item for item in bundle.candidates}


def _intervals_overlap(
    first: tuple[float, float] | None, second: tuple[float, float] | None
) -> bool | None:
    if first is None or second is None:
        return None
    return max(first[0], second[0]) <= min(first[1], second[1])


def _candidate_comparison(
    patch_sha256: str, first: CandidateResult, second: CandidateResult
) -> CandidateComparison:
    overlap = _intervals_overlap(
        first.confidence_interval_fraction, second.confidence_interval_fraction
    )
    first_effect = first.observed_speedup_fraction
    second_effect = second.observed_speedup_fraction
    if first_effect is None or second_effect is None:
        signal: Literal["consistent", "conflicting", "inconclusive"] = "inconclusive"
    elif (first_effect > 0) != (second_effect > 0):
        signal = "conflicting"
    elif overlap is False:
        # Non-overlap is not automatically conflict: effect sizes may differ across machines.
        signal = "consistent"
    else:
        signal = "consistent"
    return CandidateComparison(
        patch_sha256=patch_sha256,
        first_candidate_id=first.candidate_id,
        second_candidate_id=second.candidate_id,
        first_decision=first.decision.value,
        second_decision=second.decision.value,
        first_effect_fraction=first.observed_speedup_fraction,
        second_effect_fraction=second.observed_speedup_fraction,
        first_confidence_interval=first.confidence_interval_fraction,
        second_confidence_interval=second.confidence_interval_fraction,
        confidence_intervals_overlap=overlap,
        signal=signal,
    )


def compare_bundles(first: EvidenceBundle, second: EvidenceBundle) -> ReproductionReport:
    same_repository = first.repository == second.repository
    same_policy = first.benchmark == second.benchmark
    first_machine = first.environment.machine
    second_machine = second.environment.machine
    same_machine = first_machine == second_machine
    fields = (
        "os",
        "kernel",
        "architecture",
        "cpu_model",
        "logical_cpu_count",
        "memory_bytes",
        "cpu_governor",
        "cpu_affinity",
    )
    differences = tuple(
        f"{field}: {getattr(first_machine, field)!r} != {getattr(second_machine, field)!r}"
        for field in fields
        if getattr(first_machine, field) != getattr(second_machine, field)
    )
    first_candidates = _candidates_by_patch(first)
    second_candidates = _candidates_by_patch(second)
    shared = sorted(first_candidates.keys() & second_candidates.keys())
    comparisons = tuple(
        _candidate_comparison(digest, first_candidates[digest], second_candidates[digest])
        for digest in shared
    )
    if not same_repository or not same_policy:
        outcome = ReproductionOutcome.INCOMPARABLE
    elif not comparisons:
        outcome = ReproductionOutcome.NO_SHARED_CANDIDATE
    elif any(item.signal == "conflicting" for item in comparisons):
        outcome = ReproductionOutcome.CONFLICTING_SIGNAL
    elif all(item.signal == "consistent" for item in comparisons):
        outcome = ReproductionOutcome.CONSISTENT_SIGNAL
    else:
        outcome = ReproductionOutcome.INCONCLUSIVE
    return ReproductionReport(
        first_run_id=first.run_id,
        second_run_id=second.run_id,
        outcome=outcome,
        same_repository_commit=same_repository,
        same_benchmark_policy=same_policy,
        same_machine=same_machine,
        machine_differences=differences,
        candidates=comparisons,
        limitations=(
            "This comparison does not pool samples or prove portability; each run retains its own "
            "predeclared test and confidence interval.",
            "Matching patch bytes and effect direction cannot establish semantic equivalence or "
            "exclude machine-specific behavior.",
        ),
    )


def compare_bundle_directories(first_path: Path, second_path: Path) -> ReproductionReport:
    return compare_bundles(
        load_and_validate_bundle(first_path), load_and_validate_bundle(second_path)
    )


def write_reproduction_report(path: Path, report: ReproductionReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
