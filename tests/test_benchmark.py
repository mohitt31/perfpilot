from __future__ import annotations

import json
from pathlib import Path

import pytest

from perfpilot.benchmark import BenchmarkError, _observations, run_existing_benchmark
from perfpilot.evidence.io import load_and_validate_bundle
from perfpilot.evidence.schema import RunStatus
from perfpilot.ingest.pipeline import run_baseline
from tests.test_ingest import create_fixture_repository, fixture_job


def test_google_benchmark_output_is_filtered_by_declared_name(tmp_path: Path) -> None:
    repository, commit = create_fixture_repository(tmp_path, "cmake-healthy")
    job = fixture_job(repository, commit, healthy=True).model_copy(
        update={"benchmark_name": "BM_sum", "benchmark_unit": "ns"}
    )
    payload = {
        "benchmarks": [
            {"name": "BM_other", "time_unit": "ns", "real_time": 8.0},
            {"name": "BM_sum/4096", "time_unit": "ns", "real_time": 12.0},
        ]
    }
    assert _observations(payload, job) == 1


def test_google_benchmark_unit_mismatch_is_rejected(tmp_path: Path) -> None:
    repository, commit = create_fixture_repository(tmp_path, "cmake-healthy")
    job = fixture_job(repository, commit, healthy=True).model_copy(
        update={"benchmark_name": "BM_sum", "benchmark_unit": "ns"}
    )
    with pytest.raises(BenchmarkError, match="unit mismatch"):
        _observations(
            {"benchmarks": [{"name": "BM_sum", "time_unit": "us", "real_time": 1.0}]},
            job,
        )


def test_existing_fixture_benchmark_is_captured_without_speedup_claim(tmp_path: Path) -> None:
    repository, commit = create_fixture_repository(tmp_path, "cmake-healthy")
    job = fixture_job(repository, commit, healthy=True)
    baseline = run_baseline(job, tmp_path / "bundle")
    result = run_existing_benchmark(baseline, job)
    assert result.bundle.status is RunStatus.READY
    assert result.bundle.benchmark_run is not None
    assert result.bundle.benchmark_run.observation_count == 1
    raw_id = result.bundle.benchmark_run.raw_output_artifact_id
    raw_artifact = next(item for item in result.bundle.artifacts if item.artifact_id == raw_id)
    payload = json.loads((result.bundle_root / raw_artifact.path).read_text(encoding="utf-8"))
    assert payload["benchmark"] == "integer_sum"
    assert all("speedup" not in claim.statement.lower() for claim in result.bundle.claims)
    load_and_validate_bundle(result.bundle_root)

