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

**Everything ends on `main`, pushed. Always, unless the owner said otherwise in this session.**
A branch is a way of working, never a resting place — a session that ends with the work sitting on
`feat/…` has not finished, however green the tests are. So gate 2 is not optional and not
something to defer to the owner: merge every branch you created into `main`, push it, and remove
the worktree. Report the merge as done only after `git log origin/main` actually contains it.

If a merge or push is refused — the command classifier blocks it, a lease is held, a remote is
403 — that is a **blocker to raise immediately**, not a result to write up. Say what was refused
and the exact command, and ask; don't reorganise the report around the parts that worked, and
don't reopen or annotate issues to describe a half-landed state you could simply have asked about.
Retry once first: the classifier's stage-2 refusals are usually transient.

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
- **Check `main` isn't already carrying a partial merge of your branch.** A concurrent session may
  have merged an earlier commit of it; `git log origin/main..main` before you push, and re-merge
  the branch so the tip lands too. Pushing a partial merge ships the version your later commits
  fixed — worse than not pushing at all.
- **Push.** `kara-web` and `markibx-web` are **403** — never promise those; hand the diff to
  their owner. Report each push as `<repo> <old>..<new>`.
- **Re-run the touched suites against merged `main`,** not just against the branch. The merge
  brought in whatever else landed while you worked.

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
- anything partially done, or done but not on `main`, or on `main` but not deployed when it
  needed to be
- an issue whose acceptance criteria you can't check

Note that "not on `main`" is a gate-2 failure, not an issue-state problem. Fix it there — go get
the merge unblocked — rather than closing the issue early and then trying to annotate your way out
of it.

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
- `git worktree list` per repo you touched — none of yours should remain.
- `git log origin/main -1` per repo you touched — your merge should be there. If it isn't, the
  session is not over.

## Report

One block, no padding: pushes as `repo old..new`, what deployed (or why not), issues closed with
numbers, issues left open with the reason, and anything you could not finish. If a gate stopped
you, lead with that — not with the parts that went fine.
