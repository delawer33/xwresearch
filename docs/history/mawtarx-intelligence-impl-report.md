# WS1 + WS3 + WS4 — Implementation Report — 2026-07-07

Implements `mawtarx-intelligence-impl-plan.md`. Scope: mawtarx only. No schema change,
no backfill — all changes at engine read-time. **122 tests pass (110 prior + 12 new,
written first / TDD), zero regressions.**

---

## What shipped

**WS1 — ingest sanity**
- New `sanity.py`: conservative per-currency `PRICE_FLOOR_BY_CCY` + `is_below_floor()`.
  A sub-floor asking price (1 BHD, a EUR-2 car) → `UNAVAILABLE` (no estimate); sub-floor
  comps are excluded from every pool. Floors kill obvious "call for price" placeholders
  only, never genuine cheap cars.
- `dealscore.py` overflow guard: if the estimate ≤ `1e-6`, return an UNAVAILABLE score
  instead of computing a `price_delta_percent` that blows up.

**WS3 — honesty contract**
- New `TrustBand` (HIGH ≥70 / MEDIUM ≥50 / LOW ≥35 / VERY_LOW <35) + `trust_for()`; a
  `trust` field on every `PriceEstimate` (round-trips through `to_dict`/`from_dict`).
  Confidence is now rendered alongside the estimate.
- New `DealCategory.INSUFFICIENT_DATA`: below confidence 35 the deal badge is suppressed
  (numeric score still returned) so a self-anchored or depreciation-only estimate never
  wears a reassuring "FAIR".

**WS4 — GCC comparable scoping**
- A GCC subject's cross-border tiers (5/6) now accept only GCC-currency comps.
- **Correction to the earlier framing (measured during impl):** the FX peg table is
  GCC-only **+ JOD (Jordan)**. Every floating currency (EUR, PLN, Libyan/Iraqi dinar…)
  was *already* excluded from cross-border comps because it can't convert. So WS4's real
  effect is precisely **"stop GCC cars borrowing Jordanian comps"** — JOD is the only
  non-GCC currency that was ever reachable. The wrong-market contamination was smaller
  than the audit implied, and this closes the remaining gap honestly.

**Refactor pass:** extracted the duplicated "unavailable" `DealScore` construction (two
call sites) into `dealscore._unavailable_score()`.

---

## Benchmark: before vs after

Real `PricingEngine` + `DealScoreEngine` over a **fixed** 3,000-listing random GCC
sample (same listings both runs; baseline captured by stashing the changes).

| Metric | BEFORE | AFTER | Change |
|---|---|---|---|
| HIGH (≥70) | 48.6% | 48.6% | — |
| MEDIUM (50–69) | 33.2% | 33.2% | — |
| LOW (35–49) | 11.4% | 10.9% | −0.5pp |
| INSUFFICIENT (<35) | 6.9% | 7.4% | +0.5pp |
| **Good confidence (≥50)** | **81.7%** | **81.7%** | **— (no coverage lost)** |
| Catastrophic overflow (\|delta%\|>1e6) | **1** | **0** | **fixed** |
| max \|price_delta_percent\| | **7.55e+84** | **5.19e+03** | **astronomical → finite** |

**Deal-category mix** (the honesty change is visible here):

| Category | BEFORE | AFTER |
|---|---|---|
| overpriced | 26.6% | 26.6% |
| great | 23.1% | 23.1% |
| high | 17.5% | 15.9% |
| fair | 16.3% | 13.4% |
| good | 15.0% | 12.1% |
| **insufficient_data** | **0%** | **7.4%** |
| exceptional | 1.5% | 1.5% |
| unavailable | 0% | ~0.03% |

---

## What changed, in words

1. **The overflow bug is dead.** The worst listing went from a UI-breaking
   `7.55 × 10^84 %` below market to a finite `5,190%`; the one catastrophic case is now
   an honest `UNAVAILABLE`. Nothing renders a garbage percentage anymore.
2. **Coverage is untouched.** Good-confidence estimates hold at **81.7%** before and
   after — the cleanup cost ~zero usable estimates.
3. **~7.4% of GCC listings now say "not enough data"** instead of wearing a false
   FAIR/good/high badge. Almost all of that (6.9pp) is pre-existing low-confidence
   inventory finally being labeled honestly; only ~0.5pp is newly-lowered by removing
   Jordanian comps from GCC cars.
4. **Every estimate now carries a trust band**, so `similar_match` no longer hides a
   conf-76 local comp behind the same label as a conf-30 cross-border guess.

## Files
- `mawtarx/src/exonware/mawtarx/sanity.py` (new)
- `mawtarx/src/exonware/mawtarx/pricing.py`, `dealscore.py`, `types.py`
- `mawtarx/tests/test_ws_sanity_honesty.py` (new, 12 tests)

## Deferred (unchanged from plan)
Product-boundary "surface GCC-only" filter (API/website layer); the fraud engine could
later reuse `sanity.is_below_floor`; catalog backbone (WS2) is separate.
