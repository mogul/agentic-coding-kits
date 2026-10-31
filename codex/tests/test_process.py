import json
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class LifecycleTests(unittest.TestCase):
    def test_wrapper_only_signals_kill_uncooperative_descendants(self):
        helper = Path(__file__).resolve().parents[1] / "files/home/codex-kit/process.py"
        for signum in (signal.SIGTERM, signal.SIGHUP):
            with self.subTest(signal=signum), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                child_code = "import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(60)"
                parent_code = (
                    "import subprocess,signal,time,os,json;from pathlib import Path;"
                    "signal.signal(signal.SIGTERM,signal.SIG_IGN);"
                    f"child=subprocess.Popen([{sys.executable!r},'-c',{child_code!r}]);"
                    f"Path({str(root / 'pids')!r}).write_text(json.dumps([os.getpid(),child.pid]));time.sleep(60)"
                )
                code = (
                    "import importlib.util,os,sys;"
                    f"s=importlib.util.spec_from_file_location('owned',{str(helper)!r});"
                    "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
                    f"sys.exit(m.run([{sys.executable!r},'-c',{parent_code!r}],os.environ.copy()))"
                )
                wrapper = subprocess.Popen([sys.executable, "-c", code], stdin=subprocess.DEVNULL)
                try:
                    import time

                    deadline = time.monotonic() + 10
                    while not (root / "pids").exists():
                        if time.monotonic() > deadline:
                            self.fail("child did not initialize")
                        time.sleep(0.02)
                    pids = json.loads((root / "pids").read_text())
                    wrapper.send_signal(signum)
                    time.sleep(0.1)
                    wrapper.send_signal(signum)
                    self.assertEqual(wrapper.wait(8), 128 + signum)
                    for pid in pids:
                        status = Path(f"/proc/{pid}/stat")
                        self.assertTrue(not status.exists() or status.read_text().split()[2] == "Z")
                finally:
                    if wrapper.poll() is None:
                        wrapper.kill()
                        wrapper.wait()
