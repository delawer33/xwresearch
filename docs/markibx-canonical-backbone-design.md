# markibx canonical backbone — design (WS2, in progress)

> **Status: DESIGN, not built.** Decisions captured during a design grill (2026-07-23).
> These graduate into `docs/glossary.md` (terms) and `DECISIONS.md` (committed decisions)
> only when code lands. Until then, treat as intent, not fact.

## Problem (verified live 2026-07-23)

markibx.com catalog is **wide but unusable as a spec source**: ~9,634 vehicles / 556 makes,
but ~5% spec-field completeness, provenance/confidence 0.0, and heavy make/model
fragmentation (e.g. `Toyota|Camry` vs `Toyota|Camry Classical` vs `Toyota|Aurion`). Only the
two free sources (NHTSA vPIC + Wikidata) have ever run, on-demand, no crawler. Consumer
(mawtarx) links listings by `catalog_key` and can't reliably resolve → the fragmentation is
what mawtarx's intelligence audit blamed for ~36% of estimate error.

Scope is **global market**, not KSA/GCC — global breadth is intended, not noise.

## Decisions

- **D1 — Canonical registry above the rows.** Introduce a canonical make-registry +
  model-registry as the identity spine. Raw source strings *resolve into* canonical make/model
  IDs; `catalog_key = make|model|year|trim` becomes **derived** from the canonical IDs, not the
  raw strings. (Rejected: cleaning strings in place — can't express a *mapping* between two
  different names like Aurion→Camry, only fix typos.) `brands.py` is the seed of the make
  registry.

- **D2 — Canonical-car boundary = single-market buyer perception.** Two rows are the same
  canonical car iff a buyer in *one* market would see them as one car.
  - Cross-market renames (Versa/Sunny) and cross-make clones (GT86/BRZ/FR-S) → **one** canonical
    car, carrying regional + per-make **nameplate aliases** (reuse the existing slug/display
    pattern: stable `slug`, regional `display`).
  - Products that **coexisted as distinct cars in one market** (Aurion-V6 beside Camry-4cyl) →
    **separate** canonical cars, linked as platform-siblings, not merged.
  - Test is NOT "same name" or "same platform" — it's "one car or two on the showroom floor?",
    which is also what makes mawtarx comparable-pooling correct.

- **D3 — Registry backs `markibx.normalize`; it does not replace it.** Verified: markibx
  already owns normalization and mawtarx consumes it — `mawtarx.catalog_link` imports
  `canonical_make/canonical_model/slugify` from `markibx.normalize`; the alias tables were
  moved mawtarx→markibx on 2026-07-06 (S1) precisely to stop the two engines drifting.
  So the registry is an **internal upgrade behind the existing seam**: `normalize` stays the
  single entry point and becomes a resolver (raw string → canonical_id) over the registry;
  the hardcoded `MODEL_ALIASES`/`MODEL_TRIM_RULES` become registry data (aliases-with-
  provenance, incl. the D2 nameplate-alias sets). Consumers change nothing. (Rejected:
  consumers query a new registry directly — reintroduces the S1 drift.)

- **D4 — Authority-first seeding; resolve auto, create gated.** Makes: registry = `brands.py`
  (already has IDs); observed makes resolve in, unmatched queue for review, never auto-create.
  Models: no authority today (`canonical_model` only runs partial alias/trim rules; unmatched
  models pass through unnormalized = the fragmentation source). Seed a canonical model directory
  from a **global authoritative reference** (Wikidata + NHTSA make→model directories, one-time
  dedup pass), then resolve observed strings into it. **Load-bearing rule:** resolution into the
  canonical set is automatic (confidence-thresholded); creation of a canonical entity is
  human-gated. (Rejected: clustering canonical identity out of the observed noise — bakes in
  false-merge + false-proliferation permanently.)

- **D5 — Human gate = the existing moderation queue, fed by the resolver.** `markibx-api`'s
  `ContributionsStore` already has `KINDS=(spec_value, correction, new_entity, source_pointer)`,
  pending/approved/rejected + reviewer + counts badge, "lands as pending, no direct catalog
  write." Reuse it: confident resolution auto-links (no queue); unconfident/unmatched → the
  resolver emits a pending `new_entity` (new canonical car) or `correction` (merge/alias into an
  existing car). Delta over today = the resolver becomes a *producer* of pending contributions
  (queue is human-submitted only now). Threshold starts conservative, tuned by observed
  false-merge rate — a setting, not a hardcoded constant.

- **D4a — Model matching is containment-aware; superstring ⇒ gated merge (validated by
  prototype).** A logic prototype (`prototypes/markibx-backbone/`, run `python3 tui.py --demo`)
  drove D3–D6 by hand and surfaced a trap: whole-string similarity **mis-scores the dominant
  fragmentation pattern**. `Camry Classical` vs `Camry` scores only ~0.50 (the extra word swamps
  the ratio), so a single-threshold resolver files it as a **new_model** — creating a *fourth*
  Camry variant, the opposite of the goal — while the genuinely-distinct `Aurion` sits at 0.36. A
  lone scalar can't tell "same nameplate + descriptor" from "different car." Fix: matching tracks
  **token containment** as a separate axis, and `resolve_model` has **three** outcomes, not two —
  auto-link (near-exact/alias/typo), **gated `merge` proposal** (candidate nameplate ⊆ raw tokens,
  *or* strong-but-uncertain fuzzy; a superstring **never** auto-links because aliasing is an
  identity change per D2/D5), and `new_model` (nothing close). The claim/conflict engine (D6) was
  driven the same way and **needed no change** — the tier ceiling already delivers gap-fill-only.

