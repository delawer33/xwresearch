---
name: design
description: Turn a decided PRD or plan into a program design — file placement, signatures, call-stack sketches, and test shape as human-scannable code blocks — before splitting into issues. Exonware-adapted (layer question, tool-index reuse gate, multi-repo write-sets that feed the /orchestrate manifest). Use when the user wants a design pass, says "design this", or after a grill/PRD and before /to-issues.
---

# design

Turn a decided PRD into a **program design**: the structure of the change, written so a human
can review it in minutes. A PRD says what the system should do; this doc says what code will
exist — which repos and files, which signatures, which call path, which tests. The issue
breakdown and the `/orchestrate` manifest then derive from it mechanically.

**Why this exists:** reviewing diffs is the expensive part of agent-driven work. A wrong design
caught here costs a re-draft; caught in review it costs every diff built on it. This doc is the
cheapest artifact the human can veto.

**When to skip:** single-file fixes and changes with no new structure — say so and stop.
Anything multi-module, multi-repo, or headed for `/orchestrate` needs the pass.

## Process

### 1. Gather the source

Work from the PRD or decided plan in context, or a path/issue the user passes. Issue refs:
`gh api repos/exonware/<repo>/issues/<n>` — **never `gh issue view`/`gh issue list`**, they're
broken here. Design only settles *structure*; if behaviour is still undecided (open grill
branches), stop and send the user back to `/grill-me` — don't make product decisions here.

### 2. Placement before structure (exonware — mandatory)

Before drawing a single file tree, settle **where** each piece lives:

1. **Question zero — never reinvent:** check `docs/tool-index.md` and `xwsystem`. If a helper,
   client, parser, or utility the design needs already exists, the design *uses* it — designing
   a fresh one is the Reinvented Tool smell, caught here instead of at review.
2. **Layer question** (CLAUDE.md rule): does each piece belong in an `xw*` package before a
   product (`markibx`/`mawtarx`) or project (`kara`) repo? Priority **xw > product > project**.
   Record the answer per piece in the design doc.
3. If the design **adds a dependency, creates/moves a package, or introduces a new module**,
   run the formal gate:
   [repos/docs/prompts/PROMPT_03_ROLE_04_PLACEMENT_BOUNDARY_CHECK.md](../../../repos/docs/prompts/PROMPT_03_ROLE_04_PLACEMENT_BOUNDARY_CHECK.md)
   — record the Pass / Findings / Block verdict in the doc. **Block is a successful outcome.**
   (Ignore the prompt's Windows monorepo paths — answer from actual code under `repos/*`.)

Rare case — a slice calls an LLM: design in pinned model, schema-validated output, verify step
before state writes. Read `repos/docs/guides/GUIDE_16_AI_NATIVE.md` then; xwai#2 blocks the
structured-output path. Ship-time artifacts (`REF_16_AI.md`, `llms.txt`) belong to the shipping
change, not the design.

### 3. Explore the code at the seams

Repos may be stale? `git fetch` + report behind-counts and ask the user to run `/pull-repos`
(it's user-triggered only — never invoke it yourself) — designing against unsynced code
produces confident nonsense. Then read the actual code the design touches: the **callers** of anything
you'll change, the **implementation** of anything you'll depend on. In this workspace code and
names lie — registered connectors don't run, whole surfaces are stubs; a claim about current
behaviour is a hypothesis until you've read it. Use `docs/glossary.md` terms in every name and
signature. Prefer deep modules — much functionality behind a small, stable, isolation-testable
interface.

### 4. Draft the design

One section per vertical slice (same slicing `/to-issues` will use). **Code blocks, not
prose** — the reader scans signatures, not paragraphs. Signatures and stubs only, never
implementations: writing function bodies means you've left design.

<design-template>

# Design: <feature>

Source: <PRD/plan/issue ref>. Status: draft | reviewed.
Placement: <per piece: target repo + layer answer; gate verdict if the gate ran>

## Slice N: <name>

**Write-set:** `<repo>`: <modules/files created or edited> — per repo when the slice spans
repos. This is the parallelism key `/orchestrate` copies into its manifest.
**Depends on:** slice M / none.

### File placement

```
repos/mawtarx/src/exonware/mawtarx/pricing/
├── floor.py            NEW
├── engine.py           EDIT (call floor before verdict)
repos/mawtarx/tests/
└── test_floor.py       NEW
```

### Signatures

```python
class FloorVerdict(Enum):
    PRICED = "priced"
    INSUFFICIENT_DATA = "insufficient_data"

# Applies the comp-count floor. Pure; no store access.
def apply_floor(comps: list[Comp], min_comps: int) -> FloorVerdict: ...
```

### Call stack (main path)

```
engine.price_row()
└─ apply_floor()            NEW
   └─ (verdict gates) estimator.estimate()   existing
```

### Test shape

```
test_floor.py
├─ fewer comps than floor → INSUFFICIENT_DATA, no estimate emitted
├─ exactly at floor → PRICED
└─ verdict recorded on the row (integration, store-backed)
```

**Done when:** <verifiable — these tests pass, and/or a number to hit, e.g. "real-verdict share
on the AE sample rises from 1.8% to ≥20%">

</design-template>

Design the **main path plus the failure modes that shape the interface** — not every branch.
A product question the PRD doesn't answer goes under `## Open questions` and gets flagged in
review — never silently decided.

### 5. Design review — the point of the skill

Present slice by slice and ask directly:

- Is anything in the wrong repo or layer? (placement is the exonware failure mode)
- Would you rename anything? (a name that needs explaining is a design smell — and check it
  against `docs/glossary.md`)
- Is any signature missing a case you know is coming — or carrying speculative generality for
  one that isn't?
- Do the write-sets look right, and are the slice dependencies real?

Iterate until the user approves, then mark `reviewed`. This review replaces hours of diff
review later — don't rush past it.

### 6. Write the doc

Save it next to its PRD — `wayfinder/<feature>/` or the target repo's `docs/` — named after the
feature. This is a **build-time artifact**: its paths and signatures go stale by design; it's
consumed by the implementation cycle it belongs to, then superseded by the code. Don't let
long-lived docs (PRDs, ADRs, ARCHITECTURE.md) copy paths from it.

## Downstream

- `/to-issues`: one issue per slice; body references its design section, **Done when** becomes
  the acceptance criterion.
- `/orchestrate`: manifest columns (write-set, done condition, depends-on) copy straight from
  the slices; disjoint write-sets = parallel dispatch.
- `/code-review`: the design doc is a spec source for the Spec axis — sharper than issue prose.
