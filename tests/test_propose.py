from __future__ import annotations

import json
from pathlib import Path

import pytest

from perfpilot.benchmark import run_existing_benchmark
from perfpilot.evidence.io import load_and_validate_bundle
from perfpilot.ingest.pipeline import run_baseline
from perfpilot.profile.pipeline import run_profile
from perfpilot.propose.context import assemble_context
from perfpilot.propose.pipeline import ProposalError, run_proposals
from perfpilot.propose.provider import RecordedProposalProvider
from tests.test_ingest import REPOSITORY_ROOT, create_fixture_repository, fixture_job


def _profiled_fixture(tmp_path: Path):  # type: ignore[no-untyped-def]
    repository, commit = create_fixture_repository(tmp_path, "cmake-healthy")
    job = fixture_job(repository, commit, healthy=True)
    baseline = run_baseline(job, tmp_path / "bundle")
    benchmarked = run_existing_benchmark(baseline, job)
    return run_profile(benchmarked, job), job


def test_context_is_source_mapped_and_within_byte_budget(tmp_path: Path) -> None:
    profiled, job = _profiled_fixture(tmp_path)
    assert job.proposal is not None
    assert profiled.bundle.profile is not None
    raw = assemble_context(
        profiled.source_root, profiled.bundle.profile.hotspots[0], job.proposal
    )
    payload = json.loads(raw)
    assert len(raw) <= job.proposal.maximum_context_bytes
    assert payload["content_bytes"] <= job.proposal.maximum_context_bytes
    assert payload["sections"][0]["path"] == "src/integer_sum.cpp"
    assert "integer_sum" in payload["sections"][0]["content"]
    assert any(section["kind"] == "symbol_reference" for section in payload["sections"])


def test_recorded_provider_creates_unverified_traceable_candidates(tmp_path: Path) -> None:
    profiled, job = _profiled_fixture(tmp_path)
    response = REPOSITORY_ROOT / "fixtures/cmake-healthy/perfpilot-proposals.example.json"
    result = run_proposals(profiled, job, RecordedProposalProvider(response))
    assert len(result.bundle.candidates) == 2
    assert all(candidate.decision.value == "inconclusive" for candidate in result.bundle.candidates)
    assert all(
        candidate.reason_codes == ("not_verified",) for candidate in result.bundle.candidates
    )
    assert result.bundle.candidates[0].model.provider == "recorded"
    load_and_validate_bundle(result.bundle_root)


def test_provider_candidate_limit_is_enforced(tmp_path: Path) -> None:
    profiled, job = _profiled_fixture(tmp_path)
    assert job.proposal is not None
    constrained = job.model_copy(
        update={"proposal": job.proposal.model_copy(update={"maximum_candidates_per_hotspot": 1})}
    )
    response = REPOSITORY_ROOT / "fixtures/cmake-healthy/perfpilot-proposals.example.json"
    with pytest.raises(ProposalError, match="more candidates"):
        run_proposals(profiled, constrained, RecordedProposalProvider(response))
