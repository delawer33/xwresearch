# kara

> `exonware-kara` · `repos/kara` · v0.0.1

## A. What It Does

Pure Python, framework-agnostic domain library — the Saudi vehicle-intelligence engine. No HTTP, no UI, no database driver. Owns all business logic for the kara product: canonical listing shape, cross-source dedup, price/deal/fraud scoring, vehicle history contract, car catalog, city registry, and market intelligence. Designed to be consumed by `kara-api` and `kara-connect`.

**Product philosophy** (README.md:47–54):
- Domain types are plain dataclasses, not ORM/schema objects — light, serializable, zero coupling.
- Schema validation lives at the kara-api boundary.
- Engines are deterministic and explainable — every score carries its reasoning. No LLM in MVP.
- Security-first: plates stored only as `plate_hash`; Mojaz never shows `verified` without evidence; connectors never bypass site protections.
- `try/except on imports` is intentional — keeps core zero-dependency when optional extras (xwjson, xwstorage-db) are absent.

---

## B. Backend Architecture

**Layers** (src/exonware/kara/):

```
Types / Enums          types.py                  Canonical VehicleListing + all enums
Contracts              contracts.py              IVehicleStore, IPricingEngine, IDealScoreEngine protocols
Dedup & Versioning     dedup.py, versioning.py   Cross-source identity + price/spec history
Stores                 store.py, store_xwstorage.py  InMemory, JSON, XwJson, XwStorageDb
Engines                pricing.py, dealscore.py, fraud.py, mojaz.py, market.py
Services               service.py                Orchestrates engines into ListingIntelligence
Connectors             connectors/               Per-platform adapters + registry + pipeline
Catalog                catalog.py, catalog_*.py  Car specs DB with inheritance + enrichment
Cities                 cities.py                 Saudi canonical city registry + geocoding
Lifecycle              lifecycle.py              Reconcile disappeared listings
Insights               insights.py               Market intelligence aggregates
CLI                    cli.py                    seed / analyze / kpis / catalog-refresh
```

**Key design patterns:**
- Protocol-based decoupling (contracts.py:1–76): stores and engines swappable without code changes.
- 6-tier pricing hierarchy (pricing.py:67–161): exact_match → similar_match → regional_average → depreciation_model → manual; each tier carries explicit confidence.
- Lazy imports (\_\_init\_\_.py:128–141, store_xwstorage.py:40–41): `try/except ImportError` gates optional dependencies; core stays zero-dep.
- Thread-safe stores (store.py:57–156): RLock on InMemory; write-through on JsonFile.
- Connector registry (connectors/registry.py): `@register_source` decorator auto-registers adapter factories at import time.
- Catalog inheritance (catalog.py:168–192): sparse `attrs` dict; `resolve_car` + `flatten_car` walk parent chain for full spec.

---

## C. Main Folders and Files

