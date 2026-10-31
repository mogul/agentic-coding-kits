#!/usr/bin/env python3
"""Launch pinned Codex with per-invocation routing and persistent kit-owned state."""

import json
import os
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path

from bridge import start
from catalog import codex_catalog
from process import run as run_process
from provider import load


def environment(keys, state, token):
    env = os.environ.copy()
    for name in (*keys, "GITHUB_TOKEN", "USAI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "CODEX_API_KEY"):
        env.pop(name, None)
    # Prevent an inherited remote daemon or existing user's provider config
    # from bypassing the kit's explicit route.
    for name in list(env):
        if name.startswith("CODEX_") or name in ("OPENAI_BASE_URL", "PASEO_HOST"):
            env.pop(name)
    env.update(CODEX_HOME=str(state), ACQ_BRIDGE_TOKEN=token)
    return env


def check_args(args, ids):
    for index, argument in enumerate(args):
        if argument == "--":
            break
        if argument in (
            "--oss",
            "--local-provider",
            "--remote",
            "--remote-auth-token-env",
            "--profile",
            "-p",
            "--search",
        ):
            raise ValueError("alternate routing and native search are unsupported")
        if (
            argument.startswith(("--remote=", "--profile=", "--local-provider=", "--config=", "-c"))
            or argument == "--config"
        ):
            raise ValueError("raw configuration overrides are unsupported")
        if argument in ("-m", "--model") and (index + 1 == len(args) or args[index + 1] not in ids):
            raise ValueError("choose an exact configured model ID")
        if argument.startswith("--model=") and argument.split("=", 1)[1] not in ids:
            raise ValueError("choose an exact configured model ID")
        if argument.startswith("-m") and argument != "-m" and argument[2:] not in ids:
            raise ValueError("choose an exact configured model ID")


def run(binary, args):
    facts, models, primary, _, keys = load("CODEX")
    ids = [m["id"] for m in models]
    check_args(args, ids)
    state = Path.home() / ".local/state/acq/codex"
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    token = secrets.token_urlsafe(32)
    server = start(facts, ids, os.environ[facts["keyEnv"]], token)
    try:
        with tempfile.TemporaryDirectory(prefix="catalog-", dir=state) as directory:
            catalog = Path(directory) / "models.json"
            catalog.write_text(json.dumps(codex_catalog(models)))
            route = {
                "model": primary,
                "model_provider": "acq",
                "model_catalog_json": str(catalog),
                "model_providers.acq.name": "Configured acq provider",
                "model_providers.acq.base_url": f"http://127.0.0.1:{server.server_port}/v1",
                "model_providers.acq.env_key": "ACQ_BRIDGE_TOKEN",
                "model_providers.acq.wire_api": "responses",
                "model_providers.acq.request_max_retries": 0,
                "model_providers.acq.stream_max_retries": 0,
                "model_providers.acq.supports_websockets": False,
                "features.responses_websockets": False,
                "features.responses_websockets_v2": False,
                "features.apps": False,
                "features.code_mode": False,
                "analytics.enabled": False,
                "feedback.enabled": False,
                "web_search": "disabled",
            }
            config_args = [value for key, setting in route.items() for value in ("-c", key + "=" + json.dumps(setting))]
            return run_process([str(binary), *config_args, *args], environment(keys, state, token))
    finally:
        server.shutdown()
        server.server_close()


def main():
    binary = Path.home() / ".local/share/acq/codex/codex"
    args = sys.argv[1:]
    if not binary.is_file():
        print("codex-kit: installation not ready", file=sys.stderr)
        return 1
    if args in (["--help"], ["-h"], ["--version"], ["-V"]):
        return subprocess.call([str(binary), *args])  # noqa: S603 -- fixed binary, flags allowlist
    try:
        return run(binary, args)
    except (ValueError, OSError):
        print("codex-kit: verify provider input, credentials and supported CLI arguments", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
