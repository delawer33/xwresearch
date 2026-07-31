# Current state — mawtarx as a product (charted 2026-07-30)

Research synthesis from three read-only agents (pricing, scrapers, product-surface/catalog).
The map's tickets zoom in here. Prod is edge-gated; findings are from synced code + reachable
read-only routes. Local ≠ prod — treat quantities as indicative.

## What mawtarx IS
Dual-surface car product, not a shell:
- **Consumer marketplace** (mawtarx.com, `zone:public`, fully-built views): home, browse/search,
  listing detail, compare, valuation, brands, VIN lookup, fraud-watch, insights/trends/map,
  cars-db explorer. SAR base, multi-currency display, Arabic+RTL, GCC country set hard-coded.
- **B2B/operator console** (`zone:console`, auth-gated): dashboard KPIs, listings ops,
  intelligence, valuation, scraper research centers, providers, fraud, catalog, token/credit
  ledger, admin VIN reports.
- **Backend for karaa** (secondary): kara-api proxies pricing/deals; mirrors listings snapshot.
- **mawtarx-api**: 20 real routers under `/api/mawtarx/v1`, no 501 stubs. Consumer journey works
  end-to-end: autocomplete → faceted search → listing (price+deal+intelligence) → mojaz history
  + price-history/ratings → compare → dealer inventory → reveal contact. **No lead/message-send
  endpoint** (contact = reveal phone/whatsapp; buyer goes off-platform).
- **Blocker to being a public product**: the whole site sits behind `xwauth-id-gate`
  (302→`/_gate/login`). Real in code, not publicly reachable.

## Pricing / intelligence
- **Engine is GCC-shaped and honest**: native-currency comparison (D-002/D-003), six-currency
  floors/pegs/scoping/depreciation, trust bands, `INSUFFICIENT_DATA` (zeroes market-delta when
  confidence<35), Tukey outlier rejection, `method=unavailable` instead of fabricating. Verified
  live degrading honestly.
- **SA-only in practice**: 100% of live + real-scraped data is SA/SAR. Only `inventory_comps`
  runs in prod (pure comp, touches no catalog); the one catalog-reading method
  (`msrp_depreciation`) is SAR-anchored **and disabled**.
- **Prod is stale**: `/valuation` reports `mawtarx-pricing-5`; code is `pricing-7`. Reconcile
  off → un-rescraped rows keep pricing-5 estimates.
- **karaa.net is `listings_mode=local`, 2311 listings** — its own small SA store, NOT federated
  to the ~19k mawtarx corpus. Contradicts `vps-current-state.md` ("hybrid", 15,473). Served SA
  rows are demo-skewed (single-nameplate exotics, many `price:None`) → 0 comps by construction.
- kara-api valuation DTO is SAR-named (`fair_value_*_sar`); no native-currency read fields.

## Scrapers / coverage / data quality
- **Saudi producing in prod (5)**: syarah (~2.6k), sayarat (~2.0k), opensooq (~1.9k), saudisale
  (~1.4k), samaco (~64). haraj (largest SA marketplace) permanently 0 (WAF); dubizzle 5.1k rows
  legacy, not swept; motory a disabled stub.
- **GCC-ex-Saudi entirely dark in prod** — but real `fetch()` scrapers EXIST and are wired into
  `collect.yaml` for all 6 countries (opensooq alone spans all 6). Activation is runner/ops
  config, not new code. No non-SAR row exists to validate multi-currency end-to-end.
- **Data quality (n≈8.3k local)**: price/year/make/model 100%, trim 79%, photos 76%,
  transmission 76%, color 76%. Arabic→Latin normalization ~95% (`ar_carterms.py`). Dedup perfect
  (0 collisions). Observed price-history on 100% of rows.
- **Quality holes**: `vehicle_identity_id` empty on **100%** of rows (catalog-link unbuilt);
  seller_type 55% unknown (opensooq/saudisale 100%); opensooq 0% photos; condition 65% unknown;
  ~348 synthetic `zz*`/karaa test rows in the live store.

## Catalog (markibx spine)
- 45 makes / 3,533 models / 3,754 generations. GCC-critical nameplates present.
- **Depth ~0%**: only 114/3,754 gens carry specs; exactly 1 has trims. LLM depth engine (ADR
  0010) built, **not run**. Existing depth is US-biased EPA/NHTSA on ~110 curated gens.
- **GCC fitness gaps**: missing **Audi** (top-3 Gulf luxury), Volvo, JAC, GWM/Tank, Zeekr;
  **Lexus/Infiniti/Genesis buried** under parent makes (break make-level facets); Wikidata
  widening swamped European legacy makes with noise while GCC makes stayed thin; curation ranked
  Saudi-only; `baw` id is actually FAW (data bug).
- **Autocomplete regeneration broken** (served vocab is live; only the rebuild path fails).

## The five foundation cracks (cross-cutting)
1. Edge gate hides the consumer marketplace — no public product.
2. Catalog-link 0% (`vehicle_identity_id` unbuilt) — blocks per-unit spec/intelligence join.
3. Prod pricing-5 vs code pricing-7; karaa not federated to the corpus.
4. Only `inventory_comps` in prod; catalog fallback disabled + SAR-anchored.
5. Synthetic pollution + catalog depth ~0%.
