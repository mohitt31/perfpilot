# Statistical protocol and research basis

PerfPilot predeclares a minimum worthwhile effect, alpha, confidence level, warmups, random seed, and
maximum number of pairs. It does not sample until significant.

For every pair, baseline and candidate order is randomized. Lower-is-better relative improvement is
`(baseline - candidate) / baseline`; the hypothesis statistic is the mean of
`log(baseline / candidate)`. Up to 20 pairs use the exact sign-permutation distribution; larger sets
use 100,000 seeded sign permutations with a plus-one correction. The reported effect is the median
paired relative improvement with SciPy's BCa bootstrap interval. A degenerate equal-valued sample is
reported as an exact point interval. Holm-adjusted p-values cover all correctness-passing candidates.

Acceptance requires both adjusted `p < alpha` and `CI lower bound >= minimum effect`. A nonpositive
median or interval wholly below the threshold is rejected; other failures to clear the gates are
inconclusive. A/A calibration first requires its 95th-percentile absolute same-revision pair
difference to be below the minimum effect.

The design follows the central lesson of Kalibera and Jones: performance changes need effect sizes
with uncertainty, not isolated point estimates. It also follows Georges, Buytaert, and Eeckhout's
warning that systems performance evaluation requires rigorous repetition and statistical treatment.
Holm's sequential procedure controls family-wise error, and SciPy documents the BCa implementation
used here.

Primary sources:

- Tomas Kalibera and Richard Jones, [Quantifying Performance Changes with Effect Size Confidence
  Intervals](https://www.cs.kent.ac.uk/pubs/2012/3233/).
- Andy Georges, Dries Buytaert, and Lieven Eeckhout, [Statistically Rigorous Java Performance
  Evaluation](https://dri.es/files/oopsla07-georges.pdf), OOPSLA 2007.
- Sture Holm, [A Simple Sequentially Rejective Multiple Test
  Procedure](https://www.ime.usp.br/~abe/lista/pdf4R8xPVzCnX.pdf), 1979.
- SciPy, [`scipy.stats.bootstrap`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html).

These sources motivate the protocol; they do not certify this implementation. Unit tests, fixture
runs, source review, and future external replication address different failure modes.
