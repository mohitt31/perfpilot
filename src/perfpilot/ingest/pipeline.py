"""Exact-commit acquisition and baseline build/test pipeline."""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from perfpilot.evidence.schema import (
    Claim,
    EvidenceBundle,
    JobSpec,
    RunStatus,
)
from perfpilot.execution import ArtifactStore, Executor, LocalExecutor
from perfpilot.ingest.environment import capture_environment


class BaselinePipelineError(RuntimeError):
    """The source could not be acquired or the baseline could not be built."""


@dataclass(frozen=True)
class BaselineResult:
    bundle: EvidenceBundle
    bundle_root: Path
    source_root: Path
    store: ArtifactStore
    executor: Executor


def _new_run_id() -> str:
    now = datetime.now(UTC)
    return f"{now.strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(4)}"


def write_manifest(bundle_root: Path, bundle: EvidenceBundle) -> None:
    path = bundle_root / "manifest.json"
    path.write_text(
        json.dumps(bundle.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _bundle(
    *,
    job: JobSpec,
    run_id: str,
    status: RunStatus,
    store: ArtifactStore,
    executor: Executor,
    claims: tuple[Claim, ...],
) -> EvidenceBundle:
    policy = executor.policy  # type: ignore[attr-defined]
    limitations = [
        "Only the explicitly configured build and test commands were executed.",
        "Passing tests establish only the behavior exercised by those tests.",
    ]
    if isinstance(executor, LocalExecutor):
        limitations.append(executor.policy.warning)
    return EvidenceBundle(
        run_id=run_id,
        created_at=datetime.now(UTC),
        status=status,
        repository=job.repository,
        sandbox=policy,
        environment=capture_environment(),
        benchmark=None,
        calibration=None,
        artifacts=store.artifacts,
        commands=tuple(executor.records),
        claims=claims,
        limitations=tuple(limitations),
    )


def run_baseline(job: JobSpec, bundle_root: Path) -> BaselineResult:
    """Clone, pin, clean-build, and test a baseline using the local development backend."""
    if bundle_root.exists() and any(bundle_root.iterdir()):
        raise BaselinePipelineError(f"bundle directory is not empty: {bundle_root}")
    bundle_root.mkdir(parents=True, exist_ok=True)
    workspace = bundle_root / "workspace"
    workspace.mkdir()
    store = ArtifactStore(bundle_root)
    executor = LocalExecutor(workspace, store, job.resource_limits)
    run_id = _new_run_id()
    source = workspace / "source"

    clone = executor.run(
        "source-clone",
        "Clone repository without checking out a moving branch",
        ("git", "clone", "--no-checkout", job.repository.url, source.name),
        cwd=workspace,
    )
    if not clone.succeeded:
        raise BaselinePipelineError("repository clone failed; see captured command output")
    checkout = executor.run(
        "source-checkout",
        "Check out the exact requested commit in detached mode",
        ("git", "checkout", "--detach", job.repository.commit),
        cwd=source,
    )
    if not checkout.succeeded:
        raise BaselinePipelineError("exact commit checkout failed; see captured command output")
    identity = executor.run(
        "source-identity",
        "Verify checked-out commit identity",
        ("git", "rev-parse", "HEAD"),
        cwd=source,
    )
    actual_commit = identity.stdout.decode("utf-8", errors="replace").strip()
    if not identity.succeeded or actual_commit != job.repository.commit:
        raise BaselinePipelineError(
            f"repository identity mismatch: expected {job.repository.commit}, found {actual_commit}"
        )
    cleanliness = executor.run(
        "source-cleanliness",
        "Verify the pinned source starts without tracked or untracked changes",
        ("git", "status", "--porcelain", "--untracked-files=all"),
        cwd=source,
    )
    if not cleanliness.succeeded or cleanliness.stdout.strip():
        raise BaselinePipelineError("checked-out source is not clean")

    configure = executor.run(
        "baseline-configure",
        "Configure the baseline build",
        job.recipe.configure,
        cwd=source,
    )
    if not configure.succeeded:
        bundle = _bundle(
            job=job,
            run_id=run_id,
            status=RunStatus.FAILED,
            store=store,
            executor=executor,
            claims=(),
        )
        write_manifest(bundle_root, bundle)
        raise BaselinePipelineError("baseline configuration failed; evidence bundle was written")
    build = executor.run(
        "baseline-build",
        "Build the baseline from the clean configuration",
        job.recipe.build,
        cwd=source,
    )
    if not build.succeeded:
        bundle = _bundle(
            job=job,
            run_id=run_id,
            status=RunStatus.FAILED,
            store=store,
            executor=executor,
            claims=(),
        )
        write_manifest(bundle_root, bundle)
        raise BaselinePipelineError("baseline build failed; evidence bundle was written")
    tests = executor.run(
        "baseline-test",
        "Run the configured baseline test suite",
        job.recipe.test,
        cwd=source,
    )
    if not tests.succeeded:
        claim = Claim(
            claim_id="baseline-tests-failed",
            statement="The configured baseline test command did not complete successfully.",
            source_artifact_ids=(
                tests.record.stdout_artifact_id,
                tests.record.stderr_artifact_id,
            ),
            computation="The recorded command timed out or returned a non-zero exit status.",
        )
        bundle = _bundle(
            job=job,
            run_id=run_id,
            status=RunStatus.BASELINE_FAILED,
            store=store,
            executor=executor,
            claims=(claim,),
        )
        write_manifest(bundle_root, bundle)
        return BaselineResult(bundle, bundle_root, source, store, executor)

    claim = Claim(
        claim_id="baseline-tests-passed",
        statement="The configured baseline test command completed with exit status zero.",
        source_artifact_ids=(
            tests.record.stdout_artifact_id,
            tests.record.stderr_artifact_id,
        ),
        computation="The recorded command returned exit status zero and did not time out.",
    )
    bundle = _bundle(
        job=job,
        run_id=run_id,
        status=RunStatus.READY,
        store=store,
        executor=executor,
        claims=(claim,),
    )
    write_manifest(bundle_root, bundle)
    return BaselineResult(bundle, bundle_root, source, store, executor)
