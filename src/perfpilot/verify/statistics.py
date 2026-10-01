"""Predeclared paired performance statistics."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from itertools import product
from statistics import fmean, median

import numpy as np
from scipy.stats import bootstrap  # type: ignore[import-untyped]


@dataclass(frozen=True)
class EffectInterval:
    observed_median: float
    lower: float
    upper: float
    method: str


def paired_log_improvements(
    baseline: list[float], candidate: list[float], *, lower_is_better: bool
) -> list[float]:
    if len(baseline) != len(candidate) or not baseline:
        raise ValueError("paired samples must be non-empty and have equal length")
    if any(value <= 0 for value in (*baseline, *candidate)):
        raise ValueError("benchmark measurements must be positive")
    if lower_is_better:
        return [
            math.log(before / after)
            for before, after in zip(baseline, candidate, strict=True)
        ]
    return [
        math.log(after / before)
        for before, after in zip(baseline, candidate, strict=True)
    ]


def relative_improvements(
    baseline: list[float], candidate: list[float], *, lower_is_better: bool
) -> list[float]:
    if len(baseline) != len(candidate) or not baseline:
        raise ValueError("paired samples must be non-empty and have equal length")
    if lower_is_better:
        return [
            (before - after) / before
            for before, after in zip(baseline, candidate, strict=True)
        ]
    return [
        (after - before) / before
        for before, after in zip(baseline, candidate, strict=True)
    ]


def paired_sign_permutation_p_value(
    log_improvements: list[float],
    *,
    seed: int,
    monte_carlo_resamples: int = 100_000,
) -> float:
    """One-sided sign-permutation p-value for positive mean paired log improvement."""
    if not log_improvements:
        raise ValueError("at least one paired improvement is required")
    observed = fmean(log_improvements)
    tolerance = 1e-15
    if len(log_improvements) <= 20:
        extreme = 0
        total = 0
        for signs in product((-1.0, 1.0), repeat=len(log_improvements)):
            statistic = fmean(
                sign * improvement
                for sign, improvement in zip(signs, log_improvements, strict=True)
            )
            extreme += statistic >= observed - tolerance
            total += 1
        return extreme / total

    generator = random.Random(seed)
    extreme = 0
    for _ in range(monte_carlo_resamples):
        statistic = fmean(
            improvement if generator.getrandbits(1) else -improvement
            for improvement in log_improvements
        )
        extreme += statistic >= observed - tolerance
    return (extreme + 1) / (monte_carlo_resamples + 1)


def bootstrap_median_interval(
    improvements: list[float],
    *,
    confidence_level: float,
    resamples: int,
    seed: int,
) -> EffectInterval:
    if not improvements:
        raise ValueError("at least one improvement is required")
    observed = float(median(improvements))
    if len(set(improvements)) == 1:
        return EffectInterval(observed, observed, observed, "degenerate_exact")
    result = bootstrap(
        (np.asarray(improvements, dtype=float),),
        np.median,
        vectorized=False,
        confidence_level=confidence_level,
        n_resamples=resamples,
        method="BCa",
        random_state=seed,
    )
    lower = float(result.confidence_interval.low)
    upper = float(result.confidence_interval.high)
    if not math.isfinite(lower) or not math.isfinite(upper):
        raise ValueError("BCa bootstrap produced a non-finite confidence interval")
    return EffectInterval(observed, lower, upper, "BCa")


def holm_adjust(p_values: dict[str, float]) -> dict[str, float]:
    """Return monotone Holm-adjusted p-values, preserving candidate IDs."""
    if any(not 0 <= value <= 1 for value in p_values.values()):
        raise ValueError("p-values must lie in [0, 1]")
    ordered = sorted(p_values.items(), key=lambda item: item[1])
    adjusted: dict[str, float] = {}
    running = 0.0
    total = len(ordered)
    for rank, (identifier, value) in enumerate(ordered, start=1):
        running = max(running, min(1.0, (total - rank + 1) * value))
        adjusted[identifier] = running
    return adjusted
