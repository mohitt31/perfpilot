from __future__ import annotations

import pytest

from perfpilot.verify.statistics import (
    bootstrap_median_interval,
    holm_adjust,
    paired_log_improvements,
    paired_sign_permutation_p_value,
    relative_improvements,
)


def test_relative_and_log_improvements_preserve_pair_direction() -> None:
    before = [100.0, 110.0, 90.0]
    after = [80.0, 88.0, 72.0]
    assert relative_improvements(before, after, lower_is_better=True) == pytest.approx(
        [0.2, 0.2, 0.2]
    )
    logs = paired_log_improvements(before, after, lower_is_better=True)
    assert all(value > 0 for value in logs)


def test_exact_sign_permutation_detects_consistent_improvement() -> None:
    p_value = paired_sign_permutation_p_value([0.2] * 15, seed=42)
    assert p_value == pytest.approx(1 / 32768)


def test_bootstrap_degenerate_interval_is_explicit() -> None:
    interval = bootstrap_median_interval(
        [0.2] * 15,
        confidence_level=0.99,
        resamples=2_000,
        seed=42,
    )
    assert interval.lower == pytest.approx(0.2)
    assert interval.upper == pytest.approx(0.2)
    assert interval.method == "degenerate_exact"


def test_holm_adjustment_is_monotone_in_sorted_order() -> None:
    adjusted = holm_adjust({"a": 0.001, "b": 0.02, "c": 0.03})
    assert adjusted == pytest.approx({"a": 0.003, "b": 0.04, "c": 0.04})

