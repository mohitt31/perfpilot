# Design-partner protocol

Phase 1 needs two or three maintainers or performance owners who have agreed to a run on a real
repository. An invitation is not a success observation, and a fixture or PerfBench case is not a
design partner.

## Before source or commands are run

1. Record the partner, repository, maintainer role, date, and an explicit invitation or consent.
2. Agree on the pinned commit, existing benchmark workload, test command, acceptable machine, source
   and artifact retention, and whether any source may be sent to a model provider.
3. Predeclare the statistical policy, minimum worthwhile effect, pair cap, expected resource cost,
   and stop conditions. Establish who pays any cloud or model cost.
4. Explain that local execution is unsandboxed, Docker isolation is defense-in-depth rather than a
   complete boundary, test passage covers only tested behavior, and an inconclusive result is valid.

## Run and review

- Preserve the exact job file, commit, environment, commands, raw timing, profile, prompt/response,
  patches, tests, and statistics in a validated evidence bundle.
- Send the static report and patch only to the consenting reviewer. Do not describe a candidate as
  “correct”; say which commands passed and which risks remain untested.
- Ask the reviewer to score usefulness, evidence clarity, correctness risk, setup burden, and whether
  they would request another run. Record criticism verbatim where consent permits.

## External-action gate

PerfPilot has no PR-writing integration. Before any manual upstream submission: the maintainer has
invited it, Mohit has reviewed the exact diff and evidence, repository contribution rules have been
checked, the PR discloses AI assistance, and limitations/inconclusive evidence are retained. A
review-ready result is not authorization to submit.

## Observation record

Use one record per invited run:

```text
partner_id: pseudonymous identifier
repository_url:
invitation_evidence_location:
consented_at:
source_to_provider_policy: none | bounded_context_approved
job_sha256:
bundle_run_id:
bundle_location:
reviewer_role:
active_review_minutes:
useful: yes | no | mixed
would_run_again: yes | no | unsure
review_notes:
external_submission: none | manually_submitted_after_gate
```

Blank fields mean not measured. Do not infer missing sentiment or assign a monetary value to local
hardware time.
