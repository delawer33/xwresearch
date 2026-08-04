---
name: end-session
description: >
  Close out a session cleanly: land the work (merge to main + push), deploy it to the VPS if it
  isn't there yet, close the issues it actually implemented, and leave the record true. Use when
  the user says "end session", "wrap up", "finish up", "land everything", "close it out", or
  invokes /end-session.
---

# end-session

Four gates, in this order. Each one can stop the sequence — a session that ends with half the
work landed and an issue closed is worse than one that ends with an honest "still open".

**The rule that governs all four: land only what you verified.** Closing an issue, deploying, and
pushing are all statements to other people. Never make one you haven't checked.

## 1. Is it green?

`task doctor` then the suites for what you touched (`task test`, `task test:workspace`, or the
repo's own). **A collection error is the environment, not your change** — `task venv`, re-run.

Pre-existing failures are fine to land past, but you must *prove* they're pre-existing rather
than assume it: baseline them in a clean checkout.

```bash
git worktree add -q --detach /tmp/baseline HEAD && cd /tmp/baseline
PYTHONPATH=/tmp/baseline/src <venv>/bin/python -m pytest <the failing files> -q
git worktree remove --force /tmp/baseline
```

Two traps here: `pytest … | tail` reports **tail's** exit code, so a failing suite reads as 0 —
read the summary line, not `$?`. And a worktree's tests import *main's* code through the shared
venv's editable install unless you set `PYTHONPATH`.

## 2. Land it

The checkout is shared with other sessions, so:

- **Commit by path** — `git commit -- <paths>`, never `git add -A`. Another session's half-done
  edit sits in the same working tree; sweeping it up lands their broken code under your message.
  If the user explicitly asks you to commit everything, do it, but say in the commit message
  which parts aren't yours and that you didn't review them.
- **Merge worktree branches into main** from the main checkout, and take the merge lease first
  (the hook does it for you; see `AGENTS.md` §"Repo leases"). Then remove the worktree —
  `git worktree remove` — so the next session doesn't inherit a stale one.
- **Push.** `kara-web` and `markibx-web` are **403** — never promise those; hand the diff to
  their owner. Report each push as `<repo> <old>..<new>`.

## 3. Deploy it, if it isn't already

Only for code that runs on the VPS: `kara`/`karaa`, `mawtarx*`, `markibx*`. A library or
workspace-tooling change needs no deploy.

**Check first, don't assume it's stale.** Probe the running box for the thing you changed (the
`/deploy-vps` skill has the venv/service map; `docs/vps-current-state.md` is the written state,
which lags). If the change is already live, say so and skip. If not, run `/deploy-vps` — it
handles both venvs, the restart, and verification.

Remember the box is **dev, not prod**, and `/etc/*.env` is root-owned: if you hit a root wall,
append to `ROOT_ASKS.md` instead of routing around sudoers.

## 4. Close the issues you actually implemented

Per repo, `gh issue list --state open`, then for each one ask: **is every part of it done, landed,
and (if it needed deploying) live?**

Close only those. On each, comment with the commit SHA and how you verified it, then close:

```bash
gh issue close <n> -R <owner>/<repo> --comment "Implemented in <sha>; verified by <what you ran>."
```

**Do not close:**

- an issue you filed *this session* for future work — a workaround is not a fix
- anything partially done, or done but unpushed, or pushed but not deployed when it needed to be
- an issue whose acceptance criteria you can't check

Say which ones you left open and why. "Left #6 open — worked around, not fixed" is a good
session outcome; a wrongly-closed issue costs someone a week of believing it's handled.

## 5. Leave the record true

- `/done-today` — append this session to `DONE_TODAY.md`, including what deliberately *wasn't*
  built and any pre-existing breakage you proved, so the next agent doesn't re-debug it.
- `/sync-ecosystem-docs` — only if a **cross-repo fact** changed (what's live, a dependency, a
  port, a shared convention). Skip it otherwise.
- `DECISIONS.md` — one entry per decision a future agent would otherwise reverse.
- `task claims` — confirm you're holding nothing. Leases release at `SessionEnd`, but a crashed
  earlier run may still hold one; `task claims:reap` clears the dead.

## Report

One block, no padding: pushes as `repo old..new`, what deployed (or why not), issues closed with
numbers, issues left open with the reason, and anything you could not finish. If a gate stopped
you, lead with that — not with the parts that went fine.
