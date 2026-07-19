# Plan — make listing price history real

**Goal:** a car detail page shows that car's actual observed asking-price history.
**Status:** Phase X-A and Phase 1 landed 2026-07-19. Written 2026-07-19.

## Landed so far (2026-07-19)

| Item | What changed | Evidence |
|---|---|---|
| X-A | `xwsystem` `FileLock` rebuilt on `fcntl.flock`/`msvcrt`. It previously acquired via `open(path,"x")` and released by unlink: no release on crash (so `acquire(timeout=None)` deadlocked forever) and a racy unlink. **xwsystem did not lack a cross-process lock — it had a broken one.** | 17 new tests in `tests/0.core/io/test_core_file_lock.py`; the crash-release test is red against the old code, green against the new. 4 pre-existing FileLock tests still pass. |
| X-A2 | `xwstorage-db` `fencing.py`: the `O_CREAT|O_EXCL` claim mutex had the same defect — a holder dying mid-claim bricked the partition permanently. Added `MUTEX_STALE_AFTER` + `_mutex_age()` with an mtime fallback for an unstamped mutex. | `tests/0.core/test_fencing.py` 7/7 (2 were red). |
| — | `test_wal_durability.py`'s `_collection_records` helper looked for a `{"records": […]}` envelope; collection files are a bare JSON array, so it returned `[]` unconditionally. Three tests failed and every "nothing flushed yet" assertion passed **vacuously**. | 12/12 after the fix. **WAL durability itself is correct** — this de-risks Phase 0 item 5. |
| 1 | Reconcile disarmed. `execute_schedule` now ignores any stored `reconcile` flag; `run_manual` and `POST /{source}/update` default to `reconcile=False`; `count` is passed as `max_records` so the partial-sweep guard can actually fire. | 5 new tests in `mawtarx-api/tests/test_schedule_reconcile_safety.py`, red before / green after; full-suite failure fingerprint unchanged. |

**Deploy actions still outstanding** (config, not code): `MAWTARX_DB_DURABILITY=wal` and
`MAWTARX_SCHEDULE_RUNNER=0`.

**Blocked on environment:** the local checkout runs against **stale installed packages**, not
worktrees — `xwsystem` installed is 0.9.0.38 vs 0.9.0.79 in `src/`, installed `xwaction` has no
`caching.py`, and `exonware.xwauth` is absent. 42 mawtarx-api tests error on app construction
for that reason alone, and any xwsystem change is invisible to mawtarx until reinstalled.
Editable installs across the `xw*` repos are a prerequisite for Phases 2+.

Today the chart is generated from `random.Random(seed(listing.id))` (`mawtarx/insights.py:77`).
The version-chain engine behind it (`versioning.py`) is real and correct but has never had data,
because a price history needs a listing to be observed twice and nothing re-observes anything —
no crawl, no cron on the VPS (`docs/vps-current-state.md:161`).

**Decisions taken** (2026-07-19, with the user): rewrite the **orchestration only** — keep the 42
connectors and the tested safety modules · scraper runs as its **own process and POSTs batches**
to mawtarx-api, which stays the sole DB writer · price points live in **`db.timeseries()`**, with
the version chain capped · the chart shows the **merged listing's resolved price** · the
**synthetic chart stays up, marked indicative**, and each car flips to real data automatically once
it has two observations.

Storage behaviour: `docs/xwstorage-db-guide.md`. Invariants, edge cases and how each is proven:
`docs/price-history-test-strategy.md` — **read it before writing pipeline code**, four of its
design prerequisites (injected clock, replayable HTTP, pure sweep-outcome function, dry-run as a
real mode) are expensive to retrofit.

---

## Layer placement

A first draft of this plan built generic infrastructure inside `mawtarx`, which the cascade rule in
`AGENTS.md` §2 exists to prevent. Audited 2026-07-19; the corrections are Phase X.

**Goes to xw** — nothing car-specific about any of it:

