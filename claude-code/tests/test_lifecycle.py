"""Real launcher lifecycle checks with synthetic credentials and no upstream calls."""

import json
import os
import signal
import subprocess
import sys
import time
from contextlib import suppress
from pathlib import Path

import pytest

PAYLOAD = Path(__file__).resolve().parents[1] / "files/home/claude-code"
PYTHON = Path(sys.executable)
pytestmark = pytest.mark.skipif(not Path("/proc/self/stat").exists(), reason="Linux process inspection required")

FAKE_CLAUDE = """import json
import os
import subprocess
import sys
import time
from pathlib import Path

# An ordinary tool descendant, deliberately requiring process-group escalation.
tool = subprocess.Popen([
    sys.executable, "-c",
    "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); print('ready', flush=True); time.sleep(300)",
], stdout=subprocess.PIPE, text=True)
assert tool.stdout.readline().strip() == "ready"
if sys.stdin.isatty():
    # Immediate read must not stop on SIGTTIN before foreground handoff.
    assert sys.stdin.readline().strip() == "terminal-ready"
names = (
    "FIRST_MODEL_KEY", "SECOND_MODEL_KEY", "GITHUB_TOKEN", "USAI_API_KEY",
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN",
    "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "ANTHROPIC_MODEL",
)
record = {
    "claude": os.getpid(), "tool": tool.pid, "group": os.getpgrp(),
    "foreground": os.tcgetpgrp(0) if sys.stdin.isatty() else None,
    "environment": {name: os.environ[name] for name in names if name in os.environ},
}
target = Path(os.environ["TEST_CLAUDE_RECORD"])
pending = target.with_suffix(".pending")
pending.write_text(json.dumps(record))
pending.replace(target)
tool.wait()
"""


