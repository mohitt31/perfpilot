from __future__ import annotations

from pathlib import Path

from perfpilot.evidence.io import load_and_validate_bundle
from perfpilot.reproduce import ReproductionOutcome, compare_bundles
from tests.test_evidence_schema import _write_bundle


def test_identical_failed_runs_have_no_shared_candidate(tmp_path: Path) -> None:
    bundle = load_and_validate_bundle(_write_bundle(tmp_path))
    report = compare_bundles(bundle, bundle)
    assert report.outcome is ReproductionOutcome.NO_SHARED_CANDIDATE
    assert report.same_repository_commit
    assert report.same_benchmark_policy
    assert report.same_machine
    assert report.candidates == ()
