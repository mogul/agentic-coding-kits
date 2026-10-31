import subprocess
import sys
import unittest
from pathlib import Path


class LifecycleTests(unittest.TestCase):
    def test_stdin_stdout_forwarding(self):
        helper = Path(__file__).resolve().parents[1] / "files/home/antigravity-kit/process.py"
        code = (
            "import importlib.util,os,sys;"
            f"s=importlib.util.spec_from_file_location('owned',{str(helper)!r});"
            "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
            "sys.exit(m.run([sys.executable,'-c','import sys;print(sys.stdin.read())'],os.environ.copy()))"
        )
        result = subprocess.run(
            [sys.executable, "-c", code], input="FORWARDED", text=True, capture_output=True, timeout=10
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "FORWARDED")