| | What | Where | Why it isn't product-layer |
|---|---|---|---|
| A | Named cross-process lock | **xwsystem** | ✅ **LANDED** (`5be433c`). Correction to the original claim: xwsystem *had* a `FileLock`, but it acquired via `open(path,"x")` and never released on crash — so this was a **repair**, not a port of `SourceLock`. It now uses `fcntl.flock`/`msvcrt`. **Second correction:** xwstorage-db is *not* without cross-process safety — `fencing.py`'s `PartitionLease` (a fencing-token lease, `O_EXCL`-based, predates this work) already exists and is crash-safe as of `02126e4`. So "one primitive closes both" was wrong: they are two primitives for two problems (see item 1 below). |
| B | `update_many` / bulk upsert | **xwstorage-db** | ⚠️ **partly superseded.** `bulk_write()` already landed (`4bf74cd`) and coalesces N updates into one collection-file write (measured 72×). A separate `update_many` may no longer be worth adding — evaluate whether wrapping the loop in `bulk_write()` is enough before writing more. |
| D | Interval + cron scheduling, run ledger | **xwsystem** | `mawtarx-api/connector_cron.py` is already fully generic — cron validation, matching, next-run — merely misfiled. Generalized from three implementations, not one. |
| — | Service-to-service auth | **xwbase** (reuse) | `XWBASE_SERVICE_TOKEN` is already in the prod env. Not a decision, just don't reinvent it. |

**Stays in mawtarx** — genuinely car-domain: sweep profiles, reconcile safety, connector semantics,
dedup, the version chain, price-series projection, what a "full sweep" means.

**Deferred** (logged, not done): backup-file retention in xwstorage-db — the engine writes
`*.xwjson.backup.<ts>` on every flush and removes none, and `collect.py:319` hand-rolls pruning to
avoid filling the disk. It is the only xw item that *changes* existing behaviour, so it wants its
own change with a keep-N setting rather than riding along here.

## Phase X — xw foundations

Purely additive; no existing caller changes behaviour. xwsystem is **0.9.0.79** (pre-1.0), so the
versioning rule still allows a MINOR correction if the first consumer reshapes the API.

1. **A — cross-process lock. ✅ DONE (`xwsystem` `5be433c`).** Delivered as a repair of the
   existing broken `FileLock`, not a port of `source_lock.py`. Tests in
   `tests/0.core/io/test_core_file_lock.py` incl. a SIGKILL crash-release regression.
   > **Open decision for whoever wires the DB write path (task: "wire fencing guard"):** two
   > cross-process primitives now exist and they are *not* interchangeable. `xwsystem.FileLock`
   > is mutual exclusion (right for the scraper/`collect` "one sweep per source" case).
   > `xwstorage-db`'s `PartitionLease` adds a **fencing token** — it rejects a stale writer that
   > was paused (GC/partition) and resumed after ownership moved, which plain `flock` cannot. For
   > a single-writer DB that case is real, so the write path most likely wants `PartitionLease`,
   > **not** `FileLock`. `PartitionLease` is crash-safe now but still **unexported and unwired**;
   > wiring it into `engine.py` is its own task. Do not have xwstorage-db import `FileLock` just to
   > satisfy the original plan text — that would be the weaker tool.
2. **B — bulk update in xwstorage-db. ⚠️ mostly already present.** `bulk_write()` (`4bf74cd`)
   coalesces many updates into one collection-file write. Before adding a distinct `update_many`,
   confirm it buys anything `bulk_write()` doesn't; then move `ScrapingPersistenceAdapter`
   (`mawtarx/store.py`) off per-record `upsert()` onto whichever primitive wins.
3. **D — scheduling in xwsystem.** ⬜ **not started — this is the next real build.** Contract-first
   (`contracts.py` Protocols, per I→A→XW). Move
   `connector_cron.py`'s generic logic and `daemon_schedule.is_overdue`. Reuse the existing
   `ProcessPool`, `CircuitBreaker`, `RetryConfig` rather than writing new ones.
   > **Dependency trap:** xwsystem must never import xwstorage-db — that reverses the arrow. So the
   > run ledger is a **Protocol** in xwsystem plus a trivial in-memory default; the persistent,
   > xwstorage-db-backed implementation lives in the product layer. Getting this wrong is worse than
   > leaving the scheduler in mawtarx.
4. Scope discipline: xwsystem gets *when should this run*, *is it already running*, *what happened
   last time*. Nothing else. Prove it with exactly one consumer (mawtarx-connect) before any other
   repo adopts it, so first real usage can still change the API.

**Done when:** each has tests at foundation-library standard — the clock injected, schedule
sequences property-tested, and cross-process behaviour proven with a real second process (as
`test_core_file_lock.py` now does for the lock, spawning + SIGKILLing a child).

## Phase 0 — Storage foundations

At prod size a single write costs ~190 ms of GIL-held whole-collection serialization under the
default `sync` durability.

