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

## The loop

1. **Get today's real date** — run `date +%F`. Do not trust the date in your context.
2. **Read the `# Done today — YYYY-MM-DD` heading** at the top of `DONE_TODAY.md`.
3. **Compare:**

   - **Heading is today** → **append**. Add your work under a new `##` section, or extend an
     existing section if it's the same thread. Leave everything already there alone.
   - **Heading is older** → **stop and ask.** That file is the previous day's record and
     rewriting it destroys it. Ask the user whether to archive it or overwrite, and say what
     date it currently holds. Only rewrite after they answer — then replace the whole file with
     a new heading carrying today's date.

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

## What to write

Brief. What changed and what you learned that isn't obvious from `git log` — a verified fact
about the running system, a root cause, a doc that turned out stale. Numbers over adjectives.

Keep a **Left open** section at the end for anything unfinished, so the next session inherits it.

Don't log routine reads, greps, or tool calls that changed nothing.
