"""Run profilers, retain raw output, and produce source-mapped hotspot rankings."""

from __future__ import annotations

import json
import platform
import re
import shutil
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from perfpilot.evidence.schema import Hotspot, JobSpec, ProfileResult, RunStatus
from perfpilot.ingest.pipeline import BaselineResult, write_manifest


class ProfileError(RuntimeError):
    """Profiling failed or did not produce trustworthy parseable data."""


def _relative_source(value: str, source_root: Path) -> str | None:
    path = Path(value)
    if path.is_absolute():
        try:
            return path.resolve().relative_to(source_root.resolve()).as_posix()
        except ValueError:
            return None
    if ".." in path.parts:
        return None
    return path.as_posix()


def parse_instrumented_json(
    raw: bytes, source_root: Path, maximum_hotspots: int
) -> tuple[Hotspot, ...]:
    try:
        payload: Any = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProfileError("instrumented profiler did not emit valid JSON") from exc
    if not isinstance(payload, dict) or payload.get("backend") != "instrumented_json":
        raise ProfileError("instrumented profile has an invalid backend marker")
    rows = payload.get("hotspots")
    if not isinstance(rows, list) or not rows:
        raise ProfileError("instrumented profile contains no hotspots")
    parsed: list[tuple[str, float, int | None, str, int]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ProfileError("instrumented hotspot must be an object")
        symbol = row.get("symbol")
        percent = row.get("percent_time")
        source_path = row.get("source_path")
        source_line = row.get("source_line")
        sample_count = row.get("sample_count")
        if (
            not isinstance(symbol, str)
            or not isinstance(percent, (int, float))
            or not isinstance(source_path, str)
            or not isinstance(source_line, int)
            or not 0 <= float(percent) <= 100
            or source_line < 1
            or (sample_count is not None and not isinstance(sample_count, int))
        ):
            raise ProfileError("instrumented hotspot has invalid fields")
        relative = _relative_source(source_path, source_root)
        if relative is None or not (source_root / relative).is_file():
            raise ProfileError(f"hotspot source path is not a repository file: {source_path}")
        parsed.append((symbol, float(percent), sample_count, relative, source_line))
    parsed.sort(key=lambda item: item[1], reverse=True)
    return tuple(
        Hotspot(
            hotspot_id=f"hotspot-{rank:03d}",
            rank=rank,
            symbol=symbol,
            percent_time=percent,
            sample_count=sample_count,
            source_path=source_path,
            source_line=source_line,
        )
        for rank, (symbol, percent, sample_count, source_path, source_line) in enumerate(
            parsed[:maximum_hotspots], start=1
        )
    )


_PERF_ROW = re.compile(
    r"^\s*(?P<percent>\d+(?:\.\d+)?)%\s+(?P<symbol>.+?)\s+"
    r"(?P<source>\S+):(?P<line>\d+)\s*$"
)


def parse_perf_report(
    text: str, source_root: Path, maximum_hotspots: int
) -> tuple[Hotspot, ...]:
    rows: list[tuple[str, float, str, int]] = []
    for line in text.splitlines():
        match = _PERF_ROW.match(line)
        if match is None:
            continue
        relative = _relative_source(match.group("source"), source_root)
        if relative is None or not (source_root / relative).is_file():
            continue
        rows.append(
            (
                match.group("symbol").strip(),
                float(match.group("percent")),
                relative,
                int(match.group("line")),
            )
        )
    rows.sort(key=lambda item: item[1], reverse=True)
    if not rows:
        raise ProfileError("perf report contained no repository source-mapped hotspots")
    return tuple(
        Hotspot(
            hotspot_id=f"hotspot-{rank:03d}",
            rank=rank,
            symbol=symbol,
            percent_time=percent,
            source_path=source,
            source_line=line,
        )
        for rank, (symbol, percent, source, line) in enumerate(
            rows[:maximum_hotspots], start=1
        )
    )


_SAMPLE_ROW = re.compile(
    r"^\s*[+!]?[ ]*(?P<count>\d+)\s+(?P<symbol>.+?)\s+\(in [^)]+\)"
    r"(?:.*?\[(?P<source>[^\]]+):(?P<line>\d+)\])?\s*$"
)


def parse_macos_sample(
    text: str, source_root: Path, maximum_hotspots: int
) -> tuple[Hotspot, ...]:
    by_symbol: dict[tuple[str, str | None, int | None], int] = {}
    maximum_count = 0
    for line in text.splitlines():
        match = _SAMPLE_ROW.match(line)
        if match is None:
            continue
        count = int(match.group("count"))
        maximum_count = max(maximum_count, count)
        source_value = match.group("source")
        source = _relative_source(source_value, source_root) if source_value else None
        source_line = int(match.group("line")) if match.group("line") else None
        if source is not None and not (source_root / source).is_file():
            source = None
            source_line = None
        key = (match.group("symbol").strip(), source, source_line)
        by_symbol[key] = max(by_symbol.get(key, 0), count)
    if maximum_count == 0 or not by_symbol:
        raise ProfileError("macOS sample output contained no parseable stack samples")
    ranked = sorted(by_symbol.items(), key=lambda item: item[1], reverse=True)
    return tuple(
        Hotspot(
            hotspot_id=f"hotspot-{rank:03d}",
            rank=rank,
            symbol=key[0],
            percent_time=100.0 * count / maximum_count,
            sample_count=count,
            source_path=key[1],
            source_line=key[2],
        )
        for rank, (key, count) in enumerate(ranked[:maximum_hotspots], start=1)
    )


def _run_instrumented(baseline: BaselineResult, job: JobSpec) -> ProfileResult:
    assert job.profile is not None
    outcome = baseline.executor.run(
        "profile-instrumented",
        "Run the repository-approved instrumented profile command",
        job.profile.command,
        cwd=baseline.source_root,
    )
    if not outcome.succeeded:
        raise ProfileError("instrumented profile command failed")
    hotspots = parse_instrumented_json(
        outcome.stdout, baseline.source_root, job.profile.maximum_hotspots
    )
    return ProfileResult(
        backend="instrumented_json",
        command_id=outcome.record.command_id,
        raw_profile_artifact_id=outcome.record.stdout_artifact_id,
        hotspots=hotspots,
        limitations=(
            "Function timing is explicitly instrumented and may perturb the measured workload.",
            "The repository or fixture chooses which regions are instrumented.",
        ),
    )


def _run_linux_perf(baseline: BaselineResult, job: JobSpec) -> ProfileResult:
    assert job.profile is not None
    if platform.system() != "Linux" or shutil.which("perf") is None:
        raise ProfileError("linux_perf requires Linux and the perf executable")
    perf_data = baseline.source_root / "build" / "perfpilot.perf.data"
    record = baseline.executor.run(
        "profile-perf-record",
        "Record Linux perf samples for the configured profiling workload",
        (
            "perf",
            "record",
            "--quiet",
            "--freq",
            "99",
            "--call-graph",
            "dwarf",
            "--output",
            str(perf_data),
            "--",
            *job.profile.command,
        ),
        cwd=baseline.source_root,
    )
    if not record.succeeded or not perf_data.is_file():
        raise ProfileError("perf record failed or did not create perf.data")
    baseline.store.write(
        "profile.perf-data",
        perf_data.read_bytes(),
        suffix=".data",
        media_type="application/octet-stream",
        description="Raw Linux perf.data sampling profile",
    )
    report = baseline.executor.run(
        "profile-perf-report",
        "Render source-mapped Linux perf samples",
        (
            "perf",
            "report",
            "--stdio",
            "--no-children",
            "--percent-limit",
            "0.1",
            "--sort",
            "overhead,symbol,srcline",
            "--input",
            str(perf_data),
        ),
        cwd=baseline.source_root,
    )
    if not report.succeeded:
        raise ProfileError("perf report failed")
    hotspots = parse_perf_report(
        report.stdout.decode("utf-8", errors="replace"),
        baseline.source_root,
        job.profile.maximum_hotspots,
    )
    return ProfileResult(
        backend="linux_perf",
        command_id=report.record.command_id,
        raw_profile_artifact_id=report.record.stdout_artifact_id,
        hotspots=hotspots,
        limitations=(
            "Sampling attributes time to observed stack samples and is not deterministic.",
            "Source mapping depends on debug information and perf's symbol resolution.",
        ),
    )


def _run_macos_sample(baseline: BaselineResult, job: JobSpec) -> ProfileResult:
    assert job.profile is not None
    if platform.system() != "Darwin" or not Path("/usr/bin/sample").is_file():
        raise ProfileError("macos_sample requires macOS and /usr/bin/sample")
    sample_output = baseline.source_root / "build" / "perfpilot.sample.txt"
    wrapper = Path(__file__).with_name("macos_sample.py")
    outcome = baseline.executor.run(
        "profile-macos-sample",
        "Attach macOS sample to the configured profiling workload",
        (
            sys.executable,
            str(wrapper),
            "--output",
            str(sample_output),
            "--duration",
            str(job.profile.duration_seconds),
            "--",
            *job.profile.command,
        ),
        cwd=baseline.source_root,
        timeout_seconds=job.profile.duration_seconds + 30,
    )
    if not outcome.succeeded or not sample_output.is_file():
        raise ProfileError("macOS sample failed or did not create a report")
    artifact = baseline.store.write(
        "profile.macos-sample",
        sample_output.read_bytes(),
        suffix=".txt",
        media_type="text/plain",
        description="Raw macOS sample call-graph report",
    )
    hotspots = parse_macos_sample(
        sample_output.read_text(encoding="utf-8", errors="replace"),
        baseline.source_root,
        job.profile.maximum_hotspots,
    )
    return ProfileResult(
        backend="macos_sample",
        command_id=outcome.record.command_id,
        raw_profile_artifact_id=artifact.artifact_id,
        hotspots=hotspots,
        limitations=(
            "macOS sample reports inclusive stack counts; hotspot percentages need not sum "
            "to 100%.",
            "Source locations may be absent when debug information is unavailable.",
            "This development fallback is not interchangeable with Linux perf evidence.",
        ),
    )


def run_profile(baseline: BaselineResult, job: JobSpec) -> BaselineResult:
    """Profile a reproduced baseline and append a ranked hotspot result."""
    if baseline.bundle.status is not RunStatus.READY or baseline.bundle.benchmark_run is None:
        raise ProfileError("profiling requires a ready baseline with a reproduced benchmark")
    if job.profile is None:
        raise ProfileError("job has no profiling configuration")
    backend = job.profile.backend
    if backend == "auto":
        backend = "linux_perf" if platform.system() == "Linux" else "macos_sample"
    if backend == "instrumented_json":
        profile = _run_instrumented(baseline, job)
    elif backend == "linux_perf":
        profile = _run_linux_perf(baseline, job)
    elif backend == "macos_sample":
        profile = _run_macos_sample(baseline, job)
    else:
        raise ProfileError(f"unsupported profiling backend: {backend}")
    bundle = baseline.bundle.model_copy(
        update={
            "profile": profile,
            "artifacts": baseline.store.artifacts,
            "commands": tuple(baseline.executor.records),
            "limitations": (*baseline.bundle.limitations, *profile.limitations),
        }
    )
    bundle = type(bundle).model_validate(bundle.model_dump(mode="json"))
    write_manifest(baseline.bundle_root, bundle)
    return replace(baseline, bundle=bundle)
