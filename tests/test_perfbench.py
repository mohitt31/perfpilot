from __future__ import annotations

import json
from pathlib import Path

import pytest

from perfpilot.perfbench import (
    PerfBenchCatalog,
    PerfBenchObservations,
    canonical_sha256,
    load_suite,
    score_suite,
)

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "perfbench/public/cases-v1.json"
ANSWERS = ROOT / "perfbench/private/answers-v1.json"
OBSERVATIONS = ROOT / "perfbench/observations/not-run-v1.json"

def _synthetic_answer_key(tmp_path: Path) -> Path:
    catalog = PerfBenchCatalog.model_validate_json(CATALOG.read_text(encoding="utf-8"))
    payload = {
        "schema_version": "1.0.0",
        "suite_id": catalog.suite_id,
        "public_catalog_sha256": canonical_sha256(CATALOG),
        "answers": [
            {
                "case_id": case.case_id,
                "fix_commit": f"{index:040x}",
                "reference_url": f"https://github.com/example/project/pull/{index}",
                "title": f"Synthetic answer {index}",
                "changed_paths": ["src/example.cpp"],
                "reference_claim": "Synthetic contract fixture; not a performance result.",
            }
            for index, case in enumerate(catalog.cases, start=1)
        ],
    }
    path = tmp_path / "synthetic-answers.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_public_predeclared_catalog_is_complete() -> None:
    catalog = PerfBenchCatalog.model_validate_json(CATALOG.read_text(encoding="utf-8"))
    assert len(catalog.cases) == 8


def test_suite_lock_and_unrun_rates_are_publicly_testable(tmp_path: Path) -> None:
    synthetic_answers = _synthetic_answer_key(tmp_path)
    catalog, answers, observations = load_suite(CATALOG, synthetic_answers, OBSERVATIONS)
    assert len(answers.answers) == 8
    assert observations is not None
    score = score_suite(catalog, observations)
    assert score.total_cases == 8
    assert score.attempted_cases == 0
    assert score.hotspot_identification.denominator == 0
    assert score.hotspot_identification.fraction is None


def test_invalid_stage_order_is_rejected() -> None:
    raw = json.loads(OBSERVATIONS.read_text(encoding="utf-8"))
    raw["observations"][0]["valid_candidate"] = True
    with pytest.raises(ValueError, match="identified hotspot"):
        PerfBenchObservations.model_validate(raw)


@pytest.mark.skipif(not ANSWERS.exists(), reason="held-out answer key is intentionally not public")
def test_local_held_out_answer_key_matches_catalog() -> None:
    catalog, answers, _ = load_suite(CATALOG, ANSWERS)
    assert len(catalog.cases) == len(answers.answers) == 8
