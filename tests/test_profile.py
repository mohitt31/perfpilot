from __future__ import annotations

from pathlib import Path

import pytest

from perfpilot.benchmark import run_existing_benchmark
from perfpilot.evidence.io import load_and_validate_bundle
from perfpilot.ingest.pipeline import run_baseline
from perfpilot.profile.pipeline import (
    ProfileError,
    parse_macos_sample,
    parse_perf_report,
    run_profile,
)
from tests.test_ingest import create_fixture_repository, fixture_job


def test_perf_report_parser_keeps_repository_source_locations(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "src").mkdir(parents=True)
    (source / "src/hot.cpp").write_text("int hot();\n", encoding="utf-8")
    report = "  83.25%  hot_symbol  src/hot.cpp:1\n  16.75%  kernel  [unknown]:0\n"
    hotspots = parse_perf_report(report, source, 10)
    assert len(hotspots) == 1
    assert hotspots[0].symbol == "hot_symbol"
    assert hotspots[0].percent_time == 83.25
    assert hotspots[0].source_path == "src/hot.cpp"


def test_macos_sample_parser_reports_inclusive_percentages(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "src").mkdir(parents=True)
    file = source / "src/hot.cpp"
    file.write_text("int hot();\n", encoding="utf-8")
    report = f"  100 hot_symbol (in fixture) [0x1] [{file}:1]\n  25 child (in fixture)\n"
    hotspots = parse_macos_sample(report, source, 10)
    assert hotspots[0].symbol == "hot_symbol"
    assert hotspots[0].percent_time == 100.0
    assert hotspots[0].source_path == "src/hot.cpp"
    assert hotspots[1].percent_time == 25.0


def test_perf_parser_rejects_profile_without_source_mapping(tmp_path: Path) -> None:
    with pytest.raises(ProfileError, match="no repository source-mapped"):
        parse_perf_report("  100.00% kernel [unknown]:0\n", tmp_path, 10)


def test_fixture_profile_ranks_measured_integer_sum_first(tmp_path: Path) -> None:
    repository, commit = create_fixture_repository(tmp_path, "cmake-healthy")
    job = fixture_job(repository, commit, healthy=True)
    baseline = run_baseline(job, tmp_path / "bundle")
    benchmarked = run_existing_benchmark(baseline, job)
    result = run_profile(benchmarked, job)
    assert result.bundle.profile is not None
    first = result.bundle.profile.hotspots[0]
    assert first.symbol == "perfpilot_fixture::integer_sum"
    assert first.source_path == "src/integer_sum.cpp"
    assert first.source_line == 11
    assert first.percent_time > 50
    load_and_validate_bundle(result.bundle_root)
