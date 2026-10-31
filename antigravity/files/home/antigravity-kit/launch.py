#!/usr/bin/env python3
"""Run agy against an invocation-owned bridge and kit-owned persistent home."""

import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

from bridge import start
from process import run as run_process
from provider import load


def run(binary, args):
    facts, models, primary, small, keys = load()
    ids = [m["id"] for m in models]
    if args == ["models"]:
        for model in models:
            print(model["id"] + "\t" + model["id"])
        return 0
    for index, argument in enumerate(args):
        if argument == "--":
            break
        if argument in ("--settings", "--remote-control", "--effort") or argument.startswith(
            ("--settings=", "--effort=")
        ):
            raise ValueError("alternate settings or remote control are unsupported")
        if argument == "--model" and (index + 1 == len(args) or args[index + 1] not in ids):
            raise ValueError("choose an exact configured model ID")
        if argument.startswith("--model=") and argument.split("=", 1)[1] not in ids:
            raise ValueError("choose an exact configured model ID")
    state = Path.home() / ".local/state/acq/antigravity"
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    token = secrets.token_urlsafe(32)
    server = start(facts, ids, os.environ[facts["keyEnv"]], token, small)
    env = os.environ.copy()
    for name in (*keys, "GITHUB_TOKEN", "USAI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
        env.pop(name, None)
    env.update(
        HOME=str(state),
        XDG_CONFIG_HOME=str(state / ".config"),
        XDG_CACHE_HOME=str(state / ".cache"),
        XDG_DATA_HOME=str(state / ".local/share"),
        GEMINI_API_KEY=token,
        GOOGLE_GEMINI_BASE_URL=f"http://127.0.0.1:{server.server_port}",
    )
    settings = {
        "modelProvider": "gemini",
        "customModelsConfig": {"customModels": {value: {"modelName": value, "apiProvider": "gemini"} for value in ids}},
    }
    try:
        return run_process([str(binary), "--settings", json.dumps(settings), "--model", primary, *args], env)
    finally:
        server.shutdown()
        server.server_close()


def main():
    binary = Path.home() / ".local/share/acq/antigravity/agy"
    args = sys.argv[1:]
    if not binary.is_file():
        print("antigravity-kit: installation not ready", file=sys.stderr)
        return 1
    if args in (["--help"], ["-h"], ["--version"]):
        return subprocess.call([str(binary), *args])  # noqa: S603 -- pinned binary, flags allowlist
    try:
        return run(binary, args)
    except (ValueError, OSError):
        print("antigravity-kit: verify provider input, credentials and supported arguments", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
