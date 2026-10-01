from pathlib import Path

import pytest

from perfpilot.evidence.schema import DockerSandboxPolicy, NetworkMode, ResourceLimits
from perfpilot.execution import ExecutionError, build_docker_argv


def _policy() -> DockerSandboxPolicy:
    return DockerSandboxPolicy(
        image_reference="ghcr.io/example/perfpilot-runner",
        image_digest="a" * 64,
        network=NetworkMode.DISABLED,
        limits=ResourceLimits(
            cpu_count=2,
            memory_bytes=4_294_967_296,
            process_count=256,
            disk_bytes=10_737_418_240,
            wall_time_seconds=900,
        ),
    )


def test_docker_invocation_enforces_phase_one_controls(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    argv = build_docker_argv(
        _policy(), tmp_path, source, ("cmake", "--build", "build"), host_ids=(1000, 1000)
    )
    assert argv[:3] == ("docker", "run", "--rm")
    for required in (
        "--read-only",
        "--cap-drop",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        "--memory",
        "--cpus",
        "--user",
    ):
        assert required in argv
    assert argv[argv.index("--network") + 1] == "none"
    assert argv[argv.index("--user") + 1] == "1000:1000"
    assert argv[-3:] == ("cmake", "--build", "build")
    assert argv[-4] == "ghcr.io/example/perfpilot-runner@sha256:" + "a" * 64


def test_docker_invocation_rejects_root_host_account(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    with pytest.raises(ExecutionError, match="non-root"):
        build_docker_argv(_policy(), tmp_path, source, ("true",), host_ids=(0, 0))


def test_docker_invocation_rejects_escaping_working_directory(tmp_path: Path) -> None:
    outside = tmp_path.parent
    with pytest.raises(ExecutionError, match="escapes"):
        build_docker_argv(_policy(), tmp_path, outside, ("true",))
