# Plan B — Native-currency pricing (supersedes the SAR-conversion plan)

**Date:** 2026-07-03. Supersedes `~/.claude/plans/sleepy-crafting-wadler.md` (Plan A).
See also `mawtarx-perkm-fraction-decision.md` and [[project-karaa-system-stage]].

## What changed and why

Plan A converted every peggable currency to SAR at ingest, stored `price_sar`,
and kept the engine comparing in SAR. Grilling + live-DB data killed that framing:

- **Only 2,288 of 95,541 listings (2.4%) are SAR-priced.** The SAR-denominated
  engine serves 2.4% of inventory.
- **The biggest single currency is PLN (15,208), then AED (12,484), EUR (11,379).**
  PLN/EUR/LYD/IQD *float* — Plan A can never convert them, so they'd stay
  `UNAVAILABLE` forever. That's ~50% of the data permanently unpriced.
- **A fair-value estimate is a ratio, so the FX rate cancels for same-currency
  comparisons.** Converting to SAR to compare two AED cars is unnecessary:
  `(a·r)/(b·r) = a/b`.

**Core principle (Plan B):** the engine compares listings **in their native
currency**, scoped to the same currency. FX (static SAR pegs) is used **only** in
the cross-border fallback tiers, where currencies genuinely must be mixed. This
prices *every* currency domestically with no FX — including the floating ones
Plan A abandoned — and confines FX to the low-confidence tail where it's actually
load-bearing.

**`price_sar` is not stored and not used for correctness.** It's a derived value
(`price.val × peg`); persisting it denormalizes a rate-dependent number that can
go stale. Compute it on demand where needed (API display, cross-currency sort),
with rates centralised in `fx.py`. This deletes the backfill and de-risks
versioning.

## Changes

### 1. `fx.py` — static rate table + single conversion function

Replace the always-raising stub with:
```python
_STATIC_RATES_TO_SAR: dict[str, float] = {
    "AED": ..., "QAR": ..., "BHD": ..., "OMR": ..., "JOD": ...,  # hard USD pegs
    "KWD": ...,  # basket-pegged, NOT hard 1:1 — recheck periodically
}
def to_sar(val, cur, date) -> float:        # SAR passthrough; peg lookup; else raise FxNotConfiguredError
def to_sar_safe(val, cur, date) -> float:   # wraps to_sar, returns 0.0 for unconfigured currencies
```
- Rates sourced during implementation via web lookup of each central bank's
  published peg (SAMA, UAE CB, CBK, CBB, CBO, CBJ), with source + lookup date
  recorded in a module comment next to the table (esp. KWD, the non-hard peg).
- This is the **one place** the rule lives. All ~6 duplicated inline
  `price_sar = val if cur=="SAR" else 0.0` copies (`store.record_to_listing`,
  `types.from_dict`, `mawtarx-api mapping.py`/`listings.py` ×2, legacy `kara-api`)
  collapse to calls to `to_sar_safe`.
- `FxNotConfiguredError` behaviour unchanged for YER/LBP/SDG/EUR/etc.

### 2. `pricing.py` — compare in native currency; FX only cross-border

- **Delete** the `listing.price.cur != "SAR"` guard. New guard: refuse only if
  `listing.price.val <= 0` (malformed). Every currency is priceable domestically.
- Comp filter (line ~89): `c.price_sar > 0` → `c.price.val > 0 and c.price.cur ==
  listing.price.cur` for the same-currency tiers.
- All math moves from `c.price_sar` to `c.price.val`.
- **Per-km adjustment → fraction of value** (dimensionless, works in any currency):
  `FRAC_PER_KM = 0.18 / 38100 ≈ 4.72e-6` (~0.47%/1000km, median-anchored). Replaces
  `PER_KM_SAR`. `YEAR_RETAINED` (a ratio) is unchanged. See the fraction decision doc.
- **Tier structure:**
  - Tiers 1–4 (city / country scoped): same-currency, native math, no FX.
  - **New tier (between 4 and 5): same-currency, ANY country**, reduced confidence —
    FX-free, rescues the multi-country EUR pool and gives floating-currency
    subjects a real comparison before self-anchor.
  - Tiers 5–6 (cross-border, mixed currency): the **only** FX use. Convert subject
    + comps to SAR via peg, drop comps with no peg; a subject whose currency has no
    peg (PLN/YER) can't participate → falls through to self-anchor.
  - Tier 7 self-anchor: anchor on `listing.price.val` (native), not `price_sar`.

### 3. `dealscore.py` — native delta

- **Delete** the `price.cur != "SAR"` guard; keep the `estimate.method is
  UNAVAILABLE` short-circuit.
- `delta = listing.price.val − estimate.value` (both native, same currency by
  construction). Never reads `price_sar` → the original "0 − est = fake 100% deal"
  bug is structurally impossible.
- `deal_score` (0–100) and `price_delta_percent` are currency-agnostic ratios and
  are the correct keys for any cross-listing ranking.

### 4. `PriceEstimate` / `DealScore` types + `mawtarx-api` schema — additive

External client exists but is untestable, so **additive, non-breaking only**:
- **Keep** every existing `_sar` field, same name/type. Populate at response time
  from `native × peg` for SAR + peggable currencies; `0`/UNAVAILABLE for floating
  (same as today). Nothing the client parses changes.
- **Add** native twins: `estimated_fair_value` + `estimate_currency`,
  `price_range_min`/`max`, `price_delta`. These carry the authoritative values and
  are where floating-currency intelligence lives.
- Cross-listing "best value" ranking (`kara-api compare_helpers.py`) switches from
  absolute `price_delta_sar` to `price_delta_percent` / `deal_score`
  (currency-safe).
