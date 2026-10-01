# Recommended Linux validation runner

This setup has **not** been run on a native Linux host. Commands are a reproducible starting point,
not an observed result. Prefer a dedicated bare-metal machine; otherwise use a VM with four dedicated
host-passthrough x86_64 vCPUs, 16 GiB RAM, 80 GiB SSD, Ubuntu Server 24.04 LTS, no valuable
credentials, and no CPU overcommit. Do not use a shared CI runner for final timing claims.

## Base tools

```bash
sudo apt update
sudo apt install -y build-essential clang cmake ninja-build git python3.12 python3.12-venv \
  linux-tools-common linux-tools-generic cpufrequtils jq libcap2-bin
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
```

Install Docker Engine from Docker's official Ubuntu repository, not the convenience script. The
current authoritative commands are in [Docker's Ubuntu installation
guide](https://docs.docker.com/engine/install/ubuntu/). Install `docker-ce`, `docker-ce-cli`,
`containerd.io`, `docker-buildx-plugin`, and `docker-compose-plugin`, then record exact versions.
Membership in the `docker` group is root-equivalent; use `sudo`, a password-gated group shell, or a
dedicated runner account rather than granting a personal account permanent access. Docker documents
that risk in its [post-install guide](https://docs.docker.com/engine/install/linux-postinstall).

## CPU and noise controls

Run on AC power. Stop unrelated services, record the full VM/host topology, and use the performance
governor where the driver supports it:

```bash
sudo cpupower frequency-info
sudo cpupower frequency-set --governor performance
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
lscpu
free -b
uname -a
```

Pin the benchmark process to one dedicated physical core with `taskset`; do not select sibling SMT
threads for competing work. Record turbo/boost state rather than silently changing it. Let the system
reach thermal steady state, avoid swap pressure, and rerun A/A calibration after any host change.

## `perf` permissions

First verify the kernel-matched binary:

```bash
perf --version
perf stat -- true
cat /proc/sys/kernel/perf_event_paranoid
```

The Linux kernel recommends `CAP_PERFMON` as the least-privilege capability for performance
monitoring. In a disposable dedicated VM, grant only the needed capability to the resolved `perf`
binary and verify it survived upgrades:

```bash
perf_path=$(readlink -f "$(command -v perf)")
sudo setcap cap_perfmon=ep "$perf_path"
getcap "$perf_path"
```

On Linux 5.9+, `CAP_SYS_PTRACE` is generally unnecessary. Add no capability unless an observed denial
justifies it. Do not set `perf_event_paranoid=-1` on a shared host. The kernel documents both the
data-leak risk and the meanings of the setting in [Perf events and tool
security](https://docs.kernel.org/6.2/admin-guide/perf-security.html).

For container profiling, pass only `--cap-add PERFMON` if the runtime/kernel supports it; never use
`--privileged`. PerfPilot's default hardened measurement container drops all capabilities, so
profiling and measurement may need separate policies.

## Acceptance audit

```bash
.venv/bin/ruff check src tests
.venv/bin/mypy src/perfpilot
.venv/bin/pytest
.venv/bin/perfpilot perfbench-validate \
  perfbench/public/cases-v1.json perfbench/private/answers-v1.json
```

Record exact command output, Docker image digest, compiler/CMake versions, CPU governor, affinity,
kernel, and every failure. A Docker Desktop Linux container on macOS is useful portability testing,
but it is not the native Linux performance runner described here.
