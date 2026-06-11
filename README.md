# eXonware Repo Ecosystem — Overview

---

## kara Family

Saudi vehicle-intelligence stack. Three layered repos — each depends only on the one below it.

```
  exonware-kara              Pure domain library — entities, engines, stores (zero HTTP, zero DB driver)
         ↓
  exonware-kara-connect      Provider catalog + connector API (67 car-marketplace providers)
         ↓
  exonware-kara-api          Thin FastAPI layer — translates HTTP ↔ domain calls
```

### How They Connect

| Dependency | From | To | What crosses the boundary |
|---|---|---|---|
| `pip install -e ../kara` | kara-api | kara | VehicleListing, IVehicleStore, all engines, ScrapingPersistenceAdapter |
| `pip install -e ../kara` | kara-connect | kara | IVehicleStore, lifecycle.reconcile_disappeared, IngestionPipeline |
| `pip install -e ../kara-connect` | kara-api | kara-connect | build_connector, list_provider_info, ConnectorRunResult |
| xwapi.scrapping (3rd pkg) | kara | xwapi | IScraper, INormalizer, IPersistence, BaseScraper |

### What Each Repo Does

**`kara`** — Domain core. Owns all business logic: dedup, versioning, pricing engine (6-tier), deal score (0–100), fraud engine (7 flag types), Mojaz contract, market intelligence, city catalog, and three store backends (in-memory / JSON / xwjson). Framework-agnostic; no HTTP anywhere.

**`kara-connect`** — Provider catalog with 67 registered car marketplaces, dealer groups, auctions, CPO programs, and valuation references (Saudi-first, extends to GCC and US benchmarks). Each provider is a `Connector` subclass that wraps a `kara.connectors` adapter, handles sync, and optionally reconciles disappeared listings. It is the single source of truth for which platforms exist and how they are scraped.

**`kara-api`** — FastAPI host. Every route delegates immediately to `kara` or `kara-connect`; zero business logic lives here. Adds: Pydantic input validation, CORS, opaque bearer auth + PBKDF2 sessions, a pluggable store backend (xwjson preferred, JSON fallback), seeding on first boot, and an admin token gate.

### Runtime Flow (typical request)

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

### Listing Ingestion

Listings enter the store in two ways: scraped from external marketplaces via connector runs, or posted directly by dealers/individuals through the API. Both paths write to the same `IVehicleStore`; direct listings get a pinned dedup key so they never merge with scraped copies of the same vehicle.

### Shared Conventions

- Python ≥ 3.12; plain dataclasses (no ORM, no Pydantic in domain); enums everywhere.
- `try/except on imports` is intentional — protects core from loading optional dependencies (xwjson, xwstorage-db).
- All currency in SAR; all geo in Saudi canonical city codes (`kara.cities`).
- Mojaz never returns `verified` without real data — honest-by-default.
- Connectors never bypass bot protection, CAPTCHAs, or access controls.
- Dedup key: VIN-first; fallback to `(make, model, year, mileage_band, city)`.

---

## xwauth Family

| Repo              | Package                    | Role                                                                                                                                    |
| ----------------- | -------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| `xwauth`          | `exonware-xwauth`          | OAuth 2.0 / OIDC core library: contracts, base classes, facade, tokens, sessions, federation, JOSE, SCIM, audit, webhooks, integrations |
| `xwauth-identity` | `exonware-xwauth-identity` | First-party login ceremonies: email/password, magic links, phone OTP, TOTP, WebAuthn/passkeys, MFA, organizations, B2B, SCIM, FGA       |
| `xwauth-connect`  | `exonware-xwauth-connect`  | External IdP connector: 250+ OAuth/OIDC providers (Google, Apple, Microsoft, GitHub, …), SAML, LDAP, regional providers                 |

**Invariant:** `xwauth-identity` never imports `xwauth-connect`. Both discover each other at runtime via `discover_connect_package()` / `discover_identity_package()`.

**Install combinations:**

- `xwauth` alone → OAuth 2.0 mechanics + client helpers, no login UI
- `xwauth` + `xwauth-identity` → full first-party IdP
- `xwauth` + `xwauth-connect` → federated SSO broker
- All three → complete auth platform

---

## xwstorage Family

| Repo                | Package                      | Role                                                                                                                                                                         |
| ------------------- | ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `xwstorage`         | `exonware-xwstorage`         | Shared contracts, error types, enums, path utilities, one concrete local (file-backed) connector                                                                             |
| `xwstorage-connect` | `exonware-xwstorage-connect` | Connector runtime: 50+ backend connectors (PostgreSQL, MongoDB, Neo4j, Redis, S3, …), HTTP API server, ACID transactions, MVCC, deadlock detection, RLS, encryption, caching |
| `xwstorage-db`      | `exonware-xwstorage-db`      | Embedded XW-native database engine: XWJSON-backed, CRUD, indexing (hash/sorted/trigram), transactions, snapshots, RLS, streaming I/O, admin CLI                              |

**Dependency direction:** `xwstorage-db` → `xwstorage` ← `xwstorage-connect`. xwstorage-connect may use xwstorage-db as an engine driver; xwstorage-db must NOT import xwstorage-connect.

---

## Cross-Family Integration

```
Application
    │
    ├─ xwauth / xwauth-identity / xwauth-connect
    │       │
    │       └─ IStorageProvider ──► xwstorage / xwstorage-connect
    │
    └─ xwstorage / xwstorage-connect
            │
            └─ optional embedded engine ──► xwstorage-db
```

Auth packages use storage packages via `IStorageProvider` (pluggable). `xwstorage-connect` can wire `xwstorage-db` as the embedded engine backend.

---

## Shared Base: xwsystem

All 6 repos depend on `exonware-xwsystem` (v0.9.0.x). It provides: security primitives, HTTP client, serialization, logging, `XWObject` base class, `PolicyContext` / `IAuthContextResolver` contracts.

---

## Versions at Time of Analysis (June 2026)

| Repo              | Version  | Status    |
| ----------------- | -------- | --------- |
| xwauth            | 0.0.1.11 | Alpha     |
| xwauth-identity   | 0.0.1.4  | Alpha     |
| xwauth-connect    | 0.0.1.11 | Alpha     |
| xwstorage         | 0.0.1.9  | Alpha     |
| xwstorage-connect | 0.0.1.9  | Alpha     |
| xwstorage-db      | 0.0.1.5  | Pre-alpha |

---

## Individual Reports

- [kara.md](kara.md)
- [kara-api.md](kara-api.md)
- [kara-connect.md](kara-connect.md)
- [xwauth.md](xwauth.md)
- [xwauth-identity.md](xwauth-identity.md)
- [xwauth-connect.md](xwauth-connect.md)
- [xwstorage.md](xwstorage.md)
- [xwstorage-connect.md](xwstorage-connect.md)
- [xwstorage-db.md](xwstorage-db.md)
