<!-- label: wayfinder:map -->
# Map — mawtarx, a working product (Saudi first)

Local-markdown tracker (no issue tracker configured for this repo). Tickets are the files in
`tickets/`. Blocking is expressed by a `Blocked by:` line in each ticket (no native edges here).
The frontier = open tickets whose blockers are all closed and that are unassigned.

## Destination

**mawtarx works as a real product — trustworthy pricing/deals, broad live coverage, usable
end-to-end UX, and competitor parity — for Saudi Arabia first (the beachhead).** Primary shape:
the consumer marketplace (mawtarx.com) + the B2B/data API; secondarily the backend for karaa.
Reaching the end of this map means: the open decisions below are resolved, so someone can go
*build* "Saudi mawtarx that a real user or B2B client would call working" without further
charting. GCC-wide and then worldwide are the next horizons — held as fog (see Not yet
specified) so the Saudi design doesn't foreclose them.

## Notes

- **Domain**: GCC used-car marketplace + market-intelligence (pricing/deals/fraud/mojaz).
  mawtarx (core, pure-Python) → mawtarx-api (HTTP :8250/8252) → mawtarx-web (Vite SPA) +
  mawtarx-connect (scrapers). Depends on markibx (the spine catalog); never the reverse.
- **Charted terrain**: [current-state.md](current-state.md) — the full research synthesis
  (2026-07-30). Every ticket zooms into it rather than re-deriving.
- **Staging is fixed** (user, 2026-07-30): **Saudi first** (only market with real data today) →
  then GCC → then worldwide. This map's destination stops at Saudi; GCC/worldwide are fog.
- **The four bars** (user): trustworthy pricing/deals · broad live coverage · usable
  end-to-end UX · competitor parity. Every ticket serves one or more.
- **Plan, don't do** — tickets resolve *decisions*, not build-slices. The two `task` tickets
  (hygiene, freshness-reconcile) earn their place by unblocking a decision.
- **Skills to consult**: `grill-me`/`grill-with-docs` (HITL decisions), `prototype` (fidelity),
  `create-connector` (scraper questions), `deploy-vps` + `docs/vps-current-state.md` (prod
  truth), `run-local-stack` (exercise the SA corpus locally).
- **Prod is edge-gated** (mawtarx.com 302→login); karaa.net data routes are reachable
  read-only. Reason about prod from `/health` + reachable routes, never from local stores.

## Decisions so far

<!-- index — one line per closed ticket. Zoom the ticket for detail. -->

- [001 Launch surface](tickets/001-launch-surface-saudi-beachhead.md) — **API-first** (frontend-team
  timing uncertain); consumer marketplace stays in scope but **deferred**. The first measure of
  "working" is **karaa's users = Saudi buyers/sellers** → the mawtarx→karaa data+pricing path (008)
  is now central, not secondary.
- [002 Parity benchmark](tickets/002-saudi-parity-benchmark.md) — **Motory = direct structural peer,
  Syarah = trust ceiling, Haraj/OpenSooq = liquidity floor.** Valuation is now *table-stakes* (3/4
  incumbents have it), so mawtarx's honest engine only counts once *shipped + un-stale*. The 3
  dims that define "working" in SA: liquidity (live volume/freshness), transaction-trust, a
  reachable buyer↔seller contact loop.