## Branch 1 (identity) — CLOSED. D1–D5 above.

- **D6 — Wire the existing provenance/conflict framework BEFORE any depth source.** Big finding:
  the whole trust/provenance/conflict system already exists in code, **unwired** — `TRUST_TIERS`
  (`official-registry > oem > canon-game > community > user`, each with a confidence ceiling),
  `conflict.resolve_field(field, claims)` (lower source-priority wins, ties on confidence,
  keeps all claims), and `VehicleSourceRef` per-field provenance in `model.py`. The **live**
  catalog (`catalog.py CatalogVehicle`, sparse attrs) carries none of it — that's why prod
  confidence is 0.0. Depth-before-provenance would let a seller-typed listing overwrite an
  authoritative NHTSA value (trading emptiness for corruption). So the corrected order is
  **identity → wire provenance/conflict into the live catalog → depth pours claims through
  `resolve_field`**. This is wiring, not building. (Rejected: get data in first, retrofit
  provenance later.)

## Corrected sequencing
1. Identity backbone (D1–D5)
2. Wire provenance/trust/conflict into the live catalog (D6) — safety substrate
3. Depth: claims flow through the resolver (branch 2 below)

- **D7 — Listing write-back = mawtarx-side consensus push at lowest tier, ungated.** Direction
  forced by the dependency rule (markibx never imports mawtarx): a **mawtarx-side reconciler
  pushes to markibx-api over HTTP** (no such client exists today — the CLAUDE.md loop is
  unbuilt). Group listings by `catalog_car_id` (already set by `catalog_link`), take modal value
  per **whitelisted field** (`body_type/fuel_type/transmission/drivetrain/engine/cylinders` —
  listings carry these; NOT dims/power), emit one `FieldClaim` per (canonical car, field),
  confidence = f(agreement, volume). Enter at **lowest trust tier** so `TRUST_TIER_CEILING`
  makes it **gap-fill only** — never overrides official/OEM. Spec claims are **not** human-gated
  (the queue is for identity create/merge only); the trust math makes them safe. Cadence: batch,
  piggyback the sweep cycle.

## Open questions (grill in progress) — branch 2 (depth)

- **D8 — Source→trust-tier map.** `official-registry`: NHTSA vPIC + government open-data (EPA,
  RDW, KBA, EEA, Transport-Canada, DVLA) — free *and* top-tier for the fields they cover.
  `oem`: CarAPI/JATO/Auto-Data/ChromeData (keyed, future). `community`: Wikidata + Wikipedia/
  DBpedia (structured but crowd-edited — must lose to government on the same field; ceiling
  caps it). `user`: listing write-back + unreviewed contributions (gap-fill). Per-field
  authority (EPA=US fuel-econ, RDW=EU dims) via `conflict.py`'s within-tie `SourcePriority` is
  a **lazy refinement**, added only where a real conflict appears — not a matrix built up front.

- **D9 — Timer, not daemon.** Car facts are durable (a 2022 Camry's specs never change);
  listings are ephemeral (mawtarx needs an always-on crawler, markibx does not). Continuous
  depth already arrives free via D7's write-back (piggybacks mawtarx's sweep, no markibx
  process). Source refresh (NHTSA/Wikidata/EPA/RDW) runs the existing `pull_car_sources` on a
  **low-frequency systemd `.timer`** (~weekly) + a targeted pull on new-model-year. Needs a new
  console entry-point (`markibx-connect` has none today — `[project.scripts]` empty), a
  `markibx-connect/deploy/*.timer`, and a `vps-current-state.md` row. Deliberate asymmetry with
  `mawtarx-scraper-runner` (`.service`), justified by data durability. (Rejected: always-on
  daemon for symmetry — pure waste on near-static data.)

## Design tree — CLOSED (D1–D9)

**Branch 1 identity:** registry above rows (D1), single-market-perception boundary (D2), backs
`normalize` (D3), authority-seeded + resolve-auto/create-gated (D4), gate = existing moderation
queue fed by resolver (D5).
**Substrate:** wire the existing (unwired) provenance/trust/conflict framework into the live
catalog first (D6).
**Branch 2 depth (no money):** listing write-back as low-tier consensus push (D7); source map
with government-free at top, Wikidata capped community (D8); timer-driven refresh (D9).

## Explicitly deferred (NOT in this design)
- **Generation as an inheritance layer** — high value but phase-2, arrives with the keyed depth
  sources that carry generation data. Backbone here is make→model→year; generation slots in later.
- Keyed/paid sources (CarAPI/JATO/Auto-Data) — optional accelerator, not a dependency.
- Exact thresholds, reconciler cadence, entry-point names — build-time, not design.

## On landing → promote
When code lands, D1/D2 (identity model + boundary) and D6 (provenance-first) each warrant a
`DECISIONS.md` entry; the resolved terms (canonical car, canonical make/model registry,
nameplate alias) graduate into `docs/glossary.md`. Until then this doc is intent, not fact.
- Generation as an inheritance layer (deferred to depth phase).
- Depth without money: listing write-back + free adapters + deeper Wikidata (branch 2).
- Provenance + freshness (branch 3).
