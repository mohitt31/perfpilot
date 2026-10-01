"""Render review material without introducing claims absent from the evidence bundle."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import median
from typing import Any

from perfpilot.evidence.io import load_and_validate_bundle
from perfpilot.evidence.schema import CandidateResult, CommandRecord, Decision, EvidenceBundle


class ReportError(RuntimeError):
    """A report could not be derived from validated evidence."""


def _artifact_path(root: Path, bundle: EvidenceBundle, artifact_id: str) -> Path:
    artifact = next((item for item in bundle.artifacts if item.artifact_id == artifact_id), None)
    if artifact is None:
        raise ReportError(f"unknown report artifact: {artifact_id}")
    return root / artifact.path


def _command(bundle: EvidenceBundle, command_id: str) -> CommandRecord:
    command = next((item for item in bundle.commands if item.command_id == command_id), None)
    if command is None:
        raise ReportError(f"unknown report command: {command_id}")
    return command


def _exact(value: float | int) -> str:
    """Use Python's round-trip representation; presentation never changes an acceptance decision."""
    return repr(value)


def _timing_payload(
    root: Path, bundle: EvidenceBundle, candidate: CandidateResult
) -> dict[str, Any]:
    if candidate.raw_timing_artifact_id is None:
        raise ReportError(f"candidate {candidate.candidate_id} has no timing evidence")
    path = _artifact_path(root, bundle, candidate.raw_timing_artifact_id)
    payload: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("candidate_id") != candidate.candidate_id:
        raise ReportError(f"candidate {candidate.candidate_id} timing artifact is inconsistent")
    return payload


def _report_markdown(root: Path, bundle: EvidenceBundle) -> str:
    accepted = [item for item in bundle.candidates if item.decision is Decision.ACCEPTED]
    rejected = [item for item in bundle.candidates if item.decision is Decision.REJECTED]
    inconclusive = [item for item in bundle.candidates if item.decision is Decision.INCONCLUSIVE]
    lines = [
        "# PerfPilot evidence report",
        "",
        f"- Run: `{bundle.run_id}`",
        f"- Status: `{bundle.status.value}`",
        f"- Repository: `{bundle.repository.url}`",
        f"- Commit: `{bundle.repository.commit}`",
        f"- Execution backend: `{bundle.sandbox.kind}`",
        f"- Host OS: `{bundle.environment.machine.os}`",
        f"- Architecture: `{bundle.environment.machine.architecture}`",
        f"- CPU: `{bundle.environment.machine.cpu_model}`",
        f"- Compiler: `{bundle.environment.toolchain.compiler_version}`",
        "",
        "## Decision summary",
        "",
        f"- Accepted: `{len(accepted)}`",
        f"- Rejected: `{len(rejected)}`",
        f"- Inconclusive: `{len(inconclusive)}`",
        "",
    ]
    if bundle.calibration is not None:
        lines.extend(
            [
                "## A/A calibration",
                "",
                f"- Decision: `{bundle.calibration.decision.value}`",
                f"- Pair count: `{bundle.calibration.pair_count}`",
                "- Median signed paired difference fraction: "
                f"`{_exact(bundle.calibration.median_pair_difference_fraction)}`",
                "- 95th-percentile absolute paired difference fraction: "
                f"`{_exact(bundle.calibration.p95_absolute_pair_difference_fraction)}`",
                f"- Raw data: `{bundle.calibration.raw_timing_artifact_id}`",
                "",
            ]
        )
    lines.extend(["## Candidates", ""])
    for candidate in bundle.candidates:
        lines.extend(
            [
                f"### {candidate.candidate_id}: {candidate.title}",
                "",
                f"- Decision: `{candidate.decision.value}`",
                f"- Reason: `{','.join(candidate.reason_codes)}`",
                f"- Hotspot: `{candidate.hotspot_id}`",
                f"- Provider/model: `{candidate.model.provider}` / `{candidate.model.model}`",
                f"- Patch evidence: `{candidate.patch_artifact_id}`",
                f"- Rationale: {candidate.rationale}",
                f"- Risk: {candidate.risk}",
            ]
        )
        if candidate.observed_speedup_fraction is not None:
            assert candidate.confidence_interval_fraction is not None
            assert candidate.adjusted_p_value is not None
            lines.extend(
                [
                    "- Observed median paired speedup fraction: "
                    f"`{_exact(candidate.observed_speedup_fraction)}`",
                    "- Confidence interval fraction: "
                    f"`[{_exact(candidate.confidence_interval_fraction[0])}, "
                    f"{_exact(candidate.confidence_interval_fraction[1])}]`",
                    f"- Holm-adjusted p-value: `{_exact(candidate.adjusted_p_value)}`",
                    f"- Raw timing evidence: `{candidate.raw_timing_artifact_id}`",
                ]
            )
        lines.extend(["", "Configured test commands:", ""])
        if candidate.test_command_ids:
            for command_id in candidate.test_command_ids:
                command = _command(bundle, command_id)
                lines.append(
                    f"- `{command_id}`: exit `{command.exit_code}`, timed out "
                    f"`{str(command.timed_out).lower()}` — `{' '.join(command.argv)}`"
                )
        else:
            lines.append("- None completed for this candidate.")
        lines.append("")
    lines.extend(["## Limitations and what was not tested", ""])
    lines.extend(f"- {limitation}" for limitation in bundle.limitations)
    lines.extend(
        [
            "- Passing configured tests does not establish semantic equivalence or universal "
            "correctness.",
            "- This run does not establish performance on another machine, compiler, workload, "
            "architecture, or build configuration.",
            "",
            "## Artifact index",
            "",
            "| Artifact ID | Path | Bytes | SHA-256 |",
            "|---|---|---:|---|",
        ]
    )
    lines.extend(
        f"| `{item.artifact_id}` | `{item.path}` | `{item.size_bytes}` | `{item.sha256}` |"
        for item in bundle.artifacts
    )
    return "\n".join(lines) + "\n"


