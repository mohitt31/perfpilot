from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from perfpilot.evidence.io import BundleIntegrityError, load_and_validate_bundle, sha256_file
from perfpilot.evidence.schema import EvidenceBundle


def _manifest(artifact_path: Path) -> dict[str, object]:
    artifact_bytes = artifact_path.read_bytes()
    return {
        "schema_version": "1.0.0",
        "run_id": "20261001T120000Z-deadbeef",
        "created_at": datetime(2026, 10, 1, 12, tzinfo=UTC).isoformat(),
        "status": "baseline_failed",
        "repository": {
            "url": "https://example.invalid/project.git",
            "commit": "1" * 40,
            "dirty": False,
        },
        "sandbox": {
            "image_reference": "perfpilot/runner@sha256:" + "2" * 64,
            "image_digest": "2" * 64,
            "run_as_root": False,
            "docker_socket_mounted": False,
            "credentials_mounted": False,
            "network": "disabled",
            "capabilities": [],
            "limits": {
                "cpu_count": 2,
                "memory_bytes": 2_147_483_648,
                "process_count": 128,
                "disk_bytes": 10_737_418_240,
                "wall_time_seconds": 600,
            },
        },
        "environment": {
            "machine": {
                "os": "Linux",
                "kernel": "fixture",
                "architecture": "x86_64",
                "cpu_model": "fixture CPU",
                "logical_cpu_count": 2,
                "memory_bytes": 2_147_483_648,
                "cpu_governor": None,
                "cpu_affinity": [0],
            },
            "toolchain": {
                "compiler_path": "/usr/bin/c++",
                "compiler_id": "GNU",
                "compiler_version": "fixture",
                "cmake_version": "fixture",
                "build_type": "Release",
                "compile_flags": ["-O3"],
                "linker_flags": [],
            },
        },
        "benchmark": None,
        "calibration": None,
        "artifacts": [
            {
                "artifact_id": "baseline-test.stdout",
                "path": artifact_path.name,
                "sha256": sha256_file(artifact_path),
                "size_bytes": len(artifact_bytes),
                "media_type": "text/plain",
                "description": "Captured baseline test output",
            },
            {
                "artifact_id": "baseline-test.stderr",
                "path": "stderr.txt",
                "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                "size_bytes": 0,
                "media_type": "text/plain",
                "description": "Captured baseline test errors",
            },
        ],
        "commands": [
            {
                "command_id": "baseline-test",
                "purpose": "Establish whether the repository starts healthy",
                "argv": ["ctest", "--test-dir", "build"],
                "working_directory": ".",
                "started_at": "2026-10-01T12:00:00Z",
                "duration_seconds": 1.25,
                "exit_code": 8,
                "timed_out": False,
                "stdout_artifact_id": "baseline-test.stdout",
                "stderr_artifact_id": "baseline-test.stderr",
            }
        ],
        "candidates": [],
        "claims": [
            {
                "claim_id": "baseline-failed",
                "statement": "The configured baseline test command returned a non-zero status.",
                "source_artifact_ids": ["baseline-test.stdout", "baseline-test.stderr"],
                "computation": "The recorded command exit code is non-zero.",
            }
        ],
        "limitations": ["Only the configured CTest command was executed."],
    }


def _write_bundle(tmp_path: Path) -> Path:
    stdout_path = tmp_path / "stdout.txt"
    stdout_path.write_text("failed\n", encoding="utf-8")
    (tmp_path / "stderr.txt").write_bytes(b"")
    (tmp_path / "manifest.json").write_text(
        json.dumps(_manifest(stdout_path)), encoding="utf-8"
    )
    return tmp_path


def test_valid_bundle_and_artifact_integrity(tmp_path: Path) -> None:
    bundle = load_and_validate_bundle(_write_bundle(tmp_path))
    assert bundle.status.value == "baseline_failed"
    assert bundle.run_id == "20261001T120000Z-deadbeef"


