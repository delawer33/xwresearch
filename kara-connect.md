# kara-connect

> `exonware-kara-connect` · `repos/kara-connect` · v0.0.1

## A. What It Does

Provider catalog and Connector API for the Saudi vehicle-intelligence stack. Bridges `xwapi.scrapping` (domain-neutral scraping framework) and `kara` (vehicle-storage layer). Registers 67 car-marketplace providers — Saudi marketplaces, dealer groups, auctions, CPO programs, global valuation references — each as a typed `Connector` subclass with declarative `ProviderInfo` metadata. `kara-api` uses this package to list available sources and trigger syncs.

**Philosophy**: only sites that serve public data politely are scraped live. Everything else is catalogued honestly with status `partner`, `limited`, or `planned` — never bypassing bot protection, CAPTCHAs, rate limits, or access controls.

---

## B. Backend Architecture

```
exonware.xwapi.scrapping     IScraper / INormalizer / IPersistence + BaseScraper
         ↓ (adapter pairs from kara.connectors)
exonware.kara.connectors     per-platform car adapters + ScrapingPersistenceAdapter → IVehicleStore
         ↓
exonware.kara_connect        provider catalog + Connector base class + registry  ← THIS PACKAGE
         ↓
exonware.kara_api            FastAPI host
```

**Core patterns**:

- **`@register_provider` decorator** (registry.py:27–33): auto-registers a `Connector` subclass in the global `CONNECTOR_REGISTRY` dict at import time. Validates that `INFO: ProviderInfo` exists.
- **Auto-import at module load** (providers/\_\_init\_\_.py): imports all 67 provider modules to trigger self-registration; one import of `exonware.kara_connect` makes all providers available.
- **Lazy adapter binding** (base.py:44–49): `_build_default_adapter()` deferred to first `sync()` call. Catalog-only providers (CPO pages, auctions, valuation references) can exist in the registry without a wired scraper — `sync()` returns a clean error on first call rather than crashing at construction.
- **Source-ID aliasing** (base.py:125–130): multiple provider entries can share one underlying kara adapter. Example: `samaco`, `samaco_vw`, `samaco_audi`, `samaco_porsche`, `samaco_bentley`, `samaco_lamborghini` all use `source_id="samaco"`.
- **Exception safety in sync** (base.py:118–119): all exceptions are caught and appended to `ConnectorRunResult.errors`; the call never raises.

**Sync flow** (base.py:60–122):
1. Merge `default_request_params()` with caller `params`.
2. Build `ScrapeRequest(source=id, params=merged, max_records=max_records)`.
3. Run `BaseScraper(scraper, normalizer, ScrapingPersistenceAdapter(store))`.
4. Aggregate results into `ConnectorRunResult`.
5. If `reconcile=True` and run was NOT truncated: call `kara.lifecycle.reconcile_disappeared()` scoped to makes seen this run.
6. Return `ConnectorRunResult`.

---

## C. Main Folders and Files

| File | Purpose |
|---|---|
| `src/exonware/kara_connect/__init__.py` | Public API: ProviderInfo, Connector, registry functions, version |
| `src/exonware/kara_connect/types.py` | ProviderKind, ProviderAuth, ProviderCategory enums; ProviderInfo, ConnectorRunResult dataclasses |
| `src/exonware/kara_connect/base.py` | `Connector` base class — wraps adapter pair, handles sync + reconcile |
| `src/exonware/kara_connect/registry.py` | CONNECTOR_REGISTRY dict; @register_provider; available_providers, get_provider_info, list_provider_info, build_connector |
| `src/exonware/kara_connect/version.py` | `__version__ = "0.0.1"` |
| `src/exonware/kara_connect/providers/__init__.py` | Imports all 67 provider modules to trigger registration |
| `src/exonware/kara_connect/providers/*.py` | One file per provider (67 total): ProviderInfo definition + Connector subclass |

---

## D. Data Models and Entities

### Enums (types.py:21–62)

**`ProviderKind`** — `SCRAPE_HTML, SCRAPE_JSON, PUBLIC_API, PARTNER_API, BROKER_FEED, SYNTHETIC`

**`ProviderAuth`** — `NONE, API_KEY, OAUTH2, PARTNER_AGREEMENT`

**`ProviderCategory`** — `MARKETPLACE, REGIONAL_MARKETPLACE, GLOBAL_BENCHMARK, META_AGGREGATOR, AGGREGATOR, DIRECT_RETAILER, DEALER, DEALER_GROUP, INSIDE_DEALER, DEALER_RESELLER_PAGE, CERTIFIED_PRE_OWNED, OEM, AUCTION, FLEET_RESALE, VALUATION_REFERENCE, SOCIAL_CLASSIFIEDS, CLASSIC_SPECIALTY`