| File | Purpose |
|---|---|
| `src/exonware/kara/__init__.py` | Public API surface (179 lines); re-exports all types, stores, engines, services |
| `src/exonware/kara/types.py` | All enums + dataclasses: VehicleListing, PriceEstimate, DealScore, MojazReportSummary, FraudFlag, VehicleSearchFilter |
| `src/exonware/kara/contracts.py` | IVehicleStore, IPricingEngine, IDealScoreEngine protocols |
| `src/exonware/kara/dedup.py` | Dedup key computation (VIN-first, fallback to make/model/year/mileage_band/city) + normalize_vin |
| `src/exonware/kara/versioning.py` | Per-source version chains: record_version, price_history, history_for, compute_content_hash |
| `src/exonware/kara/store.py` | InMemoryVehicleStore, JsonFileVehicleStore, ScrapingPersistenceAdapter |
| `src/exonware/kara/store_xwstorage.py` | XwJsonVehicleStore, XwStorageDbVehicleStore (optional [storage] extra) |
| `src/exonware/kara/pricing.py` | PricingEngine: 6-tier matching, explainable fair-value estimates |
| `src/exonware/kara/dealscore.py` | DealScoreEngine: 0–100 score, category bands, mileage/history/trust modifiers |
| `src/exonware/kara/fraud.py` | FraudEngine: VIN mismatch, duplicate image, repeated phone, suspicious price, abnormal mileage |
| `src/exonware/kara/mojaz.py` | build_mojaz_summary: vehicle-history contract — never fakes `verified` |
| `src/exonware/kara/market.py` | listing_quality_score, seller_trust_score, supply_for |
| `src/exonware/kara/service.py` | analyze_listing, estimate_price, score_deal, seed_sample_data, admin_kpis |
| `src/exonware/kara/catalog.py` | CatalogVehicle/CatalogCar, ICatalogStore, InMemoryCatalogStore, JsonFileCatalogStore, resolve_car |
| `src/exonware/kara/catalog_nhtsa.py` | NHTSA vPIC client: refresh_catalog, vin_to_catalog_vehicle, decode_vin_dict |
| `src/exonware/kara/catalog_wikidata.py` | Wikidata SPARQL enrichment: enrich_wikidata_specs, ingest_wikidata_models |
| `src/exonware/kara/catalog_link.py` | link_listings_to_catalog — match listings to catalog entries |
| `src/exonware/kara/catalog_seed.py` | seed_top_ksa_models — pre-populate top KSA makes/models |
| `src/exonware/kara/car_spec.py` | CAR_SPEC_SCHEMA (34 categories, 200+ fields), schema_payload, clean_attrs |
| `src/exonware/kara/cities.py` | CityInfo, resolve_city, get_city, all_cities — Saudi city registry |
| `src/exonware/kara/lifecycle.py` | reconcile_disappeared, scope_by_makes — mark stale listings SOLD/EXPIRED |
| `src/exonware/kara/insights.py` | price_history, ratings, makers, city_availability — chart/analytics data |
| `src/exonware/kara/cli.py` | CLI: seed, analyze, kpis, catalog-refresh |
| `src/exonware/kara/connectors/registry.py` | SOURCE_REGISTRY, @register_source, build_adapter, list_sources |
| `src/exonware/kara/connectors/pipeline.py` | IngestionPipeline: orchestrates scrape runs + optional reconcile |
| `src/exonware/kara/connectors/sources/` | Per-platform adapters: synthetic, haraj, syarah, saudisale, opensooq, sayarat, samaco, … |
| `tests/conftest.py` | make_listing helper, store fixture, seeded_store fixture |
| `scripts/` | seed_sample_data.py, ingest_and_link.py, enrich_wikidata.py, scrape_saudisale.py |
| `data/` | Sample listings directory (not tracked; created by CLI) |

---

## D. Data Models and Entities

### Enums (types.py:30–122)

| Enum | Values |
|---|---|
| `SellerType` | INDIVIDUAL, DEALER, UNKNOWN |
| `ListingStatus` | DRAFT, ACTIVE, SOLD, EXPIRED, REJECTED, UNKNOWN |
| `ListingSource` | KARA, HARAJ, SAUDISALE, OPENSOOQ, SAYARAT, SAMACO, SYARAH, MOTORY, YALLAMOTOR, DUBIZZLE, CARSWITCH, CONTACTCARS, MSTAML, SYNTHETIC, OTHER |
| `DealCategory` | EXCEPTIONAL, GREAT, GOOD, FAIR, HIGH, OVERPRICED |
| `PriceMethod` | EXACT_MATCH, SIMILAR_MATCH, REGIONAL_AVERAGE, DEPRECIATION_MODEL, MANUAL |
| `MojazStatus` | NOT_AVAILABLE, REDIRECT_AVAILABLE, VERIFIED, FAILED |
| `ConnectorType` | API, FEED, MANUAL_IMPORT, MOCK, DISABLED |
| `MarketplaceStatus` | ACTIVE, LIMITED, DISABLED, PLANNED |
| `FraudType` | DUPLICATE_VIN, DUPLICATE_IMAGE, SUSPICIOUS_PRICE, ABNORMAL_MILEAGE, VIN_MISMATCH, REPEATED_PHONE, FAKE_LISTING_PATTERN, SOURCE_DUPLICATE |
| `Severity` | LOW, MEDIUM, HIGH |

### Core Dataclasses (types.py)

**`SourceProvenance`** (138–165) — `source, source_id, source_url, fetched_at`; `to_dict/from_dict`

**`ListingVersion`** (168–212) — `source, source_id, content_hash, valid_from, valid_to, seen_count, fields: dict`; `is_current()`

**`VehicleIdentity`** (215–255) — `id, vin, plate_hash, make_id, model_id, trim_id, year, body_type, fuel_type, transmission, drivetrain, engine`

**`VehiclePhoto`** (258–290) — `id, listing_id, url, sort_order, storage_key, hash, perceptual_hash, is_primary`

