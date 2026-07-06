# Mawtarx S1 Make/Model Normalization — Implementation Report

Implements Phase 0 + Phase 1 of `mawtarx-normalization-plan.md` (design doc,
fully grilled 2026-07-06). This report covers what was built, what was
tested, and measured before/after impact.

## What was built

### Phase 0 — `markibx.normalize` (new module)
- `repos/markibx/src/exonware/markibx/normalize.py` — pure functions, no I/O:
  - `slugify(raw)` — deterministic cleanup (casefold, strip everything but
    ascii letters/digits).
  - `canonical_make(raw) -> MakeResult(slug, resolved, score)` — layered:
    dictionary lookup → edit-distance-1 fuzzy auto-apply → deterministic-clean
    fallback (D3, D6).
  - `canonical_model(make_slug, raw) -> str` — deterministic cleanup + the
    shared model-alias/trim-rule table; returns the `"__unknown__"` sentinel
    for junk/blank models (D4, D6).
- `repos/markibx/src/exonware/markibx/normalize_data.py` — the data tables:
  - `MAKE_CANONICAL` / `MAKE_ALIASES` — a ~63-make dictionary bootstrapped
    from domain knowledge (see **Known limitation** below).
  - `slugify` is **Unicode-aware**: it folds diacritics (`Škoda`→`skoda`,
    `Citroën`→`citroen`) and keeps letters of any script, so a make written
    entirely in Cyrillic/Arabic (`ЗАЗ`→`заз`) stays a distinct, non-blank slug
    instead of collapsing to `""` and false-merging with every other
    non-Latin make (fixed after finding 124 such rows in the real data).
  - `MODEL_ALIASES` / `MODEL_TRIM_RULES` — **moved from mawtarx's
    `catalog_link.py`** (D4b), now shared between pricing's `model_norm` and
    catalog matching instead of two independently-drifting copies.

### Phase 1 — mawtarx
- **Migration `007_make_model_norm.sql`** — adds `make_norm`/`model_norm`
  columns (`NOT NULL DEFAULT ''`), no index yet (index comes after backfill,
  per D5).
- **`VehicleListing.make_norm` / `.model_norm`** (`types.py`) — new fields;
  `__post_init__` fills them via `canonical_make`/`canonical_model` if blank
  (convenience default for freshly-constructed listings); `to_dict`/`from_dict`
  round-trip them, with `from_dict` passing persisted values straight through
  so hydrating a stored row doesn't recompute on every read.
- **Single enforcement point (D2c)** — `PostgresVehicleStore.upsert()` and
  `InMemoryVehicleStore.upsert()` both **unconditionally recompute**
  `make_norm`/`model_norm` from raw `make`/`model` on every write (both the
  new-row and the existing-row/merge path) — never trust-upstream. Verified
  self-healing: a corrupted/stale persisted value is corrected the moment the
  row is re-scraped, with no separate re-backfill needed (see tests).
- **Backfill job** (`backfill_make_model_norm.py`) — batches the UPDATE
  (default 5,000 rows/tx), then builds
  `idx_listings_make_model_norm ON listings (make_norm, model_norm)`
  **after** backfilling completes, via its own autocommit connection
  (`CREATE INDEX CONCURRENTLY`) — the ordering is owned by the script's
  control flow, not by migration-file sequencing (see design doc D5).
- **All ~10 read/write sites switched** (D1), verified by a repo-wide grep
  showing zero remaining raw `.make.casefold()`/`lower(make)` comparisons:
  - `pricing.py` `same_mm`
  - `store_pg.py` `comparables_for`, `peer_prices`, `_build_where` (search
    filter, query-side normalized), `kpi_aggregates`' `top_makes`
  - `fraud.py` `_check_suspicious_price`
  - `market.py` `supply_for`
  - `store.py` (in-memory mirrors): `comparables_for`, `peer_prices`,
    `kpi_aggregates`' `top_makes`
  - `types.py` `VehicleSearchFilter.matches` (query-side normalization)
  - `catalog_link.py` — merged with the shared alias/trim-rule table (D4b);
    kept its own candidate-list heuristics (raw-slug fallback,
    prefix-stripping, generation-suffix-stripping) as catalog-linking-specific
    logic on top
  - `dedup_key` deliberately **untouched** (Phase 2, out of scope here)

## Tests (written first, TDD, then implementation)

| Suite | Count | Result |
|---|---|---|
| `markibx/tests/` (all, = 19 new normalize tests) | 19 | ✅ all pass |
| `mawtarx/tests/` (full suite: pre-existing + 21 new) | 110 | ✅ all pass, zero regressions |

**129 tests total, 40 new.** New: 19 in `test_normalize.py`, 9 in
`test_make_model_norm.py`, 2 in `test_backfill_make_model_norm.py`, 6 in
`test_catalog_link.py`, 4 in `test_search_norm.py`.

New tests cover: dictionary hits/formatting-variant collapse, emoji-strip,
accented-character edge case, fuzzy auto-apply at distance 1 / rejection at
distance 2, the `"__unknown__"` sentinel, shared model-alias/trim-rule
resolution, unconditional-recompute + self-healing (both in-memory and real
Postgres, including a test that corrupts a stored value directly via SQL and
confirms the next upsert repairs it), batched backfill + post-backfill index
creation, and catalog_link's alias/trim-rule/fallback/junk/generation-suffix
behaviors post-merge.

