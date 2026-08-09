---
name: checkpoint
description: >
  Land the work so far without ending the session: verify it's green, commit and push what's
  actually finished, and append the record to DONE_TODAY.md — then keep working. Does NOT deploy,
  close issues, or touch any other doc. Use when the user says "checkpoint", "land what we have",
  "save point", "commit and push what's done so far", or invokes /checkpoint.
---

# checkpoint

Three gates, run mid-flight. Nothing here assumes you're done — you land what is *finished right
now* and go back to work on the rest.

**Scope is deliberately narrow: verify, commit + push, write `DONE_TODAY.md`. Nothing else.**
No deploy, no issue closing, no `/sync-ecosystem-docs`, no `DECISIONS.md`, no CLAUDE.md /
ARCHITECTURE.md / glossary edits. If one of those is needed, *say so in the report* and leave it
for `/end-session` or an explicit ask — do not do it here.

**The rule that governs all three: land only what you verified.** Pushing is a statement to other
people. Never make one you haven't checked.

**And the mid-session rule: only land what is complete.** Work in progress stays uncommitted or
stays on its branch. A checkpoint is not a reason to push something you're still editing.

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

## 2. Commit and push it

**Comment diet first** — `task lint:comments -- <repo>` on every repo you're about to commit
(no ref = uncommitted diff vs HEAD; after a worktree merge, run it with the pre-merge SHA as
base). For each hit: delete the comment — moving anything durable into the commit body — or
keep it deliberately as a real constraint and say why in the report. The lint is a tripwire,
not a verdict, but a hit you didn't look at is a skipped gate. (Rule: AGENTS.md §4, the
cold-reader test.)

The checkout is shared with other sessions, so:

- **Commit by path** — `git commit -- <paths>`, never `git add -A`. Another session's half-done
  edit sits in the same working tree; sweeping it up lands their broken code under your message.
  Your own in-progress edits count too — leave them out of the checkpoint. If the user explicitly
  asks you to commit everything, do it, but say in the commit message which parts aren't yours
  and that you didn't review them.
- **Merge worktree branches into main** from the main checkout, and take the merge lease first
  (the hook does it for you; see `AGENTS.md` §"Repo leases"). **Keep the worktree** if you're
  still working in it — only `git worktree remove` one you're finished with.
- **Push.** `kara-web` and `markibx-web` are **403** — never promise those; hand the diff to
  their owner. Report each push as `<repo> <old>..<new>`.

Stop here on anything that isn't a clean commit + push. Don't route around a lease, a 403, or a
non-fast-forward — report it.

## 3. Write the record

`/done-today` — append this checkpoint to `DONE_TODAY.md` in that skill's report format (a `##`
headline + 3-5 one-sentence bullets, achievements not narrative), including what deliberately
*wasn't* built and any pre-existing breakage you proved, so the next agent doesn't re-debug it. A later
checkpoint in the same session appends again; don't rewrite the earlier entry. **Go through
`task done:append`, never `Edit`/`Write` on the file** — other sessions (and your own earlier
checkpoints) are appending to it too, and a read-modify-write eats their entry.

`DONE_TODAY.md` is the only file this skill writes.

Then `task claims` — you are still working, so **keep** the leases you still need. Just confirm
you hold nothing you've finished with; `task claims:reap` clears leases from crashed earlier runs.

## Report

One block, no padding: pushes as `repo old..new`, what you deliberately left uncommitted, and
anything you could not finish. If a gate stopped you, lead with that — not with the parts that
went fine.

Then, explicitly, the **deferred list**: anything that now needs a deploy, an issue closed, or a
doc updated — named, not done. That's `/end-session`'s job.

Then say in one line what you're picking back up, and continue.