### ProviderInfo (types.py:65–98) — frozen dataclass

| Field | Type | Notes |
|---|---|---|
| `id` | str | Stable provider ID (matches kara connector source_id) |
| `name` | str | Display name |
| `countries` | tuple[str, ...] | ISO 3166-1 alpha-2 codes |
| `languages` | tuple[str, ...] | BCP-47 language tags |
| `kind` | ProviderKind | |
| `category` | ProviderCategory | PRIMARY category |
| `roles` | tuple[str, ...] | Extra role tags beyond category |
| `auth` | ProviderAuth | |
| `base_url` | str | |
| `rate_per_sec` | float | Default 1.0 req/s cap (advisory) |
| `description` | str | What the platform offers |
| `legal_note` | str | Partner/ToS constraints |
| `tags` | tuple[str, ...] | Free-form filter tags |
| `source_id` | str | kara.connectors adapter ID (if different from id) |

### ConnectorRunResult (types.py:101–116) — mutable dataclass

| Field | Type | Notes |
|---|---|---|
| `provider` | str | Provider ID |
| `started_at` | datetime | UTC, set at construction |
| `finished_at` | datetime \| None | Set by mark_finished() |
| `raw_count` | int | Scraped records before normalization |
| `normalized_count` | int | After normalization |
| `persisted_count` | int | Accepted by store (new or updated) |
| `duplicates_skipped` | int | Dedup-rejected records |
| `errors` | list[str] | All caught exceptions as strings |
| `request_params` | dict | Merged params used for this run |
| `reconcile` | dict \| None | Reconciliation stats (when reconcile=True) |

Methods: `add_error(msg)`, `mark_finished()`, `to_dict() → dict`.

---

## E. APIs, Endpoints, and Services

### Public Python API (kara_connect.\_\_init\_\_)

| Symbol | Type | Notes |
|---|---|---|
| `available_providers()` | `→ list[str]` | Sorted list of all 67 provider IDs |
| `build_connector(id, store, **kwargs)` | `→ Connector` | Instantiate by provider ID |
| `get_provider_info(id)` | `→ ProviderInfo` | Single provider metadata |
| `list_provider_info(country, tag, category, role)` | `→ list[ProviderInfo]` | Filtered + sorted by (category, id) |
| `register_provider` | class decorator | Register a Connector subclass |
| `CONNECTOR_REGISTRY` | `dict[str, type[Connector]]` | Global registry |
| `ProviderInfo, ProviderKind, ProviderAuth, ProviderCategory` | enums/dataclass | |
| `Connector` | base class | |
| `ConnectorRunResult` | dataclass | |

### Connector.sync() (base.py:60–122)

```python
sync(
    params: Mapping[str, Any] | None = None,
    max_records: int | None = None,
    *,
    reconcile: bool = False,
    mark: str = "sold",
) → ConnectorRunResult
```

### Connector.default_request_params() (base.py:56–58)

```python
default_request_params() → dict[str, Any]
```

Provider-specific defaults (page ranges, filters). Subclasses override. Examples:
- `saudisale.py:42` → `{"page_start": 1, "page_end": 3}`
- `sayarat.py:44` → `{"max_details": 200}`
- `samaco.py:40` → `{"condition": "used", "max_pages": 6}`

### Registered providers (67 total)

**Active (scrape live)**: saudisale, opensooq, sayarat

**Limited/opt-in**: haraj (`KARA_ENABLE_HARAJ=1`; bot-protected HTTP 388)

**Partner feed** (bot-protected 403/reset): dubizzle, motory, contactcars, mstaml

**Direct retailers** (inspected used-car stock): syarah, carswitch, yallamotor (partner feed)

**Dealer groups & OEM** (JS/partner-gated): samaco, naghi, aljomaih, petromin, wallan, universal_motors, alissa, alj_toyota, aljazirah

**Inside-dealer pages**: samaco_vw, samaco_audi, samaco_porsche, samaco_bentley, samaco_lamborghini, alj_finance_used, aljazirah_lincoln_used, lexus_alj

**CPO programs**: bmw_premium_selection, landrover_approved, jaguar_approved, chevrolet_cpo, vw_certified, mercedes_cpo

**Auctions**: motory_mazad, awalmazad, zodha, carsbay, copart_mea, budget_saudi, lumi

