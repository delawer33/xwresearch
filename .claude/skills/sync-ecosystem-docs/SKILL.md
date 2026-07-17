---
name: sync-ecosystem-docs
description: >
  Reconcile the shared context docs of the karaa / markibx / mawtarx / xw* ecosystem
  after a session changed how the system actually works. Cleanly updates the root spine
  (CLAUDE.md = identity, ARCHITECTURE.md = the map, AGENTS.md = process, DECISIONS.md =
  why), docs/ (glossary, tool-index), and per-repo CLAUDE.md — fixing stale statements in
  place, never layering a second copy. Use when the user says "sync the docs", "update the
  docs", "reconcile the docs", "update the context", "the docs are stale now", or invokes
  /sync-ecosystem-docs — or at the end of a session that changed a cross-repo fact (what's
  live vs building, a dependency, a port, where something lives, a shared convention or term).
---

# Sync ecosystem docs

Keep the shared context an agent auto-loads TRUE, after a session changed the system.
Do the work; don't just describe it. This skill maintains the **shared spine**; for a
single new feature's usage doc + memory pointer, use `save-feature-docs` instead (and
this skill defers to it — see Step 2).

Paths below are relative to the **xwresearch root** (where `CLAUDE.md` and `docs/` live;
the repos are under `repos/`).

## Guiding principle: one fact, one home — reconcile, never layer

Every fact lives in exactly ONE doc; everything else points to it. The failure mode
this skill exists to prevent is **layering**: a fresh paragraph appended next to a
stale one, or the same fact copied into three files that then drift apart. When you
find the topic already documented, you **edit that place** — you do not add a second.

## Step 0 — Is anything doc-worthy? (do this FIRST)

Most sessions change nothing in the shared docs. Update them only when the session
changed a fact the docs assert or should assert:
- what's **live vs. being-built**, or a repo's status changed
- a **dependency direction**, port, package name, or "which repo do I touch for X"
- a **cross-repo mechanism** (how two repos talk)
- a **shared convention/workflow rule** or a recurring **term** (`AGENTS.md` / `docs/glossary.md`)
- a **platform lib** got adopted or dropped by product code (`docs/tool-index.md` Status)
- a **decision** — a tradeoff, a rejected alternative (`DECISIONS.md`)
- a **plan/report that landed** (→ archive it, Step 3)

If the change is repo-local implementation detail, a tiny tweak, or fully obvious from
the diff — **do nothing and say so.** Over-documenting rots faster than it helps.

## Step 1 — Detect and classify what changed

Look at the session's diffs across every touched repo (`git -C <repo> diff` / log).
For each real change, classify by which shared doc *owns* that kind of fact:

| Change | Owning doc |
|---|---|
| Live↔building status, dependency, port, package, "which repo for X" | `ARCHITECTURE.md` (the map) |
| How agents should *work*: a rule/convention that holds across all repos, workflow, tooling | `AGENTS.md` |
| A tradeoff/rejected alternative/constraint — *why* something is the way it is | `DECISIONS.md` (newest first) |
| A platform lib became used (or stopped being used) by product code | `docs/tool-index.md` (Status column, in place) |
| A recurring term / vocabulary agents re-derive | `docs/glossary.md` |
| Something true only inside one repo | `repos/<repo>/CLAUDE.md` |
| A single feature's usage (route/params/how-to) | → run `save-feature-docs`, not here |
| A plan/report whose work is now done+tested+committed | `docs/history/` (Step 3) |

`CLAUDE.md` (root) is **identity + triggers only** — calibration for how to think here. It is
the one auto-loaded doc, so it stays ≤ ~55 lines. Facts go in the files above; touch `CLAUDE.md`
only if a *calibration rule* itself changed (e.g. a new class of "the code lies about itself"
trap worth naming), never to record a fact.

## Step 2 — Update the ONE owner, in place

For each fact, before writing: **grep the topic across the docs first** (from the
xwresearch root):
`grep -rin "<topic>" CLAUDE.md docs repos/*/CLAUDE.md`

- **Found, and now wrong** → edit that line to the truth. Never append a corrected
  paragraph beside the stale one. If a doc's whole framing is obsolete, fix or remove
  it — don't bolt an addendum on top (this is how the pre-split root docs rotted).
- **Found, still right** → leave it; just make sure pointers to it aren't broken.
- **Not found, and doc-worthy** → add it to its one owner (above), as briefly as it can
  be stated. If another doc needs to reference it, **link** (`../../CLAUDE.md` from a
  repo, `docs/glossary.md` from the root) — do not copy the text.
- **Feature usage** → hand off to `save-feature-docs` (in-repo doc + CLAUDE.md pointer
  + memory). Don't reproduce that here.

Keep `ARCHITECTURE.md` a **map** that points down, and `docs/` files lean. If an edit makes a
file long, that fact probably belongs one level down (map → repo CLAUDE.md → deep doc), not
padded into the map. Root `CLAUDE.md` is the tightest budget of all — it is auto-loaded on
every request, so a fact almost never belongs there (see the note in Step 1).

## Step 3 — Archive landed plans

If the session finished a plan/report (work done, tested, committed): move the .md to
`docs/history/` (it keeps the paper trail without polluting the active set), and fold
any still-governing conclusion into the owning doc. Don't leave a "done" plan sitting
among active ones.

## Carefulness (this ecosystem has dirty code — do not launder it into docs)

- Write only facts you have **verified** (from a curated `CLAUDE.md`, confirmed code, or
  the user). Code existing is not proof it's canonical — much of markibx/mawtarx is
  scaffold, and scrapers don't run.
- If a fact hinges on code you're unsure is real/current, **ask the user — do not
  guess.** One wrong "fact" in a shared doc misleads every future agent.
- Low-token, important-only. No dumping file trees, no restating commit messages.
- The strict rule stays strict: `markibx ← mawtarx ← mawtarx-connect`, and the live
  product is the `karaa` stack — verify any claim against the root `CLAUDE.md` before
  you contradict it.

## Step 4 — Don't

- Don't create a new doc when an owner already exists — extend the owner.
- Don't copy a fact into a second file; link instead.
- Don't leave a stale statement standing next to the new one.
- Don't commit/push unless the user asked; report what you changed and where.

## Output

End with a short list: which docs you edited/created/archived and the one-line reason
each — or, if nothing was doc-worthy, one line saying so and why.
