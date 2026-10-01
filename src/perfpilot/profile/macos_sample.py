"""Launch a process and attach macOS `sample` without invoking a shell."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--duration", type=int, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("a target command is required after --")

    target = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    sampler = subprocess.run(
        [
            "/usr/bin/sample",
            str(target.pid),
            str(args.duration),
            "1",
            "-mayDie",
            "-fullPaths",
            "-file",
            str(args.output),
        ],
        check=False,
        capture_output=True,
    )
    target_stdout, target_stderr = target.communicate()
    sys.stdout.buffer.write(target_stdout)
    sys.stderr.buffer.write(target_stderr)
    sys.stderr.buffer.write(sampler.stderr)
    if target.returncode != 0:
        return target.returncode
    return sampler.returncode


if __name__ == "__main__":
    raise SystemExit(main())

