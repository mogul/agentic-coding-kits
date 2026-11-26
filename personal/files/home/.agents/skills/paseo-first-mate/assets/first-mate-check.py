#!/usr/bin/env python3
"""First Mate change detector.

Prints NOTHING when nothing meaningful changed since the last run, so a
wait loop that finds no change costs no model tokens. Prints one block per
change otherwise. Read-only against GitHub and Paseo; the only writes are the
local state and watch files in FIRST_MATE_DIR (default: tmp, which should be
ignored by git). FIRST_MATE_DIR is made absolute: a relative value resolves
against the current directory, except that when that directory does not exist
and this script itself sits in a directory with that path tail (the skill copies
the scripts into tmp/), the script's directory is used. Running from inside tmp/
therefore never creates tmp/tmp.

What to watch lives in first-mate-watch.json, not in this script:
  {"repos": {"qs": "OWNER/repo", ...},
   "prs": ["qs#611", ...], "issues": ["qs#503", ...],
   "releases": ["qs", ...],
   "branches": ["qs@main", ...],
   "workflows": ["qs:deploy-dev.yml@main", ...]}

A watched branch reports each new commit on it (so work that lands from other
sessions is seen). A watched workflow reports the latest run on a branch: its
head, status, and conclusion (so a deploy that stays red after a merge is seen).
A PR line shows its current head and a `stale-review=[...]` marker when a
reviewer's latest approval or change request was made on an older head.
mergeStateStatus is collapsed to conflict, behind, or ok, and a transient UNKNOWN
is re-queried (and then keeps the previous value), so recomputation does not wake you.

Saving. A report must not be consumed before it is delivered. Loops that can be
killed use the two-phase form:
  --peek    print what changed and stage a pending save bound to the exact saved
            state it was computed against; consumes nothing
  --commit  apply the staged save (and auto-prune) if that state is still current,
            otherwise drop it
A killed loop leaves the saved state untouched, so the next run reports the same
change again: a duplicate, never a miss. A commit applies only a pending save that
was staged under the same FIRST_MATE_TXN (unset matches unset), so one loop's commit
never consumes another run's report. Without a flag the detector reports and saves
in one step. State saved by an older version holds raw merge values, so run --reset
once after upgrading, or expect one CHANGED line per PR.

Usage:
  first-mate-check.py                    compare to saved state, print changes, save (one step)
  first-mate-check.py --peek             print changes and stage the save
  first-mate-check.py --commit           apply the staged save
  first-mate-check.py --show             print the full current snapshot, save nothing
  first-mate-check.py --reset            forget saved state (next run is a baseline)
  first-mate-check.py list               print the watch list
  first-mate-check.py add pr qs#637      start watching (also: issue; also OWNER/repo#N)
  first-mate-check.py add branch qs@main watch new commits on a branch
  first-mate-check.py add workflow qs:deploy-dev.yml@main
                                         watch the latest run of a workflow on a branch
  first-mate-check.py remove pr qs#611   stop watching and forget its state (also: issue, branch, workflow)
  first-mate-check.py repo qs OWNER/repo register a repo alias
  first-mate-check.py prune              stop watching merged/closed PRs and closed issues now
  first-mate-check.py autoprune on|off   do that automatically when a report is saved (default on)
  first-mate-check.py selffilter on|off  ignore comments and reviews by your own login (default off)
  first-mate-check.py agents on|off      watch your own delegated agents (off by default)
  first-mate-check.py permits on|off     watch pending permission prompts (off by default)

selffilter: your login is FIRST_MATE_SELF_LOGIN, or else `gh api user`. A human
and an agent that share one login are both filtered, which also hides the human's
own comments and reviews; leave it off in that setup. Toggling it, or running
--reset, makes the next run a baseline.

Needs Python 3.9+. The state lock uses fcntl; where that is missing (Windows) the
detector still runs but concurrent runs are not serialized.
"""

import concurrent.futures as cf
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager, nullcontext, suppress

try:
    import fcntl
except ImportError:  # no flock on this platform
    fcntl = None

