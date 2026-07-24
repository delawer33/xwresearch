---
name: doc-diet
description: >
  Write or slim an agent-facing doc (a repo's CLAUDE.md, the root spine, a README) so it earns
  its tokens. Use when the user says "write a CLAUDE.md for X", "revise/rewrite these docs",
  "simplify the docs", "are the docs bloated", "this doc is too long", "review the docs" — or
  when you're about to author one yourself. Holds the doc principles; other doc skills point here.
---

# Doc diet

Agent-facing docs are paid per read, forever. **Length isn't the enemy — un-earned length is.**
A 42k-line repo starved on 37 lines is as broken as a root file bloated to 200.

## The one test

> **Would someone fixing a bug in this repo need this line?**

If the answer is "no, but it's interesting" — cut it. Docs rot fastest when written for the
author's record instead of the next reader's task.

## The principles

1. **Write for the agent with a bug, not for the record.** War stories, session narratives, and
   "how we discovered this" belong nowhere except the skill or decision they justify.
2. **Calibration beats description.** Don't say what the code already says — it's derivable and
   it rots. Say what *looks true and isn't*: the count that means something different from what
   you'd assume, the doc that calls itself authoritative and is half-stale, the class named `AES`
   that's XOR. That's the content only a doc can carry.
3. **Sacrifice grammar for density.** A doc is read by an agent, not graded by a teacher. Drop
   articles, subjects, and connective prose when the fragment says it faster — "XOR, not AES"
   beats "Note that this class actually implements XOR rather than the AES it claims to." Full
   sentences are a tax; pay it only when the fragment would be genuinely ambiguous.
5. **Never mirror the filesystem.** File-by-file / route-by-route tables rot on every commit and
   `ls` already does the job better. (A kara-api table once documented 2 deleted files and missed
   24 real ones.) Point at the code; don't inventory it.
6. **One fact, one home; link, don't copy.** Copies drift, and then you have N truths.
7. **Budget by read-frequency.** Cost = length × how often it's read. Root `CLAUDE.md` is paid on
   *every request* → ruthless. A repo `CLAUDE.md` is per-task → generous where it earns it. A
   reference doc is read rarely → it may stay long; just say what to trust in it.
8. **Triggers, not pointers.** "See also X" never fires. "Before you write any code, read X" does.
9. **Negative space is cheap and high-value.** "What does NOT exist here", "don't add engines
   here", "NOT `../kara-connect`". One line that stops a wrong path beats a paragraph describing
   a right one.
10. **Prune while you're in there.** Every edit is a chance to cut. Net-neutral or smaller, unless
    you can say what the growth buys.

## Shape of a repo `CLAUDE.md`

Roughly, in this order — skip anything that isn't true for the repo:

- **What this repo is** — 3-6 lines. Include its *real* weight (is it load-bearing or a shim?)
  and any name that misleads.
- **⚠️ The traps** — the things that look true and aren't. This is the highest-value section and
  usually the reason the file exists.
- **Key files** — only where the name doesn't tell you. Not an inventory.
- **How to write code here** — the local idiom (which router, which deps, which base class).
- **Gotchas** — silent failures, footguns, decisions you'd otherwise reverse.
- **What does NOT exist here** — the negative space.
- **Pointers** — README for install, skills for procedures, deep docs for reference.

## Slimming an existing doc

1. **Section-size it first**: `awk '/^## /{if(n)printf "%-44s %s\n",n,NR-s; n=$0; s=NR} END{printf "%-44s %s\n",n,NR-s}' FILE`
   The bloat is usually one or two sections, not everywhere.
2. **Hunt duplication across files**, not just within one:
   `grep -rl "<distinctive phrase>" . --include=CLAUDE.md` — if a fact appears 3+ times, it has
   no home. Give it one; make the rest link.
3. **Delete on sight**: filesystem mirrors, migration maps for finished migrations, install steps
   the README owns, prose restating a code comment (point at `file.py:line` instead).
4. **Verify before you keep.** A line you can't confirm against current code is a liability —
   check it or cut it. Sync first (`/pull-repos`); a stale checkout makes you delete real things
   and keep dead ones.
5. **Re-read the headings when done.** Whole sections go missing in a rewrite — including the
   one that mattered most. (A kara-api security warning vanished between draft and disk and was
   caught only by auditing `grep -n "^## "`.)

## Don't

- Don't inline a big reference doc's contents. Say what it is and **which half to trust**.
- Don't delete a long doc just for being long — judge it on whether it's true and read.
- Don't add a "why this changed" note to a repo that wasn't involved.
- Don't let two skills carry the same principle — this file is their one home.

## Output

Report a per-file line delta (`file: 143 → 141`) and, if anything grew, one sentence on what the
growth buys.
