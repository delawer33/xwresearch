# DECISIONS.md — why things are the way they are

Append-only. Newest first. One entry = one decision that a future agent would otherwise
re-litigate or accidentally reverse.

**Write an entry when** you make a call that the code can't explain on its own — a tradeoff, a
rejected alternative, a constraint you discovered the hard way. **Don't** write one for
implementation detail the diff already shows.

**Format:** date · what was decided · why · what it supersedes · where the code lives. Keep it
to a few lines — link the deep doc, don't inline it.

---

## D-007 — price estimates are computed on write and stored, never on read

**2026-07-18** · `store.upsert()` prices a listing and stores the estimate + deal score on it
(`VehicleListing.intelligence`); every read path serves that value. A write marks its
`(make_norm, model_norm)` bucket dirty and a background pass reprices only pools whose **median
moved materially** — not every pool that changed.

**Why:** both engines are pure functions of (listing, its pool), but reads re-ran them per row,
per request — ~15k estimates for one cold `/listings/recommended` (5-7s, GIL-held on the single
worker, stalling every other in-flight request). Repricing a whole bucket on *any* change just
moved that stall into the background thread (79.6s for one write into a pool of 8,539); one new
row shifts that median ~0.01%, so materiality is the gate.

**Supersedes:** the per-request pricing that `karaa_api.mawtarx_intel` and kara-api's
`inventory_cache` comps-index/cold-start caches existed to amortize — all removed.

**Code:** `repos/mawtarx/.../intelligence.py` + `refresh_runner.py`. Serialized as
`stored_intelligence` (see `docs/glossary.md` — **not** `intelligence`, which the card builders
overwrite). Bulk loads defer pricing; refreshes persist via `bulk_persist()`, never `upsert()`.

---

## D-006 — `dedup_key` falls back per-connector, not to a fixed field set

**2026-07-05** · Cross-source listing identity is VIN-first. Without a VIN, the fallback key is
built **per connector** from only the fields that connector's data actually supports —
populated reliably *and* varying. A connector with fewer than 2 such trusted fields falls back
to `(source, source_id)` identity instead.

**Why:** a fixed fallback field set collided and merged unrelated cars on data-poor connectors
(e.g. a single-location dealer where `city` is a constant carries no identity signal). Losing
repost-merging is acceptable; merging two different real cars is not.

**Code:** `repos/mawtarx/src/exonware/mawtarx/dedup.py` (`CONNECTOR_TRUSTED_FIELDS`, line ~68).
Term: `docs/glossary.md`.

---

## D-005 — `listings_mode=hybrid`: federate karaa's own store with mawtarx's listings

**2026-07-10** · kara-api serves listings from a store that federates its own xwjson data with
mawtarx-api's listings pulled over HTTP, rather than serving purely local or purely proxied.

**Why:** *(rationale not recorded at the time — the commit records the change, not the
tradeoff. If you know why, add it here.)*

**Code:** `repos/kara-api` (`listings_mode`); commit `358a57b`. Current server config:
`docs/vps-current-state.md`. Wiring: `ARCHITECTURE.md`.

---

## D-004 — CC-002: `price_sar` is engine-internal, never serialized on public payloads

**Recorded 2026-07-17; in force since at least 2026-06-29** · The API stores and serves the
advertised price **as-is** in its native currency. `price_sar` is a derived, engine-internal
value and is never serialized on a public listing payload. FX conversion for display is the
frontend's responsibility. Market-gap on a card must be computed from `price_delta_sar`, not
`price_sar`.

**Why:** `price_sar` is `price.val × peg` — a rate-dependent number that goes stale once
persisted (see D-002). Serializing it leaks a stale derived value into the contract; a
serialized `price_sar=0` produced cards that read "overpriced" and "below market"
simultaneously.

**Supersedes:** nothing. **Enforces:** D-002 at the contract boundary.

**Code:** `repos/kara-api/src/exonware/karaa_api/models.py:165` (the CC-002 comment).

> **Provenance:** "CC-002" was never written into `repos/KARA_CONTRACT_CHANGES.md` (it has only
> CC-001). It's cited from memory in three places, and they disagree — `models.py:165` and the
> glossary mean the price decision above; `kara/CONTEXT.md` (deleted) meant an unrelated
> "European/Slavic tier is first-class" call. That tier claim is unverified and homeless:
> `git -C repos/kara show 97339d4:CONTEXT.md` if it matters. This entry records only the price
> half, which is confirmed in code. The date is when it was *recorded*, not decided.

---

## D-003 — Per-km mileage adjustment is a fraction of value, not an absolute rate

**2026-07-03** · Replaced `PER_KM_SAR = 0.18` (a SAR-denominated constant) with
`FRAC_PER_KM ≈ 4.72e-6` (~0.47% of the comparable's own price per 1,000 km), anchored to the
SAR median price of 38,100.

**Why:** under D-002 the engine works in AED/KWD/PLN/YER — adding a SAR amount to a
native-currency price is dimensionally wrong. A fraction is unit-free and needs no FX. The SAR
**median** (38,100) was chosen as the anchor over the tail-inflated **mean** (97,566), which
would under-adjust the bulk of listings. (`YEAR_RETAINED = 0.91` is already a ratio, unaffected.)

**Deep doc:** `mawtarx-perkm-fraction-decision.md`.

---

## D-002 — Plan B: price in native currency; don't store `price_sar`

**2026-07-03** · The pricing engine compares listings **in their native currency**, scoped to
the same currency. FX (static SAR pegs, centralized in `fx.py`) is used **only** in the
cross-border fallback tiers. `price_sar` is not stored and not used for correctness.

**Why (measured on the live dev DB, 95,541 listings):** only **2,288 (2.4%)** are SAR-priced —
a SAR-denominated engine served 2.4% of inventory. The biggest single currency is PLN
(15,208), then AED (12,484), EUR (11,379); PLN/EUR/LYD/IQD **float** and can never be pegged,
so Plan A would have left ~50% of the data permanently `UNAVAILABLE`. A fair-value estimate is
a **ratio**, so the FX rate cancels for same-currency comparisons: `(a·r)/(b·r) = a/b`.

**Supersedes:** Plan A (convert every peggable currency to SAR at ingest, store `price_sar`,
compare in SAR). Plan A is dead — do not reintroduce a stored `price_sar` or a SAR-denominated
comparison.

**Deep doc:** `mawtarx-fx-plan-B.md`. **Consequences:** D-003, D-004.

---

## D-001 — CC-001: catalog-backed minimal seller flow

**2026-06-25** · Sellers may post with make+model+year (from catalog-backed dropdowns) plus
price/mileage/city only — `body_type`/`fuel_type`/`transmission` are optional on create. Reads
gain an additive `resolved_spec: {body_type, fuel_type, transmission, source: "listing" |
"catalog"}`, and a new `GET /catalog/makes/{make}/models/{model}/years` completes the dropdown
chain.

**Why:** sellers shouldn't need to know a car's body/fuel/transmission to list it; the catalog
already knows. `resolved_spec.source` lets any client distinguish an observed value from a
catalog-inherited one. Raw `listing.body_type` etc. are unchanged and never mutated by catalog
resolution — strictly additive, no client breaks.

**Deep doc:** `repos/KARA_CONTRACT_CHANGES.md` (CC-001);
rationale in `repos/CATALOG_ENRICHMENT_DECISIONS.md`.
