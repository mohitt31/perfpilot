"""Versioned data contracts for Phase 1 evidence.

The manifest stores metadata and references immutable artifacts. Large command output and raw
benchmark samples belong in artifacts, not inline in the manifest.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

EVIDENCE_SCHEMA_VERSION = "1.0.0"
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
CommitSha = Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
NonNegativeFloat = Annotated[float, Field(ge=0, allow_inf_nan=False)]
PositiveFloat = Annotated[float, Field(gt=0, allow_inf_nan=False)]


class StrictModel(BaseModel):
    """Reject unknown input so misspelled evidence fields cannot disappear silently."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class RunStatus(StrEnum):
    INITIALIZED = "initialized"
    BASELINE_FAILED = "baseline_failed"
    CALIBRATION_INCONCLUSIVE = "calibration_inconclusive"
    READY = "ready"
    COMPLETED = "completed"
    FAILED = "failed"


class Decision(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    INCONCLUSIVE = "inconclusive"


class NetworkMode(StrEnum):
    DISABLED = "disabled"
    DEPENDENCY_FETCH_ONLY = "dependency_fetch_only"


class RepositoryRef(StrictModel):
    url: str = Field(min_length=1)
    commit: CommitSha
    dirty: Literal[False] = False

    @field_validator("url")
    @classmethod
    def supported_repository_url(cls, value: str) -> str:
        if not value.startswith(("https://", "file://")):
            raise ValueError("repository URL must use https:// or file://")
        return value


class ResourceLimits(StrictModel):
    cpu_count: Annotated[int, Field(ge=1)]
    memory_bytes: Annotated[int, Field(ge=1)]
    process_count: Annotated[int, Field(ge=1)]
    disk_bytes: Annotated[int, Field(ge=1)]
    wall_time_seconds: PositiveFloat


class DockerSandboxPolicy(StrictModel):
    kind: Literal["docker"] = "docker"
    image_reference: str = Field(min_length=1)
    image_digest: Sha256
    run_as_root: Literal[False] = False
    docker_socket_mounted: Literal[False] = False
    credentials_mounted: Literal[False] = False
    network: NetworkMode
    capabilities: tuple[str, ...] = ()
    limits: ResourceLimits

    @field_validator("capabilities")
    @classmethod
    def capabilities_must_be_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("capabilities must not contain duplicates")
        return value


class LocalExecutionPolicy(StrictModel):
    kind: Literal["local"] = "local"
    isolation: Literal["none"] = "none"
    host_filesystem_accessible: Literal[True] = True
    network_accessible: Literal[True] = True
    resource_limits_enforced: Literal[False] = False
    environment_sanitized: bool
    warning: str = Field(min_length=1)


ExecutionPolicy = DockerSandboxPolicy | LocalExecutionPolicy


class MachineInfo(StrictModel):
    os: str = Field(min_length=1)
    kernel: str = Field(min_length=1)
    architecture: str = Field(min_length=1)
    cpu_model: str = Field(min_length=1)
    logical_cpu_count: Annotated[int, Field(ge=1)]
    memory_bytes: Annotated[int, Field(ge=1)]
    cpu_governor: str | None = None
    cpu_affinity: tuple[int, ...] = ()


class ToolchainInfo(StrictModel):
    compiler_path: str = Field(min_length=1)
    compiler_id: str = Field(min_length=1)
    compiler_version: str = Field(min_length=1)
    cmake_version: str = Field(min_length=1)
    build_type: str = Field(min_length=1)
    compile_flags: tuple[str, ...]
    linker_flags: tuple[str, ...]


class EnvironmentInfo(StrictModel):
    machine: MachineInfo
    toolchain: ToolchainInfo


class Artifact(StrictModel):
    artifact_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")
    path: str = Field(min_length=1)
    sha256: Sha256
    size_bytes: Annotated[int, Field(ge=0)]
    media_type: str = Field(min_length=1)
    description: str = Field(min_length=1)

    @field_validator("path")
    @classmethod
    def path_is_safe_relative_posix(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or value in {"", "."}:
            raise ValueError("artifact path must be a safe relative POSIX path")
        return value


class CommandRecord(StrictModel):
    command_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")
    purpose: str = Field(min_length=1)
    argv: tuple[str, ...] = Field(min_length=1)
    working_directory: str
    started_at: datetime
    duration_seconds: NonNegativeFloat
    exit_code: int | None
    timed_out: bool
    stdout_artifact_id: str
    stderr_artifact_id: str

    @field_validator("started_at")
    @classmethod
    def timestamp_has_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("started_at must include a UTC offset")
        return value

    @field_validator("working_directory")
    @classmethod
    def working_directory_is_relative(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("working_directory must stay within the sandbox workspace")
        return value

    @model_validator(mode="after")
    def timeout_and_exit_code_are_consistent(self) -> CommandRecord:
        if self.timed_out and self.exit_code is not None:
            raise ValueError("a timed-out command cannot have an exit code")
        if not self.timed_out and self.exit_code is None:
            raise ValueError("a completed command must have an exit code")
        return self


class StatisticalPolicy(StrictModel):
    design: Literal["randomized_paired_blocks"] = "randomized_paired_blocks"
    test: Literal["paired_permutation", "wilcoxon"] = "paired_permutation"
    alpha: Annotated[float, Field(gt=0, lt=1)] = 0.01
    multiple_testing_correction: Literal["holm"] = "holm"
    confidence_level: Annotated[float, Field(gt=0, lt=1)] = 0.99
    bootstrap_resamples: Annotated[int, Field(ge=1_000)] = 10_000
    minimum_pairs: Annotated[int, Field(ge=15)] = 15
    maximum_pairs: Annotated[int, Field(ge=15)] = 50
    minimum_effect_fraction: Annotated[float, Field(gt=0, lt=1)] = 0.05
    warmup_iterations: Annotated[int, Field(ge=1)] = 5
    random_seed: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def maximum_is_not_below_minimum(self) -> StatisticalPolicy:
        if self.maximum_pairs < self.minimum_pairs:
            raise ValueError("maximum_pairs must be at least minimum_pairs")
        return self


class BenchmarkPolicy(StrictModel):
    benchmark_name: str = Field(min_length=1)
    command: tuple[str, ...] = Field(min_length=1)
    provenance: Literal["repository_existing", "owner_approved_generated"]
    lower_is_better: bool
    unit: str = Field(min_length=1)
    statistics: StatisticalPolicy


class BenchmarkRun(StrictModel):
    command_id: str
    raw_output_artifact_id: str
    benchmark_name: str = Field(min_length=1)
    observation_count: Annotated[int, Field(ge=1)]
    unit: str = Field(min_length=1)


class Hotspot(StrictModel):
    hotspot_id: str = Field(pattern=r"^hotspot-[0-9]{3,}$")
    rank: Annotated[int, Field(ge=1)]
    symbol: str = Field(min_length=1)
    percent_time: Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]
    sample_count: Annotated[int, Field(ge=0)] | None = None
    source_path: str | None = None
    source_line: Annotated[int, Field(ge=1)] | None = None

    @model_validator(mode="after")
    def source_path_and_line_are_together(self) -> Hotspot:
        if (self.source_path is None) != (self.source_line is None):
            raise ValueError("source_path and source_line must be present together")
        if self.source_path is not None:
            path = PurePosixPath(self.source_path)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("hotspot source_path must be repository-relative")
        return self


class ProfileResult(StrictModel):
    backend: Literal["linux_perf", "macos_sample", "instrumented_json"]
    command_id: str
    raw_profile_artifact_id: str
    hotspots: tuple[Hotspot, ...] = Field(min_length=1)
    limitations: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def ranks_and_ids_are_unique(self) -> ProfileResult:
        ranks = [item.rank for item in self.hotspots]
        identifiers = [item.hotspot_id for item in self.hotspots]
        if len(ranks) != len(set(ranks)) or len(identifiers) != len(set(identifiers)):
            raise ValueError("hotspot ranks and IDs must be unique")
        if ranks != sorted(ranks):
            raise ValueError("hotspots must be ordered by ascending rank")
        return self


class CalibrationDecision(StrEnum):
    ACCEPTABLE = "acceptable"
    EXCESSIVE_NOISE = "excessive_noise"


class AACalibration(StrictModel):
    """Summary of same-revision paired measurements taken before candidate evaluation."""

    raw_timing_artifact_id: str
    pair_count: Annotated[int, Field(ge=15)]
    median_pair_difference_fraction: float = Field(allow_inf_nan=False)
    p95_absolute_pair_difference_fraction: NonNegativeFloat
    decision: CalibrationDecision
    rationale: str = Field(min_length=1)


class ModelProvenance(StrictModel):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    prompt_sha256: Sha256
    prompt_artifact_id: str
    response_artifact_id: str


class CandidateResult(StrictModel):
    candidate_id: str = Field(pattern=r"^candidate-[0-9]{3,}$")
    hotspot_id: str
    title: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    risk: str = Field(min_length=1)
    patch_artifact_id: str
    context_artifact_id: str
    model: ModelProvenance
    decision: Decision
    reason_codes: tuple[str, ...] = Field(min_length=1)
    test_command_ids: tuple[str, ...]
    raw_timing_artifact_id: str | None = None
    observed_speedup_fraction: float | None = Field(default=None, allow_inf_nan=False)
    confidence_interval_fraction: tuple[float, float] | None = None
    adjusted_p_value: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def accepted_candidate_has_complete_evidence(self) -> CandidateResult:
        if self.confidence_interval_fraction is not None:
            low, high = self.confidence_interval_fraction
            if low > high:
                raise ValueError("confidence interval lower bound exceeds upper bound")
        if self.decision is Decision.ACCEPTED:
            required = (
                self.raw_timing_artifact_id,
                self.observed_speedup_fraction,
                self.confidence_interval_fraction,
                self.adjusted_p_value,
            )
            if any(item is None for item in required):
                raise ValueError(
                    "accepted candidates require complete timing and statistical evidence"
                )
            if not self.test_command_ids:
                raise ValueError("accepted candidates require at least one passing test command")
        return self


class Claim(StrictModel):
    claim_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")
    statement: str = Field(min_length=1)
    source_artifact_ids: tuple[str, ...] = Field(min_length=1)
    computation: str | None = None


class EvidenceBundle(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    run_id: str = Field(pattern=r"^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$")
    created_at: datetime
    status: RunStatus
    repository: RepositoryRef
    sandbox: ExecutionPolicy
    environment: EnvironmentInfo
    benchmark: BenchmarkPolicy | None
    benchmark_run: BenchmarkRun | None = None
    profile: ProfileResult | None = None
    calibration: AACalibration | None
    artifacts: tuple[Artifact, ...]
    commands: tuple[CommandRecord, ...]
    candidates: tuple[CandidateResult, ...] = ()
    claims: tuple[Claim, ...] = ()
    limitations: tuple[str, ...] = Field(min_length=1)

    @field_validator("created_at")
    @classmethod
    def created_at_has_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must include a UTC offset")
        return value

    @model_validator(mode="after")
    def references_and_status_are_consistent(self) -> EvidenceBundle:
        artifact_ids = [item.artifact_id for item in self.artifacts]
        command_ids = [item.command_id for item in self.commands]
        candidate_ids = [item.candidate_id for item in self.candidates]
        claim_ids = [item.claim_id for item in self.claims]
        for label, values in (
            ("artifact", artifact_ids),
            ("command", command_ids),
            ("candidate", candidate_ids),
            ("claim", claim_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{label} IDs must be unique")

        artifact_set = set(artifact_ids)
        command_set = set(command_ids)
        referenced_artifacts: list[str] = []
        for command in self.commands:
            referenced_artifacts.extend((command.stdout_artifact_id, command.stderr_artifact_id))
        if self.benchmark_run is not None:
            referenced_artifacts.append(self.benchmark_run.raw_output_artifact_id)
            if self.benchmark_run.command_id not in command_set:
                raise ValueError("benchmark run references an unknown command")
        if self.profile is not None:
            referenced_artifacts.append(self.profile.raw_profile_artifact_id)
            if self.profile.command_id not in command_set:
                raise ValueError("profile references an unknown command")
        if self.calibration is not None:
            referenced_artifacts.append(self.calibration.raw_timing_artifact_id)
        for candidate in self.candidates:
            referenced_artifacts.extend(
                (
                    candidate.patch_artifact_id,
                    candidate.context_artifact_id,
                    candidate.model.prompt_artifact_id,
                    candidate.model.response_artifact_id,
                )
            )
            if candidate.raw_timing_artifact_id is not None:
                referenced_artifacts.append(candidate.raw_timing_artifact_id)
            missing_commands = set(candidate.test_command_ids) - command_set
            if missing_commands:
                raise ValueError(
                    f"candidate references unknown commands: {sorted(missing_commands)}"
                )
            if candidate.decision is Decision.ACCEPTED:
                commands_by_id = {item.command_id: item for item in self.commands}
                failed_tests = [
                    command_id
                    for command_id in candidate.test_command_ids
                    if commands_by_id[command_id].timed_out
                    or commands_by_id[command_id].exit_code != 0
                ]
                if failed_tests:
                    raise ValueError(
                        f"accepted candidate references unsuccessful tests: {failed_tests}"
                    )
        for claim in self.claims:
            referenced_artifacts.extend(claim.source_artifact_ids)
        missing_artifacts = set(referenced_artifacts) - artifact_set
        if missing_artifacts:
            raise ValueError(f"manifest references unknown artifacts: {sorted(missing_artifacts)}")

        if self.status is RunStatus.BASELINE_FAILED:
            if self.candidates:
                raise ValueError("a baseline-failed run cannot contain candidates")
            if self.benchmark is not None:
                raise ValueError(
                    "a baseline-failed run cannot claim a benchmark policy was exercised"
                )
            if self.calibration is not None:
                raise ValueError("a baseline-failed run cannot contain A/A calibration")
        if self.status is RunStatus.CALIBRATION_INCONCLUSIVE:
            if self.benchmark is None or self.calibration is None:
                raise ValueError(
                    "a calibration-inconclusive run requires a benchmark and calibration"
                )
            if self.calibration.decision is not CalibrationDecision.EXCESSIVE_NOISE:
                raise ValueError(
                    "a calibration-inconclusive run requires an excessive-noise decision"
                )
            if self.candidates:
                raise ValueError("a calibration-inconclusive run cannot contain candidates")
        if self.status is RunStatus.COMPLETED:
            if self.benchmark is None or self.calibration is None:
                raise ValueError("a completed run requires a benchmark and A/A calibration")
            if self.calibration.decision is not CalibrationDecision.ACCEPTABLE:
                raise ValueError("a completed run requires acceptable A/A calibration")
            for candidate in self.candidates:
                if candidate.decision is not Decision.ACCEPTED:
                    continue
                assert candidate.adjusted_p_value is not None
                assert candidate.confidence_interval_fraction is not None
                if candidate.adjusted_p_value >= self.benchmark.statistics.alpha:
                    raise ValueError(
                        "accepted candidate adjusted p-value does not clear configured alpha"
                    )
                lower_confidence_bound = candidate.confidence_interval_fraction[0]
                if lower_confidence_bound < self.benchmark.statistics.minimum_effect_fraction:
                    raise ValueError(
                        "accepted candidate confidence interval does not clear minimum effect"
                    )
        artifacts_by_id = {item.artifact_id: item for item in self.artifacts}
        for candidate in self.candidates:
            prompt = artifacts_by_id[candidate.model.prompt_artifact_id]
            if prompt.sha256 != candidate.model.prompt_sha256:
                raise ValueError(
                    f"candidate {candidate.candidate_id} prompt digest does not match its artifact"
                )
        return self


class BuildRecipe(StrictModel):
    configure: tuple[str, ...] = Field(min_length=1)
    build: tuple[str, ...] = Field(min_length=1)
    test: tuple[str, ...] = Field(min_length=1)
    benchmark: tuple[str, ...] = Field(min_length=1)


class ProfileConfig(StrictModel):
    backend: Literal["auto", "linux_perf", "macos_sample", "instrumented_json"] = "auto"
    command: tuple[str, ...] = Field(min_length=1)
    duration_seconds: Annotated[int, Field(ge=1, le=60)] = 5
    maximum_hotspots: Annotated[int, Field(ge=1, le=50)] = 10


class ProposalConfig(StrictModel):
    provider: Literal["recorded", "openai"]
    model: str = Field(min_length=1)
    maximum_hotspots: Annotated[int, Field(ge=1, le=10)] = 3
    maximum_candidates_per_hotspot: Annotated[int, Field(ge=1, le=3)] = 3
    maximum_context_bytes: Annotated[int, Field(ge=4_096, le=200_000)] = 40_000
    source_window_lines: Annotated[int, Field(ge=10, le=200)] = 80


class JobSpec(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    repository: RepositoryRef
    recipe: BuildRecipe
    profile: ProfileConfig | None = None
    proposal: ProposalConfig | None = None
    benchmark_name: str = Field(min_length=1)
    benchmark_unit: str = Field(min_length=1)
    benchmark_provenance: Literal[
        "repository_existing", "owner_approved_generated"
    ] = "repository_existing"
    lower_is_better: bool = True
    statistical_policy: StatisticalPolicy
    fixture_mode: bool = False
    resource_limits: ResourceLimits = ResourceLimits(
        cpu_count=2,
        memory_bytes=4_294_967_296,
        process_count=256,
        disk_bytes=10_737_418_240,
        wall_time_seconds=900,
    )

    @model_validator(mode="after")
    def local_repository_requires_fixture_mode(self) -> JobSpec:
        if self.repository.url.startswith("file://") and not self.fixture_mode:
            raise ValueError("file:// repositories are allowed only in fixture_mode")
        return self