def running(pid):
    """Zombies have exited; PID existence alone does not mean a leaked process."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except FileNotFoundError:
        return False
    return stat.rsplit(")", 1)[1].split()[0] not in {"Z", "X"}


def wait_until(predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def direct_children(pid):
    return {int(value) for value in Path(f"/proc/{pid}/task/{pid}/children").read_text().split()}


def provider_inputs(root, provider_id, key):
    directory = root / "models/providers" / provider_id
    directory.mkdir(parents=True)
    facts = {
        "schemaVersion": "acq-provider-facts/v1",
        "providerId": provider_id,
        "apiProtocol": "openai-compatible",
        "host": "example.invalid",
        "baseUrl": "https://example.invalid/v1",
        "keyEnv": key,
    }
    snapshot = {
        "schemaVersion": "acq-neutral-model-catalog/v1",
        "providerId": provider_id,
        "models": [{"id": "model-a"}],
        "recommendations": {"primary": "model-a"},
    }
    for name, data in (("facts.json", facts), ("snapshot.json", snapshot)):
        path = directory / name
        path.write_text(json.dumps(data))
        path.chmod(0o444)


def controlling_terminal():
    """Give the wrapper a real controlling terminal without changing the runner."""
    import fcntl
    import termios

    os.setsid()
    fcntl.ioctl(0, termios.TIOCSCTTY, 0)


@pytest.fixture
def session(tmp_path):
    assert PYTHON.is_file(), f"provisioned kit interpreter required: {PYTHON}"
    home = tmp_path / "home"
    binary = home / ".local/share/acq/claude-code/claude"
    binary.parent.mkdir(parents=True)
    binary.write_text(f"#!{PYTHON}\n" + FAKE_CLAUDE)
    binary.chmod(0o755)
    root = tmp_path / "inputs"
    provider_inputs(root, "first", "FIRST_MODEL_KEY")
    provider_inputs(root, "second", "SECOND_MODEL_KEY")
    record = tmp_path / "claude.json"
    env = {
        "HOME": str(home),
        "PATH": f"{PYTHON.parent}:/usr/bin:/bin",
        "LC_ALL": "C.UTF-8",
        "PYTHONUNBUFFERED": "1",
        "ACQ_PROVIDER_INPUT_ROOT": str(root),
        "ACQ_CLAUDE_PROVIDER": "first",
        "TEST_CLAUDE_RECORD": str(record),
        **{
            name: "synthetic-" + name.lower()
            for name in (
                "FIRST_MODEL_KEY",
                "SECOND_MODEL_KEY",
                "GITHUB_TOKEN",
                "USAI_API_KEY",
                "OPENAI_API_KEY",
                "ANTHROPIC_API_KEY",
                "CLAUDE_CODE_OAUTH_TOKEN",
            )
        },
    }
    # Only explicit synthetic entries reach either the wrapper or its proxy.
    yield tmp_path, record, env


@pytest.fixture
def launched(session, request):
    import pty

    tmp_path, record, env = session
    terminal = getattr(request, "param", False)
    master, slave = pty.openpty() if terminal else (None, None)
    descendants = set()
    with (tmp_path / "launcher.log").open("w+") as output:
        wrapper = subprocess.Popen(  # noqa: S603 -- fixed local interpreter and launcher
            [str(PYTHON), str(PAYLOAD / "launch.py")],
            cwd=tmp_path,
            env=env,
            stdin=slave if terminal else subprocess.DEVNULL,
            stdout=output,
            stderr=output,
            start_new_session=not terminal,
            preexec_fn=controlling_terminal if terminal else None,
        )
        try:
            if master is not None:
                os.write(master, b"terminal-ready\n")
            assert wait_until(lambda: record.exists() or wrapper.poll() is not None, 75)
            output.seek(0)
            assert record.exists(), output.read()
            data = json.loads(record.read_text())
            descendants = direct_children(wrapper.pid) | {data["claude"], data["tool"]}
            proxies = [
                pid
                for pid in descendants
                if pid != data["tool"] and b"spawn_main" in Path(f"/proc/{pid}/cmdline").read_bytes()
            ]
            assert len(proxies) == 1, "real multiprocessing proxy must be running"
            assert all(running(pid) for pid in descendants)
            yield wrapper, data, descendants, output
        finally:
            # Failure cleanup is scoped to this wrapper and the PIDs it created.
            if record.exists():
                data = json.loads(record.read_text())
                with suppress(ProcessLookupError):
                    os.killpg(data["group"], signal.SIGKILL)
            if wrapper.poll() is None:
                descendants.update(direct_children(wrapper.pid))
                wrapper.kill()
            wrapper.wait(timeout=15)
            for pid in descendants:
                if running(pid):
                    with suppress(ProcessLookupError):
                        os.kill(pid, signal.SIGKILL)
            for fd in (master, slave):
                if fd is not None:
                    os.close(fd)


@pytest.mark.parametrize("launched", [False, True], indirect=True, ids=["pipe", "terminal"])
@pytest.mark.parametrize("signum, expected", [(signal.SIGHUP, 129), (signal.SIGTERM, 143)])
def test_targeted_signal_reaps_claude_proxy_and_tool(launched, signum, expected):
    wrapper, data, descendants, output = launched
    assert data["group"] == data["claude"]
    assert data["group"] != wrapper.pid
    if data["foreground"] is not None:
        assert data["foreground"] == data["group"]
    # Signal only main, not the wrapper's group or any of its descendants.
    os.kill(wrapper.pid, signum)
    code = wrapper.wait(timeout=25)
    output.seek(0)
    assert code == expected, output.read()
    assert wait_until(lambda: not any(running(pid) for pid in descendants)), (
        f"launcher leaked descendants: {[pid for pid in descendants if running(pid)]}"
    )


def test_two_provider_credentials_are_not_inherited_by_claude(launched):
    wrapper, data, descendants, output = launched
    env = data["environment"]
    assert not set(env).intersection(
        {
            "FIRST_MODEL_KEY",
            "SECOND_MODEL_KEY",
            "GITHUB_TOKEN",
            "USAI_API_KEY",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "CLAUDE_CODE_OAUTH_TOKEN",
        }
    )
    assert env["ANTHROPIC_AUTH_TOKEN"] and not env["ANTHROPIC_AUTH_TOKEN"].startswith("synthetic-")
    assert env["ANTHROPIC_BASE_URL"].startswith("http://127.0.0.1:")
    assert env["ANTHROPIC_MODEL"] == "model-a"
    os.kill(wrapper.pid, signal.SIGTERM)
    output.seek(0)
    assert wrapper.wait(timeout=25) == 143, output.read()
    assert wait_until(lambda: not any(running(pid) for pid in descendants))
