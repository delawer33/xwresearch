# mawtarx DB Layer — Audit + Refactor Plan — 2026-07-08

Scope: **mawtarx-api's read path** against `PostgresVehicleStore` (`mawtarx/src/exonware/mawtarx/store_pg.py`).
Not in scope (documented, not done): the writer path (`mawtarx-connect`'s scraper/daemon
upserts), and any VPS deployment — this is local/dev verification only.

Triggered by a live incident: `mawtarx-api` (:8250) stopped responding to **all** routes,
including `/health`, for over a minute. Root-caused via `pg_stat_activity` + code reading,
not guesswork — findings below are each backed by either live evidence or direct code
reference.

---

## Findings

### 🔴 Critical — connection/transaction lifecycle (the actual cause of the hang)

**F1 — `_ro()` never commits or rolls back.** Every read-only request (`get`, `search`,
`comparables_for`, `count`, …) returns its connection to the pool while still inside an
open transaction (psycopg2 defaults to `autocommit=False`; even a bare `SELECT` opens
one). *Live-confirmed:* 28 concurrent `idle in transaction` sessions in `pg_stat_activity`
under load, none ever closing.

**F2 — `iter_all()`/`iter_all_lite()` hold a connection + a named server-side cursor for
the generator's entire lifetime.** The `finally: putconn()` only runs when the generator
is fully drained, explicitly closed, or garbage-collected. Any consumer that doesn't fully
iterate leaks both the client connection and the server-side cursor permanently.
*Live-confirmed:* sessions stuck mid `FETCH FORWARD 2000 FROM "iter_all_lite_cursor"` /
`CLOSE "iter_all_lite_cursor"`, idle for minutes.

**F3 — no timeouts anywhere.** `ThreadedConnectionPool(pool_min, pool_max, dsn)` sets no
`connect_timeout`, `statement_timeout`, `idle_in_transaction_session_timeout`, or TCP
keepalives. A stalled network path (connections observed routing over what looks like a
VPN tunnel) can block a socket read forever with nothing to time it out.

**F4 — pool is never closed on app shutdown.** `AppState.shutdown()`
(`mawtarx-api/state.py`) only closes the embedded system DB; `PostgresVehicleStore.close()`
exists but is never called. Connections are dropped by the OS on process exit instead of
released cleanly.

**F5 — sync driver + sync routes share one bounded thread pool.** Every mawtarx-api route
is a plain `def` (not `async def`), so FastAPI dispatches each request onto Starlette's
worker-thread pool. Combined with F1–F3, a single stuck/leaked query permanently removes
one thread from that shared pool — eventually starving **every** route, including
`/health`, which touches no DB at all. This is the literal mechanism behind "all routes
hang forever."

### 🔴 Critical — query patterns (the amplifier)

**F6 — `GET /search/listings` is N+1.**
`"items": [card(v, store.comparables_for(v)) for v in page]` — up to **100 separate
`comparables_for()` queries per single search request** (each can return thousands of
rows for a popular make/model, e.g. ~1,900 for Toyota Camry). This is the single biggest
multiplier of F1/F2: one search hit can leak up to 100 stuck transactions at once.

**F7 — `GET /dealers/{id}` does a full `iter_all()` scan of all 141k rows**, filtering by
`dealer_id`/`seller_id` **in Python**, then N+1s `comparables_for()` again per match.

**F8 — `GET /dealers` streams all 141k rows via `iter_all_lite()`** on every request just
to `GROUP BY` dealer in Python. The codebase already knows the right pattern —
`kpi_aggregates()` pushes aggregation into SQL correctly — F7/F8 just don't follow it.

### 🟠 Schema/index hygiene

