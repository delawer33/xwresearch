# Done today — 2026-08-05

(2026-08-04's entry survives in git at `3f01b58`. This file was found 0-bytes at 19:11 — another
session had emptied it to start today's; this entry is the first written into it.)

## markibx — the backbone-before-LLM plan, measured then published

The question this session had to answer was strategic, not tactical: **will we have a good enough
backbone before any LLM work, such that ≥90–95% of GCC listings connect, without leaving debt for
other markets — and can trims + per-trim specs be filled afterwards?** Answer: yes, and the
numbers are in the PRD. 87.2% of real listings link today; the remaining gap is parse failures
(~698 `__unknown__` models, ~1,921 yearless rows ≈ 3.6pp), plus membership/alias residue (1–2pp).
Neither fix is GCC-specific, so nothing is owed to other markets later.

What was measured (2026-08-05, fresh, not from the stale 2026-08-02 audit):

- Spine: 100 makes / 4,924 models / 5,256 generations. **Spec depth 7%** (367 gens); 11,477 facts
  of which 3,546 are `manufacturer` alone. Trims: **3, on one generation.**
- 96% of models carry exactly one catch-all generation; 175 head nameplates have **no generation
  entities upstream at all** — that is the LLM-only wall, and it is why exact-gen ≥90% is
  explicitly *not* the pre-LLM bar. Model-or-better ("connect") is.
- Demand-weighted: 54.4% of head-listing nameplates carry some spec, and all of it is
  wrong-market (US EPA). The zero-spec set is exactly the GCC fleet — Patrol, Fortuner, Hilux,
  Prado, D-Max, Creta, Pegas, MG5, Territory, Emgrand.
- **markibx influences zero production prices today.** The pricing orchestrator's default is
  `inventory_comps` alone; the only catalog-fed method, `msrp_depreciation`, needs
  `original_launch_price_sar`, which exists on ~1 generation. A fact-check of another agent's claim
  came back: causal chain true, numbers stale, and two named facts wrong (`catalog_msrp` is not a
  pricing method; markibx#38's slices are already done and deployed).

Published: **markibx#51** (PRD) + 7 tracer-bullet slices — markibx-connect#3 (connect % and
demand-weighted spec-coverage KPIs), mawtarx-connect#18 (parser fixes), markibx#52 (year-window
fact scope), markibx-connect#4 (listing→candidate vote adapter), #5 (membership/alias top-up),
#6 (cohort corroborator + promotion driver), #7 (HITL: breadth run, deploy, acceptance ≥90%).
Six carry `ready-for-agent`; #7 does not, because the seed diff wants human eyes.

Decisions the grill locked, so the next agent does not relitigate them: cohort grain is
model×year on shells only; the write path is the existing ADR 0010 machinery (no second way into
the spine); thresholds ≥5 votes / ≥80% agreement / ≥2 distinct marketplaces at **eTLD+1** grain;
an 8-field allowlist (body_type, fuel_type, gearbox_type, drivetrain, doors, seats, cylinders,
displacement_l) with horsepower/trim/mpg/dims/price/mileage/condition excluded; facts land in the
listing's market layer, never global. The layer question was asked and answered **no xw\*
extraction** — this is car-domain logic.

`866b793` lands the one durable artifact: CONTEXT.md gains **year-cohort fact**, the term the whole
plan is written in.

## Implementation started, then stopped by request — nothing landed

Four slices ran in parallel worktrees on Opus (mx-52, mxc-3, mxc-4, mtc-18), then the owner said
stop. **Nothing was committed, nothing pushed, no live-store write, no deploy.** The work sits
uncommitted on its branches:

| Branch (worktree) | State when halted |
|---|---|
| `feat/mx-52-year-window` (markibx) | spine + seed loader edited; the seed **writer** was next |
| `feat/mxc-3-audit-kpis` (markibx-connect) | audit script + its unit test edited; tests next |
| `feat/mxc-4-vote-adapter` (markibx-connect) | new `listing_votes.py`, `listing_vocab.py`, driver, fixtures; fixture run next |
| `fix/mtc-18-parse-identity` (mawtarx-connect) | 4 source parsers + new `model_recovery.py` + captured fixtures; before/after audit next |

**Known defect in that WIP**, so nobody re-debugs it: `opensooq.py:207` references an undefined
`_source_of`. Resume before trusting anything in that tree.

Deliberately not built: the LLM depth sweep (last step, by standing rule), and #7's live re-sweep /
relink / deploy — parser agents were told to write the command sequence and defer, not to touch the
dev store.
