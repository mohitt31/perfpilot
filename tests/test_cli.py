from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from perfpilot.cli import app

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
runner = CliRunner()


def test_schema_command_emits_json_schema() -> None:
    result = runner.invoke(app, ["schema"])
    assert result.exit_code == 0
    schema = json.loads(result.stdout)
    assert schema["title"] == "EvidenceBundle"
    assert schema["properties"]["schema_version"]["const"] == "1.0.0"


def test_validate_job_accepts_fixture_contract() -> None:
    path = REPOSITORY_ROOT / "fixtures/cmake-healthy/perfpilot-job.example.json"
    result = runner.invoke(app, ["validate-job", str(path)])
    assert result.exit_code == 0
    assert result.stdout == "valid job specification\n"


def test_validate_job_reports_schema_errors(tmp_path: Path) -> None:
    path = tmp_path / "invalid-job.json"
    path.write_text("{}", encoding="utf-8")
    result = runner.invoke(app, ["validate-job", str(path)])
    assert result.exit_code == 2
    assert "invalid job specification" in result.stderr


def test_validate_bundle_reports_missing_manifest(tmp_path: Path) -> None:
    result = runner.invoke(app, ["validate-bundle", str(tmp_path)])
    assert result.exit_code == 2
    assert "invalid evidence bundle" in result.stderr

