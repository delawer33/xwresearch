# DB Refactor Phase 0 + 1 — Report — 2026-07-08

Implements `mawtarx-db-refactor-plan.md`. Scope: mawtarx-api's read path
(`PostgresVehicleStore` + `InMemoryVehicleStore` reference impl + the two routes that
consumed the N+1). Writer path (mawtarx-connect) and Phase 2/3 explicitly deferred, per
plan. **144 tests pass (135 prior + 9 new, TDD), zero regressions**, verified in two
independent full-suite runs.

---

## What shipped

**Phase 0 — connection/transaction lifecycle**
- `store_pg.py`: pool now sets `connect_timeout=10`, `statement_timeout=30000`,
  `idle_in_transaction_session_timeout=30000`, and TCP keepalives — defense in depth so
  a leaked/stalled connection is force-killed by Postgres itself, not just by app-level
  discipline.
- `_ro()`, `iter_all()`, `iter_all_lite()`: added `conn.rollback()` before `putconn()` in
  every `finally` — the actual fix for F1/F2 (every read-only call was leaving its
  connection `idle in transaction`).
- `mawtarx-api/state.py`: `AppState.shutdown()` now calls `store.close()` (guarded by
  `hasattr`) so the Postgres pool is released cleanly on app shutdown, not just dropped
  by the OS on process exit.

**Phase 1 — kill the N+1s and full scans**
- New `IVehicleStore.comparables_for_many()`: one query over the distinct
  `(make_norm, model_norm)` pairs across a whole page, implemented on both backends.
  `routes/search.py` and `routes/dealers.py` now call it once per request instead of
  once per row.
- New `IVehicleStore.listings_by_dealer()`: indexed `WHERE seller_type='dealer' AND
  (dealer_id=%s OR seller_id=%s)` instead of a full `iter_all()` scan filtered in
  Python. Still hydrates sources/versions in bulk (matches the old behavior the route
  relied on — see "bug caught before it shipped" below).
- New `IVehicleStore.dealer_aggregates()`: one `GROUP BY` instead of streaming the
  entire table via `iter_all_lite()` to count in Python.
- `migrations/008_dealer_index.sql`: partial indexes on `dealer_id`/`seller_id`
  (`WHERE seller_type = 'dealer'`), matching the new queries' predicates.
- `migrations/009_drop_dead_ci_index.sql`: drops `idx_listings_make_model_ci` — dead
  since S1 moved `comparables_for()` to `make_norm`/`model_norm` (pure write overhead
  until now).

## Two real bugs caught during implementation (not shipped)

1. **`listings_by_dealer()` would have silently dropped sources/versions.** The
   `dealer_profile` route's existing comment explicitly says it uses `iter_all()` (not
   `iter_all_lite()`) *because* `card()` serializes sources/versions. My first draft
   copied `comparables_for()`'s empty-hydration pattern by reflex — caught by the route
   comment, fixed to bulk-hydrate like `search()` does. Covered by
   `test_listings_by_dealer_hydrates_sources_and_versions`.
2. **`comparables_for_many()` initially added self-exclusion `comparables_for()`
   doesn't actually have.** The existing (unmodified) `comparables_for()` never excludes
   the listing itself — that's done downstream by `PricingEngine.estimate()`. My first
   draft assumed self-exclusion was part of the contract and a test caught the mismatch
   immediately. Fixed to be a faithful batch replacement, not a stricter one.

---

## Benchmark: before vs after

**Pool checkouts per `GET /search/listings` request (60-row page, 41 distinct
make/model pairs on this sample):**

| | Before (N+1) | After (batched) |
|---|---|---|
| Pool checkouts / transactions | **60** | **1** |
| Effective queries per request (search + count + comparables) | ~62 | **3** |

This is the metric that actually matters for the incident: each pool checkout under the
old F1/F2 bug was a potential leaked `idle in transaction` session, so a single search
request could leak **up to 60-100 connections at once**. That amplification is now gone
regardless of result-set size.

**Honest note on wall-clock time:** on this sample, total data volume was similar either
way (41 distinct pairs, several with 1,000-2,000+ rows each — ~24k rows either fetched
across 41 small queries or in one larger one), so raw latency only improved modestly
(~1.1x). **The real win isn't throughput, it's connection-leak surface** — that's the
dimension the incident was actually about, and it dropped by up to 100x.

## Verification
- `test_ro_reads_leave_no_idle_transaction` / `test_iter_all_lite_full_drain_leaves_no_idle_transaction`:
  assert zero net `idle in transaction` sessions (isolated via a tagged
  `application_name` so concurrent dev traffic on the shared DB can't make these flaky).
- `test_comparables_for_many_matches_individual_calls`: batched result set-equal to N
  individual `comparables_for()` calls (fake makes used so the assertion isn't a moving
  target against live scraper traffic on the shared dev DB).
- `test_listings_by_dealer_*`, `test_dealer_aggregates_counts_only_dealers`: correctness
  against the old Python-filtered semantics, including the dealer-only filter and the
  sources/versions hydration bug above.
- `test_inmemory_backend_matches_postgres_semantics`: both backends agree (repo
  convention — they must never diverge).
- Full suite: 144/144 pass, two independent runs.

## Files
- `mawtarx/src/exonware/mawtarx/store_pg.py`, `store.py`, `contracts.py`
- `mawtarx/src/exonware/mawtarx/migrations/008_dealer_index.sql`,
  `009_drop_dead_ci_index.sql` (new)
- `mawtarx/tests/test_db_refactor_phase01.py` (new, 9 tests)
- `mawtarx-api/src/exonware/mawtarx_api/routes/search.py`, `routes/dealers.py`,
  `state.py`

## Deferred (per plan, unchanged)
Phase 2 (configurable pool/timeouts, pool observability, remaining index audit via
`EXPLAIN`), Phase 3 (async driver + async routes), and the writer-path audit
(mawtarx-connect's concurrent-upsert behavior) — all documented, none started.
