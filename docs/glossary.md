# Glossary — karaa ecosystem

Terms agents keep re-deriving. Each fact has one home; this is the shortlist.

- **VehicleListing vs the catalog spine** — the distinction everything else hangs off.
  A **VehicleListing** (`mawtarx/types.py`) is *one seller's car at a point in time*: price,
  mileage, city, seller, photos, condition. The **catalog** is the markibx **spine**
  (`markibx/spine.py`): a curated `make → model → generation` registry of *reference specs* —
  no price, no seller, no mileage — each fact `{value, source, confidence}`. A listing links to
  a spine node by `catalog_car_id` (see below). The old flat `CatalogVehicle`/`CatalogCar` type
  and its `markibx/catalog.py` module were deleted (ADR 0003).

- **catalog_car_id** — a listing's link to the catalog spine: a **generation id**
  (`toyota:camry:xv70`) when the listing's year selects one, else a **model id**
  (`toyota:camry`) for a model-level link. It replaced the retired flat
  **`catalog_key`** (`make|model|year|trim`), which no longer exists.

- **generation** *(MVP catalog model — [`docs/markibx-mvp-catalog-model.md`](markibx-mvp-catalog-model.md))* —
  a model's design cycle: a year-range + manufacturer code (Camry `XV70`, 2018–2024). Specs
  cluster at this grain — constant within a generation, changed between. The **canonical spec
  unit** in the MVP model, promoting today's loose `generation` string / `year==0` parent to a
  first-class node. Curate once per generation, not per year.

- **market scope (global floor / market layers)** *(MVP catalog model)* — catalog specs are
  stored per market. `global` holds only *market-invariant* facts (the shared floor); each
  market (`GCC`, later `NA`…) is a sibling layer. A query in market M resolves `global ⊕ M`
  (M wins). **Markets never override each other**, and `global` is filled only when a fact is
  *verified* invariant (default is market-scoped). Launch price is per-`(generation, trim,
  market)` in **native currency** (Plan B). GCC seeded first ≠ GCC is "the main market".

- **price_sar** — a **derived display value, never stored and never serialized.** It is a
  field on `VehicleListing`, but `from_dict` always recomputes it from the native price
  (`to_sar_safe(price.val, price.cur, …)`), and `to_dict` deliberately omits it — it's
  `0.0`, not null, for any currency without a configured peg. The engine compares in native
  currency. Don't persist it, don't put it on a response model, and don't compute a market
  gap from it (use `price_delta_sar`). See `DECISIONS.md` D-002/D-004.

- **DealCategory** — the deal-score band on a listing: `exceptional`, `great`, `good`,
  `fair`, `high`, `overpriced` (`mawtarx/types.py`).

- **make_norm / model_norm** — the pricing-engine **matching** key (normalized, noisy:
  Arabic-script dupes, description-slug junk, one-offs). **Not** a display vocabulary —
  never build a dropdown from `SELECT DISTINCT make_norm`. See `mawtarx-api/AUTOCOMPLETE.md`.
  Noisy is the documented half; it can also be **silently wrong** — an unknown short make gets
  fuzzy-aliased onto a known one at high confidence (FAW → `baw`). Computed in *markibx*, not the
  scrapers: [`normalize-known-gaps.md`](normalize-known-gaps.md).

- **display vs slug** (autocomplete) — `slug` is the stable key (`versa`); `display` is the
  regional label (`Sunny`). Frontend sends the slug, shows the display.

- **GCC scope** — the six countries: `SA, AE, KW, QA, BH, OM`.

- **dedup_key** — cross-source listing identity: VIN-first; otherwise a per-connector
  fallback over `{make, model, year, trim, color, mileage_band, city}`, using only the
  fields that connector's data actually supports — populated reliably (low blank-rate)
  **and** varying (not a hardcoded constant, e.g. a single-location dealer's city). A
  connector needs 2+ such trusted fields or it falls back to `(source, source_id)`
  identity instead — zero collision risk, but reposts of the same real car won't merge.
  See `mawtarx/dedup.py` (`CONNECTOR_TRUSTED_FIELDS`) for the per-connector list.

- **Mojaz** — the vehicle-history contract. Never returns `verified` without real data
  (honest-by-default).

- **stored_intelligence** — the estimate + deal score computed at **write** time and stored on
  the listing; the serialization key for it. Deliberately *not* `intelligence`: the API card
  builders overwrite that key with a flat presentation block, so sharing it made kara-api
  hydrate an empty estimate. `None` means *not yet priced*, never "no comparables". D-007.

- **CC-002** — contract decision: advertised price stored as-is, FX is the frontend's job; see
  `price_sar` above. Authoritative record: `DECISIONS.md` D-004 (the "CC-002" label is informal).
