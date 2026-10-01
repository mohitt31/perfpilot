# Roadmap, milestone status, and gates

“Implemented” means code and local engineering validation exist. It does not mean the product claim
has been validated on a real repository or by a maintainer.

| Milestone | Deliverable | Status on 2026-10-01 |
|---:|---|---|
| 1 | Contracts, threat model, strict evidence schema, fixtures | Implemented; schema and integrity tests pass on macOS |
| 2 | Exact clone, clean CMake build/test, broken-baseline abort | Implemented; both fixture paths pass on macOS |
| 3 | Existing benchmark execution and raw capture | Implemented; controlled fixture run only |
| 4 | Source-mapped profiling | Linux `perf`, macOS `sample`, and instrumented fallback implemented; instrumented fixture validated, `perf` not run on native Linux |
| 5 | Byte-bounded structured proposal generation | Recorded and OpenAI Responses providers implemented; recorded provider validated, no live OpenAI request made |
| 6 | Isolated apply/build/test correctness gates | Implemented; valid and invalid fixture patches tested |
| 7 | A/A and randomized paired A/B statistics | Implemented; controlled positive, noise-stop, rejection, and correction paths tested |
| 8 | Evidence report and manual PR draft | Implemented and derived only from validated bundles |
| 9 | Six-to-eight blinded PerfBench cases | Eight cases predeclared and answer-key locked; contracts/scoring validated; all real cases remain unrun |
| 10 | Design partners and cross-machine reproduction | Protocol and comparator implemented; zero partner runs and zero second-machine product reproductions |
| 11 | Phase 1 release, audit, and founder material | Engineering package complete; product exit gate remains open pending Milestones 9–10 external evidence |

## Phase 1 gate still to clear

1. Validate recipes and execute all eight predeclared PerfBench cases on the target native Linux
   runner, retaining every setup failure and miss.
2. Complete two or three invited runs with independent maintainers or performance owners.
3. Reproduce selected exact patches on a second physical machine without pooling measurements.
4. Resolve failures, rerun the complete audit, and only then describe Phase 1 as product-validated.

## Phase 2 — evidence-led expansion

Only after the Phase 1 gate closes: harden the C++ adapter against observed failures, expand the
blinded suite by failure category, add Python plus one existing benchmark ecosystem, conduct more
invited runs, and manually submit only maintainer-welcomed, human-approved patches. Add sanitizer,
numerical, memory, binary-size, and workload-regression checks where the observed repositories need
them. Cross-machine variation is reported, never erased through favorable pooling.

## Phase 3 — product

Choose a GitHub App or on-prem runner only after partners demonstrate repeated-run demand. Candidate
work includes signed provenance, policy controls, comparison history, cost/latency impact, a polished
web report, production-trace adapters, and enterprise security. Product convenience may not weaken
the evidence gate, human review, prior maintainer contact, or AI disclosure.
