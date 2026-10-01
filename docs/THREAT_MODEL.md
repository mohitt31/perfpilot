# Threat model

## Assets to protect

- Host credentials, SSH agents, cloud tokens, browser data, and Docker control socket.
- Host filesystem and other projects.
- Availability of the host and CI runner.
- Integrity of source commits, raw timings, patches, logs, and reports.
- Maintainer trust and the confidentiality rules of future design partners.

## Adversaries and failure sources

PerfPilot assumes repository-controlled configure, build, test, and benchmark steps are arbitrary
code. A repository may be malicious, compromised, or merely buggy. Model output is also untrusted.
The host OS, container runtime, base image, package registries, compiler, and model provider remain
supply-chain dependencies. No benchmark host should be assumed perfectly quiet.

## Phase 1 controls

- Run only public repositories at exact commits in disposable workspaces.
- Never mount credentials, SSH agents, the host source tree, or the Docker socket.
- Run as a non-root container user with no added capabilities and `no-new-privileges`.
- Apply CPU, memory, process, and wall-clock limits. Use a disposable VM/volume quota for aggregate
  disk usage until the Docker executor enforces its declared `disk_bytes` value.
- Use a pinned runner image digest and record toolchain identity.
- Separate dependency acquisition from execution; disable network during build, test, profiling, and
  measurement wherever the repository contract permits it.
- Pass commands as argument arrays, not through a shell.
- Treat patches and model text as data until they enter a disposable candidate worktree.
- Hash every evidence artifact and reject bundles whose contents no longer match the manifest.
- Store no secrets in prompts, logs, bundles, or reports.

## Trust boundaries and residual risks

A container is risk reduction, not a strong security boundary. A kernel or runtime vulnerability can
escape it. Public package downloads can be compromised. Resource limits cannot prevent every denial
of service. A public repository may still contain data its maintainers did not intend to send to an
LLM. Timing results can be biased by firmware, hardware, thermal state, or unrelated host activity.
Artifact hashes detect later modification but do not prove that the original observation was honest.

Consequently, Phase 1 must run on a dedicated, non-privileged machine or disposable VM with no
valuable credentials. It must not execute untrusted repositories on a personal workstation merely
because Docker is installed.

## Out of scope in Phase 1

- Defending against container or kernel zero-days.
- Private source, secrets, proprietary datasets, or production traces.
- Multi-tenant isolation.
- Verifying package-registry or compiler correctness.
- Cryptographic attestation or signed provenance.
- Legal conclusions about repository licenses or model-provider terms.

Before private or on-prem use, this threat model must be revisited with the design partner's security
requirements.
