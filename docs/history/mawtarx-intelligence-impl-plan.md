# WS1 + WS3 + WS4 — Implementation-Ready Plan — 2026-07-07

GCC-first intelligence-accuracy pass. Decisions locked in
`mawtarx-intelligence-improvement-plan.md` + session. Scope: **mawtarx only**
(pricing.py, dealscore.py, types.py + tests). No schema change, no backfill — every
change is at engine read-time. markibx/mawtarx-connect untouched.

## Guiding constraint (learned this session)
Every change must correspond to a **measured** GCC problem. Baseline + after
benchmarks run on a fixed GCC sample; the report records the delta. If a change moves
nothing measurable, it doesn't ship.

---

## WS1 — Ingest sanity (engine read-time)

### 1a. Per-currency price floor
- **New:** `PRICE_FLOOR_BY_CCY: dict[str, float]` + `is_below_floor(cur, val) -> bool`
  in a small module `sanity.py` (so pricing + fraud can share it later).
  Values: `SAR/AED/QAR = 1000`, `KWD/OMR/BHD = 100`, `EUR/USD = 300`, `PLN = 1000`.
  Unknown currency → no floor (returns False), preserving current behaviour.
- **pricing.py `estimate()`:** replace `if listing.price.val <= 0` gate with
  `if listing.price.val <= 0 or is_below_floor(cur, val)` → `_unavailable(...,
  "Price below plausible floor — likely a 'call for price' placeholder.")`.
- **pricing.py comp filters:** the same-currency `comps` list and the `cross` list
  additionally exclude `is_below_floor(c.price.cur, c.price.val)` so placeholder rows
  never enter a pool.

### 1b. Overflow guard
- **dealscore.py:** replace `est = estimate.estimated_fair_value or listing.price.val
  or 1.0` with an explicit guard: if `estimate.estimated_fair_value <= EPS` (1e-6) →
  return an `UNAVAILABLE`-category DealScore (mirrors the existing
  `PriceMethod.UNAVAILABLE` branch). Kills the `price_delta_percent` blow-up.

**Tests:** sub-floor subject → UNAVAILABLE; sub-floor comp excluded from pool;
near-zero estimate → dealscore UNAVAILABLE, no absurd percent.

---

## WS3 — Honesty contract

### 3a. Trust band on the estimate
- **types.py:** new `class TrustBand(str, Enum)` = HIGH/MEDIUM/LOW/VERY_LOW; helper
  `trust_for(confidence) -> TrustBand` (HIGH ≥70, MEDIUM ≥50, LOW ≥35, else VERY_LOW).
  Add field `trust: TrustBand = TrustBand.VERY_LOW` to `PriceEstimate`; include in
  `to_dict`/`from_dict`.
- **pricing.py `_estimate()`:** set `trust=trust_for(confidence)`. `_unavailable` →
  VERY_LOW.

### 3b. INSUFFICIENT_DATA deal category
- **types.py:** add `DealCategory.INSUFFICIENT_DATA = "insufficient_data"`.
- **dealscore.py:** after the score is computed, if
  `estimate.confidence_score < 35` → force `category = INSUFFICIENT_DATA` (numeric
  score still returned for transparency), and append a reason
  "Not enough comparable data to rate this deal — showing an indicative estimate only."

**Tests:** conf 34 → INSUFFICIENT_DATA; conf 35 → normal category; trust bands map at
34/35/49/50/69/70 boundaries; `to_dict` round-trips `trust`.

---

## WS4 — GCC comparable scoping (engine only)

- **sanity.py (or pricing.py):** `GCC_CURRENCIES = frozenset({"SAR","AED","KWD","BHD",
  "OMR","QAR"})`.
- **pricing.py:** `subject_is_gcc = listing.price.cur in GCC_CURRENCIES`. In the
  `cross` comprehension (feeds Tier 5 + Tier 6), add
  `and (not subject_is_gcc or c.price.cur in GCC_CURRENCIES)`. Same-currency tiers
  (1–4b) are unaffected (a GCC subject's currency is already GCC). Non-GCC subjects
  keep today's any-currency behaviour.
- Product-boundary "surface GCC-only" filter is **out of scope** (API/website layer).

**Tests:** GCC subject with only non-GCC cross comps → falls past Tier 5/6 to manual
(no Polish price borrowed); GCC subject with cross-GCC comps → still uses them;
non-GCC subject → unchanged.

---

## Benchmark protocol
1. Fixed GCC sample (seeded) persisted to `bench_sample.txt` so before/after are the
   same listings.
2. `bench.py` runs the real PricingEngine + DealScoreEngine over the sample and reports:
   confidence-band distribution, method distribution, count of absurd
   `|price_delta_percent| > 1000`, and named spot-checks (a sub-floor BHD row).
3. Run **before** (baseline) and **after** (post-impl); diff appended to
   `mawtarx-intelligence-impl-report.md`.

## Sequence
WS1 → WS3 → WS4, each with tests, run full suite after each. Then re-benchmark, then a
refactor pass over the new code (extract shared helpers, dedupe, tighten names).
