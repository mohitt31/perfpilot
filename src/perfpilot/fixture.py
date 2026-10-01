"""Controlled end-to-end fixture runner for engineering validation only."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from perfpilot.evidence.schema import (
    BuildRecipe,
    JobSpec,
    ProfileConfig,
    ProposalConfig,
    RepositoryRef,
    StatisticalPolicy,
)
from perfpilot.ingest.pipeline import BaselineResult
from perfpilot.pipeline import run_full_verification


def _git(argv: tuple[str, ...], cwd: Path) -> str:
    completed = subprocess.run(
        ("git", *argv), cwd=cwd, check=True, capture_output=True, text=True
    )
    return completed.stdout.strip()


def run_controlled_fixture(
    fixture_root: Path,
    recorded_response: Path,
    output: Path,
) -> BaselineResult:
    """Create an ephemeral Git source and run the fixed fixture protocol."""
    fixture = fixture_root.resolve(strict=True)
    response = recorded_response.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="perfpilot-fixture-") as temporary:
        repository = Path(temporary) / "repository"
        shutil.copytree(fixture, repository)
        _git(("init", "--quiet"), repository)
        _git(("add", "."), repository)
        _git(
            (
                "-c",
                "user.name=PerfPilot Fixture",
                "-c",
                "user.email=fixture@perfpilot.invalid",
                "commit",
                "--quiet",
                "-m",
                "controlled fixture",
            ),
            repository,
        )
        commit = _git(("rev-parse", "HEAD"), repository)
        job = JobSpec(
            repository=RepositoryRef(url=repository.as_uri(), commit=commit),
            recipe=BuildRecipe(
                configure=(
                    "cmake",
                    "-S",
                    ".",
                    "-B",
                    "build",
                    "-DCMAKE_BUILD_TYPE=Release",
                ),
                build=("cmake", "--build", "build", "--parallel", "2"),
                test=("ctest", "--test-dir", "build", "--output-on-failure"),
                benchmark=("./build/integer_sum_benchmark",),
            ),
            profile=ProfileConfig(
                backend="instrumented_json",
                command=("./build/integer_sum_benchmark", "--profile-json"),
            ),
            proposal=ProposalConfig(
                provider="recorded",
                model="fixture-recording",
                maximum_hotspots=1,
            ),
            benchmark_name="integer_sum",
            benchmark_unit="nanoseconds",
            statistical_policy=StatisticalPolicy(
                random_seed=42,
                maximum_pairs=15,
                bootstrap_resamples=2_000,
            ),
            fixture_mode=True,
        )
        return run_full_verification(job, output, recorded_response=response)
