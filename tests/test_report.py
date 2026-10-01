from __future__ import annotations

from pathlib import Path

from perfpilot.pipeline import run_full_verification
from perfpilot.report.render import render_reports
from tests.test_ingest import REPOSITORY_ROOT, create_fixture_repository, fixture_job


def test_report_and_pr_draft_are_derived_from_verified_bundle(tmp_path: Path) -> None:
    repository, commit = create_fixture_repository(tmp_path, "cmake-healthy")
    job = fixture_job(repository, commit, healthy=True)
    recorded = REPOSITORY_ROOT / "fixtures/cmake-healthy/perfpilot-proposals.example.json"
    result = run_full_verification(
        job,
        tmp_path / "bundle",
        recorded_response=recorded,
    )
    manifest_before = (result.bundle_root / "manifest.json").read_bytes()
    summary, drafts = render_reports(result.bundle_root)
    assert len(drafts) == 1
    report = summary.read_text(encoding="utf-8")
    draft = drafts[0].read_text(encoding="utf-8")
    accepted = result.bundle.candidates[0]
    assert repr(accepted.observed_speedup_fraction) in report
    assert repr(accepted.adjusted_p_value) in report
    assert accepted.raw_timing_artifact_id in report
    assert "does not establish semantic equivalence" in report
    assert "AI assistance disclosure" in draft
    assert "has not opened or submitted a pull request" in draft
    assert (result.bundle_root / "manifest.json").read_bytes() == manifest_before

