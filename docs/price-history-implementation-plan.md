# Plan — make listing price history real

**Goal:** a car detail page shows that car's actual observed asking-price history.
**Status:** Phase X (A, B, **D**), Phase 0.6, Phase 1, and **Phases 4–5** landed. Remaining:
Phase 2 (ingest), Phase 3 (runner), Phase 6 (rollout), plus two deploy-config items. Written
2026-07-19, extended 2026-07-20.

---

## → Next agent: start here

**The data and serving halves are done; nothing observes anything yet.** A car gets a real chart
the moment it is swept twice — no code change needed, just sweeps. That's what's left.

**Do these two first — minutes, not days.** They're deploy config, still outstanding, and item 7
guards a destructive path:
- `MAWTARX_DB_DURABILITY=wal` (Phase 0 item 5) — prod is on the `sync` default, ~190 ms per write.
- `MAWTARX_SCHEDULE_RUNNER=0` (Phase 1 item 7) — the runner *is* running in prod; it fires nothing
  today only because `connector_schedules.xwjson` is empty.

**Then Phase 2 → 3 → 6, in that order.** They're sequential: nothing to run until the ingest
contract exists, nothing to roll out until something runs.

**Read before writing pipeline code:** `docs/price-history-test-strategy.md`. Two of its four
design prerequisites are already built and waiting for you —

- **the clock is a parameter** (`store.clock`, and `project_price_point(now_ms=…)`), and
- **the sweep outcome is a pure function** (`mawtarx/price_series.py` — no I/O, no clock read).

Phase 2's ingest should call `project_price_point` with the **server's** clock as `server_now_ms`
and the scraper's timestamp as `now_ms`; that's what the skew check exists for (edge 18). The
other two prerequisites — **recorded HTTP fixtures** and **dry-run as a real mode** — are *not*
built and are expensive to retrofit. Build them before the connectors, not after.

**One live gap you inherit:** on prod (`hybrid`), most listings are mawtarx-owned, and
`/listings/{id}/price-history` is **not** in `mawtarx_proxy.py`'s forwarded set — so those charts
stay `indicative` no matter how many sweeps run. karaa's own listings work end-to-end. Forwarding
that endpoint is small and belongs with Phase 2.

**Two things measured by nobody:** the per-sweep series write against a 15k store, and Phase 0's
"1,000 records in seconds" target. Both are assumptions today. Measure, don't inherit the claim.

---

## Landed so far

### 2026-07-20 — Phases 4 + 5

The whole data+serving path: a listing observed twice serves a real chart, automatically, per
listing. No scraper involved — which is why it could land before Phase 2/3.

| Item | What changed | Evidence |
|---|---|---|
| — | **New `mawtarx/price_series.py`** — the pure decision layer, and the seam Phase 2's ingest plugs into. Clock injected, no I/O, no wall-clock read (test-strategy §0.1 + §0.3). Currency is encoded in the **series name**, so C3 ("one series, one currency") cannot be violated by a caller. | 21 tests in `tests/test_price_series.py`, all of C1–C5. |
| 21 | **Version chain capped** (`versioning.cap_versions`, `MAX_VERSIONS=120`), called from `_merge_listing_fields` — the only function that grows it. Keeps the **first** row (dealscore reads `points[0]`) and **every open row** (`record_version` bumps `seen_count` on them; losing one makes the chain regrow forever). A soft target, not a hard ceiling. | `tests/test_version_cap.py` (7). |
| 22/23 | **Price points appended on resolved-price change**, at the store's merge point — *not* in `record_version`, which is scoped to one `(source, source_id)` while the chart draws the merged listing's price (§7). Native currency (D-002). | `tests/test_price_series_store.py` (15). |
| 24 | **Backfill** from existing chains (`store.backfill_price_series`), idempotent, collapsing repeated prices so a title-only edit isn't replayed as a price change. **Runs before the cap** — capping first destroys rows it would have used. | `tests/test_price_series_backfill.py` (18). |
| 25 | **Retention** (`prune_price_series`, 400-day window) via `TimeSeries.prune_before`. `downsample` unused: points are written only on price *change*, so there is nothing to thin yet. | same file. |
| 26 | **`basis: observed` iff ≥2 real points**, else the synthetic series tagged `indicative`. Promotion is per listing and automatic. | `tests/test_price_history_basis.py` (13). |
| 27/29 | Two **live** contract bugs fixed in both API repos: `currency` was documented "always SAR" while returning the native currency, and `global` was documented "market-wide trend" while being RNG around the listing's own price. `global` is now empty when `basis: observed`. | `mawtarx-api/tests/test_price_history_contract.py` (7). |
| 28 | **kara-web**: axis label from the payload currency (was hardcoded `Price (SAR)`), plus an indicative caveat on both chart surfaces, both locales, dark-mode readable. | `tsc --noEmit` clean. |

