from __future__ import annotations

from pathlib import Path

from perfpilot.evidence.io import load_and_validate_bundle
from perfpilot.evidence.schema import CalibrationDecision, Decision, RunStatus
from perfpilot.pipeline import run_full_verification
from tests.test_ingest import REPOSITORY_ROOT, create_fixture_repository, fixture_job


def test_full_fixture_run_calibrates_and_verifies_known_improvement(tmp_path: Path) -> None:
    repository, commit = create_fixture_repository(tmp_path, "cmake-healthy")
    job = fixture_job(repository, commit, healthy=True)
    recorded = REPOSITORY_ROOT / "fixtures/cmake-healthy/perfpilot-proposals.example.json"
    result = run_full_verification(
        job,
        tmp_path / "bundle",
        recorded_response=recorded,
    )
    assert result.bundle.status is RunStatus.COMPLETED
    assert result.bundle.calibration is not None
    assert result.bundle.calibration.decision is CalibrationDecision.ACCEPTABLE
    verified, invalid = result.bundle.candidates
    assert verified.decision is Decision.ACCEPTED
    assert verified.reason_codes == ("verified_speedup",)
    assert verified.observed_speedup_fraction is not None
    assert verified.observed_speedup_fraction > job.statistical_policy.minimum_effect_fraction
    assert verified.confidence_interval_fraction is not None
    assert (
        verified.confidence_interval_fraction[0]
        >= job.statistical_policy.minimum_effect_fraction
    )
    assert verified.adjusted_p_value is not None
    assert verified.adjusted_p_value < job.statistical_policy.alpha
    assert invalid.decision is Decision.REJECTED
    load_and_validate_bundle(result.bundle_root)
