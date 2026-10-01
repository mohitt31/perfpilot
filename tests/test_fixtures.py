from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPOSITORY_ROOT / "fixtures"


def _configure_and_build(source: Path, build: Path) -> None:
    subprocess.run(
        ["cmake", "-S", str(source), "-B", str(build), "-DCMAKE_BUILD_TYPE=Release"],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["cmake", "--build", str(build), "--parallel", "2"],
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.mark.skipif(shutil.which("cmake") is None, reason="CMake is not installed")
def test_healthy_fixture_builds_tests_and_emits_benchmark_json(tmp_path: Path) -> None:
    build = tmp_path / "healthy-build"
    _configure_and_build(FIXTURES / "cmake-healthy", build)
    subprocess.run(
        ["ctest", "--test-dir", str(build), "--output-on-failure"],
        check=True,
        capture_output=True,
        text=True,
    )
    output = subprocess.run(
        [str(build / "integer_sum_benchmark")],
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(output.stdout)
    assert result["benchmark"] == "integer_sum"
    assert result["elapsed_ns"] > 0
    assert result["repetitions"] == 20000


@pytest.mark.skipif(shutil.which("cmake") is None, reason="CMake is not installed")
def test_broken_baseline_fixture_builds_but_ctest_fails(tmp_path: Path) -> None:
    build = tmp_path / "broken-build"
    _configure_and_build(FIXTURES / "cmake-broken-baseline", build)
    result = subprocess.run(
        ["ctest", "--test-dir", str(build), "--output-on-failure"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "intentional baseline failure" in result.stdout
