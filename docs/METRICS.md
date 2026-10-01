# Metrics ledger

This file distinguishes definitions from observations. No Phase 1 product or design-partner run has
occurred yet, so all outcome values are **not measured**. The controlled fixture and all unit tests
are engineering validation and are excluded. Counts will be derived from validated run manifests;
costs will be derived from provider receipts and recorded compute duration. Estimates must never be
mixed with observations.

## Current observed outcomes

| Metric | Value | Evidence |
|---|---:|---|
| Repositories attempted | Not measured | No product runs yet |
| Repositories successfully built | Not measured | No product runs yet |
| Baseline test suites passed | Not measured | No product runs yet |
| Benchmarks reproduced | Not measured | No product runs yet |
| Repositories profiled | Not measured | No product runs yet |
| Candidates generated | Not measured | No product runs yet |
| Candidates compiled | Not measured | No product runs yet |
| Candidates passing configured tests | Not measured | No product runs yet |
| Statistically verified candidates | Not measured | No product runs yet |
| Inconclusive candidates | Not measured | No product runs yet |
| Human-approved candidates | Not measured | No product runs yet |
| Maintainer-invited runs | Not measured | No design-partner runs yet |
| PRs submitted | Not measured | No live submissions yet |
| PRs merged | Not measured | No live submissions yet |
| PerfBench cases predeclared | 8 | Catalog status only, not an outcome |
| PerfBench cases attempted | 0 | Complete not-run observation ledger |
| PerfBench hotspot-identification rate | Undefined (0/0) | PerfBench not run yet |
| PerfBench valid-candidate rate | Undefined (0/0) | PerfBench not run yet |
| PerfBench equivalent-fix recovery rate | Undefined (0/0) | PerfBench not run yet |
| PerfBench verified-speedup rate | Undefined (0/0) | PerfBench not run yet |
| PerfBench review-readiness rate | Undefined (0/0) | PerfBench not run yet |
| Cost per generated candidate | Not measured | Provider and compute costs not recorded yet |
| Cost per verified improvement | Not measured | No verified improvements yet |
| Median human review time | Not measured | No review observations yet |
| Design partners | 0 | No invitations or partner evaluations recorded |
| Waitlist signups | Not measured | Waitlist does not exist yet |

Fixture builds and contract tests are engineering validation, not product traction, and are excluded
from these counts.

## Funnel definitions

- **Repository attempted:** a valid job was admitted and source acquisition began.
- **Successfully built:** clean configure and build commands both completed successfully.
- **Baseline passed:** every configured baseline test command completed successfully.
- **Benchmark reproduced:** the existing/approved benchmark emitted valid samples on the pinned
  baseline using the recorded configuration.
- **Profiled:** a profile produced at least one source-mapped hotspot and passed integrity validation.
- **Candidate generated:** a structured patch proposal was recorded, even if it could not be applied.
- **Candidate compiled:** the patch applied and the clean candidate build succeeded.
- **Candidate passing tests:** every configured test command completed successfully for that candidate.
- **Statistically verified:** after family-wise correction, the candidate met all correctness,
  significance, confidence-interval, noise, and minimum-effect gates.
- **Inconclusive:** evidence was insufficient for acceptance or rejection; this is not counted as a
  failure or success.
- **Human approved:** Mohit judged the patch and evidence suitable for maintainer review.
- **PR submitted:** a disclosed PR was manually opened after maintainer contact and Mohit's review.
- **PR merged:** the upstream repository merged the submitted patch without materially removing the
  measured optimization.

## Cost definitions

- **LLM cost:** exact billed input, cached-input, and output token costs for recorded proposal calls.
- **Compute cost:** billed runner time where a receipt exists. Local hardware time is reported
  separately and is not assigned a fictional currency value.
- **Cost per candidate:** attributable LLM plus billed compute cost divided by generated candidates.
- **Cost per verified improvement:** total attributable LLM plus billed compute cost divided by
  statistically verified candidates. If the denominator is zero, report “undefined,” never zero.
- **Human review time:** measured active review duration, not wall-clock elapsed time.

## PerfBench reporting rules

Publish the case list and categories chosen before execution, the blind input commit, model/version,
prompt digest, all attempts, and all failures. Report hotspot identification, valid-candidate,
equivalent-fix, verified-speedup, and review-readiness separately. Do not collapse them into a single
favorable “hit rate.” Potential training-data contamination is a limitation for every historical case.
The score format represents a zero denominator as `null`, not zero percent. Catalog size is never the
denominator for a downstream stage that could not be reached, but unrun cases and setup failures are
reported beside every rate so attrition remains visible.
