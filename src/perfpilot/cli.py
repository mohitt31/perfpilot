"""Command-line entry points for PerfPilot contracts."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from perfpilot.evidence.io import BundleIntegrityError, load_and_validate_bundle
from perfpilot.evidence.schema import EvidenceBundle, JobSpec, RunStatus
from perfpilot.fixture import run_controlled_fixture
from perfpilot.perfbench import load_suite, score_suite, write_score
from perfpilot.pipeline import PipelineError, run_full_verification
from perfpilot.report.render import ReportError, render_reports
from perfpilot.reproduce import compare_bundle_directories, write_reproduction_report

app = typer.Typer(
    no_args_is_help=True,
    help="Evidence-first performance optimization.",
)


def _validation_error(message: str) -> None:
    typer.echo(message, err=True)
    raise typer.Exit(code=2)


@app.command("schema")
def print_schema() -> None:
    """Print the versioned evidence-bundle JSON Schema."""
    typer.echo(json.dumps(EvidenceBundle.model_json_schema(), indent=2, sort_keys=True))


@app.command("validate-job")
def validate_job(
    path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
) -> None:
    """Validate a Phase 1 job specification without executing it."""
    try:
        JobSpec.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        _validation_error(f"invalid job specification: {exc}")
    typer.echo("valid job specification")


@app.command("validate-bundle")
def validate_bundle(
    directory: Annotated[Path, typer.Argument(exists=True, file_okay=False, readable=True)],
) -> None:
    """Validate a bundle manifest and the integrity of all referenced artifacts."""
    try:
        bundle = load_and_validate_bundle(directory)
    except (OSError, ValidationError, BundleIntegrityError) as exc:
        _validation_error(f"invalid evidence bundle: {exc}")
    typer.echo(f"valid evidence bundle {bundle.run_id} (schema {bundle.schema_version})")


@app.command("run")
def run_pipeline(
    job_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    output: Annotated[Path, typer.Option("--output", "-o")],
    recorded_response: Annotated[
        Path | None,
        typer.Option("--recorded-response", exists=True, dir_okay=False, readable=True),
    ] = None,
) -> None:
    """Run the local development pipeline through candidate correctness gates."""
    try:
        job = JobSpec.model_validate_json(job_path.read_text(encoding="utf-8"))
        result = run_full_verification(
            job,
            output,
            recorded_response=recorded_response,
        )
    except (OSError, ValidationError, PipelineError, RuntimeError) as exc:
        _validation_error(f"pipeline failed: {exc}")
    typer.echo(f"run {result.bundle.run_id}: {result.bundle.status.value}")
    if result.bundle.status.value in {"baseline_failed", "calibration_inconclusive"}:
        raise typer.Exit(code=3)
    for candidate in result.bundle.candidates:
        typer.echo(
            f"{candidate.candidate_id}: {candidate.decision.value} "
            f"({','.join(candidate.reason_codes)})"
        )


@app.command("report")
def report(
    directory: Annotated[Path, typer.Argument(exists=True, file_okay=False, readable=True)],
) -> None:
    """Render a validated evidence report and accepted-candidate PR drafts."""
    try:
        summary, drafts = render_reports(directory)
    except (OSError, ValidationError, BundleIntegrityError, ReportError) as exc:
        _validation_error(f"report generation failed: {exc}")
    typer.echo(str(summary))
    for draft in drafts:
        typer.echo(str(draft))


@app.command("perfbench-validate")
def perfbench_validate(
    catalog: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    answers: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
) -> None:
    """Validate the blinded public catalog and its separately stored answer key."""
    try:
        loaded, _, _ = load_suite(catalog, answers)
    except (OSError, ValidationError, ValueError) as exc:
        _validation_error(f"invalid PerfBench suite: {exc}")
    typer.echo(f"valid PerfBench suite {loaded.suite_id} ({len(loaded.cases)} cases)")


@app.command("perfbench-score")
def perfbench_score(
    catalog: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    answers: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    observations: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    output: Annotated[Path, typer.Option("--output", "-o")],
) -> None:
    """Score complete observations without hiding unrun cases or setup failures."""
    try:
        loaded, _, observed = load_suite(catalog, answers, observations)
        assert observed is not None
        score = score_suite(loaded, observed)
        write_score(output, score)
    except (OSError, ValidationError, ValueError) as exc:
        _validation_error(f"PerfBench scoring failed: {exc}")
    typer.echo(str(output))


@app.command("compare-runs")
def compare_runs(
    first: Annotated[Path, typer.Argument(exists=True, file_okay=False, readable=True)],
    second: Annotated[Path, typer.Argument(exists=True, file_okay=False, readable=True)],
    output: Annotated[Path, typer.Option("--output", "-o")],
) -> None:
    """Compare independently validated runs without pooling their measurements."""
    try:
        comparison = compare_bundle_directories(first, second)
        write_reproduction_report(output, comparison)
    except (OSError, ValidationError, BundleIntegrityError, ValueError) as exc:
        _validation_error(f"run comparison failed: {exc}")
    typer.echo(str(output))


@app.command("fixture-run")
def fixture_run(
    output: Annotated[Path, typer.Option("--output", "-o")],
    fixture_root: Annotated[Path, typer.Option(exists=True, file_okay=False, readable=True)] = Path(
        "fixtures/cmake-healthy"
    ),
    recorded_response: Annotated[
        Path, typer.Option(exists=True, dir_okay=False, readable=True)
    ] = Path("fixtures/cmake-healthy/perfpilot-proposals.example.json"),
) -> None:
    """Run the controlled fixture; its result is never product evidence."""
    try:
        result = run_controlled_fixture(fixture_root, recorded_response, output)
        summary, _ = render_reports(result.bundle_root)
    except (
        OSError,
        subprocess.SubprocessError,
        ValidationError,
        PipelineError,
        RuntimeError,
    ) as exc:
        _validation_error(f"fixture validation failed: {exc}")
    typer.echo(f"fixture run {result.bundle.run_id}: {result.bundle.status.value}")
    typer.echo(str(summary))
    if result.bundle.status in {
        RunStatus.BASELINE_FAILED,
        RunStatus.CALIBRATION_INCONCLUSIVE,
    }:
        raise typer.Exit(code=3)