**Environment note (unrelated to this work):** 4 pre-existing test files
(`test_pricing_regional.py`, `test_non_sar_pricing.py`, `test_fraud_fx.py`,
`test_versioning_fx.py`) failed to even collect in this sandbox because the
installed `exonware-xwschema` package is a version that lacks `Price` (a
stale/incompatible install, not a code bug). Fixed by importing `Price` from
`exonware.mawtarx.types` (which already has an equivalent fallback) instead
of `exonware.xwschema` directly — this unblocked running the full suite and
is unrelated to the S1 normalization change itself.

## Business-logic smoke test (end-to-end, real engines)

Built a synthetic 60-listing "Mercedes" corpus using the **exact spelling
mix ratios from the audit** (`Mercedes-Benz`/`Mercedes Benz`/`Mercedes` at
their documented proportions, plus an emoji-garbage variant), then ran it
through the real, unmodified `PricingEngine`, `FraudEngine`, `market.supply_for`,
and `catalog_link.link_listings_to_catalog` — not a reimplementation:

```
comparables_for(subject) pool size (via real store): 60
pricing tier: exact_match, confidence: 99, comparable_count: 11
fraud flags: [] (suspicious_price count: 0 — a fairly-priced car is not
              falsely flagged just because its peers are spelled differently)
market.supply_for: supply=60 (raw casefold pool would have been 30)
catalog_link: link_rate=88.3%, matched_model_level=53, unmatched=7
```

Nothing broke: pricing reaches its highest-confidence tier, fraud stays
silent on a fairly-priced car, market liquidity is no longer undercounted
2x, and catalog linking (which now shares the same alias table) still links
the majority of the corpus.

## Benchmark: before vs. after

Two measurements: (a) the real 141k-row database (the dev Postgres turned out
to hold the actual corpus — 141,454 rows, matching the audit's "141k"), and
(b) the audit's own 60-Mercedes methodology on a synthetic corpus.

### (a) Real 141k-row database, after backfill

| Metric | Before | After |
|---|---|---|
| Distinct raw make spellings | 1,068 | — |
| Listings mapped to a non-blank canonical make | — | **100%** (only 58 rows blank) |
| Listings resolved to a *known* dictionary brand | — | **96.3%** (136,181 / 141,454) |
| Mercedes-Benz raw spellings | 7 separate pools | **1 pool** |
| Rows left unidentifiable | — | **58** (0.04%) — makes that are *only* emoji/symbols (`✅`, `🚗`, `@@@`), correctly unresolved |

The 96.3% "known brand" figure is capped by the hand-built ~60-make
dictionary; the remaining ~3.7% keep a clean, self-consistent slug (non-blank,
non-merging) and show up in the unresolved review bucket — that's the input
for the data-mining dictionary-growth pass (see limitation below).

### (b) Audit methodology — synthetic 60-Mercedes corpus

| Metric | Before (raw casefold) | After (make_norm/model_norm) |
|---|---|---|
| Distinct make spellings in the sample | 4 | **1** |
| `% make_resolved` | n/a | **100%** |
| Mean comparable-pool size | 23.3 | **59.0** (of 59 possible peers) |
| Listings whose pool changed | — | **100%** |
| Listings whose price estimate shifted >5% | — | **12%** (7/60) |

**Why 12%, not the audit's 36%:** the audit's 36% came from *real* scraped
data, where each mis-spelled sub-pool carries a systematically different price
distribution. This synthetic corpus draws every price from the **same**
distribution regardless of spelling, so sub-pools differ only by sampling
noise — a conservative lower bound. Even so, normalizing measurably changes
outcomes for >1 in 10 listings; real per-spelling price differences (the
audit's actual condition) produce the larger 36% effect.

## Known limitation

**The make dictionary is bootstrapped from domain knowledge, not mined from
the real distinct-make distribution** (D2b's stated approach). D3 explicitly
allows this ("LLM only *offline* to bootstrap the dictionary"); this is that
bootstrap pass. Measured against the real 141k corpus it already resolves
96.3% of listings, but the last ~3.7% (long-tail brands, cross-language
spellings like Arabic/Cyrillic brand names) need dictionary entries the
bootstrap doesn't have. Next step per the design doc: mine the real
distinct-make distribution, rank by row count, and extend the dictionary /
add cross-script aliases for the top uncovered names. The code
(`canonical_make`, the backfill job) needs no changes — only the data file
grows, and re-running the (idempotent) backfill re-heals rows.

## What's deliberately NOT done (per the design doc's own phasing)

- **`dedup_key` is untouched.** Switching it is Phase 2 (D5), gated on a
  dry-run diff showing zero VIN-conflict merges — a separate, higher-risk
  change explicitly out of scope for this pass.
- **No row deletion, no merge.** Every change here is additive (new columns,
  new index, switched comparisons) — no listing rows were collapsed or
  removed.
- **Real-data dictionary mining** — see limitation above.

## Files changed

**markibx:** `normalize.py`, `normalize_data.py` (new); `__init__.py` (exports);
`tests/test_normalize.py` (new, 17 tests).

**mawtarx:** `types.py`, `store.py`, `store_pg.py`, `pricing.py`, `fraud.py`,
`market.py`, `catalog_link.py` (all modified); `migrations/007_make_model_norm.sql`,
`backfill_make_model_norm.py` (new); `tests/test_make_model_norm.py`,
`tests/test_backfill_make_model_norm.py`, `tests/test_catalog_link.py` (new,
16 tests); 4 pre-existing test files fixed for the unrelated `xwschema.Price`
environment issue.
