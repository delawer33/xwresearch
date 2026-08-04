---
name: status-report
description: >
  Write a brief, human-readable summary of recent work across the ecosystem's ~30
  repos — repo names first, one line per theme, ~60 seconds to read. Use when the
  user asks for "today's report", "status report", "what shipped today", "summarize
  today's commits/work", or invokes /status-report. Default source is git history
  (the user's own commits); `/status-report from file` reads `DONE_TODAY.md` instead.
---

# Status report

A short, plain-English summary for someone who wasn't in the room — a teammate, the
client, future-you. **Brief and readable, not complete.** Not a changelog, not a
standup transcript. Target ~60 seconds of reading: 4-6 bullets total.

## Step 1 — pick the source from the argument

**No argument (default): git history, the user's commits only.** Scope is **today**
across every repo under `repos/`, unless the user names a date, range, or person.

```bash
cd repos
me=$(git config user.email)
for d in */; do
  repo="${d%/}"
  [ -d "$repo/.git" ] || continue
  commits=$(cd "$repo" && git log --author="$me" --since="<start>" --until="<end>" --oneline)
  [ -n "$commits" ] && { echo "=== $repo ==="; echo "$commits"; }
done
```

Read enough of each commit to summarize honestly — never guess from the subject line:

```bash
git show --stat --format="%B" <sha> | head -15
```

Caveat to state if it matters: **every agent session on this box commits as the same
identity**, so `--author` cannot separate the user's work from a concurrent session's.
If the day looks suspiciously full, say the report covers this box's commits.

Do **not** include uncommitted working-tree edits or server deploys in default mode.

**`from file` (or "from done_today", "use the file"): read the repo-root
`DONE_TODAY.md` and report only from it.** Don't pull, don't read git, don't verify
against repos — the file is the source of truth for that run. It records deploys and
uncommitted work too, and in this mode those belong in the report.

If a `from file` run finds no `DONE_TODAY.md`, say so and offer the git default.

## Step 2 — group by theme, then attribute to repos

Cluster into 4-6 themes a skimmer would recognize. One bullet per theme, even if it
took eight commits across three repos. Drop noise (typos, doc formatting) unless
nothing else happened.

Each bullet **opens with the repos it landed in**, in backticks, then an em dash,
then the plain-English what-and-why. Non-repo surfaces get a plain name (`VPS
scraper service`, `workspace tooling`).

## Step 3 — write it in this shape

Print it as chat prose — **not fenced in a code block** — so the markdown renders.

```
Today's work — <3-6 word theme> (<date>)

<One sentence: the throughline. No preamble.>

**Shipped & live:**

- `repo`, `repo` — what changed and why it matters, with the real numbers. Trade-offs
  stated in the same bullet, not softened.
- ...

**In progress:**

- `repo` (+ `dep-repo`) — what's being built, the one non-obvious mechanism, why.
```

Rules that keep it short and honest:

- **One line per theme, not per commit.** 2-4 lines max per bullet.
- **What changed and why it matters**, not the mechanism. "Cut ~1.7s off a 2.8s
  search" beats "removed a synchronous socket call."
- **Never name plans, issue numbers, tickets, ADRs, branch names, or slice IDs.** The
  reader has no repo access — "ran the #38 plan" tells them nothing. Say what the work
  did.
- **No commit hashes, no file paths, no code, no symbol names.**
- **Real numbers only** — quote them when the source has them, never invent one.
- **Keep the honest bad news.** A regression, a dip, a thing that didn't work is part
  of the report, in the same bullet as the win.
- Co-author trailers (`Cursor`, `Claude …`) are provenance — never surface them.

## Step 4 — the In progress section

In `from file` mode it comes from the file's own unfinished/left-open items — one
bullet each for the two or three that a reader would care about, not the whole list.
In git mode it comes only from what the **user tells you directly**; never infer
unlanded work from partial diffs or branch names. Omit the section if there's nothing.

## Worked example (`from file`)

```
Today's work — car-data soundness, safer scraping, fewer collisions (2026-08-03)

Several things that looked correct turned out measurably wrong, and got fixed with
numbers attached.

**Shipped & live:**

- `markibx`, `markibx-connect`, `mawtarx` — rebuilt the car catalog's generation
  structure: found why most generations were fake shells, retired 13 catch-alls for 55
  real generations, +54 makes / +1,392 models, unmatched makes 5.3% → 0.14%, dev
  listings 87.2% linked. Overall match dipped 66% → 62% — the old number leaned on
  those catch-alls.
- `mawtarx-connect`, `mawtarx-api`, `kara-api` — closed a data-integrity hole: a
  "demo" scraper test could make the live scraper fabricate fake cars into the real
  store, stuck on until restart. Now per-request.
- `VPS scraper service` — the scraper had been running a 5-week-old catalog library
  under an identical version number (weeks of stale vocabulary). Fixed, verified live.

**In progress:**

- `mawtarx-connect` (+ `xwsystem`, `xwapi`) — Kuwait next: stress-testing killed three
  assumptions, including the real blocker — one writer rejecting work under load, so
  parallel scraping would fail outright. Two shared-library pieces first, then a
  two-step rollout.
- `xwsystem` + workspace tooling — leases so 5+ concurrent agent sessions stop
  overwriting each other in one checkout; built, 95 tests green, not switched on.
```

## Output

Print the report directly in the response as rendered markdown — no code fence, no
artifact, no file written, unless the user asks to save or publish it.
