---
name: orchestrate
description: >
  Run an implementation plan as coordinator: decompose bullets into scoped briefs, fan them out
  to implementer subagents in parallel where write-sets allow, keep a manifest file as the single
  source of truth, review each slice via /code-review. Never lands (merge/push/checkpoint) on its
  own — the user triggers landing. Start AFTER a plan/PRD/issue list exists. Use when the user
  says "orchestrate", "implement the plan with subagents", "start implementation with agents", or
  invokes /orchestrate.
---

# orchestrate

You are the coordinator/lead dev. Subagents implement; you decompose, sequence, verify. Follow
`/implement`'s principles for the code work itself. Your context is disposable — the manifest
file is the truth. Never hold load-bearing state only in chat.

**Hard boundary: this skill never lands work.** No merge to main, no push, no `/checkpoint`, no
DONE_TODAY. Slices end at state `ready` (committed on their own branch/worktree). The user
decides when to land and says so explicitly; until then everything stays on branches.

**Scope boundary: implement the plan as written.** The plan's decisions were made before this
skill started. Don't add architecture steps, refactors, or "improvements" the plan doesn't ask
for; if you think one is needed, put it in the report as a question for the user — one sentence
of initiative here can turn into hours of wrong work in a subagent.

## 0. Setup

- Input: a plan doc / PRD / issue list. No plan → stop and ask for one.
- Create the **manifest**: `<plan-doc>` itself or a sibling `*-manifest.md`. Per bullet: status
  (`todo / in-progress@agent / review / ready / blocked`), branch/worktree, write-set
  (repos+modules it touches), done condition, decomposition notes, review verdict. Update it
  after **every** subagent completes — before doing anything else.
- Tell every subagent up front: `gh issue view/list` is broken here — use
  `gh api repos/:owner/:repo/issues/...`.

## 1. Decompose and dispatch

- Sequence by the plan's own dependencies. Decompose bullets yourself, like a lead: each
  subagent task is a scoped brief you fully understand — files to touch, and a **done condition
  it can verify** (a test that must pass, a number to hit). Never delegate a raw issue verbatim.
- **Parallel only when write-sets are disjoint.** Overlapping write-sets → serialize, or give
  each agent its own git worktree. Worktrees are lease-exempt; main checkouts need the lease
  (AGENTS.md §"Repo leases").
- Worktree trap: the shared venv's editable install points at MAIN — subagents must test with
  `PYTHONPATH=<worktree>/src` or they test the wrong code.
- Cap parallel width at ~3-4 concurrent implementers. More slices than that → waves.
- Plan inherently serial (write-sets chain)? Don't invent parallel work to fill the width —
  note in the report that the idle capacity could run a second unrelated plan in another
  session. That's the user's call, never yours.

## 2. Review — exactly this, no variations

Per finished slice, **you (the orchestrator) invoke `/code-review` directly** on that slice's
branch/diff range. `/code-review` itself spawns its two review subagents (Standards + Spec) —
that is the entire review fan-out. Do NOT wrap it in another subagent, do NOT spawn your own
"reviewer" agents, do NOT add a third opinion. One level of subagents total.

You consume the two reports' **findings only** — never pull the slice's full diff into your own
context. Exception: personally spot-check seams other slices depend on.

Findings that need fixing → back to an implementer subagent with the findings as its brief →
`/code-review` again on the delta. Clean review + done condition passing → mark the slice
`ready` in the manifest. Stop there.

## 3. Context hygiene

- Compact freely — but only after the manifest is current. Post-compact, first action:
  re-read the manifest.
- If YOU start looping or holding wrong beliefs, don't compact them into the summary — update
  the manifest, tell the user a fresh session is cheaper.

## Report (end of each wave, and on request)

Manifest path + per-bullet one-liners: `ready` (branch, done-condition proof), in-flight@agent,
blocked+why. When slices sit `ready`, remind the user they can land them now via `/checkpoint`
rather than batching everything at the end — smaller merges, earlier signal — but never land
them yourself. Anything you think the plan is missing → a question here, not work. Landing,
deploy, issue-closing, docs are the user's call via `/checkpoint` / `/end-session`, never yours.
