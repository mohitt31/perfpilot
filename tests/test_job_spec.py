from pathlib import Path

from perfpilot.evidence.schema import JobSpec

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_example_job_spec_matches_contract() -> None:
    path = REPOSITORY_ROOT / "fixtures/cmake-healthy/perfpilot-job.example.json"
    job = JobSpec.model_validate_json(path.read_text(encoding="utf-8"))
    assert job.recipe.test[0] == "ctest"
    assert job.statistical_policy.alpha == 0.01

