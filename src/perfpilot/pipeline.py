"""End-to-end orchestration through candidate correctness gates."""

from __future__ import annotations

from pathlib import Path

from perfpilot.benchmark import run_existing_benchmark
from perfpilot.evidence.schema import JobSpec, RunStatus
from perfpilot.ingest.pipeline import BaselineResult, run_baseline
from perfpilot.profile.pipeline import run_profile
from perfpilot.propose.pipeline import run_proposals
from perfpilot.propose.provider import (
    OpenAIProposalProvider,
    ProposalProvider,
    RecordedProposalProvider,
)
from perfpilot.verify.correctness import run_correctness_gates
from perfpilot.verify.performance import run_aa_calibration, run_performance_verification


class PipelineError(RuntimeError):
    """The requested pipeline configuration is incomplete."""


def provider_for_job(job: JobSpec, recorded_response: Path | None) -> ProposalProvider:
    if job.proposal is None:
        raise PipelineError("job has no proposal configuration")
    if job.proposal.provider == "recorded":
        if recorded_response is None:
            raise PipelineError("recorded proposal provider requires a response file")
        return RecordedProposalProvider(recorded_response, model=job.proposal.model)
    if recorded_response is not None:
        raise PipelineError("recorded response cannot be used with the OpenAI provider")
    return OpenAIProposalProvider(job.proposal.model)


def run_through_correctness(
    job: JobSpec,
    bundle_root: Path,
    *,
    recorded_response: Path | None = None,
) -> BaselineResult:
    baseline = run_baseline(job, bundle_root)
    if baseline.bundle.status is RunStatus.BASELINE_FAILED:
        return baseline
    benchmarked = run_existing_benchmark(baseline, job)
    profiled = run_profile(benchmarked, job)
    proposed = run_proposals(profiled, job, provider_for_job(job, recorded_response))
    return run_correctness_gates(proposed, job)


def run_full_verification(
    job: JobSpec,
    bundle_root: Path,
    *,
    recorded_response: Path | None = None,
) -> BaselineResult:
    """Run Phase 1 through statistically classified candidate evidence."""
    baseline = run_baseline(job, bundle_root)
    if baseline.bundle.status is RunStatus.BASELINE_FAILED:
        return baseline
    benchmarked = run_existing_benchmark(baseline, job)
    calibrated = run_aa_calibration(benchmarked, job)
    if calibrated.bundle.status is RunStatus.CALIBRATION_INCONCLUSIVE:
        return calibrated
    profiled = run_profile(calibrated, job)
    proposed = run_proposals(profiled, job, provider_for_job(job, recorded_response))
    correctness_checked = run_correctness_gates(proposed, job)
    return run_performance_verification(correctness_checked, job)
