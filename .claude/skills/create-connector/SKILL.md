---
name: create-connector
description: >
  Build or activate a marketplace car-listing connector in repos/mawtarx-connect —
  a scraper that pulls car adverts into the mawtarx listings DB. Use when the user
  says "add a connector / scraper", "wire up <site>", "activate <provider>", "scrape
  <marketplace>", "the connector for <site> is missing fields", or invokes
  /create-connector.
---

# Create / activate a connector

A connector pulls **car advertisements** (a specific unit for sale: price, mileage, seller,
city, photos) from one marketplace into the mawtarx listings DB. NOT a car-spec source —
model-level facts belong in markibx-connect.

Paths relative to **`repos/mawtarx-connect/`**. Python = **`repos/.venv/bin/python`**.

This is a map of how the system works and where it bites — **not a checklist.** Every site is
different; look at what the site actually serves and adapt. If a convention here fights the
reality of the site, reality wins (and note the deviation in
`repos/mawtarx-connect/docs/gcc-connector-field-notes.md` if you're on the GCC loop).

## Architecture facts (these are code-truth, not style)

- **The source file IS the connector**: `src/.../connectors/sources/<name>.py` — Scraper +
  Normalizer + `@register_source`. Everything (prod `collect.py`, debug runner, `Connector.sync`)
  resolves through it. A `providers/<name>.py` `ProviderInfo` card is optional directory metadata,
  NOT needed for ingestion, and a card existing proves nothing about a scraper existing.
- **Request params live on the source** via `register_source(..., default_params={...})`;
  `collect.yaml` overrides per-key. Params in a provider's `default_request_params()` are dead —
  production never reads them.
- **Two run surfaces**: `scripts/collect.yaml` → `scripts/collect.py` (manual/bulk); prod runner
  sweeps `sweep_profiles.py._DEFAULTS`. Registering + collect.yaml alone does NOT make prod sweep it.
- The engine drives: `scraper.fetch(request)` → per raw → `normalizer.normalize(raw, source)` →
  persist. A normalizer returning `None` drops the record **silently**.
- Copy the shape from a real source whose fetch style matches (JSON API vs HTML) — but read it
  critically; existing connectors carry bugs too.

## What persists (the contract that silently eats your work)

`record_to_listing` (`repos/mawtarx/.../store.py`) is the authority:

- A record without `make`, `model`, and a non-zero price **does not persist at all** — dropped
  silently.
- **The emit list is an allowlist.** Keys it doesn't know (e.g. `cylinder_count`) go nowhere,
  silently. A useful extra field has two homes: the `extras` dict, or promotion to a first-class
  `VehicleListing` field. Never fold data into free-text and hope.
- Standard keys (see any real normalizer): `source`, `source_id`, `source_url`, `fetched_at`,
  `title`, `make`, `model`, `year`, `trim`, `price_value`, `price_currency`, `country`,
  `mileage_km`, `city`, `region`, `body_type`, `fuel_type`, `transmission`, `drivetrain`,
  `engine`, `color`, `vin`, `description`, `photos`, `seller_type`, `seller_id`, `seller_phone`,
  `seller_whatsapp`, `dealer_id`.
- **Price is native**: `price_value` + `price_currency` (`"KWD"`). Never convert to SAR — that's
  derived downstream.
- **VIN whenever the site has it** — strongest dedup key, sidesteps the whole fallback mess.
- Cheap sanity: push one normalized record through `record_to_listing` and see which keys
  survived. Emitting a field the pipeline discards == not emitting it.

## Conventions that keep the data mergeable

- **English for structured fields** (make/model/color/body/fuel/city). Prefer the site's English
  version or JSON API. Otherwise translate via a curated table in the source file (pattern:
  `saudisale.py` `_BRANDS_AR`); leave uncovered values native rather than guessing. Free-text
  `description` may stay native.
- **Shared normalizers**: `norm_body`, `norm_fuel`, `norm_transmission`, `norm_color` from
  `connectors/normalize.py`. Unmapped label → add it to `normalize.py`, not a special case in
  your connector.
- **Dedup without VIN** falls back to a per-connector key over `{trim, color, city}`
  (`mawtarx/dedup.py :: CONNECTOR_TRUSTED_FIELDS`) needing 2 fields that are populated **and
  actually vary** — a single-location dealer's constant `city` is worthless there.
- **HTTP goes through `xwapi.scrapping`** (`RequestPolicy` / `PolicyHttpFetcher`). Don't hand-roll
  httpx.

## Traps (each one shipped a real bug)

- **A block looks exactly like "no results".** A WAF/challenge page can be HTTP 200 that parses
  to nothing; `raw=0 persisted=0` with a clean DONE is a red flag, not a pass. Make the scraper
  distinguish blocked from empty (`haraj.py` raises on the block response).
- **Seller-chosen dropdowns are noise, not specs.** Trusting a marketplace's own "Category" gave
  `bahraincars` 89% wrong `body_type`.
- **Loosely-scoped first-match regex grabs the wrong element** — locate the authoritative element,
  then match inside it (page-wide "first city-looking string" stored the wrong city for everyone).
- **A field that looks absent is often just under a label you didn't check** — skim a real detail
  page's label/value pairs before writing a field off. And distinguish "site genuinely omits it"
  (real, document it) from "my parser missed it" (bug).
- **Don't change a live connector's dedup fields or `source_id` format** without recomputing
  `dedup_key` on stored rows — drift orphans them and re-scrapes duplicate instead of update.
- **Never bypass access controls, robots, or rate limits.** Cloudflare/CAPTCHA/partner-wall →
  the connector is DEAD/parked, not a challenge to beat.

## Validate on live rows

The only proof a connector works is real rows from the live site with sensible fields. Fixture
tests are regression insurance, not evidence of life. Quick harness (no DB):

```python
from exonware.mawtarx_connect.connectors import build_adapter, get_source_defaults
from exonware.xwapi.scrapping.types import ScrapeRequest
s, n = build_adapter("<source_id>")
req = ScrapeRequest(source="<source_id>",
                    params={**get_source_defaults("<source_id>"), "page_end": 1})
for raw in s.fetch(req):
    print(n.normalize(raw, s.source))
```

Full run into a throwaway store:

```bash
repos/.venv/bin/python scripts/collect.py --sources <source_id> --fresh \
  --xwdb /tmp/connector-check
```

Judge the output like a skeptic: field blank-rates, prices in the right currency, page 1 vs
page 2 actually different listings, values that match what the site shows. What convinces *you*
it works is the bar — not a ritual.

## Catalog linking is not your job

`catalog_car_id` resolution runs downstream at ingest (`mawtarx/store.py`). `split_model_trim`
(local model/trim splitter) is fine to use; full catalog resolution is not the connector's.