**Fleet resale**: copart_mea, dubicars

**Regional/GCC**: yallamotor_me, dubizzle_ae, drivearabia, pricemycar_me, classicsofarabia

**Global benchmarks**: autotrader, cargurus, cars_com, edmunds, carmax, carvana, autotempest, ebay_motors, carsandbids, bringatrailer

**Valuation references**: edmunds, kbb, cargurus, carmax

**Meta-aggregator**: autotempest

**Social**: facebook_marketplace

**Classic specialty**: bringatrailer

Other catalogued: gogomotor, hatla2ee, mynaghi, motoryshop, syarati, kia_aljabr

---

## F. Auth, Security, Config, and Env Variables

### Env variables

| Var | Default | Purpose |
|---|---|---|
| `KARA_ENABLE_HARAJ` | unset | Opt-in to haraj scraping (bot-protected; best-effort) |

No other env vars in codebase.

### Security philosophy

- Scrapes **public pages only**, rate-limited and politely (README.md:81–86).
- Never bypasses logins, CAPTCHAs, rate limits, or access controls.
- Bot-protected sites (haraj: HTTP 388; dubizzle/motory/contactcars/mstaml: HTTP 403/reset) are catalogued honestly with `auth=PARTNER_AGREEMENT` and never scraped without explicit opt-in or partner feed.
- `rate_per_sec` in `ProviderInfo` is advisory metadata; enforcement is in the underlying `xwapi.scrapping` BaseScraper.
- Legal notes (`ProviderInfo.legal_note`) document ToS constraints for each provider.

---

## G. Database, Storage

kara-connect owns no storage. It depends on `kara.IVehicleStore` passed by the caller:

```python
store = JsonFileVehicleStore("kara-data/listings.json")
conn = build_connector("saudisale", store)
result = conn.sync(max_records=200)
```

Internally, `Connector` wraps the store in `ScrapingPersistenceAdapter` (from kara) which implements `IPersistence` for the xwapi.scrapping pipeline.

Reconciliation (mark disappeared listings SOLD/EXPIRED) calls `kara.lifecycle.reconcile_disappeared(store, source_id, seen_ids, ...)` after a full sweep.

---

## H. How to Run Locally

```bash
pip install -e .     # requires exonware-kara and exonware-xwapi as deps

# Python usage
from exonware.kara import JsonFileVehicleStore
from exonware.kara_connect import build_connector, available_providers

store = JsonFileVehicleStore("kara-data/listings.json")
print(available_providers())          # 67 IDs

conn = build_connector("saudisale", store)
result = conn.sync(params={"page_start": 1, "page_end": 2}, max_records=50)
print(result.to_dict())
```

**Requires**: Python ≥ 3.12. No CLI provided. No tests to run.

---

## I. Tests Available and Tests Missing

**No tests exist.** The `repos/kara-connect/` directory has no `tests/` folder, no `conftest.py`, no `test_*.py` files.

### What is untested

- Registry: `@register_provider`, `available_providers()`, `list_provider_info()` filtering, `build_connector()`
- `Connector.sync()` success and error paths
- Reconciliation logic (reconcile=True, truncated run detection)
- Lazy adapter binding (catalog-only provider raises clean error)
- Source-ID aliasing (shared adapter for samaco_* providers)
- All 67 `ProviderInfo` definitions (required field presence, valid enums)
- `ConnectorRunResult.to_dict()` serialization

---

## J. Risks, Unclear Parts, and Questions

### Catalog-only providers registered but no adapter wired

Many providers (CPO pages, auctions, valuation references) have `ProviderInfo` defined but no scraper wired. `sync()` returns a clean error rather than crashing (base.py:84–94). Callers can see all 67 in `available_providers()` without knowing which ones are live.

**Risk**: `kara-api` lists all providers via `/connectors`, making all 67 appear triggerable. A caller who runs `POST /connectors/bmw_premium_selection/run` gets an opaque error in `ConnectorRunResult.errors`, not a clear HTTP 422 or 501.

### Haraj opt-in not enforced in code

`haraj.py:39–41` documents `KARA_ENABLE_HARAJ=1` but no code checks that env var. `build_connector("haraj", store)` succeeds and `sync()` will attempt to reach haraj.com.sa regardless of whether the env var is set.

### Rate limiting is advisory only

`ProviderInfo.rate_per_sec` is a metadata field. It documents the intended rate but does not enforce it. Actual enforcement is in xwapi.scrapping's `BaseScraper`; kara-connect has no visibility into whether it is honored.

