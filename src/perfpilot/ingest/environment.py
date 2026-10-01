"""Best-effort environment capture for development evidence."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess

from perfpilot.evidence.schema import EnvironmentInfo, MachineInfo, ToolchainInfo


def _first_line(argv: list[str]) -> str:
    try:
        result = subprocess.run(argv, check=False, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"
    output = result.stdout.strip() or result.stderr.strip()
    return output.splitlines()[0] if output else "unavailable"


def _memory_bytes() -> int:
    if platform.system() == "Darwin":
        try:
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            return int(result.stdout.strip())
        except (OSError, ValueError, subprocess.SubprocessError):
            return 1
    try:
        return int(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES"))
    except (OSError, ValueError, KeyError):
        return 1


def capture_environment() -> EnvironmentInfo:
    compiler_path = shutil.which("c++") or "unavailable"
    compiler_version = _first_line([compiler_path, "--version"])
    cmake_version = _first_line(["cmake", "--version"])
    return EnvironmentInfo(
        machine=MachineInfo(
            os=platform.system() or "unavailable",
            kernel=platform.release() or "unavailable",
            architecture=platform.machine() or "unavailable",
            cpu_model=platform.processor() or platform.machine() or "unavailable",
            logical_cpu_count=os.cpu_count() or 1,
            memory_bytes=_memory_bytes(),
            cpu_governor=None,
            cpu_affinity=(),
        ),
        toolchain=ToolchainInfo(
            compiler_path=compiler_path,
            compiler_id=compiler_version.split()[0] if compiler_version else "unavailable",
            compiler_version=compiler_version,
            cmake_version=cmake_version,
            build_type="Release",
            compile_flags=(),
            linker_flags=(),
        ),
    )

