#!/usr/bin/env python3
"""Offline tests for the First Mate detector (first-mate-check.py) and wait loop (first-mate-wait.sh).

`gh` and `paseo` are replaced by fake executables on PATH, so nothing here touches the
network, GitHub, or a Paseo daemon. Set FIRST_MATE_ASSETS to test another copy of the
assets (for example the previous release, to see which tests it fails), and
FIRST_MATE_TEST_BASH to run the wait loop under another bash (for example a 3.2 build).

Usage: personal/scripts/test-first-mate-detector.py
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

KIT = Path(__file__).resolve().parents[1]
ASSETS = Path(os.environ.get("FIRST_MATE_ASSETS") or KIT / "files/home/.agents/skills/paseo-first-mate/assets")
BASH = os.environ.get("FIRST_MATE_TEST_BASH", "bash")
SECRET = "sentinel-secret-value-7f3a"  # noqa: S105 -- fake value used to prove it is never printed

FAKE_GH = """#!{python}
import json, os, re, sys, time
d = os.environ["FAKE_GH_DIR"]
args = sys.argv[1:]
with open(os.path.join(d, "calls.log"), "a") as fh:
    fh.write(" ".join(args) + "\\n")
time.sleep(float(os.environ.get("FAKE_GH_DELAY", "0")))


def load(name, default=None):
    path = os.path.join(d, name)
    if not os.path.exists(path):
        if default is None:
            sys.stderr.write("fake gh: no fixture " + name + "\\n")
            sys.exit(1)
        return default
    with open(path) as fh:
        return json.load(fh)


def counter(name):
    path = os.path.join(d, name)
    n = int(open(path).read()) if os.path.exists(path) else 0
    with open(path, "w") as fh:
        fh.write(str(n + 1))
    return n


if args[:2] == ["pr", "view"]:
    num = args[2]
    data = load("pr-%s.json" % num)
    seq = load("pr-%s.merge-seq.json" % num, [])
    if seq:
        data["mergeStateStatus"] = seq[min(counter("pr-%s.merge-idx" % num), len(seq) - 1)]
    print(json.dumps(data))
elif args[:1] == ["api"] and args[1] == "user":
    print(load("login.json", "me"))
elif args[:1] == ["api"] and re.match(r"repos/[^/]+/[^/]+/pulls/(\\d+)/comments", args[1]):
    num = re.match(r"repos/[^/]+/[^/]+/pulls/(\\d+)/comments", args[1]).group(1)
    logins = load("inline-%s.json" % num, [])
    jq = args[args.index("--jq") + 1]
    if jq == "length":
        print(len(logins))
    elif logins:
        print("\\n".join(logins))
elif args[:1] == ["api"] and re.match(r"repos/[^/]+/[^/]+/commits/", args[1]):
    print(json.dumps(load("branch-" + args[1].rsplit("/", 1)[1] + ".json")))
else:
    sys.stderr.write("fake gh: unsupported call: " + " ".join(args) + "\\n")
    sys.exit(1)
