# Glossary — karaa ecosystem

Terms agents keep re-deriving. Each fact has one home; this is the shortlist.

- **VehicleListing vs CatalogVehicle** — the distinction everything else hangs off.
  A **VehicleListing** (`mawtarx/types.py`) is *one seller's car at a point in time*: price,
  mileage, city, seller, photos, condition. A **CatalogVehicle** (`markibx/catalog.py`) is the
  *reference spec* for a make/model/year/trim — no price, no seller, no mileage. A listing
  links to a catalog entry by `catalog_key`. (Older docs call the latter `CatalogCar`; that
  name is gone.)

- **catalog_key** — a car's identity in the catalog: `make|model|year|trim`.
  `year == 0` = model-level parent (specs shared across years); `year > 0` = per-year
  child that inherits the parent and overrides only what changed.

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
  `price_sar` above. Record: `DECISIONS.md` D-004 — **not** `repos/KARA_CONTRACT_CHANGES.md`.