**F9 — dead index.** `004_make_model_ci_index.sql`'s `idx_listings_make_model_ci
(lower(make), lower(model))` was superseded by S1's `make_norm`/`model_norm` columns;
nothing queries that predicate anymore. Pure write overhead on every insert/update now.

**F10 — no index on `dealer_id`/`seller_id`**, needed by F7's fix.

**F11 — `_build_where()`'s `eq()` filters (`city`, `region`, `fuel_type`, `transmission`)
have no matching functional index** — falls back to a seq scan if used standalone
(unverified how often that happens in practice; needs `EXPLAIN`, not a guess).

### 🟡 Lower severity (documented, not in this pass)

- **F12** — pool size hardcoded (`pool_min=2, pool_max=60`), not env-configurable.
- **F13** — no pool/query observability (checked-out count, wait time). Today's incident
  was only diagnosable via manual `pg_stat_activity` queries.
- **F14** — no migration rollback story / dry-run.
- **F15** — sync psycopg2 inside an async app is the architectural root cause of F5's
  blast radius. An async driver would contain a slow query's damage to itself.
- **F16 (flagged by user, not audited yet)** — the writer path
  (`mawtarx-connect`'s scraper/daemon upserts via `upsert()`/`_tx()`) has not been checked
  for the same class of issues. `_tx()` does commit/rollback correctly on the happy/error
  path, so it's less suspect than `_ro()`, but concurrent-write behavior under load hasn't
  been verified. **Needs its own audit pass.**

---

## Refactor plan

### Phase 0 — stop the bleeding (this pass)
Small, behavior-preserving, no API/contract changes.

1. **`_ro()`**: add `conn.rollback()` before `putconn()` — ends any lingering read
   transaction on the happy path. (Rollback, not commit: correct for read-only and also
   safe if a bug ever lets a write slip through a "ro" cursor.)
2. **`iter_all()` / `iter_all_lite()`**: same — `conn.rollback()` before `putconn()` in
   the `finally`, so whenever cleanup *does* run, the connection is transaction-clean.
3. **Defense in depth — server-side timeouts.** Add to the DSN/pool connection options:
   `statement_timeout`, `idle_in_transaction_session_timeout` (both ~30s), and
   `connect_timeout` (~10s) + TCP keepalives. This is the fix that protects against the
   failure mode *even if* a future code path leaks a generator — Postgres itself kills
   the stuck backend instead of it sitting idle forever.
4. **`PostgresVehicleStore.close()`**: wire into `mawtarx-api`'s `AppState.shutdown()`
   (guarded by `hasattr`, since the xwjson/in-memory stores don't need it).

### Phase 1 — kill the N+1s and full scans (this pass)

5. **Batch comparables.** New `IVehicleStore.comparables_for_many(listings) -> dict[str,
   list[VehicleListing]]`: one query with `WHERE (make_norm, model_norm) IN (...)` over
   the distinct pairs on a page, grouped in Python. Implement on both
   `PostgresVehicleStore` and `InMemoryVehicleStore` (repo convention: backends never
   diverge). Update `routes/search.py` to call it once per request instead of once per row.
6. **Indexed dealer lookup.** New `IVehicleStore.listings_by_dealer(dealer_id)` backed by
   `WHERE dealer_id = %s OR seller_id = %s` (indexed) instead of `iter_all()` + Python
   filter. Update `routes/dealers.py`.
7. **SQL-side dealer aggregates.** New `IVehicleStore.dealer_aggregates()` backed by a
   `GROUP BY` query instead of streaming all 141k rows into Python.
8. **Migration `008_dealer_index.sql`**: index on `dealer_id`/`seller_id`
   (partial, `WHERE seller_type = 'dealer'`).
9. **Migration `009_drop_dead_ci_index.sql`**: `DROP INDEX IF EXISTS
   idx_listings_make_model_ci` (F9) — migrations are append-only, so this drops it via a
   new file rather than editing `004`.

### Phase 2 — operational hardening (documented only, not this pass)
Env-configurable pool size/timeouts (F12); expose pool health via `/health` or an admin
endpoint (F13); `EXPLAIN`-verified indexes for any `_build_where()` filter actually used
standalone (F11) — verify before adding, don't guess.

### Phase 3 — architectural bet (documented only, not this pass)
Move to an async driver (`psycopg3` async mode or `asyncpg`) + async routes, so the app's
concurrency isn't bottlenecked by a fixed OS-thread pool at all (F15/F5's real fix).
Bigger, riskier — touches `store_pg.py` and every route signature. Worth doing once
Phase 0/1 have proven stable.

### Not in this pass, needs its own audit
**Writer path** (F16): `mawtarx-connect`'s scraper/daemon concurrent-upsert behavior
against the same pool. Flagged for a follow-up pass, not assumed safe just because
`_tx()` looks correct in isolation.

---

## Verification plan
- Extend `tests/test_lifecycle_postgres.py`'s integration pattern: after a batch of reads,
  assert `pg_stat_activity` shows zero `idle in transaction` sessions for this backend.
- `comparables_for_many()` must return results identical to calling `comparables_for()`
  per listing (property test against a fixture set).
- `listings_by_dealer()`/`dealer_aggregates()` must match the old Python-filtered
  `iter_all()` results on a small fixture set.
- Before/after: count actual SQL round trips for a `GET /search/listings?limit=60` request
  (should drop from ~61 to ~2).
