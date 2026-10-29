#!/usr/bin/env python3
"""First Mate change detector.

Prints NOTHING when nothing meaningful changed since the last run, so a
wait loop that finds no change costs no model tokens. Prints one block per
change otherwise. Read-only against GitHub and Paseo; the only writes are the
local state and watch files in FIRST_MATE_DIR (default: ./tmp, which should be
ignored by git).

What to watch lives in first-mate-watch.json, not in this script:
  {"repos": {"qs": "OWNER/repo", ...},
   "prs": ["qs#611", ...], "issues": ["qs#503", ...],
   "releases": ["qs", ...], "ignore_agents": ["First Mate"]}

Usage:
  first-mate-check.py                    compare to saved state, print changes, save
  first-mate-check.py --show             print the full current snapshot, save nothing
  first-mate-check.py --reset            forget saved state (next run is a baseline)
  first-mate-check.py list               print the watch list
  first-mate-check.py add pr qs#637      start watching (also: issue; also OWNER/repo#N)
  first-mate-check.py remove pr qs#611   stop watching and forget its state
  first-mate-check.py repo qs OWNER/repo register a repo alias
  first-mate-check.py prune              stop watching merged/closed PRs and closed issues
"""
import concurrent.futures as cf
import json
import os
import re
import subprocess
import sys

HERE = os.path.abspath(os.environ.get("FIRST_MATE_DIR", "tmp"))
os.makedirs(HERE, exist_ok=True)
STATE = os.path.join(HERE, ".first-mate-state.json")
WATCH = os.path.join(HERE, "first-mate-watch.json")
TIMEOUT = 45

DEFAULT_WATCH = {
    "repos": {},
    "prs": [],
    "issues": [],
    "releases": [],
    "ignore_agents": ["First Mate"],
}

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
        w.setdefault(k, type(v)())
    return w


def save_watch(w):
    with open(WATCH, "w") as fh:
        json.dump(w, fh, indent=1)
        fh.write("\n")


def resolve(w, ref):
    m = REF.match(ref)
    if not m:
        raise SystemExit(f"bad reference '{ref}' (want alias#N or OWNER/repo#N)")
    alias = m.group("alias")
    repo = w["repos"].get(alias, alias if "/" in alias else None)
    if not repo:
        raise SystemExit(f"unknown repo alias '{alias}'; register it: repo {alias} OWNER/repo")
    return repo, int(m.group("num"))


def short(w, repo):
    for a, r in w["repos"].items():
        if r == repo:
            return a
    return repo.split("/")[-1]


def run(cmd):
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
    if out.returncode != 0:
        raise RuntimeError((out.stderr or out.stdout).strip().splitlines()[-1][:160])
    return out.stdout


def gh_json(args):
    return json.loads(run(["gh"] + args))


def pr_snapshot(repo, num):
    d = gh_json([
        "pr", "view", str(num), "--repo", repo, "--json",
        "headRefOid,isDraft,state,reviewDecision,mergeStateStatus,reviews,comments,statusCheckRollup",
    ])
    inline = sum(int(x) for x in run([
        "gh", "api", f"repos/{repo}/pulls/{num}/comments?per_page=100", "--paginate",
        "--jq", "length"]).split())
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
    reviews = sorted(
        f"{r['author']['login']}:{r['state']}@{(r.get('commit') or {}).get('oid', '')[:8]}"
        for r in d.get("reviews") or [])
    return (
        f"head={d['headRefOid'][:8]} {'draft' if d['isDraft'] else 'ready'} {d['state']} "
        f"decision={d.get('reviewDecision') or '-'} merge={d.get('mergeStateStatus')} "
        f"checks ok={ok} fail={bad} pending={pend}"
        + (f" failing={sorted(bad_names)}" if bad_names else "")
        + f" reviews={reviews} comments={len(d.get('comments') or [])} inline={inline}")


def issue_snapshot(repo, num):
    d = gh_json(["issue", "view", str(num), "--repo", repo, "--json", "state,comments"])
    return f"{d['state']} comments={len(d.get('comments') or [])}"


def release_snapshot(repo):
    return gh_json(["release", "view", "--repo", repo, "--json", "tagName"])["tagName"]


def agents_snapshot(ignore):
    rows = json.loads(run(["paseo", "ls", "--json"]))
    items = sorted(
        f"{r['shortId']}:{r['status']}:{r.get('name', '')[:36]}"
        for r in rows if r.get("name") not in ignore)
    return "; ".join(items) or "none"


def permits_snapshot():
    rows = json.loads(run(["paseo", "permit", "ls", "--json"]))
    return "; ".join(sorted(f"{r['agentShortId']}:{r['id']}" for r in rows)) or "none"


def collect(w):
    jobs = {}
    for ref in w["prs"]:
        repo, n = resolve(w, ref)
        jobs[f"pr {short(w, repo)}#{n}"] = (pr_snapshot, repo, n)
    for ref in w["issues"]:
        repo, n = resolve(w, ref)
        jobs[f"issue {short(w, repo)}#{n}"] = (issue_snapshot, repo, n)
    for alias in w["releases"]:
        repo = w["repos"].get(alias, alias)
        jobs[f"release {short(w, repo)}"] = (release_snapshot, repo)
    jobs["agents"] = (agents_snapshot, set(w["ignore_agents"]))
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
    with open(STATE, "w") as fh:
        json.dump(s, fh, indent=1, sort_keys=True)


def manage(w, argv):
    cmd = argv[0]
    if cmd == "list":
        print(json.dumps(w, indent=1))
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
        dropped = []
        for kind, key in (("pr", "prs"), ("issue", "issues")):
            keep = []
            for item in w[key]:
                snap = st.get(f"{kind} {item}", "")
                done = (" MERGED " in f" {snap} " or " CLOSED " in f" {snap} ") if kind == "pr" \
                    else snap.startswith("CLOSED")
                if done:
                    dropped.append(f"{kind} {item}")
                    st.pop(f"{kind} {item}", None)
                else:
                    keep.append(item)
            w[key] = keep
        save_watch(w)
        save_state(st)
        print("pruned: " + (", ".join(dropped) or "nothing"))
    else:
        raise SystemExit(__doc__)


def main():
    argv = sys.argv[1:]
    if argv and not argv[0].startswith("--"):
        manage(load_watch(), argv)
        return
    arg = argv[0] if argv else ""
    if arg == "--reset":
        if os.path.exists(STATE):
            os.remove(STATE)
        print("state reset")
        return
    w = load_watch()
    new, errors = collect(w)
    if arg == "--show":
        for k in sorted(new):
            print(f"{k}: {new[k]}")
        for k in sorted(errors):
            print(f"ERROR {k}: {errors[k]}")
        return
    old = load_state()
    lines = []
    if not old:
        lines.append(f"BASELINE saved ({len(new)} items)")
    else:
        for k in sorted(new):
            if k not in old:
                lines.append(f"NEW {k}: {new[k]}")
            elif old[k] != new[k]:
                lines.append(f"CHANGED {k}\n    was: {old[k]}\n    now: {new[k]}")
    for k in sorted(errors):
        lines.append(f"ERROR {k}: {errors[k]} (kept previous value)")
    save_state({**old, **new})
    if lines:
        print("\n".join(lines))


if __name__ == "__main__":
    main()
