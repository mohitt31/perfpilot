from __future__ import annotations

import json
from pathlib import Path

import pytest

from perfpilot.perfbench import (
    PerfBenchObservations,
    load_suite,
    score_suite,
)

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "perfbench/public/cases-v1.json"
ANSWERS = ROOT / "perfbench/private/answers-v1.json"
OBSERVATIONS = ROOT / "perfbench/observations/not-run-v1.json"

# The answer key is held out of the public repository.
needs_answers = pytest.mark.skipif(not ANSWERS.exists(), reason="private answer key not present")


@needs_answers
def test_predeclared_suite_is_locked_and_complete() -> None:
    catalog, answers, observations = load_suite(CATALOG, ANSWERS, OBSERVATIONS)
    assert len(catalog.cases) == 8
    assert len(answers.answers) == 8
    assert observations is not None


@needs_answers
def test_unrun_suite_has_undefined_rates_not_zero_percent() -> None:
    catalog, _, observations = load_suite(CATALOG, ANSWERS, OBSERVATIONS)
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
