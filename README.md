# PerfPilot

PerfPilot is an evidence-first performance optimization agent. Given a supported C++/CMake
repository, an exact commit, explicit commands, and an existing benchmark, it creates an auditable
answer to a narrow question: did this candidate improve the recorded workload on this machine while
the configured tests still passed?

It does not equate passing tests with correctness, generalize one machine to all machines, hide
inconclusive results, or open pull requests.

## Implemented pipeline

```text
pin source -> clean build/test -> reproduce benchmark -> A/A calibration -> profile
-> bounded structured proposals -> isolated clean build/test -> randomized paired A/B
-> bootstrap interval + paired permutation test + Holm correction -> evidence report
```

The versioned evidence bundle stores exact commands and environment metadata and hashes every raw
artifact. `perfpilot validate-bundle` checks internal integrity; hashes do not prove the experiment
was valid or honestly conducted.

macOS supports local development with an explicitly unsandboxed local executor and instrumented JSON
profiling fallback. The committed Phase 1 target remains a disposable Linux runner. The hardened
Docker invocation and Linux `perf` backend are implemented but have not yet been exercised on a
native Linux host; see [docs/LINUX_SETUP.md](docs/LINUX_SETUP.md).

## Development and fixture validation

Python 3.12+, CMake, a C++ compiler, and Git are required.

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/ruff check src tests
.venv/bin/mypy src/perfpilot
.venv/bin/pytest
```

Run the controlled fixture end to end (the command creates and pins an ephemeral Git repository):

```bash
perfpilot fixture-run --output work/fixture-evidence
perfpilot validate-bundle work/fixture-evidence
perfpilot report work/fixture-evidence
```

The fixture deliberately contains a removable useless load so the verifier can exercise an accepted
path. Its measurements are engineering validation, not product evidence.

Other commands:

```bash
perfpilot schema
perfpilot validate-job JOB.json
perfpilot perfbench-validate perfbench/public/cases-v1.json perfbench/private/answers-v1.json
perfpilot perfbench-score PUBLIC.json ANSWERS.json OBSERVATIONS.json -o score.json
perfpilot compare-runs FIRST_BUNDLE SECOND_BUNDLE -o comparison.json
```

Start with [docs/SCOPE.md](docs/SCOPE.md), [docs/DESIGN.md](docs/DESIGN.md), and
[docs/METRICS.md](docs/METRICS.md). No Phase 1 product outcome or design-partner result has yet been
measured.

## How this was built

PerfPilot was built with AI coding assistance. Mohit designed the product scope, evidence standard,
and statistical protocol, and reviewed every claim. AI-generated changes and proposals are treated
as untrusted until they have been inspected and supported by recorded evidence.

What has actually been run and observed:

- The end-to-end evidence workflow ran on a controlled C++/CMake fixture on macOS.
- Local ingestion, baseline checks, JSON benchmark capture, correctness gates, statistics, reporting,
  and the recorded-response proposal path were exercised in tests or fixture runs.
- Instrumented JSON profiling was validated end to end on macOS. The macOS `sample` backend received
  a smoke test, but it did not produce a useful call graph.
- Docker Desktop pulled the pinned Linux image, but both attempted containers hung before appearing
  in `docker ps`; this is not counted as a Docker or Linux execution result.

What has not yet been run or demonstrated:

- The Linux `perf` backend has not run on a native Linux host.
- The OpenAI Responses adapter has not made a live request.
- None of the eight blinded PerfBench cases has been run.
- There has been no invited design-partner run or second-machine product reproduction.
- PerfPilot has not yet demonstrated a useful optimization in an unseen real repository or earned a
  maintainer's approval.

Tests and controlled fixtures are engineering validation, not product results. The detailed,
claim-by-claim boundary is recorded in [docs/PHASE1_REVIEW.md](docs/PHASE1_REVIEW.md).
