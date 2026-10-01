from __future__ import annotations

from pathlib import Path

from perfpilot.evidence.schema import RunStatus
from perfpilot.pipeline import run_through_correctness
from tests.test_ingest import REPOSITORY_ROOT, create_fixture_repository, fixture_job


def test_end_to_end_pipeline_stops_at_correctness_not_performance(tmp_path: Path) -> None:
    repository, commit = create_fixture_repository(tmp_path, "cmake-healthy")
    job = fixture_job(repository, commit, healthy=True)
    recorded = REPOSITORY_ROOT / "fixtures/cmake-healthy/perfpilot-proposals.example.json"
    result = run_through_correctness(
        job,
        tmp_path / "bundle",
        recorded_response=recorded,
    )
    assert result.bundle.status is RunStatus.READY
    assert any(
        candidate.reason_codes
        == ("correctness_gate_passed_pending_performance_verification",)
        for candidate in result.bundle.candidates
    )
    assert all(candidate.decision.value != "accepted" for candidate in result.bundle.candidates)

