---
name: grill-with-docs
description: Grilling session that challenges your plan against the existing domain model, sharpens terminology, and updates documentation (CONTEXT.md, ADRs) inline as decisions crystallise. Use when user wants to stress-test a plan against their project's language and documented decisions.
---

<what-to-do>

Interview me relentlessly about every aspect of this plan until we reach a shared understanding. Walk down each branch of the design tree, resolving dependencies between decisions one-by-one. For each question, provide your recommended answer.

Ask the questions one at a time, waiting for feedback on each question before continuing.

If a question can be answered by exploring the codebase, explore the codebase instead.

</what-to-do>

<supporting-info>

## Placement & boundary gate (exonware repos — mandatory)

When the plan touches any repo under `repos/` and does any of: **add a dependency, create or
move a package, or introduce a new module/utility/helper/client**, the placement decision is
part of the grill — it must be resolved *before* the plan is called decided, not at
implementation time.

1. **Layer question first** (CLAUDE.md rule): does this belong in an `xw*` package before a
   product (`markibx`/`mawtarx`) or project (`kara`) repo? Ask it as a grill question with a
   recommended answer, and record the answer in the plan.
2. **Run the formal check**: [repos/docs/prompts/PROMPT_03_ROLE_04_PLACEMENT_BOUNDARY_CHECK.md](../../../repos/docs/prompts/PROMPT_03_ROLE_04_PLACEMENT_BOUNDARY_CHECK.md)
   — seven questions (package earned? dependency direction? responsibility boundary?
   tech-agnosticism? lean install? version agreement? dual-core layout?). Present the verdict
   — **Pass / Findings / Block** — as a grill question with your recommendation. **Block is a
   successful outcome**, not a failed grill: it is cheaper now than after the dependency spreads.
3. **"Never reinvent" is question zero**: check `docs/tool-index.md` and `xwsystem` before the
   seven — if the thing already exists, neither the dependency nor the module is earned.
4. When the decision lands, write the verdict to the target repo's
   `docs/logs/reviews/REVIEW_<YYYYMMDD>_PLACEMENT_<package>.md`.

Workspace caveat: the prompt cites Windows monorepo paths (`00_GLOBAL/.tools/...`,
`check_tech_agnostic.py`) that do not exist in this Linux checkout — answer the seven questions
from the actual code under `repos/*` and `ARCHITECTURE.md`, don't chase those paths.

Rare case — plan calls an LLM: grill pinned model, output schema + validation, verify step
before state writes. Read `repos/docs/guides/GUIDE_16_AI_NATIVE.md` then; xwai#2 blocks the
structured-output path.

## Done bar (mandatory — the last question before the plan is "decided")

Always end the grill with: **"What number, measured where, proves this worked?"** — with your
recommended answer. A plan without one isn't decided. This bites hardest in the data repos
(`markibx`/`mawtarx`): changes look fine locally, take days or a full sweep cycle to prove,
and a wrong one silently poisons stored rows (a broken normaliser once marked 3,000/3,000
listings SOLD while every gate passed; a purge once reported success and didn't stick).

The answer needs four parts:

1. **Metric + scope + threshold + when** — "AE real-verdict share on the *prod* store ≥20%
   after the next sweep", never "pricing improves". Name the store: local ≠ prod.
2. **Baseline, measured first** — the metric's current value before any code. Unknown baseline →
   measuring it becomes the plan's first bullet. Never fix from an audit alone.
3. **Counter-metric** — the number whose move in the wrong direction means the change broke
   something else (rows priced ↑ but median confidence ↓; seen-set size collapsing). Data
   pipelines fail silently; the done bar must catch the failure, not just confirm the success.
4. **Cost of being wrong** — if proof takes a sweep cycle or a mistake writes bad rows to the
   store, say so in the plan: it changes the rollout (one source first, sample first, dry-run
   diff before store writes).

Record the answer in the plan. It flows downstream unchanged: `/design` **Done when** →
`/to-issues` acceptance criteria → `/orchestrate` done condition.

## Domain awareness

During codebase exploration, also look for existing documentation:

### File structure

Most repos have a single context:

```
/
├── CONTEXT.md
├── docs/
│   └── adr/
│       ├── 0001-event-sourced-orders.md
│       └── 0002-postgres-for-write-model.md
└── src/
```

If a `CONTEXT-MAP.md` exists at the root, the repo has multiple contexts. The map points to where each one lives:

```
/
├── CONTEXT-MAP.md
├── docs/
│   └── adr/                          ← system-wide decisions
├── src/
│   ├── ordering/
│   │   ├── CONTEXT.md
│   │   └── docs/adr/                 ← context-specific decisions
│   └── billing/
│       ├── CONTEXT.md
│       └── docs/adr/
```

Create files lazily — only when you have something to write. If no `CONTEXT.md` exists, create one when the first term is resolved. If no `docs/adr/` exists, create it when the first ADR is needed.

## During the session

### Challenge against the glossary

When the user uses a term that conflicts with the existing language in `CONTEXT.md`, call it out immediately. "Your glossary defines 'cancellation' as X, but you seem to mean Y — which is it?"

### Sharpen fuzzy language

When the user uses vague or overloaded terms, propose a precise canonical term. "You're saying 'account' — do you mean the Customer or the User? Those are different things."

### Discuss concrete scenarios

When domain relationships are being discussed, stress-test them with specific scenarios. Invent scenarios that probe edge cases and force the user to be precise about the boundaries between concepts.

### Cross-reference with code

When the user states how something works, check whether the code agrees. If you find a contradiction, surface it: "Your code cancels entire Orders, but you just said partial cancellation is possible — which is right?"

### Update CONTEXT.md inline

When a term is resolved, update `CONTEXT.md` right there. Don't batch these up — capture them as they happen. Use the format in [CONTEXT-FORMAT.md](./CONTEXT-FORMAT.md).

`CONTEXT.md` should be totally devoid of implementation details. Do not treat `CONTEXT.md` as a spec, a scratch pad, or a repository for implementation decisions. It is a glossary and nothing else.

### Offer ADRs sparingly

Only offer to create an ADR when all three are true:

1. **Hard to reverse** — the cost of changing your mind later is meaningful
2. **Surprising without context** — a future reader will wonder "why did they do it this way?"
3. **The result of a real trade-off** — there were genuine alternatives and you picked one for specific reasons

If any of the three is missing, skip the ADR. Use the format in [ADR-FORMAT.md](./ADR-FORMAT.md).

</supporting-info>