**`VehicleListing`** (310–466) — Core identity and pricing fields, geo (city_code, lat, lng), presentation (title, trim, description, color, photos), vehicle identity (vin, plate_hash, body_type, fuel_type, transmission, drivetrain), trust signals (accident_free, owner_count, service_history, warranty_active), contact (seller_phone, seller_whatsapp), cross-source tracking (sources list, versions list, dedup_key, first/last_seen_at), extras dict. Methods: `primary_photo`, `to_dict/from_dict`.

**`PriceEstimate`** (472–513) — `listing_id, estimated_fair_value_sar, price_range_min/max_sar, confidence_score, comparable_count, method: PriceMethod, explanation: list[str]`

**`DealScore`** (516–551) — `listing_id, score: int, category: DealCategory, price_delta_sar, price_delta_percent, reasons: list[str]`

**`MojazReportSummary`** (554–597) — `listing_id, status: MojazStatus, vin, ownership_count, accident_records_count, insurance_claims_count, odometer_records_count, inspection_records_count, report_url, fetched_at`

**`FraudFlag`** (641–673) — `listing_id, type: FraudType, severity: Severity, score_impact: float, evidence: list[str]`

**`VehicleSearchFilter`** (679–776) — Full filter: make, model, trim, year range, price range, mileage range, city, region, seller_type, source, status, fuel_type, transmission, has_vin, featured_only, text, sort, limit, offset. Method: `matches(listing)`.

**`CatalogVehicle`** (catalog.py:52–161) — `make, model, year, trim, generation, variant, parent_id, vehicle_type, body_type, fuel_type, transmission, drivetrain, doors, engine_cylinders, displacement_l, original_launch_price_sar, attrs: dict, source, specs: dict`. Method: `key` property.

**`ListingIntelligence`** (service.py:42–58) — `estimate: PriceEstimate, deal_score: DealScore, mojaz: MojazReportSummary, fraud_flags: list[FraudFlag], quality_score: float`. Method: `to_dict()`.

**`CityInfo`** (cities.py:25–40) — `code, name_en, name_ar, region_en, region_ar, lat, lng`.

---

## E. APIs, Endpoints, and Services

### Store Protocol (contracts.py:30–59)

| Method | Signature | Notes |
|---|---|---|
| `upsert` | `(listing) → bool` | Insert or merge by dedup_key; True if new |
| `get` | `(listing_id) → VehicleListing \| None` | By id |
| `get_by_dedup_key` | `(dedup_key) → VehicleListing \| None` | By dedup key |
| `search` | `(flt: VehicleSearchFilter) → list[VehicleListing]` | Filtered + sorted + paged |
| `iter_all` | `() → Iterable[VehicleListing]` | Stream all |
| `count` | `() → int` | Total |

### Service Functions (service.py)

| Function | Signature | Notes |
|---|---|---|
| `analyze_listing` | `(listing, store, mojaz_redirect_base=None) → ListingIntelligence` | Full pass: price + deal + Mojaz + fraud + quality |
| `estimate_price` | `(listing, store) → PriceEstimate` | Pricing engine only |
| `score_deal` | `(listing, store) → DealScore` | Price + deal score |
| `seed_sample_data` | `(store, count=200, seed=None) → int` | Populate with synthetic listings |
| `admin_kpis` | `(store) → dict` | Dashboard KPIs |

### Engine Methods

| Engine | Method | Returns |
|---|---|---|
| `PricingEngine` | `estimate(listing, comparables)` | `PriceEstimate` |
| `DealScoreEngine` | `score(listing, estimate, mojaz=None)` | `DealScore` |
| `FraudEngine` | `evaluate(listing, store)` | `list[FraudFlag]` |

### Connectors

| Function | Notes |
|---|---|
| `@register_source(source_id)` | Decorator; registers adapter factory |
| `build_adapter(source_id, **kwargs)` | Returns `(IScraper, INormalizer)` |
| `list_sources() → list[MarketplaceSource]` | All registered sources |
| `IngestionPipeline(store).run(source_id, ...)` | Full scrape run with optional reconcile |

---

## F. Auth, Security, Config, and Env Variables

### Security measures

- `plate_hash` only — plate number never stored in plain text (types.py:VehicleListing)
- Mojaz contract — `build_mojaz_summary` returns `NOT_AVAILABLE` or `REDIRECT_AVAILABLE` only; never forges `VERIFIED` (mojaz.py:7–12)
- VIN validation — normalize to uppercase, length-checked to 17 chars (dedup.py:43–50)
- Connectors — xwapi.scrapping framework enforces rate limits; no bypass of robots.txt, CAPTCHAs, or access controls (README.md:54)
- No LLM — all scoring is deterministic and explainable

### Optional env vars (catalog.py:248–275)

