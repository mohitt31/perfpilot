"""Apply each proposal in an isolated worktree and enforce build/test gates."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from perfpilot.evidence.schema import CandidateResult, Decision, JobSpec, RunStatus
from perfpilot.ingest.pipeline import BaselineResult, write_manifest


class CorrectnessError(RuntimeError):
    """The correctness gate could not run under the declared contract."""


def _artifact_path(baseline: BaselineResult, artifact_id: str) -> Path:
    artifact = next(
        (item for item in baseline.store.artifacts if item.artifact_id == artifact_id), None
    )
    if artifact is None:
        raise CorrectnessError(f"candidate references missing artifact: {artifact_id}")
    path = (baseline.bundle_root / artifact.path).resolve(strict=True)
    if not path.is_relative_to(baseline.bundle_root.resolve()):
        raise CorrectnessError("candidate patch resolves outside the evidence bundle")
    return path


def _updated(
    candidate: CandidateResult,
    decision: Decision,
    reason: str,
    test_command_ids: tuple[str, ...] = (),
) -> CandidateResult:
    return candidate.model_copy(
        update={
            "decision": decision,
            "reason_codes": (reason,),
            "test_command_ids": test_command_ids,
        }
    )


def _verify_candidate(
    baseline: BaselineResult,
    job: JobSpec,
    candidate: CandidateResult,
    candidates_root: Path,
) -> CandidateResult:
    candidate_root = candidates_root / candidate.candidate_id
    worktree = baseline.executor.run(
        f"{candidate.candidate_id}.worktree",
        f"Create isolated worktree for {candidate.candidate_id}",
        (
            "git",
            "worktree",
            "add",
            "--detach",
            str(candidate_root),
            job.repository.commit,
        ),
        cwd=baseline.source_root,
    )
    if not worktree.succeeded:
        return _updated(candidate, Decision.REJECTED, "worktree_creation_failed")

    patch_path = _artifact_path(baseline, candidate.patch_artifact_id)
    apply_check = baseline.executor.run(
        f"{candidate.candidate_id}.apply-check",
        f"Check whether {candidate.candidate_id} applies cleanly",
        ("git", "apply", "--check", str(patch_path)),
        cwd=candidate_root,
    )
    if not apply_check.succeeded:
        return _updated(candidate, Decision.REJECTED, "patch_does_not_apply")
    apply = baseline.executor.run(
        f"{candidate.candidate_id}.apply",
        f"Apply {candidate.candidate_id} in its isolated worktree",
        ("git", "apply", str(patch_path)),
        cwd=candidate_root,
    )
    if not apply.succeeded:
        return _updated(candidate, Decision.REJECTED, "patch_application_failed")
    changed = baseline.executor.run(
        f"{candidate.candidate_id}.changed-paths",
        f"List paths changed by {candidate.candidate_id}",
        ("git", "diff", "--name-only", "--diff-filter=ACMRTUXB"),
        cwd=candidate_root,
    )
    if not changed.succeeded:
        return _updated(candidate, Decision.REJECTED, "changed_path_inspection_failed")
    paths = [line.strip() for line in changed.stdout.decode("utf-8").splitlines() if line.strip()]
    if not paths:
        return _updated(candidate, Decision.REJECTED, "empty_patch")
    protected_prefixes = ("test/", "tests/", "benchmark/", "benchmarks/")
    if any(path.startswith(protected_prefixes) for path in paths):
        return _updated(candidate, Decision.REJECTED, "modifies_test_or_benchmark")

    configure = baseline.executor.run(
        f"{candidate.candidate_id}.configure",
        f"Cleanly configure {candidate.candidate_id}",
        job.recipe.configure,
        cwd=candidate_root,
    )
    if not configure.succeeded:
        return _updated(candidate, Decision.REJECTED, "configure_failed")
    build = baseline.executor.run(
        f"{candidate.candidate_id}.build",
        f"Cleanly build {candidate.candidate_id}",
        job.recipe.build,
        cwd=candidate_root,
    )
    if not build.succeeded:
        return _updated(candidate, Decision.REJECTED, "build_failed")
    tests = baseline.executor.run(
        f"{candidate.candidate_id}.test",
        f"Run the full configured tests for {candidate.candidate_id}",
        job.recipe.test,
        cwd=candidate_root,
    )
    if not tests.succeeded:
        reason = "tests_timed_out" if tests.record.timed_out else "tests_failed"
        return _updated(candidate, Decision.REJECTED, reason, (tests.record.command_id,))
    return _updated(
        candidate,
        Decision.INCONCLUSIVE,
        "correctness_gate_passed_pending_performance_verification",
        (tests.record.command_id,),
    )


def run_correctness_gates(baseline: BaselineResult, job: JobSpec) -> BaselineResult:
    """Build and test every proposed patch without making a performance decision."""
    if baseline.bundle.status is not RunStatus.READY or not baseline.bundle.candidates:
        raise CorrectnessError("correctness gates require at least one proposed candidate")
    candidates_root = baseline.bundle_root / "workspace" / "candidates"
    candidates_root.mkdir(parents=True, exist_ok=False)
    results = tuple(
        _verify_candidate(baseline, job, candidate, candidates_root)
        for candidate in baseline.bundle.candidates
    )
    bundle = baseline.bundle.model_copy(
        update={
            "candidates": results,
            "artifacts": baseline.store.artifacts,
            "commands": tuple(baseline.executor.records),
        }
    )
    bundle = type(bundle).model_validate(bundle.model_dump(mode="json"))
    write_manifest(baseline.bundle_root, bundle)
    return replace(baseline, bundle=bundle)