DEFAULT_DIR = "tmp"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def resolve_dir(value, cwd=None, script_dir=None):
    """Absolute FIRST_MATE_DIR (see the module docstring for the rule)."""
    value = value or DEFAULT_DIR
    if os.path.isabs(value):
        return os.path.normpath(value)
    value = os.path.normpath(value)
    candidate = os.path.join(os.path.abspath(cwd or os.getcwd()), value)
    script_dir = os.path.abspath(script_dir or SCRIPT_DIR)
    if not os.path.isdir(candidate) and script_dir.endswith(os.sep + value) and os.path.dirname(script_dir) != os.sep:
        return script_dir
    return candidate


HERE = resolve_dir(os.environ.get("FIRST_MATE_DIR"))
os.makedirs(HERE, exist_ok=True)
STATE = os.path.join(HERE, ".first-mate-state.json")
PENDING = os.path.join(HERE, ".first-mate-pending.json")
LASTRUN = os.path.join(HERE, ".first-mate-lastrun")
LOCKFILE = os.path.join(HERE, ".state.lock")
REPORT_LOCKFILE = os.path.join(HERE, ".report.lock")
WATCH = os.path.join(HERE, "first-mate-watch.json")
TIMEOUT = 45
UNKNOWN_RETRIES = 3
UNKNOWN_SLEEP = float(os.environ.get("FIRST_MATE_UNKNOWN_SLEEP", "3"))
LOGIN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*(?:\[bot\])?$")
GATING = ("APPROVED", "CHANGES_REQUESTED", "DISMISSED")

DEFAULT_WATCH = {
    "repos": {},
    "prs": [],
    "issues": [],
    "releases": [],
    "branches": [],
    "workflows": [],
    # Local orchestration watches are OFF by default: the harness already sends
    # "[Agent finished]" notices and surfaces pending permission prompts, so
    # watching the coordinator's own delegated agents (and its own permits) here
    # would make the loop wake on its own actions. Enable with `agents on` /
    # `permits on` for heartbeat flows that receive no harness finish notices.
    "watch_agents": False,
    "watch_permits": False,
    # Drop merged/closed PRs and closed issues from the watch list when a report
    # that shows them is saved. Ignore your own login's comments and reviews
    # (off: a human and an agent often share one login).
    "autoprune": True,
    "self_filter": False,
}

BRANCH_REF = re.compile(r"^(?P<alias>[A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)?)@(?P<branch>.+)$")
WORKFLOW_REF = re.compile(r"^(?P<alias>[A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)?):(?P<workflow>[^@:]+)@(?P<branch>.+)$")
BAD_CONCLUSIONS = {"FAILURE", "TIMED_OUT", "ACTION_REQUIRED", "STARTUP_FAILURE"}
BAD_STATES = {"FAILURE", "ERROR"}
REF = re.compile(r"^(?:(?P<alias>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+|[A-Za-z0-9_-]+)#)(?P<num>\d+)$")


def load_watch():
    if not os.path.exists(WATCH):
        save_watch(DEFAULT_WATCH)
        return json.loads(json.dumps(DEFAULT_WATCH))
    with open(WATCH) as fh:
        w = json.load(fh)
    for k, v in DEFAULT_WATCH.items():
        w.setdefault(k, json.loads(json.dumps(v)))
    return w


def write_atomic(path, text):
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def save_watch(w):
    write_atomic(WATCH, json.dumps(w, indent=1) + "\n")


