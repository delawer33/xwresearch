# Decision: per-km mileage adjustment → fraction-of-value (Plan B)

**Date:** 2026-07-03
**Context:** FX / Plan B rework of `mawtarx` pricing. Under Plan B the pricing
engine compares listings **in their native currency**, scoped to same currency,
and only uses FX (static SAR pegs) in the cross-border fallback tiers. See the
FX plan (`sleepy-crafting-wadler.md`) and [[project-karaa-system-stage]].

## Problem

`pricing.py:47` `PER_KM_SAR = 0.18` is a **currency-denominated** constant
("0.18 SAR shaved per extra km"), used to normalize comparables to the subject's
mileage. Once the engine works in AED/KWD/PLN/YER instead of SAR, adding a SAR
amount to a native-currency price is dimensionally wrong. (`YEAR_RETAINED = 0.91`
is a ratio, so it is unaffected.)

## Decision

Replace the absolute per-km rate with a **fraction of the comparable's own
price**, which is unit-free and works for every currency with no FX:

```
FRAC_PER_KM = 0.18 / <SAR median price> = 0.18 / 38100 ≈ 4.72e-6   (~0.47% per 1000 km)

# mileage adjust, was:  comp.price_sar + (comp_km - subject_km) * 0.18
# now:                  comp.price.val + (comp_km - subject_km) * (comp.price.val * FRAC_PER_KM)
```

**Anchor = SAR median (38,100)** so the typical Saudi car is preserved exactly.
Chosen over the tail-inflated mean (97,566), which would under-adjust the bulk
of listings.

## Data grounding (live dev DB, 2026-07-03)

- Total listings: **95,541**. SAR-priced (`price_cur='SAR' AND price_sar>0`):
  only **2,288 (2.4%)** — the SAR-denominated engine served 2.4% of inventory.
- Biggest single currency is **PLN (15,208)**, which floats — Plan A could never
  convert it; Plan B prices it domestically with zero FX. Same for EUR (11,379),
  LYD, IQD, etc. GCC pegs (AED/KWD/BHD/OMR/QAR/JOD) ≈ 41k rows.
- SAR price distribution: p25 23,000 · median 38,100 · p75 80,000 · mean 97,566.

## Impact on Saudi estimates (simulated, leave-one-out, make+model+year groups)

| Segment | Median change | Note |
|---|---|---|
| Mid-market 30–120k SAR (bulk) | **~2–3%** | negligible |
| All Saudi cars (overall) | **~5%** median abs; signed median −1.2% | |
| Cheap ≤30k SAR (~42%) | **~18%** | fixes a segment where flat 0.18/km was pathological (could subtract > the car's whole value on a high-mileage comp) |
| Luxury >120k | ~2–3% | barely moves |

Counter-intuitively, **cheap cars move most, luxury least** (percentage = adjustment
÷ estimate; small denominators + large mileage gaps dominate). The large cheap-car
divergence is a **correction**, not a regression.

Caveats: simulation **overstates** real divergence (no mileage-band filter, unlike
`pricing.py` tiers 1–2, which collapse km gaps). Only 466 subjects had ≥4 SAR comps
(thin-SAR reality) — cheap-bucket tails are directional, not precise.

## Follow-up

- Regression test: assert a handful of mid-range SAR listings don't move materially.
- Reproduce: `scratchpad/sim_perkm.py` (leave-one-out simulator) + the median query.
