"""Existing-benchmark execution and raw evidence capture."""

from __future__ import annotations

import json
from dataclasses import replace
from statistics import median
from typing import Any

from perfpilot.evidence.schema import BenchmarkPolicy, BenchmarkRun, Claim, JobSpec, RunStatus
from perfpilot.ingest.pipeline import BaselineResult, write_manifest


class BenchmarkError(RuntimeError):
    """The configured benchmark failed or emitted unsupported output."""


def _observations(payload: Any, job: JobSpec) -> int:
    if not isinstance(payload, dict):
        raise BenchmarkError("benchmark output must be a JSON object")
    google_observations = payload.get("benchmarks")
    if google_observations is not None:
        if not isinstance(google_observations, list):
            raise BenchmarkError("Google Benchmark 'benchmarks' must be a list")
        matching = [
            item
            for item in google_observations
            if isinstance(item, dict)
            and isinstance(item.get("name"), str)
            and (
                item["name"] == job.benchmark_name
                or item["name"].startswith(f"{job.benchmark_name}/")
            )
        ]
        if not matching:
            raise BenchmarkError(
                f"Google Benchmark output has no observation for {job.benchmark_name!r}"
            )
        units = {item.get("time_unit") for item in matching}
        if units != {job.benchmark_unit}:
            raise BenchmarkError(
                f"benchmark unit mismatch: expected {job.benchmark_unit!r}, found {units!r}"
            )
        return len(matching)

    if payload.get("benchmark") != job.benchmark_name:
        raise BenchmarkError(
            f"benchmark name mismatch: expected {job.benchmark_name!r}, "
            f"found {payload.get('benchmark')!r}"
        )
    elapsed_key = {
        "nanoseconds": "elapsed_ns",
        "microseconds": "elapsed_us",
        "milliseconds": "elapsed_ms",
        "seconds": "elapsed_seconds",
    }.get(job.benchmark_unit)
    if elapsed_key is None or not isinstance(payload.get(elapsed_key), (int, float)):
        raise BenchmarkError(
            f"generic benchmark output lacks a numeric value for unit {job.benchmark_unit!r}"
        )
    return 1


def extract_measurement(raw: bytes, job: JobSpec) -> float:
    """Extract one positive per-operation measurement in the job's declared unit."""
    try:
        payload: Any = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BenchmarkError("benchmark measurement is not valid JSON") from exc
    _observations(payload, job)
    assert isinstance(payload, dict)
    google_observations = payload.get("benchmarks")
    if isinstance(google_observations, list):
        values = [
            float(item["real_time"])
            for item in google_observations
            if isinstance(item, dict)
            and isinstance(item.get("name"), str)
            and (
                item["name"] == job.benchmark_name
                or item["name"].startswith(f"{job.benchmark_name}/")
            )
            and item.get("time_unit") == job.benchmark_unit
            and isinstance(item.get("real_time"), (int, float))
            and not item.get("aggregate_name")
        ]
        if not values or any(value <= 0 for value in values):
            raise BenchmarkError("Google Benchmark output has no positive real_time observations")
        return float(median(values))
    elapsed_key = {
        "nanoseconds": "elapsed_ns",
        "microseconds": "elapsed_us",
        "milliseconds": "elapsed_ms",
        "seconds": "elapsed_seconds",
    }[job.benchmark_unit]
    elapsed = payload[elapsed_key]
    repetitions = payload.get("repetitions", 1)
    if (
        not isinstance(elapsed, (int, float))
        or not isinstance(repetitions, int)
        or elapsed <= 0
        or repetitions <= 0
    ):
        raise BenchmarkError("generic benchmark values must be positive")
    return float(elapsed) / repetitions


def run_existing_benchmark(baseline: BaselineResult, job: JobSpec) -> BaselineResult:
    """Run and parse an existing benchmark without drawing comparative conclusions."""
    if baseline.bundle.status is not RunStatus.READY:
        raise BenchmarkError(f"benchmark requires ready baseline, found {baseline.bundle.status}")
    outcome = baseline.executor.run(
        "baseline-benchmark",
        "Reproduce the configured existing baseline benchmark",
        job.recipe.benchmark,
        cwd=baseline.source_root,
    )
    if not outcome.succeeded:
        failed = baseline.bundle.model_copy(
            update={
                "status": RunStatus.FAILED,
                "artifacts": baseline.store.artifacts,
                "commands": tuple(baseline.executor.records),
            }
        )
        write_manifest(baseline.bundle_root, failed)
        raise BenchmarkError("configured benchmark failed; evidence bundle was updated")
    try:
        payload = json.loads(outcome.stdout)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BenchmarkError("configured benchmark did not emit valid JSON") from exc
    observation_count = _observations(payload, job)
    policy = BenchmarkPolicy(
        benchmark_name=job.benchmark_name,
        command=job.recipe.benchmark,
        provenance=job.benchmark_provenance,
        lower_is_better=job.lower_is_better,
        unit=job.benchmark_unit,
        statistics=job.statistical_policy,
    )
    benchmark_run = BenchmarkRun(
        command_id=outcome.record.command_id,
        raw_output_artifact_id=outcome.record.stdout_artifact_id,
        benchmark_name=job.benchmark_name,
        observation_count=observation_count,
        unit=job.benchmark_unit,
    )
    claim = Claim(
        claim_id="baseline-benchmark-reproduced",
        statement=(
            "The configured baseline benchmark completed successfully and emitted parseable output."
        ),
        source_artifact_ids=(outcome.record.stdout_artifact_id,),
        computation="Parse the captured JSON using the declared benchmark output contract.",
    )
    bundle = baseline.bundle.model_copy(
        update={
            "benchmark": policy,
            "benchmark_run": benchmark_run,
            "artifacts": baseline.store.artifacts,
            "commands": tuple(baseline.executor.records),
            "claims": (*baseline.bundle.claims, claim),
        }
    )
    # Revalidate cross-record references after model_copy, which deliberately skips validation.
    bundle = type(bundle).model_validate(bundle.model_dump(mode="json"))
    write_manifest(baseline.bundle_root, bundle)
    return replace(baseline, bundle=bundle)