@contextmanager
def file_lock(path):
    if fcntl is None:
        yield
        return
    with open(path, "a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        yield


def state_lock():
    """Serializes every read-modify-write of the state, pending, and watch files.
    Held only around local file work, never around network calls."""
    return file_lock(LOCKFILE)


def resolve(w, ref):
    m = REF.match(ref)
    if not m:
        raise SystemExit(f"bad reference '{ref}' (want alias#N or OWNER/repo#N)")
    alias = m.group("alias")
    repo = w["repos"].get(alias, alias if "/" in alias else None)
    if not repo:
        raise SystemExit(f"unknown repo alias '{alias}'; register it: repo {alias} OWNER/repo")
    return repo, int(m.group("num"))


def repo_of(w, alias):
    repo = w["repos"].get(alias, alias if "/" in alias else None)
    if not repo:
        raise SystemExit(f"unknown repo alias '{alias}'; register it: repo {alias} OWNER/repo")
    return repo


def parse_branch(w, ref):
    m = BRANCH_REF.match(ref)
    if not m:
        raise SystemExit(f"bad branch reference '{ref}' (want alias@branch)")
    repo = repo_of(w, m.group("alias"))
    return repo, m.group("branch"), f"{short(w, repo)}@{m.group('branch')}"


def parse_workflow(w, ref):
    m = WORKFLOW_REF.match(ref)
    if not m:
        raise SystemExit(f"bad workflow reference '{ref}' (want alias:workflow-file@branch)")
    repo = repo_of(w, m.group("alias"))
    wf, br = m.group("workflow"), m.group("branch")
    return repo, wf, br, f"{short(w, repo)}:{wf}@{br}"


def short(w, repo):
    for a, r in w["repos"].items():
        if r == repo:
            return a
    return repo


def run(cmd):
    exe = shutil.which(cmd[0])
    if sys.platform == "win32" and exe and exe.lower().endswith((".cmd", ".bat")):
        # Windows cannot exec a .cmd/.bat directly; route it through cmd.exe.
        out = subprocess.run(subprocess.list2cmdline(cmd), capture_output=True, text=True, timeout=TIMEOUT, shell=True)
    else:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
    if out.returncode != 0:
        raise RuntimeError((out.stderr or out.stdout).strip().splitlines()[-1][:160])
    return out.stdout


def gh_json(args):
    return json.loads(run(["gh"] + args))


_SELF = []


def self_login():
    """The login to ignore when selffilter is on. Never reads a token: it asks gh."""
    if not _SELF:
        login = (os.environ.get("FIRST_MATE_SELF_LOGIN") or run(["gh", "api", "user", "-q", ".login"])).strip()
        if not LOGIN.match(login):
            raise RuntimeError("could not determine your GitHub login; set FIRST_MATE_SELF_LOGIN")
        _SELF.append(login)
    return _SELF[0]


def login_of(item, key="author"):
    return (item.get(key) or {}).get("login") or "ghost"


def collapse_merge_state(raw):
    """DIRTY and BEHIND are real; UNKNOWN is None (not known yet); the rest is ok."""
    if raw == "UNKNOWN":
        return None
    return {"DIRTY": "conflict", "BEHIND": "behind"}.get(raw, "ok")


def previous_merge(prev):
    """The merge value of the last saved snapshot, in collapsed form (old saves held the raw value)."""
    m = re.search(r" merge=(\S+)", prev or "")
    if not m:
        return "ok"
    return m.group(1) if m.group(1) in ("conflict", "behind", "ok") else collapse_merge_state(m.group(1)) or "ok"


def stale_reviews(reviews, head):
    """Each reviewer's latest approval or change request made on a known head other than `head`."""
    latest = {}
    for r in sorted(reviews, key=lambda x: x.get("submittedAt") or ""):
        if r.get("state") in GATING:
            latest[login_of(r)] = r
    return sorted(
        f"{who}:{r['state']}@{(r.get('commit') or {}).get('oid', '')[:8]}"
        for who, r in latest.items()
        if r["state"] != "DISMISSED" and (r.get("commit") or {}).get("oid") not in (None, "", head)
    )


def pr_snapshot(repo, num, prev=None, self_filter=False):
    for attempt in range(UNKNOWN_RETRIES):
        d = gh_json(
            [
                "pr",
                "view",
                str(num),
                "--repo",
                repo,
                "--json",
                "headRefOid,isDraft,state,reviewDecision,mergeStateStatus,reviews,comments,statusCheckRollup",
            ]
        )
        merge = collapse_merge_state(d.get("mergeStateStatus"))
        if merge is not None or d.get("state") != "OPEN":
            break
        if attempt + 1 < UNKNOWN_RETRIES:
            time.sleep(UNKNOWN_SLEEP)
    if merge is None:
        merge = previous_merge(prev)
    ignore = self_login() if self_filter else None
    inline = len(
        [
            who
            for who in run(
                [
                    "gh",
                    "api",
                    f"repos/{repo}/pulls/{num}/comments?per_page=100",
                    "--paginate",
                    "--jq",
                    '.[] | (.user.login // "ghost")',
                ]
            ).splitlines()
            if who != ignore
        ]
    )
    ok = bad = pend = 0
    bad_names = []
    for c in d.get("statusCheckRollup") or []:
        concl, state, status = c.get("conclusion"), c.get("state"), c.get("status")
        name = c.get("name") or c.get("context") or "?"
        if concl in BAD_CONCLUSIONS or state in BAD_STATES:
            bad += 1
            bad_names.append(name)
        elif status not in (None, "COMPLETED") or state == "PENDING":
            pend += 1
        else:
            ok += 1
    head = d["headRefOid"]
    shown = [r for r in d.get("reviews") or [] if login_of(r) != ignore]
    reviews = sorted(f"{login_of(r)}:{r['state']}@{(r.get('commit') or {}).get('oid', '')[:8]}" for r in shown)
    stale = stale_reviews(shown, head)
    n_comments = sum(1 for c in d.get("comments") or [] if login_of(c) != ignore)
    return (
        f"head={head[:8]} {'draft' if d['isDraft'] else 'ready'} {d['state']} "
        f"decision={d.get('reviewDecision') or '-'} merge={merge} "
        f"checks ok={ok} fail={bad} pending={pend}"
        + (f" failing={sorted(bad_names)}" if bad_names else "")
        + f" reviews={reviews}"
        + (f" stale-review={stale}" if stale else "")
        + f" comments={n_comments} inline={inline}"
    )


def issue_snapshot(repo, num):
    d = gh_json(["issue", "view", str(num), "--repo", repo, "--json", "state,comments"])
    return f"{d['state']} comments={len(d.get('comments') or [])}"


def release_snapshot(repo):
    return gh_json(["release", "view", "--repo", repo, "--json", "tagName"])["tagName"]


def branch_snapshot(repo, branch):
    d = gh_json(["api", f"repos/{repo}/commits/{branch}"])
    subject = (d.get("commit", {}).get("message") or "").splitlines()[:1]
    return f"{d['sha'][:8]} {(subject[0] if subject else '')[:80]}"


def workflow_snapshot(repo, workflow, branch):
    rows = gh_json(
        [
            "run",
            "list",
            "--repo",
            repo,
            "--workflow",
            workflow,
            "--branch",
            branch,
            "--limit",
            "1",
            "--json",
            "databaseId,headSha,status,conclusion",
        ]
    )
    if not rows:
        return "no runs"
    r = rows[0]
    return f"run {r['databaseId']} head={r['headSha'][:8]} {r['status']} {r.get('conclusion') or '-'}"


def agents_snapshot(self_id):
    args = ["paseo", "ls", "--json"]
    if self_id:
        args += ["--label", f"paseo.parent-agent-id={self_id}"]
    rows = json.loads(run(args))
    items = sorted(f"{r['shortId']}:{r['status']}:{r.get('name', '')[:36]}" for r in rows)
    return "; ".join(items) or "none"


def permits_snapshot():
    rows = json.loads(run(["paseo", "permit", "ls", "--json"]))
    return "; ".join(sorted(f"{r['agentShortId']}:{r['id']}" for r in rows)) or "none"


def collect(w, prev=None):
    prev = prev or {}
    jobs = {}
    for ref in w["prs"]:
        repo, n = resolve(w, ref)
        key = f"pr {short(w, repo)}#{n}"
        jobs[key] = (pr_snapshot, repo, n, prev.get(key), bool(w.get("self_filter")))
    for ref in w["issues"]:
        repo, n = resolve(w, ref)
        jobs[f"issue {short(w, repo)}#{n}"] = (issue_snapshot, repo, n)
    for alias in w["releases"]:
        repo = w["repos"].get(alias, alias)
        jobs[f"release {short(w, repo)}"] = (release_snapshot, repo)
    for ref in w["branches"]:
        repo, br, label = parse_branch(w, ref)
        jobs[f"branch {label}"] = (branch_snapshot, repo, br)
    for ref in w["workflows"]:
        repo, wf, br, label = parse_workflow(w, ref)
        jobs[f"workflow {label}"] = (workflow_snapshot, repo, wf, br)
    if w.get("watch_agents"):
        jobs["agents"] = (agents_snapshot, os.environ.get("PASEO_AGENT_ID", ""))
    if w.get("watch_permits"):
        jobs["permission prompts"] = (permits_snapshot,)
    results, errors = {}, {}
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(*j): k for k, j in jobs.items()}
        for f in cf.as_completed(futs):
            k = futs[f]
            try:
                results[k] = f.result()
            except Exception as e:  # noqa: BLE001 - report, keep old value
                errors[k] = str(e) or e.__class__.__name__
    return results, errors


