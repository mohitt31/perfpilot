from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from perfpilot.evidence.io import load_and_validate_bundle
from perfpilot.evidence.schema import (
    BuildRecipe,
    JobSpec,
    ProfileConfig,
    ProposalConfig,
    RepositoryRef,
    RunStatus,
    StatisticalPolicy,
)
from perfpilot.ingest.pipeline import run_baseline

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def create_fixture_repository(tmp_path: Path, fixture_name: str) -> tuple[Path, str]:
    source = REPOSITORY_ROOT / "fixtures" / fixture_name
    repository = tmp_path / f"{fixture_name}-repository"
    shutil.copytree(source, repository)
    subprocess.run(["git", "init", "--quiet", str(repository)], check=True)
    subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "-c",
            "user.name=PerfPilot Tests",
            "-c",
            "user.email=tests@perfpilot.invalid",
            "commit",
            "--quiet",
            "-m",
            "fixture",
        ],
        check=True,
    )
    commit = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return repository, commit


def fixture_job(repository: Path, commit: str, *, healthy: bool) -> JobSpec:
    benchmark = (
        ("./build/integer_sum_benchmark", "--fixture-deterministic-json")
        if healthy
        else ("./build/noop_benchmark",)
    )
    return JobSpec(
        repository=RepositoryRef(url=repository.as_uri(), commit=commit),
        recipe=BuildRecipe(
            configure=("cmake", "-S", ".", "-B", "build", "-DCMAKE_BUILD_TYPE=Release"),
            build=("cmake", "--build", "build", "--parallel", "2"),
            test=("ctest", "--test-dir", "build", "--output-on-failure"),
            benchmark=benchmark,
        ),
        profile=(
            ProfileConfig(
                backend="instrumented_json",
                command=("./build/integer_sum_benchmark", "--profile-json"),
            )
            if healthy
            else None
        ),
        proposal=(
            ProposalConfig(
                provider="recorded",
                model="fixture-recording",
                maximum_hotspots=1,
            )
            if healthy
            else None
        ),
        benchmark_name="integer_sum" if healthy else "noop",
        benchmark_unit="nanoseconds",
        statistical_policy=StatisticalPolicy(
            random_seed=42,
            maximum_pairs=15,
            bootstrap_resamples=2_000,
        ),
        fixture_mode=True,
    )


@pytest.mark.skipif(shutil.which("cmake") is None, reason="CMake is not installed")
def test_healthy_repository_reaches_ready_with_valid_evidence(tmp_path: Path) -> None:
    repository, commit = create_fixture_repository(tmp_path, "cmake-healthy")
    output = tmp_path / "healthy-bundle"
    result = run_baseline(fixture_job(repository, commit, healthy=True), output)
    assert result.bundle.status is RunStatus.READY
    assert result.bundle.repository.commit == commit
    assert [record.command_id for record in result.bundle.commands][-3:] == [
        "baseline-configure",
        "baseline-build",
        "baseline-test",
    ]
    loaded = load_and_validate_bundle(output)
    assert loaded.run_id == result.bundle.run_id


@pytest.mark.skipif(shutil.which("cmake") is None, reason="CMake is not installed")
def test_broken_baseline_is_terminal_and_evidence_is_valid(tmp_path: Path) -> None:
    repository, commit = create_fixture_repository(tmp_path, "cmake-broken-baseline")
    output = tmp_path / "broken-bundle"
    result = run_baseline(fixture_job(repository, commit, healthy=False), output)
    assert result.bundle.status is RunStatus.BASELINE_FAILED
    command_ids = [record.command_id for record in result.bundle.commands]
    assert "baseline-test" in command_ids
    assert "benchmark" not in command_ids
    assert not result.bundle.candidates
    load_and_validate_bundle(output)
