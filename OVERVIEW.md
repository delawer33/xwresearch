# kara — System Overview

Three repos form the Saudi vehicle-intelligence stack. They are layered: each package depends only on the one below it.

```
  exonware-kara              Pure domain library — entities, engines, stores (zero HTTP, zero DB driver)
         ↓
  exonware-kara-connect      Provider catalog + connector API (67 car-marketplace providers)
         ↓
  exonware-kara-api          Thin FastAPI layer — translates HTTP ↔ domain calls
```

## How They Connect

| Dependency | From | To | What crosses the boundary |
|---|---|---|---|
| `pip install -e ../kara` | kara-api | kara | VehicleListing, IVehicleStore, all engines, ScrapingPersistenceAdapter |
| `pip install -e ../kara` | kara-connect | kara | IVehicleStore, lifecycle.reconcile_disappeared, IngestionPipeline |
| `pip install -e ../kara-connect` | kara-api | kara-connect | build_connector, list_provider_info, ConnectorRunResult |
| xwapi.scrapping (3rd pkg) | kara | xwapi | IScraper, INormalizer, IPersistence, BaseScraper |

## What Each Repo Does

**`kara`** — Domain core. Owns all business logic: dedup, versioning, pricing engine (6-tier), deal score (0–100), fraud engine (7 flag types), Mojaz contract, market intelligence, city catalog, and three store backends (in-memory / JSON / xwjson). Framework-agnostic; no HTTP anywhere.

**`kara-connect`** — Provider catalog with 67 registered car marketplaces, dealer groups, auctions, CPO programs, and valuation references (Saudi-first, extends to GCC and US benchmarks). Each provider is a `Connector` subclass that wraps a `kara.connectors` adapter, handles sync, and optionally reconciles disappeared listings. It is the single source of truth for which platforms exist and how they are scraped.

**`kara-api`** — FastAPI host. Every route delegates immediately to `kara` or `kara-connect`; zero business logic lives here. Adds: Pydantic input validation, CORS, opaque bearer auth + PBKDF2 sessions, a pluggable store backend (xwjson preferred, JSON fallback), seeding on first boot, and an admin token gate.

## Runtime Flow (typical request)

```
Browser → GET /search/listings
  └── kara-api: validate query params → VehicleSearchFilter
        └── kara: store.search(filter) → list[VehicleListing]
              └── for each listing: PricingEngine + DealScoreEngine → card intelligence
  └── kara-api: serialize → JSON response

Browser → POST /connectors/saudisale/run  (admin)
  └── kara-api: require_admin → kara_connect.build_connector("saudisale", store)
        └── kara-connect: Connector.sync() → BaseScraper pipeline
              └── xwapi.scrapping: IScraper fetches pages → INormalizer → IPersistence
                    └── kara: ScrapingPersistenceAdapter.save() → store.upsert(listing)
        └── kara-connect: optional reconcile_disappeared()
  └── kara-api: return ConnectorRunResult.to_dict()
```

## Listing Ingestion

Listings enter the store in two ways: scraped from external marketplaces via connector runs, or posted directly by dealers/individuals through the API. Both paths write to the same `IVehicleStore`; direct listings get a pinned dedup key so they never merge with scraped copies of the same vehicle.

## Shared Conventions

- Python ≥ 3.12; plain dataclasses (no ORM, no Pydantic in domain); enums everywhere.
- `try/except on imports` is intentional — protects core from loading optional dependencies (xwjson, xwstorage-db).
- All currency in SAR; all geo in Saudi canonical city codes (`kara.cities`).
- Mojaz never returns `verified` without real data — honest-by-default.
- Connectors never bypass bot protection, CAPTCHAs, or access controls.
- Dedup key: VIN-first; fallback to `(make, model, year, mileage_band, city)`.
