# DECISIONS.md — why things are the way they are

Append-only. Newest first. One entry = one decision that a future agent would otherwise
re-litigate or accidentally reverse.

**Write an entry when** you make a call that the code can't explain on its own — a tradeoff, a
rejected alternative, a constraint you discovered the hard way. **Don't** write one for
implementation detail the diff already shows.

**Format:** date · what was decided · why · what it supersedes · where the code lives. Keep it
to a few lines — link the deep doc, don't inline it.

---

## D-018 — cross-field car physics lives in the markibx core, and the depth engine got its driver

**2026-08-04 · markibx-connect#1** — Two calls a future agent would otherwise reverse.

**1. The fuel-economy coherence rule belongs to the core, not to the ingest that had the bug.**
`combined` is a 55/45 blend of city/highway, so it must lie BETWEEN them — a *cross-field* rule
that no per-field validator (`car_spec`, `PlausibilityValidator`, `fact_merger`'s tier guard) can
express. Two callers in two repos need it: the EPA harvest (markibx-connect) and the ADR 0010 LLM
promotion path (markibx). Putting it in the ingest would mean either duplicating the physics or
letting the LLM path promote what the ingest refuses, and the layer cascade runs core → connect.
Home: `markibx/fuel_economy.py`, enforced in the seed gate (4th soundness rule), in
`PromotionWriter.promote` (refuses, `blocked`), and by the EPA aggregation. **Rejected: the
`city ≤ combined ≤ highway` form the issue specified** — that ordering is a combustion habit, and
an EV's city MPGe is legitimately the highest of the three; measured on the seed it flags 46 rows
of which only 10 are broken, so it would have withdrawn 36 correct electric generations.
Repo-local detail: markibx ADR 0014.

**2. The ADR 0010 depth engine is runnable, which updates D-016's "built but not run" note.** Its
missing `ILlmClient` + entry point now live in markibx-connect (`llm_depth.py`,
`scripts/run_depth_extraction.py`). Still **not run at scale** — a full sweep is 1,623 × 3 = 4,869
API calls and needs `$MARKIBX_LLM_API_KEY`. Two constraints that are decisions, not details:
**temperature must be > 0** (0 makes N "independent" samples identical, so self-consistency
promotes on one assertion — the client refuses it), and **the ask is restricted to
market-invariant fields** (mpg/CO₂ are outputs of a regulator's test cycle, so staging them in the
`global` layer would assert EPA's cycle as universal).

Code: markibx `1d245c6`, markibx-connect `8155438`. **Deployed to the dev VPS 2026-08-04** (both
venvs; verified via `/catalog/resolve` — `toyota:camry:xv50` no longer serves any mpg field).

## D-017 — concurrent agents: worktrees by default, scoped leases on the main checkout

**2026-08-03 · repo-lease system** — 5+ sessions run against `repos/*` at once, and two agents in one
main checkout corrupt each other through *git state*, not through files: the index and `MERGE_HEAD`
are repo-wide even when the edits are disjoint. Decided: **worktrees stay the normal way to work**
(no coordination needed — own index, own HEAD), and leases cover only the main checkout. Within it,
a **section** lease (the file's directory, or the file itself in a flat dir like
`mawtarx-connect/providers/`, 663 siblings) lets non-overlapping work proceed — the ~80% case — while
a **vcs** lease serialises git commands and a **merge** lease makes the repo exclusive while a
transition is in flight.

**Rejected:** section-only granularity with no git rule (unsafe — a "small change" agent's bare
`git commit` commits another agent's half-resolved merge), and worktree-everything (a 3-line doc fix
shouldn't cost a checkout, and the shared `repos/.venv` editable installs point at *main*).
**The rule that makes concurrency safe is the pathspec:** `git commit -- <paths>` ignores whatever
else is staged, so index-wide git commands are refused while someone else holds a section.

Undecidable cases (shared files like `pyproject.toml`) return **ASK-OWNER** rather than guessing;
the owner's verdict is recorded once in `.claude/locks/decisions.jsonl`. Fails **open for edits,
closed for destructive git** — an unprotected edit costs a merge conflict, an unprotected merge
costs a commit. Primitive: `xwsystem` `io.LeaseRegistry` (P1, stdlib-only, path-loadable because
`import exonware.xwsystem` costs ~1.4s — itself a violation of AGENTS.md:132, filed as
[xwsystem#6](https://github.com/Exonware/xwsystem/issues/6)). Policy: `scripts/repo_lease.py`.
Protocol: `AGENTS.md` §"Repo leases".

## D-016 — catalog membership widened to Wikidata reality; a curated-gate keeps it from fragmenting curation

**2026-07-30 · breadth run + deploy** — ran the live Wikidata membership widening across all 45
makes (`markibx-connect/scripts/ingest_membership_widening.py --live`): **249 → 3,754 generations /
3,533 models**, every new row an identity-only shell (QID-anchored, idempotent). Deployed to the dev
VPS (markibx core into both markibx-api + mawtarx-api venvs). This is #4/#10 — the breadth D-015
called unbuilt is now built.

- **Curated-gate (the load-bearing call):** a naive full run *fragmented* curated identity — it
  injected codeless QID-shells under 101 already-curated models (Accord +13, …) and split variants
  ("Camry Hybrid") into their own models. Fix: every Wikidata entity is run through
  `CanonicalRegistry.match_model` (D-015's seam); anything that folds into a curated model is
  **skipped** (345 skipped), only the uncurated tail is created — ADR 0002 (matching decides
  new-vs-existing, never creates identity). Rejected: blind full-run (fragments); accept-and-update
  guard-tests (degrades resolve).
- **QID pins:** `resolve_manufacturer_qid` mis-anchors (Ford→surname Q11247279, Mitsubishi→parent
  conglomerate) and misses Hyundai/Suzuki/Skoda/Dongfeng, so the runner carries 7 verified
  `MANUFACTURER_QID_PINS`; Jaecoo/Rox stay unresolved (too new for Wikidata).
- **Depth is still 0%** — LLM candidate-corroboration (ADR 0010) is built but **not run** (postponed
  by choice). Non-LLM depth harvesters (`spine_ingest/{dbpedia_year_ranges,epa_specs,nhtsa_dimensions}`,
  `sources/*`) exist but haven't run across the breadth — that's the next step, year-ranges first.

Code: markibx `1408320`, markibx-connect `2238ff3`. Completes D-015's "unbuilt" note.

## D-015 — the legacy flat catalog is retired in code; the spine is the only catalog

**2026-07-29 · implementation + deploy** — markibx ADR 0003's hard break (D-014 above) is **built
across all repos and DEPLOYED to the dev VPS**. Deleted: `markibx/catalog.py` + `store_catalog.py` +
`catalog_seed.py` + `catalog_entity.py` + `catalog_specs_seed.py` and every `CatalogVehicle`/
`CatalogCar`/`ICatalogStore`/`catalog_key`/`resolve_car`/`flatten_car`/`seed_top_ksa_models`/
`CATALOG_PROVIDERS` export; markibx-connect's connector-into-legacy-store pipeline
(`wikidata_catalog`, `catalog_pipeline`, `launch_price`, the CatalogVehicle-builders in
`nhtsa_catalog` — VIN decode kept). Consumers rewritten spine-native: markibx-api/mawtarx-api
`routes/catalog.py` (resolve+browse, no flat surface), all three APIs' `state.catalog` is now a
`CanonicalRegistry` (`build_seed_registry()`, data-as-code), kara-api dropped `MawtarxCatalogStore`.

- **P3:** `mawtarx/catalog_link.py` links listings through the spine's `resolve()` seam
  (precision ladder exact→generation→model; `catalog_car_id` holds a spine node id, not a
  `catalog_key`). `catalog_msrp` reads launch price via `resolve_sheet` + best-trim fallback;
  `catalog_lookup_from_store` is kept as an alias of `catalog_lookup_from_registry`.
- **New seam:** `CanonicalRegistry.match_model(make, model)` (model-level link fallback).
- **Deploy outcome (dev VPS, coordinated 6-repo, one ssh call per venv):** two facts were born at
  deploy. (1) **kara-web compat shim** — we have no push access to kara-web, so `/catalog/vehicles`
  is kept as a read-only flat-projection of the spine in mawtarx-api (+ a `vehicles` key on
  `/catalog/stats`) so its Car Database holds its contract unchanged. (2) **kara-api pinned to HTTP**
  transport — the newer code activates xwapi's WS-RPC `/service-ws`, gated by `XWBASE_SERVICE_TOKEN`,
  which differs between the karaa-api/mawtarx-api env files on the box → gate mismatch broke every
  proxied `/catalog`+`/pricing` call; HTTP is the known-good path (revert once the env tokens align).
- **Served catalog was curate-first — 222 Gulf-curated models / 247 gens** at this deploy, not the
  old ~9.6k rows; membership widening (#4/#10) has since run — see **D-016** (now 3,533 / 3,754).

Supersedes nothing new; **completes** D-014's intent, deployed. Code: the diffs across the 7 repos.

## D-014 — markibx is global-first; its catalog decisions now live in the repo's own ADRs

**2026-07-27 · scope** — markibx was GCC-shaped for exactly one reason: **D-g defined catalog
membership by mawtarx listing volume**, so the car knowledge base's contents were a function of one
Saudi marketplace's inventory. A car nobody was advertising in Riyadh did not exist. That coupling
is severed: **membership is manufacturing reality**; listing volume survives only as a
*curation-order* signal.

Six decisions now live in **`repos/markibx/docs/adr/`** (0001–0006), with that repo's `CONTEXT.md`
as the domain glossary. They supersede or amend older entries: **D-g superseded** (membership),
**D-b amended** (generation identity is a stable id, not a year range), **D-011 superseded** (the
spine now *replaces* the legacy catalog rather than coexisting with it). D-c, D-d/D-009 and D-012
are **upheld** unchanged.

What matters at ecosystem level: `docs/markibx-mvp-catalog-model.md`'s GCC build order is no longer
the plan, and retiring the legacy catalog is a **deliberate pre-1.0 break** across three repos
(19 importing files — mawtarx 7, kara-api 7, markibx-api 5). It is affordable only because **prod
pricing does not read the catalog** (see `repos/mawtarx/CLAUDE.md`).

**The measurement that overturned the plan** (live, 2026-07-27): Wikidata has 13,780 car models but
years for only **6%**; DBpedia has years for **80%**; EPA's bulk dataset carries displacement +
cylinders for **97%** of 49,995 rows. So identity comes from Wikidata, years from DBpedia, specs
from EPA — and **horsepower is unobtainable from any free source**. EPA is US-market only and misses
Hilux/Patrol/Sunny/Pajero, so global breadth and GCC depth are now separate workstreams.

Plan + tickets: `repos/markibx/docs/global-first-plan.md`, Exonware/markibx#3 (PRD) and #4–#13.

## D-013 — xwmemory keeps graphiti_core's extraction; we replaced only the storage layer

**2026-07-26 · scope** — xwmemory's whole tool surface (`add_memory`, both search tools) now
delegates to `graphiti_core`'s pipeline over our `XWMemoryGraphDriver`, rather than growing an
in-house extraction/dedup/ranking stack. The brief was always *replace FalkorDB*, not replace
Graphiti; reimplementing LLM extraction, dedup and bi-temporal edge invalidation buys
independence nobody asked for and duplicates upstream forever.

**Consequences that will look like bugs if you don't know this:** there is **no storage-only
mode left** — the tool surface hard-requires the `[graphiti]` extra plus a reachable
LLM/embedder, and search fails loudly rather than degrading to BM25. Extraction *quality* is
therefore a model/ontology question, not an xwmemory one (Exonware/xwmemory#9).

Rejected: our own LLM pipeline; non-LLM extraction. Repo detail + the A2a follow-up live in
`repos/xwmemory/docs/logs/DECIDE_20260726_113000_000_ADD_MEMORY_DELEGATES_TO_GRAPHITI.md`.

## D-012 — the spine seed loads fail-soft, and seed validation gates the deploy

**2026-07-24 · robustness** — for landing the catalog spine in prod. Two coupled calls:

1. **Fail-soft boot.** `state.py`'s `self.spine = build_seed_registry()` (run unconditionally on
   every boot, per D-f) is wrapped so a `SeedError` sets `self.spine = None` and logs, instead of
   propagating out of `startup()`. The spine routes (`resolve_sheet`/browse) then return an honest
   **503 "spine unavailable"** rather than the process failing to boot. Everything else in
   markibx-api (legacy catalog, mountables, auth) stays up.
2. **Deploy-gate validation.** `pack-bundle.sh` runs a seed-load/validation step and **aborts the
   build on `SeedError`** — a malformed generation file never reaches the VPS.

**Why:** `build_seed_registry()` was unguarded, unlike the catalog store's try/except. A single
malformed 2a generation JSON would make `startup()` raise → markibx-api won't boot → **restart
loop that neither the guarded-restart trap nor the watchdog can fix** (both restart a *crashing*
process; they can't repair a code/data fault). Worse, the shared-venv deploy (D — see
`vps-current-state.md`) reinstalls markibx core into the **mawtarx** venv and restarts mawtarx-api
too, so a bad markibx seed's blast radius reaches **mawtarx prod**. Fail-soft + a pre-ship gate
shrinks a bad seed's blast radius to **the spine routes only** — the whole point of curated
data-as-code is that a data mistake degrades a feature, it doesn't take down two products.

**Trade-off:** fail-hard would surface a broken seed loudly (no silent-degraded spine). Rejected:
"loud" here means an outage across markibx **and** mawtarx; the 503 + deploy-gate is loud enough
(build fails before ship; routes report unavailable) without coupling a data typo to a two-product
outage. **Relates to:** D-f (seed rebuilt every boot), D-010 (2a seed is the gate).

**Code — BUILT** (merged to `main` 2026-07-27, markibx-api `57a823a`): `state.py` wraps
`build_seed_registry`; the spine routes 503 via `require_spine_or_503`; `pack-bundle.sh` gates the
build on `markibx --validate-seed` *before* any tarball is staged. A fourth call site was found
and fixed later (`6df33b7`): `_prefill_spine` let `require_spine()`'s `RuntimeError` escape as a
bare **500**, so a connector pull failed outright instead of degrading — it now returns
`{skipped: "spine unavailable"}` and still persists its catalog rows. Lesson worth keeping: a
fail-soft decision has to be enforced at **every** reader of the nullable field, not just the
obvious ones. Tests corrupt a real copy of the committed seed and run the real loader rather than
mocking `SeedError`.

---

## D-011 — the spine console runs alongside the legacy catalog surface, it does not replace it

**2026-07-24 · scoping** — for landing the catalog spine in markibx-web (the operator console).
The live console today renders the **legacy** catalog surface (`/catalog/car/*` over the old
`CatalogVehicle` / `catalog.xwjson`). The new spine (`/catalog/resolve` + `/catalog/browse/*`,
make→model→generation→trim with per-field provenance) lands as an **additive second view**, its
own route/nav entry. The legacy page is left untouched.

**Why:** at 2a (identity rows + prefilled `global` invariants, before 2b depth — see D-010) the
spine covers only the curated N generations — *narrower* than whatever the legacy catalog shows
today. Repointing the existing catalog page at the spine now would be a visible **regression** for
cars the legacy surface already lists (even though the legacy data is shallow/`confidence:0` and
the spine's is trustable-with-provenance where it exists). Running alongside ships step 3 with
**zero regression** and **decouples the web work from curation progress**. The legacy surface is
retired **later, deliberately**, once 2b makes the spine a strict superset — never as a side
effect of this change.

**Consequence:** two catalog surfaces coexist in markibx-web on purpose; the spine view is the
future canonical one but is not yet authoritative. A future agent seeing both should not "clean up"
by deleting either until the deliberate retirement. **Relates to:** D-010 (2a gate / 2b depth).

**Code — BUILT** (#30/#32), merged to markibx-web `main` **locally only — the account has no push
access to `Exonware/markibx-web` (403)**. The spine view is `src/views/spine-catalog.ts`, registered
as `{id: "console.spine", zone: "console", guard: "auth"}` in
`src/pages/shared/loaders/route-registry.ts`; the typed client is `src/app/spine.ts`. Both surfaces
coexist as decided — the legacy `src/views/catalog.ts` is untouched.

⚠️ **Path note:** origin/main refactored `src/pages/` → `src/views/` with a shared route registry
and deleted `src/pages/router.ts`, so this entry's original paths are stale. Ignore any doc that
still says `src/pages/user/catalog.ts`.

---

## D-010 — deep GCC curation is a depth pass, not a gate on "works in markibx-web"

**2026-07-24 · scoping** — for the markibx MVP catalog spine. #27 ("derive N + curate the ~80%
GCC batch", `docs/markibx-mvp-catalog-model.md` D-g) bundles two things that are **not** on the
same critical path. Split them:

- **2a — derive N + seed generation *identity* rows** (which make·model·generations exist, year
  ranges, markets). Needs a prod mawtarx snapshot but is **mechanical** — no brochures, no human
  judgment. This is the real dependency.
- **2b — deep OEM/brochure/dealer curation** (trims, native launch prices, filled specs, `oem`
  ~0.95 / `dealer-pricelist` ~0.75). Heavy, human, source-gated. This is the value for Consumer B
  (mawtarx pricing) — but it is **continuous depth, not a gate**.

**Why:** #26 connector prefill is already built and merged (core `spine_prefill.py`, api on the
`/catalog/connectors/pull` path). It auto-fills `fields.global` **invariant** fields (body_type,
doors, VIN-decode) from NHTSA — keyless, live, no human — attaching to *existing generation rows*.
So once **2a** seeds the identity rows, the markibx-web operator console can browse the **real**
GCC catalog and render **real, provenance-tagged** sheets (`official-registry` ~0.85) with **zero
2b curation**. "Works in markibx-web" therefore depends on **2a + prefill (#26)**, not 2b. Treating
the full human curation batch as a launch blocker would stall the console behind a task it doesn't
need — the mechanism is fully real without it; 2b only makes the sheets *deep*.

**Consequence:** the MVP critical path to a live console is **merge → 2a identity seed → deploy**;
2b runs as an ongoing pass *after* the console is live, not before. This is **not** cutting to a
demo — the spine, resolve/browse, provenance, and prefill are the real planned system; only the
human depth-fill is deferred off the gate. **Does not** change D-g's definition of N or D-e's
source lanes; it sequences them. **Relates to:** D-e (source lanes), D-g (N by coverage), #26, #27.

**Code — BUILT and merged to `main` 2026-07-27.** Prefill: core `spine_prefill.py`, api
`routes/catalog.py::_prefill_spine`. 2a: `scripts/rank_gcc_models.py` +
`scripts/seed_gcc_identity.py` → 222 rows in `repos/markibx/.../data/spine_seed/`.

**Correction to this entry's premise:** 2a was recorded as needing a **prod** snapshot, and #33
was left un-startable for that reason. It didn't — `repos/mawtarx-connect/mawtarx-data/xwdb-saudi-v2`
already held 8,315 genuinely scraped SA listings. The blocker was never real; nobody had looked
past the two obvious small stores. The generalizable lesson: **before calling work blocked on data
you can't reach, enumerate every store on disk** — `find . -name "*.xwjson" -size +50k` would have
answered it in one command. Note the console is live on 2a + prefill exactly as this decision
predicted, so the sequencing call itself held.

---

## D-009 — markibx stores launch price native, but its resolved output keeps `original_launch_price_sar`

**2026-07-24 · design, not built** — for the markibx MVP catalog model
(`docs/markibx-mvp-catalog-model.md`, decision D-d). markibx will *store* launch price
structured and native, per `(generation, trim, market)` (`launch_price {amount, currency,
market}`), consistent with D-002. But the **resolved-car output keeps emitting the flat
`original_launch_price_sar`** field as a derived value (= the SAR-market amount).

**Why:** mawtarx pricing's MSRP-depreciation method reads `original_launch_price_sar` *by that
exact name* (`repos/mawtarx/.../pricing_methods/msrp_depreciation.py`, `catalog_msrp.py`). For
the GCC MVP, native currency **is** SAR, so the number is identical — the compat field lets the
new native-storage model ship with **zero mawtarx changes**. It is the real markibx→mawtarx
contract, not a hack. The day a non-SAR market is added is the day pricing must learn currency
(read structured `launch_price`) — a clean future step, not debt taken on now.

**Supersedes:** markibx's current single `CatalogVehicle.original_launch_price_sar` *storage*
field (an FX-derived SAR value that contradicts D-002). After this lands, `_sar` survives only as
a **derived output**, never as the stored truth. **Relates to:** D-002 (Plan B, native currency).

**Code:** not yet built. Design + build order: `docs/markibx-mvp-catalog-model.md`. Consumers to
keep working: `repos/mawtarx/.../pricing_methods/{msrp_depreciation,catalog_msrp}.py`.

---

## D-008 — the never-empty title fallback lives on first insert only, never in `record_to_listing`

**2026-07-22** · The synthesized `{year} {make} {model}` title fallback moved from
`record_to_listing` (runs on every observation) to `store.upsert()`'s `existing is None` branch
(runs only on a listing's first insert).

**Why:** `record_to_listing` synthesized the fallback unconditionally, so `incoming.title` was
never falsy by the time it reached `_merge_listing_fields`'s own guard
(`existing.title = incoming.title or existing.title`). A source whose title selector degraded —
identity fields (make/model/year) still parsing, title parsing empty — silently replaced a rich
stored title with a generic one on every re-scrape. Numeric fields (price, mileage) were never
exposed because they have no such fallback. Filed as `mawtarx-api#1` (S4 gap, test-strategy edge
3); see `docs/price-history-test-strategy.md`.

**Code:** `repos/mawtarx/.../store.py` — fallback in `upsert()`, guard unchanged in
`_merge_listing_fields`. Regression: `tests/test_title_fallback_merge_guard.py`.

---

## D-007 — price estimates are computed on write and stored, never on read

**2026-07-18** · `store.upsert()` prices a listing and stores the estimate + deal score on it
(`VehicleListing.intelligence`); every read path serves that value. A write marks its
`(make_norm, model_norm)` bucket dirty and a background pass reprices only pools whose **median
moved materially** — not every pool that changed.

**Why:** both engines are pure functions of (listing, its pool), but reads re-ran them per row,
per request — ~15k estimates for one cold `/listings/recommended` (5-7s, GIL-held on the single
worker, stalling every other in-flight request). Repricing a whole bucket on *any* change just
moved that stall into the background thread (79.6s for one write into a pool of 8,539); one new
row shifts that median ~0.01%, so materiality is the gate.

**Supersedes:** the per-request pricing that `karaa_api.mawtarx_intel` and kara-api's
`inventory_cache` comps-index/cold-start caches existed to amortize — all removed.

**Code:** `repos/mawtarx/.../intelligence.py` + `refresh_runner.py`. Serialized as
`stored_intelligence` (see `docs/glossary.md` — **not** `intelligence`, which the card builders
overwrite). Bulk loads defer pricing; refreshes persist via `bulk_persist()`, never `upsert()`.

---

## D-006 — `dedup_key` falls back per-connector, not to a fixed field set

**2026-07-05** · Cross-source listing identity is VIN-first. Without a VIN, the fallback key is
built **per connector** from only the fields that connector's data actually supports —
populated reliably *and* varying. A connector with fewer than 2 such trusted fields falls back
to `(source, source_id)` identity instead.

**Why:** a fixed fallback field set collided and merged unrelated cars on data-poor connectors
(e.g. a single-location dealer where `city` is a constant carries no identity signal). Losing
repost-merging is acceptable; merging two different real cars is not.

**Code:** `repos/mawtarx/src/exonware/mawtarx/dedup.py` (`CONNECTOR_TRUSTED_FIELDS`, line ~68).
Term: `docs/glossary.md`.

---

## D-005 — `listings_mode=hybrid`: federate karaa's own store with mawtarx's listings

**2026-07-10** · kara-api serves listings from a store that federates its own xwjson data with
mawtarx-api's listings pulled over HTTP, rather than serving purely local or purely proxied.

**Why:** *(rationale not recorded at the time — the commit records the change, not the
tradeoff. If you know why, add it here.)*

**Code:** `repos/kara-api` (`listings_mode`); commit `358a57b`. Current server config:
`docs/vps-current-state.md`. Wiring: `ARCHITECTURE.md`.

---

## D-004 — CC-002: `price_sar` is engine-internal, never serialized on public payloads

**Recorded 2026-07-17; in force since at least 2026-06-29** · The API stores and serves the
advertised price **as-is** in its native currency. `price_sar` is a derived, engine-internal
value and is never serialized on a public listing payload. FX conversion for display is the
frontend's responsibility. Market-gap on a card must be computed from `price_delta_sar`, not
`price_sar`.

**Why:** `price_sar` is `price.val × peg` — a rate-dependent number that goes stale once
persisted (see D-002). Serializing it leaks a stale derived value into the contract; a
serialized `price_sar=0` produced cards that read "overpriced" and "below market"
simultaneously.

**Supersedes:** nothing. **Enforces:** D-002 at the contract boundary.

**Code:** `repos/kara-api/src/exonware/karaa_api/models.py:165` (the CC-002 comment).

> **On the "CC-002" label:** it's informal — cited from memory in code and the glossary, never
> recorded in a formal contract-changes doc. **This entry is its authoritative record**, and
> covers only the price decision above (advertised price stored as-is, `price_sar`
> engine-internal, market-gap from `price_delta_sar`). An unrelated "European/Slavic tier"
> call was once also tagged "CC-002" in a since-deleted `kara/CONTEXT.md`; that claim is
> unverified and out of scope here. The date is when this was *recorded*, not decided.

---

## D-003 — Per-km mileage adjustment is a fraction of value, not an absolute rate

**2026-07-03** · Replaced `PER_KM_SAR = 0.18` (a SAR-denominated constant) with
`FRAC_PER_KM ≈ 4.72e-6` (~0.47% of the comparable's own price per 1,000 km), anchored to the
SAR median price of 38,100.

**Why:** under D-002 the engine works in AED/KWD/PLN/YER — adding a SAR amount to a
native-currency price is dimensionally wrong. A fraction is unit-free and needs no FX. The SAR
**median** (38,100) was chosen as the anchor over the tail-inflated **mean** (97,566), which
would under-adjust the bulk of listings. (`YEAR_RETAINED = 0.91` is already a ratio, unaffected.)

**Code:** `repos/mawtarx/src/exonware/mawtarx/pricing.py:58` (`FRAC_PER_KM = 0.18 / 38100.0`,
`YEAR_RETAINED = 0.91`). The full derivation is inline above — this entry is self-contained.

---

## D-002 — Plan B: price in native currency; don't store `price_sar`

**2026-07-03** · The pricing engine compares listings **in their native currency**, scoped to
the same currency. FX (static SAR pegs, centralized in `fx.py`) is used **only** in the
cross-border fallback tiers. `price_sar` is not stored and not used for correctness.

**Why (measured on the live dev DB, 95,541 listings):** only **2,288 (2.4%)** are SAR-priced —
a SAR-denominated engine served 2.4% of inventory. The biggest single currency is PLN
(15,208), then AED (12,484), EUR (11,379); PLN/EUR/LYD/IQD **float** and can never be pegged,
so Plan A would have left ~50% of the data permanently `UNAVAILABLE`. A fair-value estimate is
a **ratio**, so the FX rate cancels for same-currency comparisons: `(a·r)/(b·r) = a/b`.

**Supersedes:** Plan A (convert every peggable currency to SAR at ingest, store `price_sar`,
compare in SAR). Plan A is dead — do not reintroduce a stored `price_sar` or a SAR-denominated
comparison.

**Code:** `repos/mawtarx/src/exonware/mawtarx/fx.py` (static USD/SAR pegs; its module header
records this Plan-B decision). The measured rationale above stands on its own — no external doc.
**Consequences:** D-003, D-004.

---

## D-001 — CC-001: catalog-backed minimal seller flow

**2026-06-25** · Sellers may post with make+model+year (from catalog-backed dropdowns) plus
price/mileage/city only — `body_type`/`fuel_type`/`transmission` are optional on create. Reads
gain an additive `resolved_spec: {body_type, fuel_type, transmission, source: "listing" |
"catalog"}`, and a new `GET /catalog/makes/{make}/models/{model}/years` completes the dropdown
chain.

**Why:** sellers shouldn't need to know a car's body/fuel/transmission to list it; the catalog
already knows. `resolved_spec.source` lets any client distinguish an observed value from a
catalog-inherited one. Raw `listing.body_type` etc. are unchanged and never mutated by catalog
resolution — strictly additive, no client breaks.

**Design rationale:** `repos/CATALOG_ENRICHMENT_DECISIONS.md` (matching cascade, enrichment
pipeline, confidence model). The client-contract surface (CC-001) is fully captured above —
this entry is self-contained.