- Behavioural note to coordinate with client owner: GCC listings move from
  UNAVAILABLE → populated; SAR estimates shift ~2–3% from the fraction model.
  (Optional gate if the client contract is rigid: freeze `_sar` at today's
  behaviour and expose all new value only via native fields.)

### 5. `versioning.py` — track native price

- `_VERSION_FIELDS` / `snapshot_fields()`: hash `price_val` + `price_cur`, drop
  `price_sar` from the hash. Change-detection = "did the advertised price move",
  currency/FX-agnostic, correct under static table or future live API.
- `price_history()`: return native `price_val` (with currency) so price-drop trends
  work for **all** currencies, not just SAR/GCC. Optional secondary SAR series for
  peggable currencies.

### 6. `store_pg.py` — price filter/sort without a stored column

- Price `min/max` filter and `price_asc/desc` sort: within a single currency, sort
  on native `price_val`. For cross-currency sort (only if the product needs
  "cheapest across the GCC"), convert **in the query** via a `CASE price_cur`
  expression parameterised by the `fx.py` rates — computed fresh, never stale, no
  stored column.
- Perf: per-row multiply on cross-currency sort is negligible at ~95k rows; add a
  functional index / materialized view later only if profiling demands.

### 7. `fraud.py` + `insights.py` — same unit bug, must convert too

Audit found the *same* class of bug we killed in pricing/dealscore, un-fixed here
(DW-003 named both as `price_sar` consumers; they were never guarded):

- **`fraud.py` `_check_suspicious_price`** (lines 134–166) compares
  `listing.price_sar` against the median of peers' `price_sar` (filtered
  `price_sar > 0`). For a listing whose `price_sar` is 0 (floating currency), the
  check reads `0 < median * LOW_RATIO` → **falsely flags it as `SUSPICIOUS_PRICE`,
  HIGH severity, −20** ("Price 0 SAR is far below…"). Today it's mostly masked
  because non-SAR peers are excluded so `len(peers) < 3` short-circuits — but a
  non-SAR car sharing make/model/year with ≥3 SAR cars gets a false fraud flag.
  **Fix:** peer filter gains `o.price.cur == listing.price.cur`; compare native
  `price.val`; evidence string uses the native currency. (Same shape as pricing
  tiers 1–4.)
- **`insights.py price_history`** (line 76): `now_price = listing.price_sar or 0
  or 50000.0` — a floating-currency car falls back to a hardcoded **50,000 SAR**
  anchor, producing a fictional chart in the wrong currency (return also hardcodes
  `"currency": "SAR"`). **Fix:** anchor on native `price.val`; return the listing's
  actual currency.
- **`insights.py` market aggregates** (lines 129/158/229) median/mean over
  `price_sar > 0` across the store — only valid within one currency. **Fix:** scope
  these per-currency (or per-market); lower priority than the two above.

### 8. Performance — guard removal turns a skipped scan into an always-run scan

`analyze_listing`/`estimate`/`fraud.evaluate` each pass **`store.iter_all()`** (all
~95k rows) and filter in Python. Today the pricing guard returns UNAVAILABLE for
non-SAR **before** the comp scan (pricing.py:72 precedes the `comps = [...]` at
:85), so 97.6% of listings skip the full scan. **Plan B removes that guard**, so
every listing now runs the full-store scan — potentially many × per search page.
**Mitigation:** pre-filter the candidate set (same make/model, and for tiers 1–4
same currency) at the store level before passing to `estimate()`/`evaluate()`,
instead of handing them the whole store. Measure first; this may be the one place
Plan B needs a real query change rather than an in-Python filter.

### Explicitly NOT doing

- **No backfill.** `price_sar` isn't a stored correctness dependency, so there's
  nothing to backfill. (Plan A's `backfill_fx.py` / `003_fx_price_sar.sql` dropped.)
- **Not storing `price_sar`.** The physical column becomes vestigial (leave at 0
  or drop in a later migration once nothing reads it).

## Testing (TDD)

1. `test_fx.py` (new): `to_sar` correct per peggable currency; raises for
   YER/LBP/EUR/unknown; `to_sar_safe` returns 0.0 for the refused set.
2. `test_pricing.py`: AED subject vs AED comps → real native estimate, no FX
   invoked; PLN subject vs PLN comps → real estimate (the Plan A killer case);
   mixed-currency country (UA: USD subject, UAH comps) → comps correctly excluded
   by currency filter.
3. Cross-border tiers: AED subject with thin domestic data → SAR-converted
   cross-border estimate; PLN subject with thin data → self-anchor (no peg).
4. New same-currency-cross-country tier: EUR subject pooled across countries,
   reduced confidence, no FX.
5. `test_dealscore.py`: native delta correct for AED/PLN; the old
   `test_non_sar_pricing.py` assertions (KWD → UNAVAILABLE) are now **wrong** and
   must be rewritten — KWD now prices.
6. Per-km fraction regression: representative mid-range SAR listings don't move
   materially (median preserved by construction).
7. `test_versioning.py`: same `price.val`, different (hypothetical) rate → NO new
   version (price_sar not hashed); changed `price.val` → new version; PLN price
   drop shows in `price_history`.
8. API: `_sar` fields unchanged for the client; native fields populated for
   floating currencies; cross-currency ranking uses percent/score.
9. `test_fraud.py`: a floating-currency listing is NOT falsely flagged
   `SUSPICIOUS_PRICE`; a genuinely-underpriced same-currency listing still is.
10. `test_insights.py`: `price_history` for a non-SAR listing anchors on native
    `price.val` and returns the listing's currency (not the 50,000-SAR fallback).
11. Manual: run `mawtarx-api /listings/{id}/intelligence` for a real AED and a real
    PLN listing — both return real intelligence end-to-end (pricing, deal, fraud,
    insights all currency-correct).

Not committing until reviewed.
