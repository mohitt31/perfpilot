"""Turn bounded hotspot context into unverified structured candidates."""

from __future__ import annotations

import hashlib
from dataclasses import replace

from pydantic import Field, ValidationError

from perfpilot.evidence.schema import (
    CandidateResult,
    Decision,
    JobSpec,
    ModelProvenance,
    RunStatus,
    StrictModel,
)
from perfpilot.ingest.pipeline import BaselineResult, write_manifest
from perfpilot.propose.context import ContextError, assemble_context
from perfpilot.propose.provider import ProposalProvider


class ProposalError(RuntimeError):
    """Proposal context or provider output violated the Phase 1 contract."""


class ProposedCandidate(StrictModel):
    title: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    risk: str = Field(min_length=1)
    expected_effect: str = Field(min_length=1)
    patch: str = Field(min_length=1, max_length=100_000)


class ProposalResponse(StrictModel):
    candidates: tuple[ProposedCandidate, ...] = Field(min_length=1, max_length=3)


def _validate_patch(patch: str) -> None:
    lines = patch.splitlines()
    if not lines or not lines[0].startswith("diff --git a/"):
        raise ProposalError("candidate patch is not a unified Git diff")
    if "GIT binary patch" in patch or "Binary files" in patch:
        raise ProposalError("binary patches are not supported")
    for line in lines:
        if line.startswith(("--- ", "+++ ")):
            path = line[4:].split("\t", maxsplit=1)[0]
            if path == "/dev/null":
                continue
            if not path.startswith(("a/", "b/")) or ".." in path.split("/"):
                raise ProposalError(f"unsafe patch path: {path}")


def _prompt(context: bytes, maximum_candidates: int) -> bytes:
    prefix = (
        "Analyze the source-mapped hotspot and repository context below. Produce between one and "
        f"{maximum_candidates} conservative performance candidates as unified diffs. Each patch "
        "must be independently applicable to the exact baseline. Do not alter tests or benchmarks. "
        "Do not claim measured speedup. JSON context follows:\n"
    )
    return prefix.encode() + context


def run_proposals(
    baseline: BaselineResult,
    job: JobSpec,
    provider: ProposalProvider,
) -> BaselineResult:
    """Generate structured candidates but leave every decision inconclusive pending verification."""
    if baseline.bundle.status is not RunStatus.READY or baseline.bundle.profile is None:
        raise ProposalError("proposal generation requires a source-mapped profile")
    if job.proposal is None:
        raise ProposalError("job has no proposal configuration")
    candidates: list[CandidateResult] = []
    candidate_number = 1
    for hotspot in baseline.bundle.profile.hotspots[: job.proposal.maximum_hotspots]:
        try:
            context = assemble_context(baseline.source_root, hotspot, job.proposal)
        except ContextError as exc:
            raise ProposalError(str(exc)) from exc
        context_artifact = baseline.store.write(
            f"{hotspot.hotspot_id}.context",
            context,
            suffix=".json",
            media_type="application/json",
            description=f"Bounded repository context for {hotspot.hotspot_id}",
        )
        prompt = _prompt(context, job.proposal.maximum_candidates_per_hotspot)
        prompt_artifact = baseline.store.write(
            f"{hotspot.hotspot_id}.prompt",
            prompt,
            suffix=".txt",
            media_type="text/plain",
            description=f"Exact proposal prompt for {hotspot.hotspot_id}",
        )
        output = provider.generate(prompt.decode("utf-8"))
        response_artifact = baseline.store.write(
            f"{hotspot.hotspot_id}.response",
            output.raw_response,
            suffix=".json",
            media_type="application/json",
            description=f"Raw structured proposal response for {hotspot.hotspot_id}",
        )
        try:
            response = ProposalResponse.model_validate_json(output.raw_response)
        except ValidationError as exc:
            raise ProposalError(f"provider returned invalid proposal JSON: {exc}") from exc
        if len(response.candidates) > job.proposal.maximum_candidates_per_hotspot:
            raise ProposalError("provider returned more candidates than the configured maximum")
        provenance = ModelProvenance(
            provider=output.provider,
            model=output.model,
            prompt_sha256=hashlib.sha256(prompt).hexdigest(),
            prompt_artifact_id=prompt_artifact.artifact_id,
            response_artifact_id=response_artifact.artifact_id,
        )
        for proposal in response.candidates:
            _validate_patch(proposal.patch)
            candidate_id = f"candidate-{candidate_number:03d}"
            patch_artifact = baseline.store.write(
                f"{candidate_id}.patch",
                proposal.patch.encode("utf-8"),
                suffix=".diff",
                media_type="text/x-diff",
                description=f"Unverified patch proposed as {candidate_id}",
            )
            candidates.append(
                CandidateResult(
                    candidate_id=candidate_id,
                    hotspot_id=hotspot.hotspot_id,
                    title=proposal.title,
                    rationale=proposal.rationale,
                    risk=proposal.risk,
                    patch_artifact_id=patch_artifact.artifact_id,
                    context_artifact_id=context_artifact.artifact_id,
                    model=provenance,
                    decision=Decision.INCONCLUSIVE,
                    reason_codes=("not_verified",),
                    test_command_ids=(),
                )
            )
            candidate_number += 1
    bundle = baseline.bundle.model_copy(
        update={
            "candidates": tuple(candidates),
            "artifacts": baseline.store.artifacts,
            "commands": tuple(baseline.executor.records),
        }
    )
    bundle = type(bundle).model_validate(bundle.model_dump(mode="json"))
    write_manifest(baseline.bundle_root, bundle)
    return replace(baseline, bundle=bundle)
