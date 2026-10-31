"""Bounded ownership of one CLI process group and its terminal."""

import os
import signal
import subprocess
import sys
from contextlib import suppress


def foreground(group):
    previous = signal.signal(signal.SIGTTOU, signal.SIG_IGN)
    try:
        os.tcsetpgrp(sys.stdin.fileno(), group)
    finally:
        signal.signal(signal.SIGTTOU, previous)


def claim_terminal():
    foreground(os.getpgrp())


def run(argv, env):
    terminal = sys.stdin.isatty()
    previous_group = os.tcgetpgrp(sys.stdin.fileno()) if terminal else None
    child = subprocess.Popen([sys.executable, __file__, *argv], env=env, process_group=0)  # noqa: S603 -- fixed helper, trusted CLI argv

    def interrupted(signum, _):
        raise InterruptedError(signum)

    handlers = {s: signal.signal(s, interrupted) for s in (signal.SIGTERM, signal.SIGHUP)}
    try:
        return child.wait()
    except InterruptedError as error:
        return 128 + error.args[0]
    except KeyboardInterrupt:
        return 130
    finally:
        # Cleanup cannot be interrupted by repeated supervisor/terminal signals.
        protected = {s: signal.signal(s, signal.SIG_IGN) for s in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT)}
        with suppress(ProcessLookupError):
            os.killpg(child.pid, signal.SIGTERM)
        with suppress(subprocess.TimeoutExpired):
            child.wait(3)
        with suppress(ProcessLookupError):
            os.killpg(child.pid, signal.SIGKILL)
        child.wait()
        if previous_group is not None:
            foreground(previous_group)
        for signum in protected:
            signal.signal(signum, handlers.get(signum, protected[signum]))


if __name__ == "__main__":
    if sys.stdin.isatty():
        claim_terminal()
    os.execvpe(sys.argv[1], sys.argv[1:], os.environ)  # noqa: S606 -- pinned CLI, argv only