5. Set `MAWTARX_DB_DURABILITY=wal` for mawtarx-api. Deploy config, not code (`wal` not `batch`:
   same speed, no crash window).
6. Move `ScrapingPersistenceAdapter` (`mawtarx/store.py:759-781`) off per-record `upsert()` onto
   the batch primitive from Phase X item B (`bulk_write()`, or `update_many` if it earns its place).

**Done when:** 1,000 records ingested into a 15k-row store in seconds not minutes, and mawtarx-api
p99 latency is unchanged during ingest. Measure, don't assume.

## Phase 1 — Disarm reconcile (live today) — ✅ CODE LANDED (`mawtarx-api` `454c42e`)

The destructive path: `execute_schedule` defaulted `reconcile=True`, passed the bound only as
`params={"count": …}` (so the partial-sweep guard at `pipeline.py:86` was permanently `False`),
and `count` is honoured by only **3 of 44** connectors — so a run seeing ~30 listings marked the
rest of a source's active inventory SOLD.

7. ⬜ **Still outstanding (deploy, not code):** set `MAWTARX_SCHEDULE_RUNNER=0` in prod.
8. ✅ `execute_schedule` now ignores any stored `reconcile` flag entirely — a schedule never
   reconciles. `run_manual` and `POST /{source}/update` default `reconcile=False`; the capability
   stays opt-in for a human who knows the sweep was complete.
9. ✅ Regression tests landed first (red), then the fix: `tests/test_schedule_reconcile_safety.py`
   (5 tests). `count` is now also passed as `max_records` so the truncation guard can fire.

> **Note for the next agent:** reconciliation was *disarmed*, not *rehomed*. The plan's intended
> destination — reconcile on the sweep-completion path, gated on `should_skip_reconcile` against a
> per-source baseline (Phase 2 item 14) — is **not built yet**. Until it is, nothing reconciles at
> all, which is the safe state.

## Phase 2 — The ingest contract

The scraper never opens the database. mawtarx-api stays the only writer.

10. Batch payload: `{source, sweep_id, batch_id, profile, raw_count, records: [...]}`.
11. `POST /ingest/batch`, authenticated via **xwbase service tokens**. Validate, enqueue on a
    **bounded** queue, return 202. Never upsert inside the request.