def _pr_draft(root: Path, bundle: EvidenceBundle, candidate: CandidateResult) -> str:
    payload = _timing_payload(root, bundle, candidate)
    pairs = payload.get("pairs")
    if not isinstance(pairs, list) or not pairs:
        raise ReportError("timing artifact has no pairs")
    baseline_values = [float(pair["baseline"]) for pair in pairs]
    candidate_values = [float(pair["candidate"]) for pair in pairs]
    assert candidate.confidence_interval_fraction is not None
    assert candidate.adjusted_p_value is not None
    tests = [_command(bundle, identifier) for identifier in candidate.test_command_ids]
    lines = [
        f"# {candidate.title}",
        "",
        "## Summary",
        "",
        candidate.rationale,
        "",
        "This draft is for maintainer review. PerfPilot has not opened or submitted a pull "
        "request.",
        "",
        "## Measured result",
        "",
        f"- Benchmark: `{bundle.benchmark.benchmark_name if bundle.benchmark else 'unavailable'}`",
        f"- Paired measurements: `{len(pairs)}`",
        f"- Baseline median ({payload.get('unit')}): `{_exact(float(median(baseline_values)))}`",
        f"- Candidate median ({payload.get('unit')}): `{_exact(float(median(candidate_values)))}`",
        "- Median paired speedup fraction: "
        f"`{_exact(candidate.observed_speedup_fraction or 0.0)}`",
        "- Confidence interval fraction: "
        f"`[{_exact(candidate.confidence_interval_fraction[0])}, "
        f"{_exact(candidate.confidence_interval_fraction[1])}]`",
        f"- Holm-adjusted p-value: `{_exact(candidate.adjusted_p_value)}`",
        f"- Raw timing artifact: `{candidate.raw_timing_artifact_id}`",
        "",
        "The result applies only to the recorded machine, workload, compiler, flags, and commit.",
        "",
        "## Validation performed",
        "",
    ]
    lines.extend(
        f"- `{' '.join(command.argv)}` — exit `{command.exit_code}`; "
        f"timed out `{str(command.timed_out).lower()}`"
        for command in tests
    )
    lines.extend(
        [
            "",
            "## Risks and limitations",
            "",
            f"- {candidate.risk}",
            "- The configured tests cover only behavior exercised by those tests.",
            "- No cross-machine or cross-compiler performance claim is made.",
            "- Review the patch and raw evidence before considering submission.",
            "",
            "## AI assistance disclosure",
            "",
            "PerfPilot used an AI model to propose this candidate. A human reviewed the proposal, "
            "and PerfPilot independently applied the patch, ran the configured tests, and measured "
            "the recorded benchmark. The maintainer should treat both the patch and this "
            "explanation as review material, not as a correctness guarantee.",
            "",
            f"Patch artifact: `{candidate.patch_artifact_id}`",
            "",
        ]
    )
    return "\n".join(lines)


def render_reports(bundle_root: Path) -> tuple[Path, tuple[Path, ...]]:
    """Validate first, then render a run report and PR drafts for accepted candidates."""
    bundle = load_and_validate_bundle(bundle_root)
    reports = bundle_root / "reports"
    reports.mkdir(exist_ok=True)
    summary_path = reports / "evidence-report.md"
    summary_path.write_text(_report_markdown(bundle_root, bundle), encoding="utf-8")
    drafts: list[Path] = []
    for candidate in bundle.candidates:
        if candidate.decision is not Decision.ACCEPTED:
            continue
        path = reports / f"{candidate.candidate_id}-pr-draft.md"
        path.write_text(_pr_draft(bundle_root, bundle, candidate), encoding="utf-8")
        drafts.append(path)
    return summary_path, tuple(drafts)
