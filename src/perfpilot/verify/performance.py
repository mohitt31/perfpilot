"""A/A calibration and randomized paired A/B verification."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, replace
from pathlib import Path
from statistics import median

import numpy as np

from perfpilot.benchmark import BenchmarkError, extract_measurement
from perfpilot.evidence.schema import (
    AACalibration,
    CalibrationDecision,
    CandidateResult,
    Claim,
    Decision,
    JobSpec,
    RunStatus,
)
from perfpilot.ingest.pipeline import BaselineResult, write_manifest
from perfpilot.verify.statistics import (
    EffectInterval,
    bootstrap_median_interval,
    holm_adjust,
    paired_log_improvements,
    paired_sign_permutation_p_value,
    relative_improvements,
)


class VerificationError(RuntimeError):
    """The statistical verification contract could not be completed."""


def _measure(
    baseline: BaselineResult,
    job: JobSpec,
    *,
    command_id: str,
    purpose: str,
    cwd: Path,
) -> tuple[float, str]:
    outcome = baseline.executor.run(
        command_id,
        purpose,
        job.recipe.benchmark,
        cwd=cwd,
    )
    if not outcome.succeeded:
        raise VerificationError(f"benchmark command failed: {command_id}")
    try:
        value = extract_measurement(outcome.stdout, job)
    except BenchmarkError as exc:
        raise VerificationError(f"invalid benchmark output for {command_id}: {exc}") from exc
    return value, outcome.record.stdout_artifact_id


def run_aa_calibration(baseline: BaselineResult, job: JobSpec) -> BaselineResult:
    """Measure same-revision pairs and stop if observed noise exceeds the effect threshold."""
    if baseline.bundle.status is not RunStatus.READY or baseline.bundle.benchmark is None:
        raise VerificationError("A/A calibration requires a reproduced ready baseline")
    policy = job.statistical_policy
    for warmup in range(1, policy.warmup_iterations + 1):
        _measure(
            baseline,
            job,
            command_id=f"calibration-warmup-{warmup:03d}",
            purpose="Warm up the baseline before A/A calibration",
            cwd=baseline.source_root,
        )
    generator = random.Random(policy.random_seed)
    pairs: list[dict[str, object]] = []
    differences: list[float] = []
    for pair_index in range(1, policy.maximum_pairs + 1):
        order = ["a", "b"]
        generator.shuffle(order)
        values: dict[str, float] = {}
        artifacts: dict[str, str] = {}
        for label in order:
            value, artifact_id = _measure(
                baseline,
                job,
                command_id=f"calibration-{pair_index:03d}-{label}",
                purpose=f"A/A calibration pair {pair_index}, copy {label}",
                cwd=baseline.source_root,
            )
            values[label] = value
            artifacts[label] = artifact_id
        denominator = (values["a"] + values["b"]) / 2
        difference = (values["a"] - values["b"]) / denominator
        differences.append(difference)
        pairs.append(
            {
                "pair": pair_index,
                "order": order,
                "a": values["a"],
                "b": values["b"],
                "relative_difference": difference,
                "output_artifacts": artifacts,
            }
        )
    p95 = float(np.percentile(np.abs(differences), 95))
    observed_median = float(median(differences))
    acceptable = p95 < policy.minimum_effect_fraction
    decision = (
        CalibrationDecision.ACCEPTABLE
        if acceptable
        else CalibrationDecision.EXCESSIVE_NOISE
    )
    raw = {
        "kind": "a_a_calibration",
        "benchmark": job.benchmark_name,
        "unit": job.benchmark_unit,
        "seed": policy.random_seed,
        "warmup_iterations": policy.warmup_iterations,
        "pair_count": policy.maximum_pairs,
        "pairs": pairs,
        "median_pair_difference_fraction": observed_median,
        "p95_absolute_pair_difference_fraction": p95,
        "acceptance_rule": "p95_absolute_pair_difference_fraction < minimum_effect_fraction",
        "minimum_effect_fraction": policy.minimum_effect_fraction,
    }
    artifact = baseline.store.write(
        "calibration.raw-timings",
        (json.dumps(raw, indent=2, sort_keys=True) + "\n").encode(),
        suffix=".json",
        media_type="application/json",
        description="Raw ordered A/A calibration timings and derived noise summary",
    )
    calibration = AACalibration(
        raw_timing_artifact_id=artifact.artifact_id,
        pair_count=policy.maximum_pairs,
        median_pair_difference_fraction=observed_median,
        p95_absolute_pair_difference_fraction=p95,
        decision=decision,
        rationale=(
            "The 95th percentile absolute paired difference is below the configured minimum "
            "worthwhile effect."
            if acceptable
            else "Observed A/A variation is too large relative to the minimum worthwhile effect."
        ),
    )
    status = RunStatus.READY if acceptable else RunStatus.CALIBRATION_INCONCLUSIVE
    bundle = baseline.bundle.model_copy(
        update={
            "status": status,
            "calibration": calibration,
            "artifacts": baseline.store.artifacts,
            "commands": tuple(baseline.executor.records),
        }
    )
    bundle = type(bundle).model_validate(bundle.model_dump(mode="json"))
    write_manifest(baseline.bundle_root, bundle)
    return replace(baseline, bundle=bundle)


@dataclass(frozen=True)
class _CandidateEvidence:
    candidate: CandidateResult
    interval: EffectInterval
    raw_p_value: float


def _candidate_measurements(
    baseline: BaselineResult, job: JobSpec, candidate: CandidateResult
) -> _CandidateEvidence:
    policy = job.statistical_policy
    candidate_root = baseline.bundle_root / "workspace/candidates" / candidate.candidate_id
    for warmup in range(1, policy.warmup_iterations + 1):
        _measure(
            baseline,
            job,
            command_id=f"{candidate.candidate_id}.warmup-baseline-{warmup:03d}",
            purpose=f"Warm up baseline for {candidate.candidate_id}",
            cwd=baseline.source_root,
        )
        _measure(
            baseline,
            job,
            command_id=f"{candidate.candidate_id}.warmup-candidate-{warmup:03d}",
            purpose=f"Warm up candidate for {candidate.candidate_id}",
            cwd=candidate_root,
        )
    generator = random.Random(policy.random_seed + int(candidate.candidate_id.split("-")[1]))
    baseline_values: list[float] = []
    candidate_values: list[float] = []
    pairs: list[dict[str, object]] = []
    for pair_index in range(1, policy.maximum_pairs + 1):
        order = ["baseline", "candidate"]
        generator.shuffle(order)
        values: dict[str, float] = {}
        artifacts: dict[str, str] = {}
        for label in order:
            cwd = baseline.source_root if label == "baseline" else candidate_root
            value, artifact_id = _measure(
                baseline,
                job,
                command_id=f"{candidate.candidate_id}.pair-{pair_index:03d}-{label}",
                purpose=(
                    f"Paired A/B measurement {pair_index} for "
                    f"{candidate.candidate_id}: {label}"
                ),
                cwd=cwd,
            )
            values[label] = value
            artifacts[label] = artifact_id
        baseline_values.append(values["baseline"])
        candidate_values.append(values["candidate"])
        pairs.append(
            {
                "pair": pair_index,
                "order": order,
                "baseline": values["baseline"],
                "candidate": values["candidate"],
                "output_artifacts": artifacts,
            }
        )
    relative = relative_improvements(
        baseline_values, candidate_values, lower_is_better=job.lower_is_better
    )
    log_improvements = paired_log_improvements(
        baseline_values, candidate_values, lower_is_better=job.lower_is_better
    )
    interval = bootstrap_median_interval(
        relative,
        confidence_level=policy.confidence_level,
        resamples=policy.bootstrap_resamples,
        seed=policy.random_seed,
    )
    raw_p_value = paired_sign_permutation_p_value(
        log_improvements,
        seed=policy.random_seed,
    )
    raw = {
        "kind": "randomized_paired_a_b",
        "candidate_id": candidate.candidate_id,
        "benchmark": job.benchmark_name,
        "unit": job.benchmark_unit,
        "lower_is_better": job.lower_is_better,
        "seed": policy.random_seed,
        "warmup_iterations_per_revision": policy.warmup_iterations,
        "pair_count": policy.maximum_pairs,
        "pairs": pairs,
        "relative_improvements": relative,
        "observed_median_speedup_fraction": interval.observed_median,
        "confidence_interval_fraction": [interval.lower, interval.upper],
        "confidence_interval_method": interval.method,
        "confidence_level": policy.confidence_level,
        "raw_p_value": raw_p_value,
        "hypothesis_test": "one-sided paired sign permutation on mean log improvement",
    }
    artifact = baseline.store.write(
        f"{candidate.candidate_id}.raw-timings",
        (json.dumps(raw, indent=2, sort_keys=True) + "\n").encode(),
        suffix=".json",
        media_type="application/json",
        description=f"Raw randomized paired timings for {candidate.candidate_id}",
    )
    updated = candidate.model_copy(
        update={
            "raw_timing_artifact_id": artifact.artifact_id,
            "observed_speedup_fraction": interval.observed_median,
            "confidence_interval_fraction": (interval.lower, interval.upper),
        }
    )
    return _CandidateEvidence(updated, interval, raw_p_value)


def run_performance_verification(baseline: BaselineResult, job: JobSpec) -> BaselineResult:
    """Measure correctness-passing candidates, correct p-values, and classify evidence."""
    if (
        baseline.bundle.status is not RunStatus.READY
        or baseline.bundle.calibration is None
        or baseline.bundle.calibration.decision is not CalibrationDecision.ACCEPTABLE
    ):
        raise VerificationError("performance verification requires acceptable A/A calibration")
    eligible = [
        candidate
        for candidate in baseline.bundle.candidates
        if candidate.reason_codes
        == ("correctness_gate_passed_pending_performance_verification",)
    ]
    if not eligible:
        raise VerificationError("no correctness-passing candidate is available for measurement")
    measured = [_candidate_measurements(baseline, job, candidate) for candidate in eligible]
    adjusted = holm_adjust(
        {item.candidate.candidate_id: item.raw_p_value for item in measured}
    )
    measured_by_id = {item.candidate.candidate_id: item for item in measured}
    results: list[CandidateResult] = []
    claims = list(baseline.bundle.claims)
    for candidate in baseline.bundle.candidates:
        evidence = measured_by_id.get(candidate.candidate_id)
        if evidence is None:
            results.append(candidate)
            continue
        adjusted_p = adjusted[candidate.candidate_id]
        interval = evidence.interval
        minimum = job.statistical_policy.minimum_effect_fraction
        if adjusted_p < job.statistical_policy.alpha and interval.lower >= minimum:
            decision = Decision.ACCEPTED
            reason = "verified_speedup"
        elif interval.observed_median <= 0 or interval.upper < minimum:
            decision = Decision.REJECTED
            reason = "does_not_meet_minimum_effect"
        elif adjusted_p >= job.statistical_policy.alpha:
            decision = Decision.INCONCLUSIVE
            reason = "not_significant_after_holm_correction"
        else:
            decision = Decision.INCONCLUSIVE
            reason = "confidence_interval_crosses_minimum_effect"
        result = evidence.candidate.model_copy(
            update={
                "decision": decision,
                "reason_codes": (reason,),
                "adjusted_p_value": adjusted_p,
            }
        )
        results.append(result)
        if decision is Decision.ACCEPTED:
            assert result.raw_timing_artifact_id is not None
            claims.append(
                Claim(
                    claim_id=f"{candidate.candidate_id}-verified-speedup",
                    statement=(
                        f"{candidate.candidate_id} met the configured statistical and minimum "
                        "effect gates on this recorded environment."
                    ),
                    source_artifact_ids=(result.raw_timing_artifact_id,),
                    computation=(
                        "Median paired relative improvement with BCa interval, one-sided paired "
                        "sign-permutation test, then Holm correction across measured candidates."
                    ),
                )
            )
    bundle = baseline.bundle.model_copy(
        update={
            "status": RunStatus.COMPLETED,
            "candidates": tuple(results),
            "artifacts": baseline.store.artifacts,
            "commands": tuple(baseline.executor.records),
            "claims": tuple(claims),
        }
    )
    bundle = type(bundle).model_validate(bundle.model_dump(mode="json"))
    write_manifest(baseline.bundle_root, bundle)
    return replace(baseline, bundle=bundle)
