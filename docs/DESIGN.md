# Design log

This is a living decision record. Major changes require a dated entry containing the evidence that
motivated them and the alternatives rejected.

## D-001 — Narrow Phase 1 to public C++/CMake repositories

- **Status:** accepted
- **Date:** 2026-10-01
- **Decision:** Linux, CPU-only, public C++ repositories with explicit CMake recipes are the committed
  vertical. Python is gated on Phase 1 completion.
- **Why:** This matches the founder's demonstrated expertise and reduces environment variance enough
  to make the central evidence claim credible.
- **Rejected:** C++ and Python in parallel. It doubles adapters and failure modes before the verifier
  is proven.

## D-002 — Evidence bundle is the source of truth

- **Status:** accepted
- **Date:** 2026-10-01
- **Decision:** Reports are derived from a versioned manifest plus content-addressed artifacts. Strict
  schemas reject unknown fields, unsafe paths, dangling references, and incomplete accepted results.
- **Why:** A reviewer must be able to trace every claim to captured output or raw samples. Hashes make
  accidental post-run changes detectable.
- **Rejected:** Store only a Markdown report. It is readable but cannot enforce provenance or retain
  sufficient raw data for reanalysis.
- **Limit:** Hashes establish internal integrity, not independent attestation.

## D-003 — Require explicit command recipes before automatic detection

- **Status:** accepted for the first runner
- **Date:** 2026-10-01
- **Decision:** A versioned job file specifies configure, build, test, and benchmark argument arrays.
  Detection may later propose a recipe, but the user approves it before execution.
- **Why:** CMake projects are heterogeneous. Explicit recipes make failures explainable and prevent a
  detector guess from being confused with repository intent.
- **Rejected:** Infer and immediately execute commands. It expands the trust boundary and creates
  ambiguous failures.

## D-004 — A broken baseline is a terminal, honest result

- **Status:** accepted
- **Date:** 2026-10-01
- **Decision:** If the configured baseline tests fail, record `baseline_failed`, render the exact
  command results and limitations, and stop before benchmarks, profiling, or proposals.
- **Why:** PerfPilot cannot attribute later failures to a candidate when the pinned baseline is
  unhealthy.
- **Rejected:** Continue while ignoring known failing tests or compare the candidate against the same
  failures. That may eventually be an explicit expert mode, but it is too easy to misrepresent.

## D-005 — Statistical design is predeclared and paired

- **Status:** accepted as a contract; implementation is a later milestone
- **Date:** 2026-10-01
- **Decision:** Use randomized paired A/B blocks, a paired permutation test by default, bootstrap
  confidence intervals, a separate minimum worthwhile effect, a fixed maximum sample count, and Holm
  correction across candidates. Perform A/A calibration first.
- **Why:** Pairing controls temporal drift; the confidence interval communicates magnitude and
  uncertainty; a predeclared cap avoids sampling until significance; Holm controls family-wise error.
- **Rejected:** Two unpaired batches with Mann–Whitney U. They discard the temporal pairing. Also
  rejected: accept on p-value alone, because statistical detectability is not practical value.

## D-006 — No autonomous pull requests

- **Status:** accepted
- **Date:** 2026-10-01
- **Decision:** PerfPilot stops at an evidence bundle and review draft. Maintainer contact, human
  review, and AI disclosure are mandatory before the founder manually submits a patch.
- **Why:** Maintainer trust is more valuable than volume, and automated submissions create asymmetric
  reputational harm.
- **Rejected:** GitHub token support in Phase 1.

## D-007 — Fixture benchmark validates plumbing only

- **Status:** accepted
- **Date:** 2026-10-01
- **Decision:** The healthy fixture contains a dependency-free timed executable so the build pipeline
  is runnable offline. Its results cannot be used as evidence of a performance improvement.
- **Why:** Milestone 1 needs deterministic fixtures, while scientifically defensible measurement is a
  separate milestone.
- **Rejected:** Fetch Google Benchmark for the fixture. It adds a network dependency before ingestion
  and dependency policy exist.
- **Test mode:** Automated verifier tests pass `--fixture-deterministic-json`, which emits predeclared
  baseline/candidate markers (100 and 80) so acceptance-path tests cannot flake with host noise. The
  default fixture command measures wall time and remains subject to A/A rejection. Deterministic
  markers are never product measurements.

## D-008 — A/A calibration is structured evidence

- **Status:** accepted
- **Date:** 2026-10-01
- **Decision:** The manifest records raw A/A timing evidence, pair count, median signed difference,
  95th-percentile absolute paired difference, a decision, and its rationale. Excessive noise is a
  terminal `calibration_inconclusive` result and candidate generation does not begin.
- **Why:** Treating calibration as prose would allow a report to omit or reinterpret an inconvenient
  noise result. The explicit terminal state makes “inconclusive” enforceable.
