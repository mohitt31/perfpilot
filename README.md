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
