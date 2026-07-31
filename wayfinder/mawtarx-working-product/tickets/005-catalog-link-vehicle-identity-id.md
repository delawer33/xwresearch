# 005 — Catalog-link: build `vehicle_identity_id` at ingest?

- Type: `wayfinder:research` (AFK; likely spawns a `task`)
- Status: **resolved** 2026-07-30
- Blocked by: —
- Assignee: —

## Question

`vehicle_identity_id` is empty on 100% of listings — nothing joins a listing to its markibx spine
node, so per-unit spec/intelligence can't attach and cross-market analytics are impossible. The
resolution keys already exist on every row (`make_norm`, `model_norm`, year). Decide whether to
resolve the spine link **at ingest** (via `catalog_link.py` → spine `resolve()`), what to store
(generation id when year selects one, else model id — per ADR 0003), the expected hit-rate
against the current spine, and how unresolved listings are handled.

This is foundational — it gates trustable per-listing intelligence and any spec-driven UX,
regardless of country.

Resolve to: a link-build decision (yes/how/where in the ingest path) + measured expected
resolve-rate on the real SA corpus + handling for misses.

## Resolution (2026-07-30, research — ran the real spine resolve seam over the corpus)

Ran every real row's `(make_norm, model_norm, year)` through the actual path `catalog_link.py`
uses (`build_seed_registry()` → `CanonicalRegistry.resolve()`/`.match_model()`, market=GCC) over
**7,967 real SA rows** (synthetic excluded). Registry: 45 makes / 3,533 models / 3,754 gens.

**Measured resolve-rate (today's spine, zero curation):**
- Generation id: **76.1%** (72.4% exact year-covered + 3.7% single-candidate)
- Model-level id: 6.1% → **any link = 82.2%**; miss = 17.8%.
- **Ceiling ≈ 94% of *parseable* rows** — half the miss is unparseable, see below.

**Miss decomposition (the actionable part):**
- **5.9% `model_norm=='__unknown__'`** → the *scraper* never parsed a model. **NOT a catalog gap
  — a connector-parse backlog.** Route to mawtarx-connect, not curation.
- **3.6%** make absent (audi 60, ferrari 29, jac 23, foton 18, maserati 18, lucid 15, greatwall
  11… — **Audi is the single biggest hole**, confirms 010).
- **8.3%** make present / model absent (haval v7, nissan urvan, vw touareg, mg 7, porsche panamera…).

**Two reasons the field is empty on 100% of rows (both real bugs):**
1. **Field-split bug.** `types.py` has *two* fields — `catalog_car_id` (511) and
   `vehicle_identity_id` (506). The linker (`link_listings_to_catalog`) writes **`catalog_car_id`**;
   **nothing writes `vehicle_identity_id`** (the field this ticket tracks). Both are 0%.
2. **Never wired to ingest.** The linker's only caller is the manual CLI `mawtarx catalog-link`
   (`cli.py:132`); no scrape/upsert/`deferred_pricing` path calls it. The batch was never run on
   this corpus. Logic is sound (already implements ADR 0003's exact-gen→gen→model ladder).

**Decision — build the link at ingest: YES.**
- **Fix the field split first** (cheapest, highest-leverage): pick one canonical field
  (`vehicle_identity_id` vs `catalog_car_id`) or collapse them — else running the batch still
  leaves this ticket's field empty.
- **Wire the existing ladder into the store's `deferred_pricing()` bulk-write seam**, resolving
  **once per distinct `(make_norm, model_norm, year)` tuple** (pure/in-memory, cache it) — never
  per-row in `upsert()` (the 68× antipattern the mawtarx CLAUDE.md warns against).
- **Expected: ~82% linked today**, ~88–90% after curating Audi + the top ~15 model gaps (→ 010).
- **Miss-handling:** keep the linker's honesty (empty on `CatalogMiss`, never fabricate); its
  `top_unmatched` already feeds a curation queue; re-link idempotently (`relink=True`) after each
  spine widening. Split misses for ops: `__unknown__` → connector-parse backlog; real gaps → 010.

**Cross-links:** unblocks per-unit spec/intelligence join; is the prerequisite the catalog
pricing-fallback (003 decision 3) waits on; its curation queue = 010's input.

## Update 2026-07-31 (post Muhammad's main merge)

`catalog_link.py` was reworked + merged to main (better matching), and `types.py` keeps
`catalog_car_id` as the canonical spine-link field (resolves our field-split question — **use
`catalog_car_id`**, not `vehicle_identity_id`). BUT the linker is **still CLI-only** (`cli.py:134`);
nothing calls it from ingest, so `catalog_car_id` remains empty on the corpus.
**Open implementation task = wire `link_listings_to_catalog` into the `deferred_pricing()` bulk seam
+ one backfill run.** This is the map's first implementation slice.

## IMPLEMENTED 2026-07-31 (branch `feat/mx-14-catalog-link-ingest`, unpushed; GitHub Exonware/mawtarx#14)

Shipped across mawtarx / mawtarx-connect / mawtarx-api (committed, not pushed, not deployed):

- **Found + fixed a second bug the research missed:** the linker persisted via
  `getattr(vstore,"_save")()`, which early-returns unless `_dirty` is set (the mutation never set
  it) and is **absent entirely on the prod `XwStorageDbVehicleStore`** → the link was never
  written on ANY store, even if the CLI had run. Now flushes via `bulk_persist()`/`mark_persist()`
  (DB-store safe), skips the flush when nothing changed.
- **Wired into the real bulk seam:** `ScrapingPersistenceAdapter.flush()` links the rows a sweep
  touched (scoped by dedup_key, per-`(make,model,year)` cache, best-effort — a resolver/seed fault
  is logged, never loses scraped rows). Registry injected at all three prod sites via mawtarx-api's
  `state.catalog`. NB: wired at the adapter flush (the actual bulk-ingest seam), not the literal
  `deferred_pricing()` CM (which only suppresses pricing) — same intent, links only touched rows.
- **Cache keyed on RAW `(make,model,year)`**, not `make_norm` — provably byte-identical to calling
  `resolve()` directly (avoids depending on store-norm == resolver-norm); still dedups the dominant
  repeat-nameplate case.
- **`relink=True` now clears a stale link** that no longer resolves (honesty invariant).
- Tests: per-tuple caching, no-op-no-write, file-store persistence round-trip, relink-clears-stale,
  adapter links-on-flush / off-without-registry / survives-resolver-failure. All green.

**Still an ops step (NOT in this change):** the one-time whole-store backfill on the real corpus.
The path exists (`mawtarx catalog-link` CLI now actually persists; and the next ingest sweep
auto-links touched rows), but running it on prod is root/deploy-gated → folds into **013**.

---
## PROD-RUN DONE 2026-07-31 (dev box)
Whole-store `mawtarx catalog-link --store …/system --market GCC` run on the live dev store (via
shukri venv+store ACL, inside a watchdog window). **Identity coverage ~0% → 96.4%** (pool-health
`unknown_identity` 697 / 19,354). #14's existing-row backfill is now real. Backup:
`collections/listings.xwjson.bak-preop-20260731`.