def load_state():
    if os.path.exists(STATE):
        with open(STATE) as fh:
            return json.load(fh)
    return {}


def save_state(s):
    write_atomic(STATE, json.dumps(s, indent=1, sort_keys=True))


def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


def remove_quietly(path):
    with suppress(FileNotFoundError):
        os.remove(path)


PR_STATE = re.compile(r"^head=\S+ (?:draft|ready) (OPEN|MERGED|CLOSED) ")


def finished(kind, snap):
    """True for a merged or closed PR, or a closed issue (from its saved snapshot)."""
    if kind == "pr":
        m = PR_STATE.match(snap or "")
        return bool(m) and m.group(1) in ("MERGED", "CLOSED")
    return (snap or "").startswith("CLOSED")


def prunable(w, snaps):
    """Watched PRs and issues whose snapshot says they are finished: [(kind, item, label)]."""
    found = []
    for kind, key in (("pr", "prs"), ("issue", "issues")):
        for item in w[key]:
            snap = snaps.get(f"{kind} {item}")
            if snap is not None and finished(kind, snap):
                found.append((kind, item, PR_STATE.match(snap).group(1) if kind == "pr" else "CLOSED"))
    return found


def apply_prune(w, st, found):
    for kind, item, _ in found:
        key = "prs" if kind == "pr" else "issues"
        w[key] = [x for x in w[key] if x != item]
        st.pop(f"{kind} {item}", None)


