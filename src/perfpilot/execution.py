"""Portable command execution with evidence capture.

The local backend is intentionally not described as a sandbox. It exists for development on macOS.
The Docker backend builds a hardened Linux invocation but requires a pinned image and Docker daemon.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Protocol

from perfpilot.evidence.io import sha256_file
from perfpilot.evidence.schema import (
    Artifact,
    CommandRecord,
    DockerSandboxPolicy,
    LocalExecutionPolicy,
    ResourceLimits,
)


class ExecutionError(RuntimeError):
    """A command could not be started or its execution contract was invalid."""


class ArtifactStore:
    """Write immutable run artifacts beneath a bundle directory."""

    def __init__(self, bundle_root: Path) -> None:
        self.bundle_root = bundle_root.resolve()
        self.artifact_root = self.bundle_root / "artifacts"
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self._artifacts: list[Artifact] = []
        self._ids: set[str] = set()

    @property
    def artifacts(self) -> tuple[Artifact, ...]:
        return tuple(self._artifacts)

    def write(
        self,
        artifact_id: str,
        data: bytes,
        *,
        suffix: str,
        media_type: str,
        description: str,
    ) -> Artifact:
        if artifact_id in self._ids:
            raise ExecutionError(f"duplicate artifact ID: {artifact_id}")
        safe_name = artifact_id.replace(".", "-")
        relative_path = Path("artifacts") / f"{safe_name}{suffix}"
        path = self.bundle_root / relative_path
        if path.exists():
            raise ExecutionError(f"refusing to overwrite artifact: {relative_path}")
        path.write_bytes(data)
        artifact = Artifact(
            artifact_id=artifact_id,
            path=relative_path.as_posix(),
            sha256=sha256_file(path),
            size_bytes=len(data),
            media_type=media_type,
            description=description,
        )
        self._ids.add(artifact_id)
        self._artifacts.append(artifact)
        return artifact


@dataclass(frozen=True)
class CommandOutcome:
    record: CommandRecord
    stdout: bytes
    stderr: bytes

    @property
    def succeeded(self) -> bool:
        return not self.record.timed_out and self.record.exit_code == 0


class Executor(Protocol):
    records: list[CommandRecord]

    def run(
        self,
        command_id: str,
        purpose: str,
        argv: Sequence[str],
        *,
        cwd: Path,
        timeout_seconds: float | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> CommandOutcome: ...


class LocalExecutor:
    """Execute directly on the host and record that no isolation is provided."""

    def __init__(
        self,
        workspace_root: Path,
        store: ArtifactStore,
        limits: ResourceLimits,
    ) -> None:
        self.workspace_root = workspace_root.resolve()
        self.store = store
        self.limits = limits
        self.records: list[CommandRecord] = []
        self.policy = LocalExecutionPolicy(
            environment_sanitized=True,
            warning=(
                "Local development execution is not sandboxed: repository code can access the "
                "host filesystem and network, and configured resource limits are not enforced."
            ),
        )

    def _environment(self, extra_env: dict[str, str] | None) -> dict[str, str]:
        allowed = ("PATH", "TMPDIR", "LANG", "LC_ALL", "CC", "CXX", "SDKROOT")
        environment = {key: os.environ[key] for key in allowed if key in os.environ}
        environment["HOME"] = str(self.workspace_root / ".home")
        (self.workspace_root / ".home").mkdir(exist_ok=True)
        if extra_env:
            environment.update(extra_env)
        return environment

    def run(
        self,
        command_id: str,
        purpose: str,
        argv: Sequence[str],
        *,
        cwd: Path,
        timeout_seconds: float | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> CommandOutcome:
        if not argv:
            raise ExecutionError("command argv cannot be empty")
        resolved_cwd = cwd.resolve(strict=True)
        if not resolved_cwd.is_relative_to(self.workspace_root):
            raise ExecutionError("command working directory escapes the run workspace")
        timeout = timeout_seconds or self.limits.wall_time_seconds
        started_at = datetime.now(UTC)
        started_clock = monotonic()
        timed_out = False
        exit_code: int | None
        try:
            completed = subprocess.run(
                list(argv),
                cwd=resolved_cwd,
                env=self._environment(extra_env),
                capture_output=True,
                check=False,
                timeout=timeout,
            )
            stdout = completed.stdout
            stderr = completed.stderr
            exit_code = completed.returncode
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or b""
            stderr = exc.stderr or b""
            timed_out = True
            exit_code = None
        except OSError as exc:
            raise ExecutionError(f"could not execute {argv[0]!r}: {exc}") from exc
        duration = monotonic() - started_clock
        stdout_artifact = self.store.write(
            f"{command_id}.stdout",
            stdout,
            suffix=".log",
            media_type="text/plain",
            description=f"Standard output for {purpose}",
        )
        stderr_artifact = self.store.write(
            f"{command_id}.stderr",
            stderr,
            suffix=".log",
            media_type="text/plain",
            description=f"Standard error for {purpose}",
        )
        record = CommandRecord(
            command_id=command_id,
            purpose=purpose,
            argv=tuple(argv),
            working_directory=resolved_cwd.relative_to(self.workspace_root).as_posix() or ".",
            started_at=started_at,
            duration_seconds=duration,
            exit_code=exit_code,
            timed_out=timed_out,
            stdout_artifact_id=stdout_artifact.artifact_id,
            stderr_artifact_id=stderr_artifact.artifact_id,
        )
        self.records.append(record)
        return CommandOutcome(record=record, stdout=stdout, stderr=stderr)


def build_docker_argv(
    policy: DockerSandboxPolicy,
    workspace_root: Path,
    cwd: Path,
    argv: Sequence[str],
    *,
    host_ids: tuple[int, int] | None = None,
) -> tuple[str, ...]:
    """Construct the hardened Docker invocation used by the Linux backend.

    ``host_ids`` overrides the (uid, gid) pair; it exists so the non-root rule
    can be tested independently of the account running the test suite.
    """
    root = workspace_root.resolve(strict=True)
    resolved_cwd = cwd.resolve(strict=True)
    if not resolved_cwd.is_relative_to(root):
        raise ExecutionError("Docker working directory escapes the run workspace")
    if not argv:
        raise ExecutionError("command argv cannot be empty")
    uid, gid = host_ids if host_ids is not None else (os.getuid(), os.getgid())
    if uid == 0:
        raise ExecutionError("Docker runner must be launched by a non-root host account")
    image = f"{policy.image_reference}@sha256:{policy.image_digest}"
    container_cwd = Path("/workspace") / resolved_cwd.relative_to(root)
    network = "none" if policy.network.value == "disabled" else "bridge"
    return (
        "docker",
        "run",
        "--rm",
        "--read-only",
        "--network",
        network,
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        str(policy.limits.process_count),
        "--memory",
        str(policy.limits.memory_bytes),
        "--cpus",
        str(policy.limits.cpu_count),
        "--user",
        f"{uid}:{gid}",
        "--env",
        "HOME=/tmp/perfpilot-home",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=512m",
        "--volume",
        f"{root}:/workspace:rw",
        "--workdir",
        container_cwd.as_posix(),
        image,
        *argv,
    )


class DockerExecutor:
    """Execute repository commands through a pinned, constrained Linux container."""

    def __init__(
        self,
        workspace_root: Path,
        store: ArtifactStore,
        policy: DockerSandboxPolicy,
    ) -> None:
        self.workspace_root = workspace_root.resolve()
        self.store = store
        self.policy = policy
        self._host = LocalExecutor(workspace_root, store, policy.limits)
        self.records = self._host.records

    def run(
        self,
        command_id: str,
        purpose: str,
        argv: Sequence[str],
        *,
        cwd: Path,
        timeout_seconds: float | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> CommandOutcome:
        if extra_env:
            raise ExecutionError("Docker extra environment variables are not yet supported")
        docker_argv = build_docker_argv(self.policy, self.workspace_root, cwd, argv)
        return self._host.run(
            command_id,
            purpose,
            docker_argv,
            cwd=self.workspace_root,
            timeout_seconds=timeout_seconds,
        )