| Var | Purpose |
|---|---|
| `KARA_CARAPI_TOKEN` | CarAPI.app catalog enrichment (requires key) |
| `KARA_AUTODATA_KEY` | Auto-Data.net enrichment (requires key) |
| `KARA_JATO_KEY` | JATO enrichment — best for Saudi launch prices (requires key) |

No `.env` file in repo. Core requires no env vars.

---

## G. Database, Storage, Queues, Background Jobs

### Store implementations

| Store | Location | Notes |
|---|---|---|
| `InMemoryVehicleStore` | store.py:57–156 | Thread-safe (RLock); dicts by dedup_key and id; full merge on upsert |
| `JsonFileVehicleStore` | store.py:158–220 | Extends InMemory; write-through to JSON (atomic rename + .tmp fallback); handles corrupt files |
| `XwJsonVehicleStore` | store_xwstorage.py | Extends InMemory; binary xwjson serialization; recommended for production; lazy import |
| `XwStorageDbVehicleStore` | store_xwstorage.py | Scaffold; requires xwstorage-db dep; lazy import |
| `InMemoryCatalogStore` | catalog.py:296–363 | Thread-safe dict-backed |
| `JsonFileCatalogStore` | catalog.py:366– | JSON persistence + bulk upsert_many |

No queue system. No background jobs. Connector runs and catalog refreshes are caller-triggered.

---

## H. How to Run Locally

```bash
# Install
pip install -e .             # core (in-memory / JSON stores)
pip install -e .[storage]    # + xwjson / xwstorage-db
pip install -e .[dev]        # + black / mypy / pytest

# CLI
kara seed --out data/listings.json --count 200
kara analyze --store data/listings.json --limit 5
kara kpis --store data/listings.json
kara catalog-refresh --out kara-data/catalog.xwjson

# Quick Python start
from exonware.kara import InMemoryVehicleStore, seed_sample_data, score_deal
store = InMemoryVehicleStore()
seed_sample_data(store, count=200)
listing = next(iter(store.iter_all()))
print(score_deal(listing, store).category)
```

**Requires**: Python ≥ 3.12. `pytest` runs via `pytest tests/` (addopts: `-q`).

---

## I. Tests Available and Tests Missing

### Test files (tests/)

| File | What it covers |
|---|---|
| `conftest.py` | make_listing helper, bare store, seeded_store (200 synthetic listings) |
| `test_pricing.py` | Exact-match tier (city cluster), manual fallback (no comparables), nearby-years tier |
| `test_dealscore.py` | Below-market → GREAT/EXCEPTIONAL, above-market → HIGH/OVERPRICED, low-confidence tempering |
| `test_fraud_and_mojaz.py` | Suspicious low price, repeated phone, VIN-year mismatch, abnormal mileage, Mojaz NOT_AVAILABLE and REDIRECT_AVAILABLE |
| `test_store.py` | Dedup-merge, cross-source provenance, version chain on price change, JSON round-trip |
| `test_types_and_dedup.py` | Type serialization, dedup key computation |
| `test_connectors.py` | Connector integration, synthetic data generation |
| `test_catalog.py` | Catalog store CRUD, inheritance, query |
| `test_insights.py` | Price history series, ratings, maker aggregates, city availability |

### Missing tests

- No thread-safety tests (concurrent upserts under RLock)
- No load tests (pricing/dedup on 100k+ listings)
- No lifecycle/reconcile_disappeared edge cases
- No city resolver tests (Arabic/English normalization)
- No NHTSA vPIC integration tests (requires network)
- No Wikidata enrichment tests
- No real connector adapter tests (haraj, syarah, etc. — disabled by default, no mock path)

---

## J. Risks, Unclear Parts, and Questions

### Code risks

**`REFERENCE_YEAR` hardcoded** (dealscore.py:34, fraud.py:31, insights.py): `REFERENCE_YEAR = 2026` set as module-level constant in multiple engines. Breaks silently in multi-year or multi-region deployments. Should be injected at engine construction time.

**Bare exception handlers** (store.py:185, 197; catalog.py:392, 399; store_xwstorage.py:67–70): `except Exception: pass` with `# noqa: BLE001` comments. Intentional for corrupt-file recovery, but makes debugging disk/permission errors invisible.

**Circular import guard** (service.py:95–96): `IngestionPipeline` imported inside `seed_sample_data()` to avoid a circular dependency. Fragile — any refactor of the import graph could silently break it.

**Plate hash** — `plate_hash` field exists on VehicleListing but no hash algorithm, salt, or hashing function is defined in this library. How plates are hashed before storage is undefined.