def manage(w, argv):
    cmd = argv[0]
    if cmd == "list":
        print(json.dumps(w, indent=1))
    elif cmd in ("add", "remove") and len(argv) == 3 and argv[1] in ("branch", "workflow"):
        kind = argv[1]
        key = "branches" if kind == "branch" else "workflows"
        label = parse_branch(w, argv[2])[2] if kind == "branch" else parse_workflow(w, argv[2])[3]
        if cmd == "add":
            if label not in w[key]:
                w[key].append(label)
            save_watch(w)
            print(f"watching {kind} {label}")
        else:
            w[key] = [x for x in w[key] if x != label]
            save_watch(w)
            st = load_state()
            st.pop(f"{kind} {label}", None)
            save_state(st)
            print(f"stopped watching {kind} {label}")
    elif cmd in ("add", "remove") and len(argv) == 3 and argv[1] in ("pr", "issue"):
        key = "prs" if argv[1] == "pr" else "issues"
        repo, n = resolve(w, argv[2])
        alias = short(w, repo)
        item = f"{alias}#{n}"
        if cmd == "add":
            if item not in w[key]:
                w[key].append(item)
            save_watch(w)
            print(f"watching {argv[1]} {item}")
        else:
            w[key] = [x for x in w[key] if x != item]
            save_watch(w)
            st = load_state()
            st.pop(f"{argv[1]} {item}", None)
            save_state(st)
            print(f"stopped watching {argv[1]} {item}")
    elif cmd == "repo" and len(argv) == 3:
        w["repos"][argv[1]] = argv[2]
        save_watch(w)
        print(f"alias {argv[1]} -> {argv[2]}")
    elif cmd == "prune":
        st = load_state()
        found = prunable(w, st)
        apply_prune(w, st, found)
        save_watch(w)
        save_state(st)
        print("pruned: " + (", ".join(f"{k} {i}" for k, i, _ in found) or "nothing"))
    elif cmd in ("agents", "permits", "autoprune", "selffilter") and len(argv) == 2 and argv[1] in ("on", "off"):
        key = {
            "agents": "watch_agents",
            "permits": "watch_permits",
            "autoprune": "autoprune",
            "selffilter": "self_filter",
        }[cmd]
        changed = w.get(key) != (argv[1] == "on")
        w[key] = argv[1] == "on"
        save_watch(w)
        print(f"{cmd} {'on' if w[key] else 'off'}")
        if cmd == "selffilter" and changed:
            remove_quietly(STATE)
            remove_quietly(PENDING)
            print("state cleared: the next run is a baseline")
    else:
        raise SystemExit(__doc__)