**Totals:** mawtarx 302 passed · mawtarx-api 58 · kara-api 129 · kara-web typechecks.
Pre-existing failures unchanged (3 mawtarx-api, 6 kara-api — verified by stashing).

**The one finding worth repeating here:** the feature was **inert on the live product** and every
test still passed. `kara-api` has its *own* price-history route, and three layers each defeated it
independently — the route passed the per-request `buyer_store` view (empty series),
`HybridVehicleStore` didn't forward `price_points`, and kara-api's `models.py` carried its own
copies of both false descriptions. Wiring `mawtarx-api` alone changes nothing users see. Guarded
by `kara-api/tests/test_price_history_basis.py`.

The other three (the `TimeSeries.points` property, series crash-safety, the xwjson sidecar) are
recorded in their owning docs — `docs/xwstorage-db-guide.md` and `repos/kara-api/CLAUDE.md` — not
repeated here.

> **Known gap, not silent:** on prod (`hybrid` mode) most listings are **mawtarx-owned**, their
> series lives in mawtarx-api's store, and `/listings/{id}/price-history` is **not** in
> `mawtarx_proxy.py`'s forwarded set. Those listings correctly serve `indicative` from kara-api
> rather than a chart it cannot substantiate. Karaa's own listings work end-to-end. Proxying that
> endpoint is Phase 2/3 work.

### 2026-07-20 — foundations

| Item | What changed | Evidence |
|---|---|---|
| X-D | **Scheduling now lives in `xwsystem`** (`scheduling/` subpackage, `3cf5558`). `ISchedule`/`IRunLedger` Protocols, `XwSchedule` (interval + restricted cron, injected clock, catch-up-immediately), `InMemoryRunLedger` (default kept in xwsystem so the lib never imports a store to satisfy the contract). Generalized from `connector_cron.py` + `daemon_schedule.py`, which stay in place until Phase 3 consumes the xwsystem version. | 44 core tests incl. a seeded property loop; `PYTHONPATH=src pytest tests/0.core/scheduling`. |
| X-A (DB half) | **`PartitionLease` fencing wired into the engine write path** (`xwstorage-db` `e47d3bd`), opt-in via `options={"fencing": …}`. Off by default (existing consumers byte-identical). When on: open takes the lease (fencing a stale owner), every write renews-or-revalidates the token, a stolen partition fails the writer loudly, close releases. This is the "DB wants the fencing token, not plain `FileLock`" decision, resolved. | 5 wiring tests incl. a controlled-clock stolen-partition case; 0.core 263 passed (2 pre-existing FORMAT_ERROR reds unrelated). |
| 0.6 | **A scrape sweep persists in one write, not per row.** `ScrapingPersistenceAdapter` holds one `bulk_persist()` block per run; `XwStorageDbVehicleStore.upsert` now defers inside a bulk block (it wrote through unconditionally before) and coalesces via `bulk_write()`. Required a small `xwapi` fix (`37697fc`): `BaseScraper.run` now calls `flush()` in `finally`, so a batch is never lost when fetch aborts mid-sweep. | mawtarx `61a5c70` (3 tests, full suite 220 green); xwapi `37697fc` (2 tests incl. fatal-fetch). |

### 2026-07-19

