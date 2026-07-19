# Plan — make listing price history real

**Goal:** a car detail page shows that car's actual observed asking-price history.
**Status:** not started. Written 2026-07-19.

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
| A | Named cross-process lock | **xwsystem** | No `fcntl`/`flock` exists anywhere in xwsystem/xwapi/xwstorage/xwbase. `SourceLock` is the ecosystem's only one, stranded in a car repo — and xwstorage-db has **zero** cross-process safety, so one primitive closes both. |
| B | `update_many` / bulk upsert | **xwstorage-db** | The engine has `insert_many` and no update equivalent, which is the *only* reason mawtarx hand-rolls `bulk_persist`/`mark_persist`. |
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

1. **A — named cross-process lock in xwsystem.** Generalize `mawtarx-connect/source_lock.py`
   (already a real `fcntl.flock` mutex with cross-process tests). Keep its stale-lock/max-runtime
   handling. Then have xwstorage-db use it, closing the two-writer corruption hole.
2. **B — `update_many` in xwstorage-db.** Bulk upsert firing one `_persist_mutation` per batch, the
   same shape as `insert_many`. Afterwards mawtarx's `bulk_persist`/`mark_persist` gymnastics
   *shrinks*; it does not grow a workaround.
3. **D — scheduling in xwsystem.** Contract-first (`contracts.py` Protocols, per I→A→XW). Move
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
sequences property-tested, and the lock's cross-process behaviour covered as `test_source_lock.py`
already does.

## Phase 0 — Storage foundations

At prod size a single write costs ~190 ms of GIL-held whole-collection serialization under the
default `sync` durability.

5. Set `MAWTARX_DB_DURABILITY=wal` for mawtarx-api. Deploy config, not code (`wal` not `batch`:
   same speed, no crash window).
6. Move `ScrapingPersistenceAdapter` (`mawtarx/store.py:759-781`) off per-record `upsert()` onto
   Phase X item 2's `update_many`.

**Done when:** 1,000 records ingested into a 15k-row store in seconds not minutes, and mawtarx-api
p99 latency is unchanged during ingest. Measure, don't assume.

## Phase 1 — Disarm reconcile (live today)

`ConnectorScheduleRunner` runs in production now — `MAWTARX_SCHEDULE_RUNNER` defaults to `"1"`
(`mawtarx-api/state.py:175`). It has no schedules so it does nothing, but anyone adding one through
the admin API fires a destructive path:

`execute_schedule` defaults `reconcile=True` (`schedule_runner.py:131`) · it passes the bound as
`params={"count": …}` and never sets `max_records`, so the partial-sweep guard at `pipeline.py:86`
evaluates `False` · `count` is honoured by only **3 of 44** connectors, so the rest scrape their
default page range · and `should_skip_reconcile` is imported **only by `collect.py`**. Result: a run
seeing ~30 listings marks the rest of that source's active inventory SOLD.

7. **Immediately:** set `MAWTARX_SCHEDULE_RUNNER=0` in prod. Costs nothing, removes a live footgun.
8. Retire the scheduling half of `ConnectorScheduleRunner`; keep `run_manual` for admin-triggered
   runs, routed through the new safety checks.
9. Regression test first, then fix: a partial sweep of a source with N active listings marks
   **zero** sold. The test is the deliverable; the fix is secondary.

## Phase 2 — The ingest contract

The scraper never opens the database. mawtarx-api stays the only writer.

10. Batch payload: `{source, sweep_id, batch_id, profile, raw_count, records: [...]}`.
11. `POST /ingest/batch`, authenticated via **xwbase service tokens**. Validate, enqueue on a
    **bounded** queue, return 202. Never upsert inside the request.
12. Background worker drains the queue, one `update_many` per batch, marks `(make_norm, model_norm)`
    buckets dirty so D-007's refresh reprices normally.
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