def report_lines(old, new, errors, pruned, baseline):
    lines = []
    if baseline:
        lines.append(f"BASELINE saved ({len(new)} items)")
    else:
        for k in sorted(new):
            if k not in old:
                lines.append(f"NEW {k}: {new[k]}")
            elif old[k] != new[k]:
                lines.append(f"CHANGED {k}\n    was: {old[k]}\n    now: {new[k]}")
    for k in sorted(errors):
        lines.append(f"ERROR {k}: {errors[k]} (kept previous value)")
    for kind, item, label in pruned:
        lines.append(f"PRUNED {kind} {item} ({label}): no longer watched after this report")
    return lines


def detect(arg):
    """One detector pass. Concurrent passes take turns (the report lock), so a change is
    never reported twice in one-step mode. The state lock covers only local file work,
    never the network calls, so add/remove/--commit are not blocked behind a slow collect."""
    with file_lock(REPORT_LOCKFILE) if arg != "--show" else nullcontext():
        run_detect(arg)


def run_detect(arg):
    with state_lock():
        w = load_watch()
        old = load_state()
        baseline = not os.path.exists(STATE)
    new, errors = collect(w, old)
    if arg == "--show":
        for k in sorted(new):
            print(f"{k}: {new[k]}")
        for k in sorted(errors):
            print(f"ERROR {k}: {errors[k]}")
        return
    if new or not errors:  # a pass where every query failed did not complete
        write_atomic(LASTRUN, f"{int(time.time())}\n")
    found = prunable(w, new) if w.get("autoprune") else []
    lines = report_lines(old, new, errors, found, baseline)
    if lines:
        print("\n".join(lines), flush=True)
    pending = {
        "base": digest(old),
        "txn": os.environ.get("FIRST_MATE_TXN", ""),
        "new": new,
        "prune": [[k, i] for k, i, _ in found],
    }
    with state_lock():
        if arg == "--peek":
            if lines:
                write_atomic(PENDING, json.dumps(pending, sort_keys=True))
            else:
                remove_quietly(PENDING)
        else:
            apply_save(pending)


def apply_save(pending):
    """Save the fresh snapshots (and prunes) over the saved state. Caller holds the lock."""
    st = {**load_state(), **pending["new"]}
    w = load_watch()
    apply_prune(w, st, [(k, i, "") for k, i in pending.get("prune", [])])
    save_state(st)
    save_watch(w)


def commit_pending():
    with state_lock():
        if not os.path.exists(PENDING):
            return
        try:
            with open(PENDING) as fh:
                pend = json.load(fh)
        except (OSError, ValueError):
            remove_quietly(PENDING)
            return
        txn = os.environ.get("FIRST_MATE_TXN", "")
        if pend.get("txn", "") != txn:
            return  # staged by another run; only that run may commit it
        if pend.get("base") == digest(load_state()):
            apply_save(pend)
        remove_quietly(PENDING)  # a stale pending (state moved) is dropped; the next run recomputes


def main():
    argv = sys.argv[1:]
    if argv and not argv[0].startswith("--"):
        with state_lock():
            manage(load_watch(), argv)
        return
    arg = argv[0] if argv else ""
    if arg == "--commit":
        commit_pending()
    elif arg == "--reset":
        with state_lock():
            remove_quietly(STATE)
            remove_quietly(PENDING)
        print("state reset")
    elif arg in ("", "--peek", "--show"):
        detect(arg)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