| Item | What changed | Evidence |
|---|---|---|
| X-A | `xwsystem` `FileLock` rebuilt on `fcntl.flock`/`msvcrt`. It previously acquired via `open(path,"x")` and released by unlink: no release on crash (so `acquire(timeout=None)` deadlocked forever) and a racy unlink. **xwsystem did not lack a cross-process lock — it had a broken one.** | 17 new tests in `tests/0.core/io/test_core_file_lock.py`; the crash-release test is red against the old code, green against the new. 4 pre-existing FileLock tests still pass. |
| X-A2 | `xwstorage-db` `fencing.py`: the `O_CREAT|O_EXCL` claim mutex had the same defect — a holder dying mid-claim bricked the partition permanently. Added `MUTEX_STALE_AFTER` + `_mutex_age()` with an mtime fallback for an unstamped mutex. | `tests/0.core/test_fencing.py` 7/7 (2 were red). |
| — | `test_wal_durability.py`'s `_collection_records` helper looked for a `{"records": […]}` envelope; collection files are a bare JSON array, so it returned `[]` unconditionally. Three tests failed and every "nothing flushed yet" assertion passed **vacuously**. | 12/12 after the fix. **WAL durability itself is correct** — this de-risks Phase 0 item 5. |
| 1 | Reconcile disarmed. `execute_schedule` now ignores any stored `reconcile` flag; `run_manual` and `POST /{source}/update` default to `reconcile=False`; `count` is passed as `max_records` so the partial-sweep guard can actually fire. | 5 new tests in `mawtarx-api/tests/test_schedule_reconcile_safety.py`, red before / green after; full-suite failure fingerprint unchanged. |

**Deploy actions still outstanding** (config, not code): `MAWTARX_DB_DURABILITY=wal` and
`MAWTARX_SCHEDULE_RUNNER=0`.

**Environment: resolved 2026-07-20 — the diagnosis above was wrong.** Editable installs were
never the problem. `repos/.venv` carries 21 `__editable__` `.pth` files and every package
resolves to its worktree (`xwsystem` 0.9.0.79 — not 0.9.0.38; `exonware.xwaction.caching` and
`exonware.xwauth` both present). The 42 mawtarx-api errors were **one env var**: the venv is
built on GIL-enabled `/usr/bin/python3.13`, and `xwbase/config.py:85` refuses to serve on a
GIL-enabled interpreter unless `XWBASE_ALLOW_GIL=1`. Every test constructing the app died at
import with a `RuntimeError` that looked exactly like a broken install.

Fixed at the environment level: `repos/.venv/…/site-packages/xwresearch_env.py` +
`zz_xwresearch_env.pth` set the override via `setdefault`. **It is a `.pth`, not a
`sitecustomize.py`, deliberately** — Debian ships `/usr/lib/python3.13/sitecustomize.py` and
stdlib precedes site-packages on `sys.path`, so a `sitecustomize.py` there is silently shadowed
and never runs. The real fix is a free-threaded interpreter (`python3.13t`); this unblocks local
runs until then, and is venv-local so the guard still applies on the VPS.

Also found: `pytest-asyncio` was neither installed nor declared, so
`mawtarx/tests/test_scrape_persistence_batching.py`'s async test — the Phase 0.6 evidence —
**had never actually executed**. Now installed and declared in mawtarx's `dev` extra; all 3
pass, so the 0.6 claim holds, but it was unproven until today.

Baselines on a clean env (no `PYTHONPATH`, no env vars): mawtarx **all green**; mawtarx-api 3
failed / **0 errors** (`test_admin_sync`, `test_homepage`, `test_vin_report` — real product
bugs, not environmental); xwstorage-db `0.core` the 2 known FORMAT_ERROR reds.