def test_tampered_artifact_is_rejected(tmp_path: Path) -> None:
    directory = _write_bundle(tmp_path)
    (directory / "stdout.txt").write_text("changed but same-ish\n", encoding="utf-8")
    with pytest.raises(BundleIntegrityError, match=r"size mismatch|digest mismatch"):
        load_and_validate_bundle(directory)


def test_parent_artifact_path_is_rejected(tmp_path: Path) -> None:
    stdout_path = tmp_path / "stdout.txt"
    stdout_path.write_text("failed\n", encoding="utf-8")
    manifest = _manifest(stdout_path)
    manifest["artifacts"][0]["path"] = "../stdout.txt"  # type: ignore[index]
    with pytest.raises(ValidationError, match="safe relative POSIX path"):
        EvidenceBundle.model_validate(manifest)


def test_baseline_failure_cannot_contain_candidate(tmp_path: Path) -> None:
    stdout_path = tmp_path / "stdout.txt"
    stdout_path.write_text("failed\n", encoding="utf-8")
    manifest = _manifest(stdout_path)
    manifest["candidates"] = [
        {
            "candidate_id": "candidate-001",
            "hotspot_id": "hotspot-001",
            "title": "Fixture candidate",
            "rationale": "Exercise schema invariants",
            "risk": "Fixture only",
            "patch_artifact_id": "baseline-test.stdout",
            "context_artifact_id": "baseline-test.stdout",
            "model": {
                "provider": "fixture",
                "model": "fixture",
                "prompt_sha256": "3" * 64,
                "prompt_artifact_id": "baseline-test.stdout",
                "response_artifact_id": "baseline-test.stdout",
            },
            "decision": "rejected",
            "reason_codes": ["baseline_failed"],
            "test_command_ids": [],
        }
    ]
    with pytest.raises(ValidationError, match="baseline-failed run cannot contain candidates"):
        EvidenceBundle.model_validate(manifest)


def test_unknown_fields_are_rejected(tmp_path: Path) -> None:
    stdout_path = tmp_path / "stdout.txt"
    stdout_path.write_text("failed\n", encoding="utf-8")
    manifest = _manifest(stdout_path)
    manifest["favorable_rounding"] = True
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        EvidenceBundle.model_validate(manifest)


def test_accepted_candidate_cannot_reference_failed_test(tmp_path: Path) -> None:
    stdout_path = tmp_path / "stdout.txt"
    stdout_path.write_text("failed\n", encoding="utf-8")
    manifest = _manifest(stdout_path)
    manifest["status"] = "completed"
    manifest["benchmark"] = {
        "benchmark_name": "fixture",
        "command": ["./fixture"],
        "provenance": "repository_existing",
        "lower_is_better": True,
        "unit": "nanoseconds",
        "statistics": {
            "random_seed": 42,
        },
    }
    manifest["calibration"] = {
        "raw_timing_artifact_id": "baseline-test.stdout",
        "pair_count": 15,
        "median_pair_difference_fraction": 0.0,
        "p95_absolute_pair_difference_fraction": 0.01,
        "decision": "acceptable",
        "rationale": "Fixture calibration",
    }
    manifest["candidates"] = [
        {
            "candidate_id": "candidate-001",
            "hotspot_id": "hotspot-001",
            "title": "Fixture candidate",
            "rationale": "Exercise schema invariants",
            "risk": "Fixture only",
            "patch_artifact_id": "baseline-test.stdout",
            "context_artifact_id": "baseline-test.stdout",
            "model": {
                "provider": "fixture",
                "model": "fixture",
                "prompt_sha256": "3" * 64,
                "prompt_artifact_id": "baseline-test.stdout",
                "response_artifact_id": "baseline-test.stdout",
            },
            "decision": "accepted",
            "reason_codes": ["verified"],
            "test_command_ids": ["baseline-test"],
            "raw_timing_artifact_id": "baseline-test.stdout",
            "observed_speedup_fraction": 0.08,
            "confidence_interval_fraction": [0.06, 0.1],
            "adjusted_p_value": 0.001,
        }
    ]
    with pytest.raises(ValidationError, match="references unsuccessful tests"):
        EvidenceBundle.model_validate(manifest)
