# Phase 1 engineering review

## Milestones and exit status

1. **Contracts:** complete. Strict job/evidence schemas, integrity validation, threat model, workflow,
   healthy fixture, and broken-baseline fixture are tested.
2. **Ingestion:** complete for the local backend. Exact detached commit, clean-tree check, clean CMake
   configure/build/test, captured commands, and terminal baseline abort are tested.
3. **Benchmarking:** complete for declared JSON-emitting commands. Generic and Google Benchmark JSON
   parsing and immutable raw output capture are tested on the fixture.
4. **Profiling:** portable implementation complete. Instrumented JSON is validated end to end on
   macOS; macOS `sample` capture received a smoke test but not a useful call graph; Linux `perf` is
   implemented and parser-tested but not run on native Linux.
5. **Proposals:** complete at the interface. Serialized context respects the configured byte limit;
   recorded structured responses run end to end. The OpenAI Responses adapter is implemented but has
   made no live request.
6. **Correctness gates:** complete. Each candidate gets an isolated worktree, patch safety checks,
   clean build, configured tests, and protected test/benchmark path checks. Tests cover a passing and
   a compile-failing patch.
7. **Statistics:** complete for the predeclared protocol. Tests cover A/A gating, randomized paired
   order, exact/Monte Carlo sign permutation, BCa and degenerate intervals, Holm correction, accepted,
   rejected, and inconclusive classification.
8. **Reporting:** complete. Markdown reports and manual PR drafts are derived from validated bundles,
   preserve exact numeric representations, list commands, and state limitations and AI assistance.
9. **PerfBench:** catalog/scorer complete; external evaluation incomplete. Eight cases are selected,
   public inputs are separated from the hash-locked answer key, and zero-denominator rates are null.
   All eight cases are still unrun.
10. **Design partners/reproduction:** tooling complete; external evidence incomplete. The consent and
    review protocol and non-pooling cross-machine comparator are tested. No partner or second-machine
    product run exists.
11. **Packaging:** complete as an engineering release. Documentation, Linux setup, founder material,
    CI, full tests, and a controlled evidence bundle are included. Phase 1's product exit is not met
    until real PerfBench and invited partner runs finish.

The observed macOS host unexpectedly exposed Docker Desktop 29.3.1 despite the initial environment
assumption. Pulling `python:3.12-bookworm` completed at digest
`sha256:dbbe4ceb97851e2e5fa83798b239811f871cb743b259ba3563737349f6bcfaa0`, but both the full
audit container and a minimal `python --version` container hung before any container appeared in
`docker ps`; both were interrupted. Therefore no Docker/Linux execution result is counted.

## Defensible boundary

The strongest accurate statement is: PerfPilot's end-to-end evidence machinery works on a controlled
C++/CMake fixture on the recorded macOS host. It has not yet shown that it can recover a useful
optimization in an unseen real repository, satisfy a maintainer, reproduce an effect on physical
Linux, or operate its real model provider. Those are the next experiments, not documentation tasks.