- **Rejected:** Store only a scalar noise floor. It loses the raw data and decision context required
  for later audit or reanalysis.

## D-009 — Fixed-count randomized paired measurements

- **Status:** implemented
- **Date:** 2026-10-01
- **Decision:** Warmups are fixed and excluded. A/A and A/B use the predeclared maximum pair count;
  order is randomized inside every pair from a recorded seed. There is no early significance stop.
- **Why:** Pairing reduces temporal drift; a fixed cap avoids optional stopping. The one-sided sign
  permutation statistic is mean log improvement, while effect size is median relative improvement.
- **Limit:** The permutation null assumes exchangeability of pair signs. Serial dependence, thermal
  regimes, workload invalidity, and benchmark bugs remain possible.

## D-010 — Acceptance needs significance and practical magnitude

- **Status:** implemented
- **Date:** 2026-10-01
- **Decision:** Accept only when the Holm-adjusted p-value is strictly below alpha and the BCa
  confidence interval lower bound is at least the predeclared minimum effect. All candidates in the
  measured family are included in Holm correction.
- **Why:** A p-value alone does not show useful magnitude. Holm controls family-wise error without
  requiring independent candidate tests.
- **Limit:** A confidence interval is conditional on the benchmark, machine, sampling design, and
  model assumptions; it is not a portability guarantee.

## D-011 — Proposal context and output are bounded data

- **Status:** implemented
- **Date:** 2026-10-01
- **Decision:** Only source-mapped windows and selected tests/build guidance enter a serialized byte
  budget. Proposals must match a strict structured schema and safe unified-diff paths. Exact prompt,
  response, model identifier, and prompt digest are evidence.
- **Why:** This reduces accidental source disclosure and makes model behavior inspectable.
- **Rejected:** Repository-wide upload or free-form prose extraction.

## D-012 — macOS is development fallback, Linux remains the claim target

- **Status:** implemented with unverified Linux paths
- **Date:** 2026-10-01
- **Decision:** Local macOS runs explicitly record no isolation and use `sample` where permitted or an
  instrumented JSON profile. Linux uses `perf`; hardened Docker command construction is available.
- **Observed:** The full controlled fixture uses the instrumented fallback on macOS 26.5.2 arm64,
  Apple clang 21.0.0. `sample` command capture was smoke-tested, but macOS permissions prevented a
  useful busy-process call graph. Docker Desktop 29.3.1 was present and an official Python Linux
  image was pulled, but even a minimal `docker run` hung before a container appeared; it was
  interrupted and no Linux command result is claimed. Native Linux `perf` has not been run.
- **Limit:** Docker Desktop Linux is virtualized and cannot substitute for physical Linux performance
  validation or unrestricted hardware counters. The Docker invocation enforces CPU, memory, process,
  and wall-time controls, but the declared aggregate workspace disk-byte limit is not yet enforced;
  the runner must rely on a disposable VM/volume quota until that gate is implemented.

## D-013 — PerfBench truth stays separate from agent input

- **Status:** implemented; real cases unrun
- **Date:** 2026-10-01
- **Decision:** The public catalog contains only repository and exact pre-fix commit; the answer key
  stores the merged fix and is cryptographically locked to the public catalog bytes. Scoring requires
  one observation for every case and represents undefined rates as null.
- **Why:** This blocks accidental answer leakage through the runner and prevents omitted failures from
  improving rates.
- **Limit:** Public historical patches may be in model training data. Equivalent-fix recovery needs a
  blinded human judge and cannot establish decontamination.

## D-014 — Cross-machine comparison does not pool samples

- **Status:** implemented; no real cross-machine pair observed
- **Date:** 2026-10-01
- **Decision:** Runs are comparable only for the same repository commit and exact benchmark policy;
  candidates match by patch artifact SHA-256. Each machine retains its own effect, interval, and
  decision.
- **Why:** Pooling samples from different machines can conceal heterogeneity and violate pairing.
- **Limit:** Matching direction or overlapping intervals is descriptive, not a formal equivalence or
  portability test.

## D-015 — Provider boundary is explicit

- **Status:** implemented, live call unverified
- **Date:** 2026-10-01
- **Decision:** The real provider uses OpenAI Responses structured output; tests use a recorded
  provider with the same result contract. Source is never transmitted merely by validating a job.
- **Observed:** Recorded provider exercised end to end. No OpenAI API request has been made and no API
  latency, cost, or model quality result is claimed.

## D-016 — Milestone completion and Phase 1 validation are different

- **Status:** accepted
- **Date:** 2026-10-01
- **Decision:** Engineering milestones may be implemented and locally validated while the product
  exit remains open. PerfBench and design-partner outcomes cannot be replaced by fixtures.
- **Why:** Calling the package “Phase 1 proven” before independent use would weaken the central claim.
