# Phase 1 scope

## Claim

For a supported public C++/CMake repository with an existing benchmark and test suite, PerfPilot can
propose a source change and produce reproducible evidence about whether that change is faster without
breaking behavior exercised by the configured tests.

The words in that claim are intentional:

- **supported** means the repository satisfies the contract below; it does not imply arbitrary CMake
  compatibility;
- **public** avoids transmitting private source or secrets in Phase 1;
- **evidence** means raw observations and command output, not an LLM assertion;
- **whether** permits accepted, rejected, and inconclusive results;
- **configured tests** does not claim semantic equivalence or universal correctness.

## Supported repository contract

Phase 1 accepts a pinned 40-character Git commit for a public repository that:

1. builds on CPU-only Linux using CMake in a pinned runner image;
2. supplies an explicit configure, build, test, and benchmark recipe;
3. has no required interactive setup or secret credentials;
4. has an existing project benchmark, or a generated benchmark explicitly approved by its owner;
5. completes inside configured CPU, memory, process, disk, and wall-clock limits; and
6. permits its public source to be sent to the selected model provider.

## Phase 1 exit criteria

- A clean machine can reproduce both fixture paths.
- A broken baseline aborts before profiling or candidate generation.
- Every displayed numeric claim resolves to immutable raw evidence.
- A/A calibration distinguishes the environment's observed noise from the configured worthwhile
  effect threshold.
- Verification uses randomized paired blocks, at least 15 measured pairs, a predeclared maximum,
  bootstrap confidence intervals, and Holm correction across candidates.
- Six to eight blinded historical cases have complete, failure-inclusive records.
- Two to three maintainers or repository owners evaluate a report produced for an invited run.

These are targets until measured. `docs/METRICS.md` is the source of actual results.

## Explicit non-goals

- Opening or submitting pull requests.
- Claiming a patch is universally correct because configured tests passed.
- Claiming product support for Windows, macOS, GPUs, cross-compilation, or arbitrary build systems.
  macOS is a documented local-development fallback, not a Phase 1 performance target.
- Automatically trusting generated benchmarks.
- Running private repositories or mounting user credentials.
- A GitHub App, hosted multi-tenant service, or polished interactive report.
- Python support or multiple fully implemented LLM providers.
- Autonomous dependency upgrades or changes to public APIs.
- Publishing a repository ranking without maintainer consent.

Python, more providers, and product surfaces remain behind Phase 1 gates. A cross-machine comparator
exists, but a second-machine product reproduction has not occurred.
