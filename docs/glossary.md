# Glossary — karaa ecosystem

Terms agents keep re-deriving. Each fact has one home; this is the shortlist.

- **catalog_key** — a car's identity in the catalog: `make|model|year|trim`.
  `year == 0` = model-level parent (specs shared across years); `year > 0` = per-year
  child that inherits the parent and overrides only what changed.

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

- **CC-002** — contract decision: the API stores the advertised price as-is; `price_sar` is
  engine-internal and never serialized; FX conversion is the frontend's responsibility. Record:
  `DECISIONS.md` D-004 — **not** in `repos/KARA_CONTRACT_CHANGES.md`, which only ever contained
  CC-001 (the "full list" pointer here was dangling for weeks).