- [004 Saudi coverage](tickets/004-saudi-coverage-target-haraj-dubizzle.md) — target **~40–60k
  unique active SA listings** (needs Haraj; without it the ceiling is ~15–20k ≈ today's ~19k, i.e.
  the dealer/aggregator layer, missing Haraj's individual-seller long tail). Freshness: new ≤24h,
  delisted ≤24–48h, reconcile armed. **Haraj → DEFER** (WAF/388, no lawful high-value path; BD/
  partner-feed only; never bypass). **Dubizzle → REACTIVATE** if its SERP still server-renders
  Algolia hits (config-only, recovers ~5k rows) → ticket 012.
- [008 Prod freshness + karaa federation](tickets/008-prod-freshness-karaa-federation.md) — karaa.net
  serves its own **2311-row `local` store, NOT federated**; prod pricing is **pricing-5** vs code
  **pricing-7**; reconcile **off**. Intended source = **federate to the ~19k mawtarx corpus
  (hybrid)** — but blocked on (a) the single-worker karaa-api concurrency fix → ticket 011, and
  (b) root env access for the mode/reconcile flip → ticket 013. `docs/vps-current-state.md` is
  stale (self-contradictory: line 198 right, 55/94/174 wrong) — corrections captured in 008/013.
- [003 Pricing-trust on the real SA corpus](tickets/003-pricing-trust-on-real-saudi-corpus.md) —
  measured pricing-7 over 7,967 real rows: **~32% get a defensible estimate** (trust≥medium),
  58.7% `insufficient_data`. Where it fires it's **accurate** (p50 err 5.4%, p90 25%). **Failure is
  coverage, not correctness** → the lever is denser comps (004), **not** the catalog fallback (which
  can't help until 005/MSRP exist). **Trust bar = trust≥medium** (already the gate). Deploy pricing-7
  as a correctness fix (→013), accepting it slightly lowers the rate.

- [005 Catalog-link `vehicle_identity_id`](tickets/005-catalog-link-vehicle-identity-id.md) — **~82%
  of the real corpus would link at ingest today** (76% gen-level, 6% model-level) on the existing
  spine, ~88–90% after curating Audi + top gaps. Empty on 100% for two real bugs: a **field-split**
  (`link_listings_to_catalog` writes `catalog_car_id`, not the `vehicle_identity_id` this tracks)
  and it's **never wired to ingest** (only a manual CLI, never run). **Build it: YES** — fix the
  field, wire the existing ADR-0003 ladder into the `deferred_pricing()` bulk seam (resolve once per
  `(make,model,year)` tuple). Misses split: 5.9% `__unknown__` → connector-parse backlog; ~12% real
  gaps → 010's curation queue. Prereq for the catalog pricing-fallback (003).

### CORRECTION (2026-07-30, user) — karaa gets estimations only, never listings

**karaa users must NOT see mawtarx's scraped listings.** karaa serves its own inventory and
consumes mawtarx for **price estimations only**. This **revises 008** (rejects hybrid listing
federation) and **dissolves 011**: the estimations-only path is a *cached snapshot + write-time
pricing* (`MawtarxComparablesPool`), which was purpose-built for `local` mode and carries none of
the F2/F3 read-path saturation risk. What looked like the hard critical ticket is a deploy/config
diagnosis instead.

### New tickets (graduated from the research)

- [011 karaa estimations path](tickets/011-karaa-api-concurrency-for-federation.md) — ✅ **resolved**
  by the correction + code read: the `local`-mode `MawtarxComparablesPool` wiring already exists
  (`state.py:304-315`); estimations-only = no federation, no concurrency design needed. Prod's
  `comparable_count:0` is a build/env/token/snapshot problem → folded into 013.
- [012 Dubizzle reactivation health-check](tickets/012-dubizzle-reactivation-healthcheck.md) —
  ❌ **RESOLVED: DEAD (2026-07-31).** Probe → Cloudflare JS-fingerprint wall (24KB challenge, 0
  listings); no code change. Premise was also stale (dubizzle already ACTIVE in-repo; prod exclusion
  is a root override, not a flippable `disabled`). Recovery needs a partner feed — Haraj class, not
  cheap. The 5.1k rows are legacy/static.
- [013 Prod-freshness + karaa estimations ops](tickets/013-prod-freshness-ops.md) — 🟡 root access
  has a path now (**user's boss holds root**): deploy pricing-7 to both venvs + re-price sweep +
  reconcile-on + **make the `local`-mode estimations path work** (NOT hybrid) + fix the stale VPS
  doc. Deliverable = a precise checklist for the boss. ✅ **CHECKLIST WRITTEN**:
  [tickets/013-BOSS-CHECKLIST.md](tickets/013-BOSS-CHECKLIST.md) — runnable 6-step (pricing-7 both
  venvs → #14 catalog-link backfill of existing ~19k → #009 purge → re-price → reconcile-on →
  karaa comps-pool). Still root-gated to execute.

## Not yet specified

<!-- in-scope fog toward the destination, or the next horizons; graduates to tickets as the
     frontier advances. Deliberately coarse. -->

- **GCC activation (next horizon)** — UAE/KW/QA/BH/OM connectors already exist and sit in
  `collect.yaml`; the runner just doesn't sweep them. When Saudi is "working", graduate:
  which countries first, turning the runner on, and validating the multi-currency price
  pipeline end-to-end (no non-SAR row exists today to prove it).
- **Currency-native read contract** — kara-api's valuation DTO is SAR-named
  (`fair_value_*_sar`); pan-GCC needs native-currency read fields. Sharpens once a second
  currency has real data.
- **Pan-GCC catalog re-ranking** — spine curation was ranked on a Saudi-only snapshot; GCC
  volume may reorder it. Graduates with GCC activation.
- **Worldwide (far fog)** — non-GCC connectors (autoria, olx_pl, mobile_bg…), floating-currency
  FX (engine refuses to guess non-pegged currencies today), non-Arabic/-English locales. Kept
  visible per user so Saudi choices stay expansion-safe; not chartable now.

## Out of scope

<!-- ruled beyond this map's destination; never graduates unless the destination is redrawn. -->

- **Worldwide execution** — only the Saudi beachhead is in scope; worldwide lives as far fog.
- **The karaa consumer product itself** — mawtarx is karaa's *backend*; karaa's own UX/product
  decisions belong to a different effort. (But feeding karaa good data+pricing IS in scope — 008/011.)
- **xw* platform-library work** — reuse them; don't rebuild them under this map.
- **Haraj ingestion (deferred, biggest coverage gap)** — [004](tickets/004-saudi-coverage-target-haraj-dubizzle.md)
  found no lawful high-value path (WAF/388; free-text posts even via the lawful sitemap). Out of
  scope until a BD/partner feed exists — then it returns as a fresh effort. Named here because it's
  the single largest gap between "aggregator-layer coverage" (reachable) and "feels complete".
- **Consumer-marketplace launch (deferred, not dropped)** — per 001, the public marketplace stays
  "on its place" but waits on frontend-team availability. The two consumer-only decisions,
  [006 edge-gate](tickets/006-edge-gate-decision.md) and [007 lead-loop](tickets/007-consumer-lead-loop.md),
  are parked (blocked by "consumer phase"), not resolved. They graduate when the frontend team lands.

---

## 2026-07-31 — Reconciled with Muhammad's main merge (planning ≈ done; implementation backlog)

Muhammad merged **PR #1 (`grill/saudi-identity`) → main**. He runs the same program as
**GitHub `Exonware/mawtarx` issues #2–#8** (that tracker, not this map, is canonical). Verified on main:

- **Pool module + pool-health + Saudi baseline** (issues #5/#6): `pool.py`, `pool_health.py`,
  `docs/saudi-baseline-2026-07-28`. His baseline **agrees with our 003** (coverage-bound;
  `__unknown__` = 5.93%/474, an exact match). → **003 measurement is his, done.**
- **Curation worklist** (#7): `curation_worklist.py` + generated worklist. → **010's curation-queue
  half is his, done.**
- **UNKNOWN_MODEL never self-pools** (#3, CLOSED): confirms our 005 `__unknown__` split.
- **`catalog_link.py` reworked** + **`pricing_methods/catalog_msrp.py`** (spine-native launch-price
  lookup): on main.

**Correction (supersedes an earlier note):** the `catalog_msrp` "conflict" was WRONG. `DEFAULT_METHODS`
on main is still `("inventory_comps",)` — the catalog fallback stays **off by default**, exactly per
003. He fixed only the lookup *plumbing*; native launch prices exist only on sparse curated trims, so
it rescues little today. **003 stands, no conflict.**

**The one genuinely-open CODE task he did NOT do:** `catalog_link` is still **CLI-only**
(`cli.py:134`), never wired to ingest → `catalog_car_id` empty on the corpus. That is 005's core
recommendation, ready to build on his freshly-merged linker.

### Implementation backlog (ranked)

1. ~~**[005] Wire catalog-link into ingest**~~ — ✅ **IMPLEMENTED 2026-07-31** (branch
   `feat/mx-14-catalog-link-ingest` in mawtarx / mawtarx-connect / mawtarx-api; **committed, UNPUSHED,
   not deployed**; GitHub **Exonware/mawtarx#14**). Wired into `ScrapingPersistenceAdapter.flush()`
   (the real bulk seam), per-tuple cache, one-flush persist. **Found + fixed a second bug:** the
   linker's `_save()` persistence silently no-op'd on every store (incl. absent on the prod DB
   store) — the field would have stayed empty even if the CLI had run. See ticket 005 for detail.
   ✅ **BACKFILL RUN 2026-07-31** on the dev store (shukri venv+store ACL): identity coverage
   **~0% → 96.4%** (pool-health `unknown_identity` 697/19,354). #14 now real on the existing corpus.
2. ~~**[009] Live-store hygiene**~~ — ✅ **IMPLEMENTED (purge) 2026-07-31** (same branch/issue #14).
   `mawtarx purge-synthetic`, dry-run default. Data-safety: `karaa` (the default `source`) is NOT
   purged unless `--include-default-source`. Standing ingest guard deferred. ✅ **PURGE RUN
   2026-07-31** on the dev store: 248 `source:synthetic` rows deleted (19,602 → 19,354), dry-run
   now 0, first-party intact.
3. **[012] Dubizzle reactivation** — live SERP health-check → runner-config flip (~5k rows → denser
   comps → better estimations). Flip needs deploy access.
4. **[013 = issue #8] Prod freshness + karaa estimations** — deploy pricing-7 to both venvs,
   reconcile-on, make karaa `local`-mode comps pool fill, **+ run the 005 catalog-link backfill and
   the 009 purge on prod**. **Boss-gated (root).**

Decisions (not code): 002 parity + 004 coverage are resolved and feed prioritization; 010 catalog
*depth* (LLM engine, ADR 0010) is a larger later build. 006/007 consumer parked; Haraj out of scope.

**Tracker:** #005+#009 filed together as **Exonware/mawtarx#14** (done, unpushed). #012 still to file.
The 5 review-verified changes need a human `git push` + PR (branch ready in all 3 repos).
