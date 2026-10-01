"""Load evidence manifests and check artifact integrity."""

from __future__ import annotations

import hashlib
from pathlib import Path

from perfpilot.evidence.schema import EvidenceBundle


class BundleIntegrityError(ValueError):
    """An evidence artifact does not match its manifest entry."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_and_validate_bundle(directory: Path) -> EvidenceBundle:
    """Parse `manifest.json` and validate every artifact's path, size, and digest."""
    root = directory.resolve(strict=True)
    manifest_path = root / "manifest.json"
    bundle = EvidenceBundle.model_validate_json(manifest_path.read_text(encoding="utf-8"))

    for artifact in bundle.artifacts:
        path = (root / artifact.path).resolve(strict=True)
        if not path.is_relative_to(root):
            raise BundleIntegrityError(
                f"artifact {artifact.artifact_id!r} resolves outside the bundle"
            )
        if not path.is_file():
            raise BundleIntegrityError(f"artifact {artifact.artifact_id!r} is not a regular file")
        actual_size = path.stat().st_size
        if actual_size != artifact.size_bytes:
            raise BundleIntegrityError(
                f"artifact {artifact.artifact_id!r} size mismatch: "
                f"expected {artifact.size_bytes}, found {actual_size}"
            )
        actual_digest = sha256_file(path)
        if actual_digest != artifact.sha256:
            raise BundleIntegrityError(
                f"artifact {artifact.artifact_id!r} digest mismatch: "
                f"expected {artifact.sha256}, found {actual_digest}"
            )
    return bundle

