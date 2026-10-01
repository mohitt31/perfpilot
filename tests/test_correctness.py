from __future__ import annotations

from pathlib import Path

from perfpilot.benchmark import run_existing_benchmark
from perfpilot.evidence.io import load_and_validate_bundle
from perfpilot.ingest.pipeline import run_baseline
from perfpilot.profile.pipeline import run_profile
from perfpilot.propose.pipeline import run_proposals
from perfpilot.propose.provider import RecordedProposalProvider
from perfpilot.verify.correctness import run_correctness_gates
from tests.test_ingest import REPOSITORY_ROOT, create_fixture_repository, fixture_job


def test_candidates_are_isolated_and_correctness_gated(tmp_path: Path) -> None:
    repository, commit = create_fixture_repository(tmp_path, "cmake-healthy")
    job = fixture_job(repository, commit, healthy=True)
    baseline = run_baseline(job, tmp_path / "bundle")
    benchmarked = run_existing_benchmark(baseline, job)
    profiled = run_profile(benchmarked, job)
    recorded = REPOSITORY_ROOT / "fixtures/cmake-healthy/perfpilot-proposals.example.json"
    proposed = run_proposals(profiled, job, RecordedProposalProvider(recorded))
    result = run_correctness_gates(proposed, job)

    valid, invalid = result.bundle.candidates
    assert valid.decision.value == "inconclusive"
    assert valid.reason_codes == ("correctness_gate_passed_pending_performance_verification",)
    assert len(valid.test_command_ids) == 1
    valid_test = next(
        record
        for record in result.bundle.commands
        if record.command_id == valid.test_command_ids[0]
    )
    assert valid_test.exit_code == 0
    assert invalid.decision.value == "rejected"
    assert invalid.reason_codes == ("build_failed",)
    assert invalid.test_command_ids == ()

    candidate_root = result.bundle_root / "workspace/candidates"
    assert (candidate_root / "candidate-001/src/integer_sum.cpp").is_file()
    assert (candidate_root / "candidate-002/src/integer_sum.cpp").is_file()
    load_and_validate_bundle(result.bundle_root)
