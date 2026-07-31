# 003 — Does the pricing engine clear a "trustworthy" bar on the real Saudi corpus?

- Type: `wayfinder:research` (AFK; may spawn a `prototype`)
- Status: **resolved** 2026-07-30
- Blocked by: —
- Assignee: —

## Question

The engine is honest but never measured on the real ~8k SA corpus
(`repos/mawtarx-connect/mawtarx-data/xwdb-saudi-v2`). Run `inventory_comps` (the only prod
method) over it and measure: comp-pool-size distribution, trust-band mix, `INSUFFICIENT_DATA` /
`unavailable` / `manual` rates, and eyeball the tail for obvious mispricings. Then decide the
**pricing-trust bar** for Saudi launch and whether it's clearable with comps alone or requires
enabling/ fixing the catalog fallback (`msrp_depreciation`, currently SAR-anchored + off) and
upgrading prod from pricing-5 to pricing-7.

Use `run-local-stack` to serve the real corpus. Read-only on prod.

Resolve to: a measured trust bar (e.g. "% of listings with a defensible estimate") + a verdict
on comps-only vs catalog-fallback + the prod-version-upgrade call.

## Resolution (2026-07-30, research — ran pricing-7 over the real corpus)

Ran the prod method `inventory_comps` (pricing-7) via the engine's own store over **7,967 real SA
rows** (348 synthetic `zz*`/`karaa` excluded; pools built from real rows only).

**Measured:**
- **Defensible-estimate rate: ~32%** (trust ≥ medium, the engine's own confidence≥50 cut) — ~41%
  if you count everything that isn't very_low. **58.7% = `insufficient_data`** (very_low, no badge).
- **Accuracy where it fires** (|ask−est|/est, trust≥medium, n=2,584): **p50 5.4%, p75 13%, p90 25%,
  p95 37%; only 3% exceed a 50% gap.** Tight.
- Comp pools actually used after tier/variant/Tukey filtering: median 3, ≥3 comps 52%, ≥5 24%. Raw
  make/model pools are much fatter (85% have ≥5) — the strict tiering is what thins them.
- Tail: the worst mispricings are ~all very_low (self-anchor `manual` echoing the ask, or 1-comp
  `depreciation`). **The very_low band catches essentially the entire tail — it degrades honestly.**

**Decisions:**
1. **Trust bar = trust ≥ medium (confidence ≥ 50)** — adopt the engine's existing cut; that's what
   gates a visible estimate/deal badge. Expect a rated valuation on **~32–41% of SA listings**;
   show the rest as "not enough market data" (already the honest behavior).
2. **The failure is coverage, not correctness.** The lever to lift 32% is **denser comp data**
   (more real listings → ticket 004 coverage; and possibly wider year-banding in the mid tiers —
   graduate as fog if 004's volume gains don't suffice). **NOT** the catalog fallback.
3. **Catalog fallback (`msrp_depreciation`) stays off** — it can't help until markibx has MSRP +
   `vehicle_identity_id` (005). Enabling today rescues ~nothing and risks garbage.
4. **Deploy pricing-7 anyway** (→ 013): it's a real correctness fix (kills fabricated
   cross-variant/UNKNOWN_MODEL estimates); with reconcile off the stale pricing-5 rows never heal.
   It will *slightly lower* the defensible% by being stricter — accept that; honesty > vanity rate.

Key files: `pricing.py` (tier cascade), `dealscore.py:182` (insufficient_data=very_low), `types.py:176`
(trust 35/50/70), `pricing_methods/config.py:15`.
