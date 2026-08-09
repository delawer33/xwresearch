---
name: done-today
description: >
  Record what this session did in the repo-root `DONE_TODAY.md`. Use at the end of any session
  that changed something, or whenever the user says "log this", "write down what we did",
  "update DONE_TODAY", "done today", or invokes /done-today.
---

# done-today

`DONE_TODAY.md` lives at the xwresearch root and holds **one day's** work. The file already
exists — never create a second one, never start a fresh file elsewhere.

## Never edit the file directly

Several sessions run at once, and `/checkpoint` calls this skill too. Two agents doing
read-modify-write on `DONE_TODAY.md` in the same minute means the slower one rebuilds the file
from a stale snapshot and the other entry vanishes — that already happened (the file was found
0 bytes on 2026-08-05). So an entry is written as an **append through a locked helper**, never
with `Edit`/`Write` on `DONE_TODAY.md`:

```bash
task done:append -- --file /path/to/entry.md
```

It takes an exclusive `flock`, re-reads the file *inside* the lock, appends, and replaces it
atomically. A concurrent session waits (up to 120s) and lands after you instead of over you.
`task done:date` prints the date the heading currently holds.

## The loop

1. **Write your entry to a scratch file** — the `##` sections only. No `# Done today — …`
   heading; the helper owns that line and will reject a block containing one.
2. **Append it** with `task done:append -- --file <that file>`. The helper checks today's real
   date itself (`date +%F` in your context can be wrong) against the heading.
3. **If it exits 3**, the heading is an *older* day — that file is the previous day's record and
   rewriting it destroys it. **Stop and ask the user** whether to archive or overwrite, saying
   what date it holds. Only after they answer, re-run with `--new-day` (add
   `--archive-to <path>` if they want the old text kept).

Extending an existing section from the same thread is fine — write the extension as its own
short `##` block rather than rewriting the file to splice it in.

## Whose work goes in — mine only

This is **my** log, not the team's. Everything written here must be work I did: this session's
changes, plus my own commits if you're pulling from git.

When pulling from git — including when the input came from `/status-report`, which reports the
**whole team** by default — filter by author first:

```bash
git config user.email          # resolve my identity once
git log --since=… --author="<that email>" --oneline
```

Other people's commits are **cut, not attributed** — no "landed today by X" paragraph, no
"for context" note. If a teammate's commit matters to my work, that belongs in **Left open** as
a thing I have to deal with, phrased as my problem — not as a record of their day.

## What to write — for /status-report extraction, not a session log

The owner reads this file through `/status-report from file`, which compresses each session to
1-3 single-sentence bullets. Write so those bullets can be lifted near-verbatim:

- One `##` headline naming the outcome, then **3-5 bullets, one sentence each** — specific
  achievements (what changed, where, the number/SHA that proves it), never session narrative.
- The whole entry ≈ one paragraph of text. A long session gets the same budget — cut, don't
  append; commits and memory carry the detail, this file carries the points.
- Still worth a bullet: what you deliberately did NOT build, and any pre-existing breakage you
  proved (so the next agent doesn't re-debug it). Numbers over adjectives.
- End with **Left open** — one line per unfinished item, so the next session inherits it.

Don't log routine reads, greps, or tool calls that changed nothing.
