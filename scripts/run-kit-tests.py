#!/usr/bin/env python3
"""Dispatch a named root kit's tests; sandbox/live verification is always disabled."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

KIT_NAMES = ("opencode-go-provider", "pi-coding-agent", "first-mate-skill", "claude-code", "codex", "antigravity")


def test_commands(root: Path, name: str, *, install: bool = False) -> tuple[Path, list[list[str]]]:
    if name not in KIT_NAMES:
        raise ValueError(f"unknown kit: {name}")
    kit = root / name
    if not kit.is_dir() or kit.is_symlink() or not (kit / "spec.yaml").is_file():
        raise ValueError(f"kit must be an actual root directory with spec.yaml: {kit}")
    if name in ("opencode-go-provider", "pi-coding-agent"):
        commands = [["npm", "test"]]
        if install:
            commands.insert(0, ["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"])
        if name == "pi-coding-agent":
            commands.append(["bash", "scripts/verify"])
    elif name == "first-mate-skill":
        commands = [["bash", "scripts/verify"]]
    else:
        # The kit owns its isolated, hash-locked runtime test environment.
        commands = [[sys.executable, "scripts/test"]]
    return kit, commands


def run_tests(root: Path, name: str, *, install: bool = False) -> None:
    kit, commands = test_commands(root, name, install=install)
    environment = dict(os.environ, RUN_ACQ="0", RUN_LIVE="0", RUN_CLAUDE_LIVE="0", PYTHON_BIN=sys.executable)
    for command in commands:
        executable = shutil.which(command[0])
        if executable is None:
            raise ValueError(f"required test executable not found: {command[0]}")
        subprocess.run([executable, *command[1:]], cwd=kit, env=environment, check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kit", choices=(*KIT_NAMES, "all"))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--install", action="store_true", help="install Node dependencies with lifecycle scripts disabled"
    )
    args = parser.parse_args(argv)
    try:
        for name in KIT_NAMES if args.kit == "all" else (args.kit,):
            run_tests(args.root.resolve(), name, install=args.install)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"kit tests failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
