# Golden workflow contract

This workflow is a state machine. A failed required transition produces evidence and stops; it does
not silently skip forward.

```text
job validated
  -> source acquired at exact commit
  -> sandbox policy applied
  -> clean configure and build
  -> baseline tests
       failure -> BASELINE_FAILED -> report and stop
       success -> benchmark reproduced
  -> A/A environment calibration
       excessive noise -> CALIBRATION_INCONCLUSIVE -> report and stop
       acceptable noise -> profile baseline
  -> rank hotspots
  -> generate bounded candidates
  -> for each isolated candidate:
       apply -> clean build -> configured tests -> randomized paired A/B
       -> reject / inconclusive / statistically accepted
  -> apply Holm correction across tested candidates
  -> render evidence bundle and review draft
  -> human review (always)
```

## Invariants

1. Source identity is a pinned commit and `dirty` is false.
2. The baseline and candidate use the same toolchain, flags, benchmark, resource policy, and host.
3. Candidate worktrees are isolated from one another and from the baseline.
4. Dependency acquisition, if permitted, is a separate recorded stage. Measurement has no network.
5. Every subprocess records arguments, working directory, start time, duration, result, stdout, and
   stderr. Shell interpretation is not used for repository commands.
6. Warmups are not included in measured samples.
7. A/B order is randomized within paired blocks from a recorded seed.
8. The sampling limit and statistical policy are fixed before candidate measurements begin.
9. Failed tests reject a candidate. Excessive noise or insufficient evidence is inconclusive.
10. The report distinguishes observed behavior, inference, and untested limitations.

## Fixture paths

`fixtures/cmake-healthy` must configure, build, pass CTest, and emit parseable benchmark JSON. Its
benchmark exists to validate plumbing and must never be presented as performance evidence.

`fixtures/cmake-broken-baseline` must configure and build, then fail CTest deliberately. A future
runner must assign `baseline_failed`, preserve the output, and never run its benchmark or proposal
stage.