### Source-ID aliasing and concurrent syncs

Ten providers share four underlying adapters (samaco, alj_toyota, naghi, yallamotor). If two aliased providers are synced concurrently, both write through the same `ScrapingPersistenceAdapter` and the same `store.upsert()` lock. Reconciliation scoped to makes-seen-this-run could mark listings from one branded sub-page as SOLD while the other sub-page is mid-sync.

### Reconciliation truncation detection

If `max_records` is set and `raw_count >= max_records`, reconciliation is skipped with a message (base.py:105–107). If a provider's full catalog is exactly `max_records` size, there is no way to distinguish a complete run from a truncated one; reconciliation is always skipped.

### Architectural issues 

**No `status` field on Connector distinguishing live from planned**: `list_provider_info()` returns all 67 regardless of whether an adapter exists. Consumers need to attempt `sync()` and inspect errors to discover liveness. A `Connector.is_live() → bool` method or a `ProviderStatus` field on `ProviderInfo` would make this discoverable.

**Flat providers/ directory with 67 files**: all provider modules live in one directory. As the count grows, navigation and onboarding become harder. No grouping by category (marketplaces/, dealers/, auctions/).

**No documented process for adding a provider**: README explains what providers exist but not how to add one. There is no checklist, no template file, no validation that new providers have required fields.

**Error discrimination missing in ConnectorRunResult**: all caught exceptions are stringified into `errors: list[str]`. Callers cannot distinguish network timeouts, parse failures, and access-denied errors without string parsing.

**`default_request_params()` not validated**: catalog-only providers return `{}` by default. If a caller passes no `params`, a catalog-only provider's `sync()` fails at scraper construction — but the failure message does not tell the caller it is because no adapter is wired vs. missing required params.

### Open questions

- Which of the 67 providers have a working adapter today (beyond saudisale, opensooq, sayarat)?
- Is `KARA_ENABLE_HARAJ=1` enforcement intended to be added, or is it purely documentary?
- Are concurrent syncs of aliased providers (samaco_vw + samaco_audi simultaneously) a supported use case?
- What is the intended mechanism for callers to distinguish live providers from catalog-only ones?

---

## K. Suggested First Improvements

### Risk analysis

1. **Enforce `KARA_ENABLE_HARAJ`**: in the haraj `Connector` constructor or `sync()`, check `os.environ.get("KARA_ENABLE_HARAJ") != "1"` and return an error result immediately. Make the opt-in actually opt-in.

2. **Add `Connector.is_live() → bool`**: return `True` only if `_build_default_adapter()` succeeds without error. Let `kara-api` use this to gate `POST /connectors/{source}/run` with a 501 rather than a misleading 200+errors.

3. **Add `ProviderStatus` to ProviderInfo**: `active | limited | partner | planned | catalog_only`. Populate from existing `legal_note` patterns. Lets consumers filter before attempting a sync.

4. **Write a test suite**: at minimum —
   - Registry unit tests: register, lookup, filter by country/category/role, build
   - `ConnectorRunResult` serialization tests
   - `Connector.sync()` with mocked adapter: success, error, reconcile paths
   - Catalog-only provider returns clean error on sync
   - All 67 `ProviderInfo` definitions validated (required fields, valid enum values)

### Architectural analysis

5. **Group providers by category**: create subdirectories `providers/marketplaces/`, `providers/dealers/`, `providers/auctions/`, etc. Update `providers/__init__.py` accordingly. Improves discoverability for the next developer.

6. **Add error type to ConnectorRunResult**: add `error_type: str | None` or an `ErrorKind` enum (`network, parse, access_denied, not_implemented, unknown`) so callers can programmatically handle failure modes without string matching.

7. **Add a "New Provider" checklist to README**: document the 5-step process (create ProviderInfo, subclass Connector, override `default_request_params`, register, add tests). Makes onboarding the next provider predictable.

8. **Document rate-limit enforcement**: clarify whether `rate_per_sec` in `ProviderInfo` is purely informational or whether the scraping layer reads and enforces it. If informational only, rename to `recommended_rate_per_sec`.

9. **Add `was_truncated` to ConnectorRunResult**: boolean set when `raw_count >= max_records`. Allows callers to know confidently that reconciliation was skipped due to truncation vs. skipped because not requested.

10. **Add a `sync_dry_run()` method**: runs the scraper without calling `store.upsert()` (or with a no-op store). Useful for testing new providers and auditing what data would be ingested before committing to the store.