**Dedup key immutability** (dedup.py, store.py): `dedup_key` is computed once and cached. If a listing's VIN is corrected later, the key becomes stale; no re-key logic exists.

**Version content hash covers only 7 fields** (versioning.py:32–40): changes to color, body_type, vin, or other fields do not trigger a new version entry — silently overwritten on merge.

### Architectural issues 

**Fraud score not wired into DealScore**: `FraudEngine` produces scored flags; `DealScoreEngine` does not consume them. `analyze_listing` returns both separately. A listing with HIGH-severity fraud flags can still get `DealCategory.EXCEPTIONAL`. The two signals are never combined into a single "trustworthy + fair" metric.

**Listing quality score unused in ranking**: `listing_quality_score()` (market.py:29–56) is computed in `analyze_listing` but is not used by `store.search()` sort order. Buyers never see quality-weighted results.

**Pricing tier logic is hard-coded**: The 6-tier if-chain in pricing.py:67–161 is not data-driven or pluggable. Changing tier thresholds, adding a new source of comparables, or tuning confidence weights requires editing engine code rather than configuration.

**VehicleSearchFilter.matches() normalizes case but not script**: casefold() applied but no Arabic diacritic normalization. A buyer searching "الرياض" vs "رياض" may get different results.

**Connector pagination state not persisted between runs**: `IngestionPipeline` creates a new `ScrapingPersistenceAdapter` per run. There is no "last-seen cursor" or checkpoint; each run re-scans from page 1.

**InMemoryCatalogStore and JsonFileCatalogStore duplicate store logic**: Both implement the same CRUD pattern as vehicle stores but with no shared base. The vehicle and catalog store contracts differ minimally, yet share no code.

**Market intelligence uses hardcoded per-make review profiles** (insights.py:41–52): Baseline review scores per brand are baked into synthetic generation. Real integrations (Edmunds, KBB, MotorTrend) are scaffolded but not plugged in; the schema would need changes to support external review sources.

### Open questions

- What hash algorithm is used for `plate_hash`? Where does hashing happen (client? API boundary?)?
- When are real connector adapters (haraj, syarah) expected to be activated?
- Should `REFERENCE_YEAR` be a config value per deployment environment?
- How deep can the `CatalogVehicle.parent_id` chain go? Is there a documented max depth?

---

## K. Suggested First Improvements

### Risk analysis

1. **Inject `REFERENCE_YEAR` at engine init**: Pass current year to `DealScoreEngine`, `FraudEngine`, and `insights` functions rather than reading a module constant. Fixes multi-year deployments and makes tests deterministic.

2. **Define plate hashing contract**: Add a `hash_plate(plate: str) → str` function (HMAC-SHA256 with a secret, or SHA-256 with a salt) inside `kara` so the hashing algorithm is explicit and testable. The current implementation is undefined.

3. **Wire fraud impact into DealScore**: Pass `fraud_flags` to `DealScoreEngine.score()` (or to `analyze_listing`). Apply a score penalty for HIGH/MEDIUM severity flags so the final `DealCategory` reflects both price fairness and listing trust.

4. **Fix re-key logic**: When `store.upsert()` detects a VIN update on an existing listing (old dedup_key used `make/model` fallback, new one has VIN), migrate the record to the new key rather than creating a duplicate.

5. **Add thread-safety and load tests**: The `InMemoryVehicleStore` RLock is untested under concurrent writes. Add a pytest fixture that spawns 10 threads and verifies counts.

### Architectural analysis

6. **Include quality score in search ranking**: Expose `listing_quality_score` as an optional sort key (e.g., `sort=quality`) in `VehicleSearchFilter`. Currently computed but never surfaced to buyers.

7. **Make pricing tiers configurable**: Extract the tier thresholds and confidence weights in `PricingEngine` to a `PricingConfig` dataclass passed at construction. Allows A/B testing and region-specific tuning without engine code changes.

8. **Add Arabic normalization to search filter**: In `VehicleSearchFilter.matches()`, normalize Arabic text (strip diacritics, unify forms) before casefold comparison so city/make searches work in both scripts.

9. **Shared base for catalog stores**: Extract a `BaseFileStore` or mixin that both `JsonFileVehicleStore` and `JsonFileCatalogStore` extend. Reduces duplicated atomic-write and corrupt-file-recovery logic.

10. **Add scraper checkpoint support**: Add an optional `cursor` parameter to `IngestionPipeline.run()` that lets callers pass the last-seen page or ID, enabling incremental scrapes rather than full re-scans.