> **Caveat for the next agent:** `repos/.venv` is untracked, so a rebuilt venv loses both fixes.
> Re-apply the `.pth` and `pip install pytest-asyncio` if 42 errors or a "async not natively
> supported" failure reappear.

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
| B | `update_many` / bulk upsert | **xwstorage-db** | ✅ **resolved: `bulk_write()` suffices.** It coalesces N updates into one collection-file write (measured 72×); Phase 0.6 consumed it. A distinct `update_many` was evaluated and skipped — no benefit over `bulk_write()`. |
| D | Interval + cron scheduling, run ledger | **xwsystem** | ✅ **LANDED** (`3cf5558`) as the `scheduling/` subpackage. `connector_cron.py`'s generic logic was fully generic and merely misfiled; the xwsystem version generalizes it + `daemon_schedule.is_overdue`. |
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
2. **B — bulk update in xwstorage-db. ✅ resolved: `bulk_write()` is enough, no `update_many`.**
   `bulk_write()` (`4bf74cd`) coalesces many updates into one collection-file write; Phase 0.6
   moved `ScrapingPersistenceAdapter` onto it via the store's `bulk_persist()` block. A distinct
   `update_many` was evaluated and skipped — it buys nothing over wrapping the loop in
   `bulk_write()`, and pre-1.0 the guides say don't add surface you don't need.
3. **D — scheduling in xwsystem. ✅ DONE (`xwsystem` `3cf5558`).** Contract-first as planned:
   `ISchedule`/`IRunLedger` Protocols, `XwSchedule`, `InMemoryRunLedger`. The dependency trap was
   honoured — the run ledger is a Protocol + in-memory default in xwsystem; a durable
   xwstorage-db-backed ledger is a product-layer impl not built yet (Phase 3 wires it).
   `connector_cron.py`/`daemon_schedule.py` are **not yet deleted** — they keep running the live
   API until Phase 3's runner consumes the xwsystem version, so nothing regresses in between.
4. Scope discipline (held): xwsystem got *when should this run*, *is it already running (ledger
   RUNNING state + the caller's lock)*, *what happened last time*. No executor, no process pool, no
   retry policy. First real consumer is Phase 3's `mawtarx_connect.runner`; the API can still change
   until then.

**Done when:** each has tests at foundation-library standard — the clock injected, schedule
sequences property-tested, and cross-process behaviour proven with a real second process (as
`test_core_file_lock.py` now does for the lock, spawning + SIGKILLing a child).

## Phase 0 — Storage foundations

At prod size a single write costs ~190 ms of GIL-held whole-collection serialization under the
default `sync` durability.

5. Set `MAWTARX_DB_DURABILITY=wal` for mawtarx-api. Deploy config, not code (`wal` not `batch`:
   same speed, no crash window). ⬜ Still outstanding (deploy, not code).
6. ✅ **DONE** (`mawtarx` `61a5c70` + `xwapi` `37697fc`). `ScrapingPersistenceAdapter` is off
   per-record `upsert()` — it holds one `bulk_persist()` block per sweep and the DB store coalesces
   the batch into one `bulk_write()`. See the 2026-07-20 landed table.

**Done when:** 1,000 records ingested into a 15k-row store in seconds not minutes, and mawtarx-api
p99 latency is unchanged during ingest. ⬜ **Not yet measured** — the code path exists and is
unit-proven (one write per sweep), but the end-to-end timing on a 15k store still needs measuring,
and depends on item 5's `wal` durability being set. Measure, don't assume.

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

## Phase 4 — Price history data — ✅ DONE (items 21–25)

See the 2026-07-20 landed table. Two constraints still govern:

**Size budget:** a SeriesSet is one file rewritten whole on flush. ~15k listings × ~12 points is
single-digit MB, negligible beside the 41 MB listings collection and crucially not touching it.
Revisit sharding past ~50 MB.

**Unmeasured:** the series write now happens once per sweep (`_flush_bulk`). Its cost against a
15k store has not been measured — same gap as Phase 0's item 5. Measure, don't assume.

## Phase 5 — Serving — ✅ DONE (items 26–29)

See the 2026-07-20 landed table, including the known kara-api proxy gap that keeps mawtarx-owned
listings on `indicative` until Phase 2/3 forwards the endpoint.

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

Phases X, 0–1 and 4–5 are done. **Phases 2–3 are the bulk that remains, 1–2 weeks.** Then
**calendar time**: no car has a history until swept twice, so the first real chart appears one
sweep interval after Phase 6 begins and charts only look like charts after several. Reconcile
lands last, after the baseline period — which is why the synthetic series stays up, marked,
until then.

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