12. Background worker drains the queue, one batch write per batch (Phase X item B's primitive),
    marks `(make_norm, model_norm)` buckets dirty so D-007's refresh reprices normally.
13. Idempotent per `(sweep_id, batch_id)`; a replayed batch bumps `seen_count` and nothing else.
14. `POST /ingest/sweep/{sweep_id}/complete` carrying the union of `seen_ids` and total `raw_count`.
    **Reconcile runs here, server-side, and only here** — it needs the whole sweep's seen-ids, which
    is exactly what per-batch reconciliation gets wrong. Gated on `should_skip_reconcile` against a
    persisted per-source baseline, and only for a completed `full` profile sweep.

## Phase 3 — The scraper runner

Nothing schedules scraping any more: `daemon.py` and `collect_incremental.py` were **deleted
2026-07-19** with the SQL backend they required, and `collect.py` is now collect-only. This phase
builds the one replacement, on Phase X's scheduler rather than a fourth private one. The safety
primitives it consumes (`daemon_schedule`, `source_lock`, `sweep_tracker`, `reconcile_safety`,
`incremental_stop`) all survived and are still tested.

15. New module `exonware.mawtarx_connect.runner`, consuming xwsystem's scheduler + lock.
16. **Sweep profiles.** Each source declares `full` and `incremental` profiles carrying its own
    parameter shape — the seven Saudi connectors take five different ones (page ranges;
    `max_details`, saudisale's default cap being **60**; brands × `max_pages`; a tag with
    `page_start: 0`; and motory with none). Reconcile is permitted only after a completed `full`
    sweep, never off connector defaults. Rationale: test-strategy §1.
17. **One home for cadence config** — today split across `collect.yaml`, `daemon.yaml` and the API's
    `connector_schedules`. `configured_sources.py` stays the authority on *which* sources are real.
18. **Only full sweeps feed price history.** `incremental_stop.py` states it detects new listings
    only and "does not detect price changes on existing listings" — incremental is for discovery.
19. Dry-run mode: execute a real sweep, write nothing, report what would change.
20. systemd unit with graceful drain, own user.

## Phase 4 — Price history data

21. Cap `listing.versions` — retention keeping the first point plus the last K. Unbounded growth on
    a fully-resident collection is the real RAM ceiling and `dealscore.py:172` only needs
    first-vs-last. Do this **before** repeated scraping starts.
22. When the merged listing's **resolved** price changes, `db.ts_append("listing_prices",
    listing.id, epoch_ms, price_val)`. Native currency (D-002).
23. Guard a currency change — start a new series rather than mixing units.
24. One-off backfill projecting existing version chains into the series.
25. Retention via `TimeSeries.prune_before` + `downsample` — full fidelity recent, thinned older.

**Size budget:** a SeriesSet is one file rewritten whole on flush. ~15k listings × ~12 points is
single-digit MB, negligible beside the 41 MB listings collection and crucially not touching it.
Revisit sharding past ~50 MB.

## Phase 5 — Serving

26. `insights.price_history` reads the series. **≥2 observed points → `basis: "observed"`**;
    otherwise keep the synthetic series tagged `basis: "indicative"`. Promotion is per listing and
    automatic — no flag day.
27. Fix `PriceHistoryOut.currency`: documented "ISO 4217 code, always SAR", actually returns native
    `listing.price.cur`. Independent live bug — ship early.
28. kara-web: axis label from the payload, not the hardcoded `Price (SAR)`
    (`price-history-chart.ts:71`); show an affordance when `basis != "observed"`.
29. `global_` is documented "market-wide price trend" and is RNG around the listing's own price.
    Out of scope — mark it indicative or drop it, but **do not leave it documented as market-wide**.

## Phase 6 — Rollout

30. Phase 0 alone to prod; measure write cost and latency.
31. One low-volume Saudi source, **reconcile off**, dry-run first; watch API latency and RSS.
32. First full sweep. Confirm version chains reach length 2 and series gain points — the first
    moment anything is provable.
33. **Baseline period: 2–3 weeks of full sweeps with reconcile still off**, recording what it
    *would* have marked. `reconcile_drop_threshold_pct` cannot be chosen a priori — Saudi
    seasonality (Ramadan, Hajj) can plausibly exceed the default 30%. Test strategy §5.
34. Enable reconcile on the evidence from 33, one source at a time.
35. Widen to the remaining Saudi sources. Chart flips per car as data lands.

## Effort and the honest timeline

Phase X is days (its logic largely exists and moves). Phases 0–1 are days. Phases 2–3 are the bulk,
1–2 weeks. Phases 4–5 about a week. Then **calendar time**: no car has a history until swept twice,
so the first real chart appears one sweep interval after Phase 6 begins and charts only look like
charts after several. Reconcile lands last, after the baseline period — which is why the synthetic
series stays up, marked, until then.

## Production state — verified 2026-07-19 by read-only SSH inspection

- **`MAWTARX_DB_DURABILITY` is not set** → the engine runs on the `sync` default. Phase 0 applies.
- **`MAWTARX_SCHEDULE_RUNNER` is not set** → defaults to `"1"`, so the runner **is running in
  production**. `connector_schedules.xwjson` is an empty record set, so it fires nothing today:
  item 7 is precautionary, not an emergency — still do it.
- **`schedule_runner.py` is deployed** (Jul 18 19:48), so the code read here is the code running.
- **mawtarx-api is a single process, no `--workers`** — one event loop, so background scraping CPU
  would compete directly with request serving. Confirms the process-isolation decision.
- **RSS 597 MB against a 41 MB `listings.xwjson`** — a ~14× disk→RAM multiplier, consistent with
  mawtarx keeping `_by_key`/`_by_id` on top of the engine's resident cache. ~7.5 GB free of 16 GB,
  multi-tenant: room for a scraper process, no room to be careless.

### Found in passing — not part of this plan

- **`GET /api/mawtarx/v1/connectors/synthetic/status` returns 500**, reproducibly, since at least
  Jul 18. That is the surface this work extends, so look at it first.
- **karaa-api reports `listings_mode: "local"` with 2,563 listings** while mawtarx holds the rest —
  `/deploy-vps` names this as the "listing counts look low" trap. Whether `local` was intended is
  unconfirmed since 2026-07-18. Worth settling separately; it may be a bigger live problem than
  price history.
- Two 22 MB `listings.xwjson.backup.cylinders.*` files from Jul 11 sit unreferenced in the data dir.
