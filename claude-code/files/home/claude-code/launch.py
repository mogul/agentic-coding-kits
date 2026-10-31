#!/usr/bin/env python3
"""Run Claude with a private proxy; each invocation owns only its own child."""

import json
import multiprocessing
import os
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
from contextlib import suppress
from pathlib import Path

from models import compose_settings, settings_argv
from provider import credential_names, load_provider


def serve(sock, facts, ids, token, ready):
    # Use the guest system trust bundle for the Python HTTPS client too.
    ca = Path("/etc/ssl/certs/ca-certificates.crt")
    if ca.is_file():
        os.environ.setdefault("SSL_CERT_FILE", str(ca))
        os.environ.setdefault("REQUESTS_CA_BUNDLE", str(ca))
    import uvicorn
    from proxy import make_app

    config = uvicorn.Config(make_app(facts, ids, token), log_level="critical", access_log=False, lifespan="off")
    server = uvicorn.Server(config)

    async def run():
        import asyncio

        task = asyncio.create_task(server.serve(sockets=[sock]))
        while not server.started and not task.done():
            await asyncio.sleep(0.02)
        if server.started:
            ready.send(True)
        await task

    import asyncio

    asyncio.run(run())


def claude_environment(facts, roles, port, token, keys=()):
    env = os.environ.copy()
    # Do not hand the actual upstream credential (or unrelated GitHub token)
    # to Claude. The proxy child alone uses the injected provider credential.
    for name in (
        *keys,
        facts["keyEnv"],
        "GITHUB_TOKEN",
        "USAI_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "CLAUDE_CODE_OAUTH_TOKEN",
        "CLAUDE_CODE_USE_BEDROCK",
        "CLAUDE_CODE_USE_VERTEX",
        "CLAUDE_CODE_USE_FOUNDRY",
    ):
        env.pop(name, None)
    env.update(
        ANTHROPIC_BASE_URL=f"http://127.0.0.1:{port}",
        ANTHROPIC_AUTH_TOKEN=token,
        ANTHROPIC_MODEL=roles["primary"],
        ANTHROPIC_DEFAULT_SONNET_MODEL=roles["primary"],
        ANTHROPIC_DEFAULT_HAIKU_MODEL=roles["small"],
        ANTHROPIC_DEFAULT_OPUS_MODEL=roles["opus"],
        CLAUDE_CODE_SUBAGENT_MODEL=roles["primary"],
        DISABLE_AUTOUPDATER="1",
        CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1",
        DISABLE_TELEMETRY="1",
        DISABLE_ERROR_REPORTING="1",
        DISABLE_NON_ESSENTIAL_MODEL_CALLS="1",
        MAX_THINKING_TOKENS="0",
        CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS="1",
        ENABLE_TOOL_SEARCH="false",
    )
    ca = Path("/etc/ssl/certs/ca-certificates.crt")
    if ca.is_file():
        env.setdefault("NODE_EXTRA_CA_CERTS", str(ca))
    return env


def run_session(binary, args):
    facts, ids, roles = load_provider()
    # Temporary settings are kit-owned and contain model metadata only. No
    # global Claude or Paseo config writer; discovery invocations use them too.
    with tempfile.TemporaryDirectory(prefix="acq-claude-models-") as directory:
        args, composed = compose_settings(args, ids, roles)
        settings = Path(directory) / "settings.json"
        settings.write_text(json.dumps(composed))
        settings.chmod(0o600)
        return run_configured_session(binary, settings_argv(args, settings), facts, ids, roles)


def run_configured_session(binary, args, facts, ids, roles):
    token = secrets.token_urlsafe(32)
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(128)
        worker = context.Process(target=serve, args=(sock, facts, ids, token, sender))
        worker.start()
        try:
            sender.close()
            if not receiver.poll(60) or not receiver.recv():
                raise ValueError("proxy did not become ready within 60 seconds")
            env = claude_environment(facts, roles, sock.getsockname()[1], token, credential_names(os.environ))
            # Trusted fixed binary; operator's CLI arguments are passed without a shell.
            terminal = sys.stdin.isatty()
            previous_group = os.tcgetpgrp(sys.stdin.fileno()) if terminal else None
            # Main launcher is single-threaded. Claim terminal in the child after
            # setpgid and BEFORE exec, eliminating the immediate-read SIGTTIN race.
            child = subprocess.Popen(  # noqa: S603 -- trusted binary, no shell
                [str(binary), *args],
                env=env,
                process_group=0,
                preexec_fn=claim_terminal if terminal else None,
            )
            try:
                return child.wait()
            finally:
                stop_group(child)
                if previous_group is not None:
                    foreground(previous_group)
        finally:
            receiver.close()
            worker.terminate()
            worker.join(10)
            if worker.is_alive():
                worker.kill()
                worker.join()


def foreground(group):
    previous = signal.signal(signal.SIGTTOU, signal.SIG_IGN)
    try:
        os.tcsetpgrp(sys.stdin.fileno(), group)
    finally:
        signal.signal(signal.SIGTTOU, previous)


def claim_terminal():
    foreground(os.getpgrp())


def stop_group(child):
    # Only this Claude invocation's process group, never another agent's tree.
    try:
        os.killpg(child.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    with suppress(subprocess.TimeoutExpired):
        child.wait(10)
    with suppress(ProcessLookupError):
        os.killpg(child.pid, signal.SIGKILL)
    child.wait()


def main():
    binary = Path.home() / ".local/share/acq/claude-code/claude"
    args = sys.argv[1:]
    if not binary.is_file():
        print("claude-code: installation not ready; check the kit startup install output", file=sys.stderr)
        return 1
    if args in (["--help"], ["-h"], ["--version"], ["-v"]):
        return subprocess.call([str(binary), *args])  # noqa: S603 -- fixed binary, allowlisted flags
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    signal.signal(signal.SIGHUP, lambda *_: sys.exit(129))
    try:
        return run_session(binary, args)
    except (ValueError, OSError, EOFError):
        print(
            "claude-code: not ready; verify installation, provider selection, and credential injection", file=sys.stderr
        )
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