"""

FAKE_PASEO = """#!/bin/sh
echo "paseo called: $*" >> "$FAKE_GH_DIR/calls.log"
echo "fake paseo: not available" >&2
exit 1
"""


def pr(head="aaaaaaaa11111111", state="OPEN", merge="CLEAN", reviews=(), comments=(), draft=False, decision=None):
    return {
        "headRefOid": head,
        "isDraft": draft,
        "state": state,
        "reviewDecision": decision,
        "mergeStateStatus": merge,
        "reviews": [
            {
                "author": None if who is None else {"login": who},
                "state": st,
                "commit": {"oid": oid},
                "submittedAt": f"2026-01-01T00:00:{i:02d}Z",
            }
            for i, (who, st, oid) in enumerate(reviews)
        ],
        "comments": [{"author": None if who is None else {"login": who}} for who in comments],
        "statusCheckRollup": [],
    }


class Env:
    def __init__(self, root: Path, assets: Path = ASSETS):
        self.root = root
        self.fake = root / "fake"
        self.bin = root / "bin"
        self.state = root / "state"
        self.tools = root / "tools"
        for path in (self.fake, self.bin, self.state, self.tools):
            path.mkdir()
        gh = self.bin / "gh"
        gh.write_text(FAKE_GH.format(python=sys.executable))
        paseo = self.bin / "paseo"
        paseo.write_text(FAKE_PASEO)
        for exe in (gh, paseo):
            exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
        for name in ("first-mate-check.py", "first-mate-wait.sh"):
            shutil.copy2(assets / name, self.tools / name)
        self.check = self.tools / "first-mate-check.py"
        self.wait = self.tools / "first-mate-wait.sh"
        self.extra_env: dict[str, str] = {}

    def env(self, **more):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("FIRST_MATE", "PASEO_", "GITHUB_", "GH_"))}
        env.update(
            PATH=f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            HOME=str(self.root),
            FAKE_GH_DIR=str(self.fake),
            FIRST_MATE_DIR=str(self.state),
            FIRST_MATE_UNKNOWN_SLEEP="0",
            FIRST_MATE_SELF_LOGIN="",
            GITHUB_TOKEN=SECRET,
        )
        env.update(self.extra_env)
        env.update(more)
        return env

    def put(self, name, data):
        (self.fake / name).write_text(json.dumps(data))

    def set_pr(self, num, **fields):
        self.put(f"pr-{num}.json", pr(**fields))

    def det(self, *args, cwd=None, **more):
        return subprocess.run(  # noqa: S603 -- fixed local script and synthetic fixtures
            [sys.executable, str(self.check), *args],
            capture_output=True,
            text=True,
            env=self.env(**more),
            cwd=cwd,
            timeout=60,
            check=False,
        )

    def sh(self, *args, **more):
        return subprocess.run(  # noqa: S603 -- fixed local script and synthetic fixtures
            [BASH, str(self.wait), *args],  # noqa: S607
            capture_output=True,
            text=True,
            env=self.env(**more),
            timeout=60,
            check=False,
        )

    def setup_pr(self, num=1, **fields):
        self.set_pr(num, **fields)
        self.det("repo", "r", "o/r")
        self.det("add", "pr", f"r#{num}")

    def baseline(self):
        out = self.det("--peek")
        self.det("--commit")
        return out

    def calls(self):
        path = self.fake / "calls.log"
        return path.read_text() if path.exists() else ""

    def state_json(self):
        return json.loads((self.state / ".first-mate-state.json").read_text())

    def watch_json(self):
        return json.loads((self.state / "first-mate-watch.json").read_text())


class DetectorCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.e = Env(Path(self._tmp.name))


class TwoPhaseSaveTests(DetectorCase):
    def test_repeat_peek_is_identical(self):
        self.e.setup_pr()
        self.e.baseline()
        self.e.set_pr(1, head="bbbbbbbb22222222")
        first, second = self.e.det("--peek"), self.e.det("--peek")
        self.assertIn("CHANGED pr r#1", first.stdout)
        self.assertEqual(first.stdout, second.stdout)

    def test_peek_without_commit_consumes_nothing(self):
        self.e.setup_pr()
        self.e.baseline()
        before = (self.e.state / ".first-mate-state.json").read_text()
        self.e.set_pr(1, comments=["alice"])
        self.assertIn("comments=1", self.e.det("--peek").stdout)
        self.assertEqual((self.e.state / ".first-mate-state.json").read_text(), before)
        self.assertIn("comments=1", self.e.det("--peek").stdout)

    def test_commit_consumes_the_reported_change(self):
        self.e.setup_pr()
        self.e.baseline()
        self.e.set_pr(1, comments=["alice"])
        self.assertIn("CHANGED", self.e.det("--peek").stdout)
        self.e.det("--commit")
        self.assertEqual(self.e.det("--peek").stdout, "")

    def test_state_moved_between_peek_and_commit_drops_the_commit(self):
        self.e.setup_pr()
        self.e.baseline()
        self.e.set_pr(1, comments=["alice"])
        self.e.det("--peek")
        self.e.det("remove", "pr", "r#1")
        self.e.det("--commit")
        self.assertNotIn("pr r#1", self.e.state_json())
        self.assertFalse((self.e.state / ".first-mate-pending.json").exists())

    def test_commit_only_applies_its_own_peek(self):
        self.e.setup_pr()
        self.e.baseline()
        self.e.set_pr(1, comments=["alice"])
        self.e.det("--peek", FIRST_MATE_TXN="loop-a")
        self.e.det("--commit", FIRST_MATE_TXN="loop-b")
        self.assertIn("CHANGED", self.e.det("--peek", FIRST_MATE_TXN="loop-c").stdout)
        self.e.det("--peek", FIRST_MATE_TXN="loop-a")
        self.e.det("--commit", FIRST_MATE_TXN="loop-a")
        self.assertEqual(self.e.det("--peek").stdout, "")

    def test_one_step_run_reports_once_under_concurrency(self):
        self.e.setup_pr()
        self.e.baseline()
        self.e.set_pr(1, comments=["alice"])
        procs = [
            subprocess.Popen(  # noqa: S603 -- fixed local script and synthetic fixtures
                [sys.executable, str(self.e.check)],
                stdout=subprocess.PIPE,
                text=True,
                env=self.e.env(FAKE_GH_DELAY="0.4"),
            )
            for _ in range(2)
        ]
        outputs = [p.communicate(timeout=60)[0] for p in procs]
        self.assertEqual(sum("CHANGED" in out for out in outputs), 1, outputs)

    def test_reset_forgets_pending_too(self):
        self.e.setup_pr()
        self.e.baseline()
        self.e.set_pr(1, comments=["alice"])
        self.e.det("--peek")
        self.e.det("--reset")
        self.assertIn("BASELINE", self.e.det("--peek").stdout)
        self.e.det("--commit")
        self.assertEqual(self.e.det("--peek").stdout, "")


class LoginFilterTests(DetectorCase):
    def test_own_comments_wake_the_loop_by_default(self):
        self.e.setup_pr()
        self.e.baseline()
        self.e.set_pr(1, comments=["me"])
        self.assertIn("comments=1", self.e.det("--peek", FIRST_MATE_SELF_LOGIN="me").stdout)

    def test_selffilter_on_ignores_own_comments_and_reviews(self):
        self.e.setup_pr()
        self.assertIn("selffilter on", self.e.det("selffilter", "on").stdout)
        self.e.baseline()
        self.e.set_pr(1, comments=["me"], reviews=[("me", "COMMENTED", "aaaaaaaa11111111")])
        self.e.put("inline-1.json", ["me"])
        self.assertEqual(self.e.det("--peek", FIRST_MATE_SELF_LOGIN="me").stdout, "")
        self.e.set_pr(1, comments=["me", "alice"])
        self.assertIn("comments=1", self.e.det("--peek", FIRST_MATE_SELF_LOGIN="me").stdout)

    def test_selffilter_asks_gh_for_the_login_when_unset(self):
        self.e.setup_pr()
        self.e.det("selffilter", "on")
        self.e.put("login.json", "mate")
        self.e.baseline()
        self.assertIn("api user", self.e.calls())

    def test_a_deleted_account_does_not_crash_the_detector(self):
        self.e.setup_pr(reviews=[(None, "COMMENTED", "aaaaaaaa11111111")], comments=[None])
        out = self.e.det("--show")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("ghost:COMMENTED", out.stdout)


class MergeStateTests(DetectorCase):
    def test_flicker_between_blocked_clean_and_unstable_is_not_a_change(self):
        self.e.setup_pr(merge="CLEAN")
        self.e.baseline()
        for flicker in ("BLOCKED", "UNSTABLE", "HAS_HOOKS", "CLEAN"):
            self.e.set_pr(1, merge=flicker)
            self.assertEqual(self.e.det("--peek").stdout, "", flicker)

    def test_conflict_and_behind_are_reported(self):
        self.e.setup_pr(merge="CLEAN")
        self.e.baseline()
        self.e.set_pr(1, merge="DIRTY")
        self.assertIn("merge=conflict", self.e.det("--peek").stdout)
        self.e.det("--commit")
        self.e.set_pr(1, merge="BEHIND")
        self.assertIn("merge=behind", self.e.det("--peek").stdout)

    def test_unknown_is_requeried_until_it_settles(self):
        self.e.setup_pr(merge="CLEAN")
        self.e.baseline()
        self.e.put("pr-1.merge-seq.json", ["UNKNOWN", "UNKNOWN", "CLEAN"])
        self.assertEqual(self.e.det("--peek").stdout, "")
        self.assertEqual(self.e.calls().count("pr view 1"), 4)

    def test_unknown_that_never_settles_keeps_the_previous_value(self):
        self.e.setup_pr(merge="DIRTY")
        self.e.baseline()
        self.e.put("pr-1.merge-seq.json", ["UNKNOWN"])
        self.assertEqual(self.e.det("--peek").stdout, "")
        self.assertIn("merge=conflict", self.e.state_json()["pr r#1"])


class PruneTests(DetectorCase):
    def merged(self):
        self.e.set_pr(1, state="MERGED")

    def test_merged_pr_is_reported_and_pruned_on_commit(self):
        self.e.setup_pr()
        self.e.baseline()
        self.merged()
        out = self.e.det("--peek").stdout
        self.assertIn("MERGED", out)
        self.assertIn("PRUNED pr r#1", out)
        self.assertEqual(self.e.watch_json()["prs"], ["r#1"], "peek must not change the watch list")
        self.e.det("--commit")
        self.assertEqual(self.e.watch_json()["prs"], [])
        self.assertNotIn("pr r#1", self.e.state_json())

    def test_autoprune_off_keeps_the_pr(self):
        self.e.setup_pr()
        self.e.det("autoprune", "off")
        self.e.baseline()
        self.merged()
        self.assertNotIn("PRUNED", self.e.det("--peek").stdout)
        self.e.det("--commit")
        self.assertEqual(self.e.watch_json()["prs"], ["r#1"])

    def test_manual_prune_still_works(self):
        self.e.setup_pr()
        self.e.det("autoprune", "off")
        self.e.baseline()
        self.merged()
        self.e.det("--peek")
        self.e.det("--commit")
        self.assertIn("pruned: pr r#1", self.e.det("prune").stdout)

    def test_open_pr_whose_title_says_closed_is_not_pruned(self):
        self.e.setup_pr()
        self.e.baseline()
        self.e.set_pr(1, state="OPEN", reviews=[("CLOSED", "COMMENTED", "aaaaaaaa11111111")])
        self.e.det("--peek")
        self.e.det("--commit")
        self.assertEqual(self.e.watch_json()["prs"], ["r#1"])


class ReportContentTests(DetectorCase):
    def test_current_head_is_shown(self):
        self.e.setup_pr(head="c0ffee00deadbeef")
        self.assertIn("head=c0ffee00", self.e.det("--show").stdout)

    def test_review_of_an_older_head_is_marked_stale(self):
        self.e.setup_pr(
            head="bbbbbbbb22222222",
            reviews=[("wz", "CHANGES_REQUESTED", "aaaaaaaa11111111")],
            decision="CHANGES_REQUESTED",
        )
        self.assertIn("stale-review=['wz:CHANGES_REQUESTED@aaaaaaaa']", self.e.det("--show").stdout)

    def test_review_of_the_current_head_is_not_stale(self):
        self.e.setup_pr(head="aaaaaaaa11111111", reviews=[("wz", "APPROVED", "aaaaaaaa11111111")])
        self.assertNotIn("stale-review", self.e.det("--show").stdout)

    def test_a_later_review_on_the_current_head_supersedes_an_old_one(self):
        self.e.setup_pr(
            head="bbbbbbbb22222222",
            reviews=[("wz", "CHANGES_REQUESTED", "aaaaaaaa11111111"), ("wz", "APPROVED", "bbbbbbbb22222222")],
        )
        self.assertNotIn("stale-review", self.e.det("--show").stdout)

    def test_a_new_head_that_leaves_a_review_behind_is_reported(self):
        self.e.setup_pr(head="aaaaaaaa11111111", reviews=[("wz", "APPROVED", "aaaaaaaa11111111")])
        self.e.baseline()
        self.e.set_pr(1, head="bbbbbbbb22222222", reviews=[("wz", "APPROVED", "aaaaaaaa11111111")])
        out = self.e.det("--peek").stdout
        self.assertIn("head=bbbbbbbb", out)
        self.assertIn("stale-review", out)


class PathTests(DetectorCase):
    def test_running_from_inside_the_state_dir_does_not_nest_it(self):
        work = self.e.root / "work"
        tmp = work / "tmp"
        tmp.mkdir(parents=True)
        for name in ("first-mate-check.py", "first-mate-wait.sh"):
            shutil.copy2(self.e.tools / name, tmp / name)
        env = {"FIRST_MATE_DIR": "tmp"}
        out = subprocess.run(  # noqa: S603 -- fixed local script
            [sys.executable, str(tmp / "first-mate-check.py"), "repo", "r", "o/r"],
            capture_output=True,
            text=True,
            env=self.e.env(**env),
            cwd=tmp,
            timeout=60,
            check=False,
        )
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertTrue((tmp / "first-mate-watch.json").exists())
        self.assertFalse((tmp / "tmp").exists(), "stray tmp/tmp was created")

    def test_relative_dir_from_the_repo_root_uses_that_root(self):
        work = self.e.root / "repo"
        (work / "tmp").mkdir(parents=True)
        shutil.copy2(self.e.check, work / "tmp" / "first-mate-check.py")
        out = subprocess.run(  # noqa: S603 -- fixed local script
            [sys.executable, str(work / "tmp" / "first-mate-check.py"), "repo", "r", "o/r"],
            capture_output=True,
            text=True,
            env=self.e.env(FIRST_MATE_DIR="tmp"),
            cwd=work,
            timeout=60,
            check=False,
        )
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertTrue((work / "tmp" / "first-mate-watch.json").exists())
        self.assertFalse((work / "tmp" / "tmp").exists())


class SecretTests(DetectorCase):
    def test_no_secret_is_printed_and_no_token_command_runs(self):
        self.e.setup_pr(reviews=[("wz", "APPROVED", "aaaaaaaa11111111")])
        self.e.det("selffilter", "on", FIRST_MATE_SELF_LOGIN="me")
        outputs = [self.e.det("--peek"), self.e.det("--commit"), self.e.det("--show"), self.e.det("list")]
        outputs.append(self.e.sh("status"))
        for out in outputs:
            self.assertNotIn(SECRET, out.stdout + out.stderr)
        calls = self.e.calls()
        for forbidden in ("auth", "token", "hosts.yml"):
            self.assertNotIn(forbidden, calls)
        self.assertNotIn("paseo called", calls)
        for name in ("first-mate-check.py", "first-mate-wait.sh"):
            text = (ASSETS / name).read_text()
            self.assertNotRegex(text, r"gh auth|printenv|export -p|GITHUB_TOKEN|USAI_API_KEY")


@unittest.skipUnless(shutil.which("flock"), "flock not installed")
class WaitLoopTests(DetectorCase):
    def test_cap_expiry_prints_one_line_and_exits_3(self):
        self.e.setup_pr()
        self.e.baseline()
        out = self.e.sh("1", "0")
        self.assertEqual(out.returncode, 3, out.stderr)
        lines = out.stdout.strip().splitlines()
        self.assertEqual(len(lines), 1, out.stdout)
        self.assertIn("cap", lines[0])

    def test_change_prints_the_report_then_commits_it(self):
        self.e.setup_pr()
        self.e.baseline()
        self.e.set_pr(1, comments=["alice"])
        out = self.e.sh("1", "5")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("CHANGED pr r#1", out.stdout)
        self.assertEqual(self.e.det("--peek").stdout, "", "the loop's report must have been committed")

    def test_a_loop_killed_before_commit_loses_nothing(self):
        self.e.setup_pr()
        self.e.baseline()
        self.e.set_pr(1, comments=["alice"])
        self.e.det("--peek", FIRST_MATE_TXN="dead-loop")
        self.assertIn("CHANGED", self.e.sh("1", "5").stdout)

    def test_status_reports_the_age_of_the_last_run(self):
        self.e.setup_pr()
        self.e.baseline()
        self.e.sh("1", "0")
        out = self.e.sh("status").stdout
        self.assertTrue(out.startswith("none"), out)
        self.assertRegex(out, r"last-run=\d+s ago")

    def test_status_warns_when_the_last_run_is_older_than_twice_the_interval(self):
        self.e.setup_pr()
        self.e.baseline()
        stale = int(time.time()) - 3 * 3600
        (self.e.state / ".first-mate-lastrun").write_text(f"{stale}\n")
        # FIRST_MATE_MINUTE_SECS=1 makes the loop's "minute" one second, so a 1-minute
        # interval means the warning threshold is 2 seconds, and a detector stuck on a slow
        # gh never refreshes the file.
        loop = subprocess.Popen(  # noqa: S603 -- fixed local script
            [BASH, str(self.e.wait), "1", "30"],  # noqa: S607
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=self.e.env(FIRST_MATE_OWNER="alice", FAKE_GH_DELAY="30", FIRST_MATE_MINUTE_SECS="1"),
        )
        try:
            out = ""
            for _ in range(60):
                out = self.e.sh("status", FIRST_MATE_OWNER="alice", FIRST_MATE_MINUTE_SECS="1").stdout
                if out.startswith("mine"):
                    break
                time.sleep(0.2)
            self.assertTrue(out.startswith("mine"), out)
            self.assertIn("last-run=3h", out)
            self.assertNotIn("WARNING", out, "a loop younger than two intervals must not warn yet")
            time.sleep(3.5)
            out = self.e.sh("status", FIRST_MATE_OWNER="alice", FIRST_MATE_MINUTE_SECS="1").stdout
            self.assertIn("WARNING", out)
        finally:
            self.e.sh("stop", "--force", FIRST_MATE_OWNER="alice")
            loop.wait(timeout=30)

    def test_default_cap_is_long_enough_for_a_long_session(self):
        text = self.e.wait.read_text()
        self.assertRegex(text, r"max=\$\{2:-(\d+)\}")
        cap = int(__import__("re").search(r"max=\$\{2:-(\d+)\}", text).group(1))
        self.assertGreaterEqual(cap, 480)

    def test_relative_state_dir_is_not_nested(self):
        work = self.e.root / "work"
        tmp = work / "tmp"
        tmp.mkdir(parents=True)
        for name in ("first-mate-check.py", "first-mate-wait.sh"):
            shutil.copy2(self.e.tools / name, tmp / name)
        out = subprocess.run(  # noqa: S603 -- fixed local script
            [BASH, str(tmp / "first-mate-wait.sh"), "status"],  # noqa: S607
            capture_output=True,
            text=True,
            env=self.e.env(FIRST_MATE_DIR="tmp"),
            cwd=tmp,
            timeout=60,
            check=False,
        )
        self.assertEqual(out.stdout.split()[0], "none", out.stdout + out.stderr)
        self.assertFalse((tmp / "tmp").exists(), "stray tmp/tmp was created")


if __name__ == "__main__":
    print(textwrap.dedent(f"  assets under test: {ASSETS}"))
    unittest.main(verbosity=2)
