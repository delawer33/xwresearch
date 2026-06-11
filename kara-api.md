# kara-api

> `exonware-kara-api` · `repos/kara-api` · v0.0.1

## A. What It Does

Thin FastAPI layer over `exonware-kara`. Every route delegates immediately to the core library — no business logic lives here. Adds HTTP validation (Pydantic), CORS, opaque bearer auth + PBKDF2 user sessions, pluggable store backend (xwjson preferred, JSON file fallback), synthetic seeding on first boot, and a static admin-token gate.

On first start it seeds a JSON/xwjson store with synthetic Riyadh listings (default 250). OpenAPI docs auto-generated at `/docs`.

---

## B. Backend Architecture

**Pattern**: Hexagonal/Adapter — routes are pure translators from HTTP to domain calls.

**Layers**:
```
HTTP layer        routes/*.py         Pydantic validation, response shaping
Adapter layer     mapping.py, deps.py Bridge HTTP payloads → domain objects
State layer       state.py, auth_store.py  In-memory caches + persistence bridges
Core layer        exonware.kara       All business logic (never defined here)
```

**Key design decisions**:
- **Pluggable store** (state.py:46–71): tries `XwJsonVehicleStore` first; falls back to `JsonFileVehicleStore`. Same pattern for catalog store.
- **PBKDF2 sessions** (auth_store.py:22–34): 100,000 iterations, salted; opaque bearer tokens; multiple tokens per user allowed.
- **Admin gating** (deps.py:43–62): checks `KARA_ADMIN_TOKEN` bearer token first; then session user with `role="admin"`; if neither set → dev mode (all admin routes open).
- **Anonymous path** (deps.py:24–33): logged-in → session user; X-User-Id header → that ID; otherwise "guest". Enables anonymous favorites/searches.
- **Pinned dedup keys for user-posted listings** (mapping.py:26–63): user-created listings get unique dedup keys to prevent merging with scraped same-spec entries.
- **Intelligence computed at read time** (mapping.py:66–80): `PricingEngine` + `DealScoreEngine` run on every card fetch; no pre-computation cache.

---

## C. Main Folders and Files

| File | Purpose |
|---|---|
| `src/exonware/kara_api/app.py` | FastAPI factory + router registration + lifespan (startup/shutdown) |
| `src/exonware/kara_api/settings.py` | All env-driven config (Pydantic Settings or plain env reads) |
| `src/exonware/kara_api/state.py` | Shared mutable app state: stores, users, favorites, searches, leads, compare sets |
| `src/exonware/kara_api/models.py` | Pydantic request/response schemas |
| `src/exonware/kara_api/deps.py` | FastAPI dependency functions: get_state, get_current_user, require_admin, get_user_id |
| `src/exonware/kara_api/auth_store.py` | In-memory user + session store with PBKDF2 hashing |
| `src/exonware/kara_api/mapping.py` | ListingCreate → VehicleListing, card intelligence builder |
| `src/exonware/kara_api/cli.py` | `kara-api` CLI entry point (uvicorn runner) |
| `src/exonware/kara_api/routes/health.py` | GET /health |
| `src/exonware/kara_api/routes/auth.py` | POST /auth/register, /auth/login; GET /auth/me |
| `src/exonware/kara_api/routes/search.py` | GET /search/listings |
| `src/exonware/kara_api/routes/listings.py` | CRUD /listings + /listings/{id}/intelligence |
| `src/exonware/kara_api/routes/pricing.py` | POST /pricing/estimate |
| `src/exonware/kara_api/routes/deals.py` | POST /deals/score |
| `src/exonware/kara_api/routes/mojaz.py` | GET /mojaz/{listing_id} |
| `src/exonware/kara_api/routes/compare.py` | POST /compare; GET /compare/{id} |
| `src/exonware/kara_api/routes/account.py` | /favorites + /searches |
| `src/exonware/kara_api/routes/leads.py` | POST /leads/click; GET /leads/summary (admin) |
| `src/exonware/kara_api/routes/dealers.py` | GET /dealers, /dealers/{id} |
| `src/exonware/kara_api/routes/connectors.py` | GET /connectors; POST /connectors/{source}/run (admin) |
| `src/exonware/kara_api/routes/catalog.py` | Full car database API (VIN decode, NHTSA, Wikidata, make/model reference) |
| `src/exonware/kara_api/routes/insights.py` | /listings/{id}/price-history, /ratings, /makers, /map/availability |
| `src/exonware/kara_api/routes/admin.py` | GET /admin/kpis, /admin/fraud |
| `tests/test_api.py` | Smoke tests via TestClient |

---

## D. Data Models and Entities

All defined in `models.py` unless noted.

**`ListingCreate`** (models.py:22–48): `make, model, year (1950–2100), price_sar (≥0), mileage_km (≥0), city, region, seller_id, seller_type (individual|dealer), title, trim, description, vin, body_type, fuel_type, transmission, color, photos: list[str], seller_phone, seller_whatsapp, accident_free, owner_count, service_history, warranty_active, is_featured, dealer_id`

**`ListingUpdate`** (models.py:51–60): `price_sar, mileage_km, title, description, status (draft|active|sold|expired|rejected), photos, is_featured, seller_phone, seller_whatsapp` — all optional

**`EstimateRequest`** (models.py:63–65): `listing_id: str | None`, `listing: ListingCreate | None` — either existing ID or hypothetical

**`ScoreRequest`** (models.py:68–69): `listing_id: str`

**`CompareRequest`** (models.py:72–73): `listing_ids: list[str]` (1–4 items)

**`LeadClick`** (models.py:76–79): `listing_id, channel (whatsapp|call|view|message), user_id`

**`SavedSearchCreate`** (models.py:82–84): `name: str, query: dict`

**`AuthCredentials`** (models.py:87–89): `email: str, password: str (min 4)`

**`User`** (auth_store.py:37–45) — dataclass (not Pydantic): `id, email, password_hash, role (user|admin)`. Method: `public() → dict` (no password_hash).

---

## E. APIs, Endpoints, and Services

### Health
| Method | Path | Response |
|---|---|---|
| GET | `/health` | `{status, version, listings}` |

### Auth (`/auth`)
| Method | Path | Auth | Response |
|---|---|---|---|
| POST | `/auth/register` | — | `{token, user: {id, email, role}}` |
| POST | `/auth/login` | — | `{token, user}` or 401 |
| GET | `/auth/me` | Bearer | `{user}` or 401 |

### Search & Listings

Listings enter the store in two ways:
- **Scraped** — connectors pull from external marketplaces (saudisale, opensooq, …) via `POST /connectors/{source}/run`
- **User-posted** — a dealer or individual submits directly via `POST /listings` (source=KARA)

User-posted listings get a pinned dedup key so they never merge with a scraped listing of the same vehicle.

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/search/listings` | optional | Query: make, model, trim, min/max_year, min/max_price, min/max_mileage, city, region, seller_type, source, fuel_type, transmission, featured_only, text, sort, limit (1–100), offset. Response: `{items, total, limit, offset}` |
| POST | `/listings` | optional | Direct listing submission (dealer or individual). Body: ListingCreate. Returns 201 + listing dict |
| GET | `/listings/{id}` | optional | Returns card with intelligence |
| PATCH | `/listings/{id}` | optional | Body: ListingUpdate. Returns updated listing |
| DELETE | `/listings/{id}` | optional | Returns 204 |
| GET | `/listings/{id}/intelligence` | optional | Full ListingIntelligence: estimate, mojaz, deal_score, fraud_flags |

### Pricing & Deals
| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/pricing/estimate` | EstimateRequest | `{estimated_fair_value_sar, confidence_score, method, explanation, ...}` |
| POST | `/deals/score` | ScoreRequest | `{estimate, deal_score: {score, category, price_delta_sar, price_delta_percent, ...}}` |

### Mojaz
| Method | Path | Response |
|---|---|---|
| GET | `/mojaz/{listing_id}` | `{status: not_available\|redirect_available, ...}` |

### Compare
| Method | Path | Notes |
|---|---|---|
| POST | `/compare` | Body: CompareRequest (1–4 IDs). Returns `{id, items: [{full intelligence}]}` |
| GET | `/compare/{id}` | Returns saved compare set |

### Account
| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/favorites/{listing_id}` | X-User-Id or Bearer | Returns `{favorites: [ids]}` |
| DELETE | `/favorites/{listing_id}` | X-User-Id or Bearer | Returns `{favorites: [ids]}` |
| GET | `/favorites` | X-User-Id or Bearer | Returns `{items: [cards]}` |
| GET | `/searches` | X-User-Id or Bearer | Returns `{items: [{name, query}]}` |
| POST | `/searches` | X-User-Id or Bearer | Body: SavedSearchCreate. Returns `{items}` |

### Leads
| Method | Path | Auth | Response |
|---|---|---|---|
| POST | `/leads/click` | optional | Body: LeadClick → `{ok: true, total_leads}` |
| GET | `/leads/summary` | admin | `{total, by_channel, top_listings}` |

### Dealers
| Method | Path | Response |
|---|---|---|
| GET | `/dealers` | `{items: [{id, listing_count}]}` |
| GET | `/dealers/{dealer_id}` | `{id, listing_count, average_price_sar, listings: [cards]}` |

### Connectors (admin)
| Method | Path | Notes |
|---|---|---|
| GET | `/connectors` | `{items: [provider metadata]}` |
| GET | `/connectors/{source}/status` | `{status, ...}` |
| POST | `/connectors/{source}/run` | Query: count=100, reconcile=false → `{source, raw_count, normalized_count, persisted_count, duplicates_skipped, reconcile, errors}` |

### Catalog (mostly admin)
| Method | Path | Notes |
|---|---|---|
| GET | `/catalog/providers` | All catalog providers |
| GET | `/catalog/schema` | Full 34-category car spec schema |
| GET | `/catalog/car` | `?id=` → resolved (inherited) spec |
| GET | `/catalog/car/raw` | `?id=` → stored fields only |
| POST | `/catalog/car` | admin; create catalog entry |
| GET | `/catalog/stats` | `{vehicles, makes}` |
| GET | `/catalog/makes` | Make name list |
| GET | `/catalog/makes/{make}/models` | `?year=` |
| GET | `/catalog/vehicles` | `?make,model,year,level,resolved,limit,offset` |
| GET | `/catalog/decode-vin/{vin}` | NHTSA VIN decode |
| POST | `/catalog/refresh` | admin; pull NHTSA |
| POST | `/catalog/enrich/wikidata` | admin; Wikidata enrichment |
| POST | `/catalog/ingest/wikidata` | admin; ingest Wikidata models |
| POST | `/catalog/link` | admin; link listings to catalog |
| POST | `/catalog/seed` | admin; seed top KSA models |

### Insights
| Method | Path | Response |
|---|---|---|
| GET | `/listings/{id}/price-history` | `{local: [12 months], global: [12 months]}` |
| GET | `/listings/{id}/ratings` | `{scores: [6 rating dimensions]}` |
| GET | `/makers` | `{items: [make aggregates]}` |
| GET | `/map/availability` | `{items: [{city_code, city, region, count, avg_price, lat, lng}], total, unresolved}` |

### Admin
| Method | Path | Response |
|---|---|---|
| GET | `/admin/kpis` | `{active_listings, ...}` |
| GET | `/admin/fraud` | `?limit=50` → `{items: [{listing, flags}], count}` |

---

## F. Auth, Security, Config, and Env Variables

### Authentication

- **Bearer tokens**: opaque, issued on register/login, stored in `UserStore._tokens` (auth_store.py:75–78).
- **PBKDF2**: SHA-256, 100,000 iterations, per-user salt (auth_store.py:22–34).
- **Admin gate**: static `KARA_ADMIN_TOKEN` checked first; then session user with `role="admin"`; if neither set → dev mode (deps.py:49–57).
- **Anonymous**: X-User-Id header or "guest" string (deps.py:24–33).

### CORS (app.py:59–66)

Configured from `KARA_CORS_ORIGINS`. Defaults: `localhost:5173, localhost:4173`. `allow_methods=["*"]`, `allow_headers=["*"]`, `allow_credentials=True`.

### Env variables (settings.py:10–43)

| Var | Default | Purpose |
|---|---|---|
| `KARA_STORE_FILE` | `./kara-data/listings.xwjson` | Vehicle store path |
| `KARA_CATALOG_FILE` | `./kara-data/catalog.xwjson` | Catalog store path |
| `KARA_CATALOG_REFRESH_ON_EMPTY` | `0` | Pull NHTSA on cold start if catalog empty |
| `KARA_SEED_ON_EMPTY` | `1` | Seed synthetic listings on first boot |
| `KARA_SEED_COUNT` | `250` | Listings to seed |
| `KARA_ADMIN_EMAIL` | `admin@kara.sa` | Default admin email |
| `KARA_ADMIN_PASSWORD` | `admin12345` | Default admin password |
| `KARA_MOJAZ_REDIRECT_BASE` | `""` | Mojaz service base URL; empty → NOT_AVAILABLE |
| `KARA_ADMIN_TOKEN` | unset | Static bearer for admin routes |
| `KARA_CORS_ORIGINS` | `http://localhost:5173,http://localhost:4173` | Allowed origins |

---

## G. Database, Storage, Queues, and Background Jobs

### Persistent stores

| Store | Backend | Default path | Fallback |
|---|---|---|---|
| VehicleListing | XwJsonVehicleStore | `KARA_STORE_FILE` | JsonFileVehicleStore |
| CatalogCar | XwJsonCatalogStore | `KARA_CATALOG_FILE` | JsonFileCatalogStore |

Both stores loaded in `state.startup()` (state.py:42–73) via lifespan context manager (app.py:45–49).

### Volatile in-memory stores (lost on restart)

| Store | Type | Notes |
|---|---|---|
| `users` | UserStore | User accounts + session tokens |
| `favorites` | `defaultdict[str, set[str]]` | Per-user listing IDs |
| `saved_searches` | `defaultdict[str, list[dict]]` | Per-user search configs |
| `leads` | `list[dict]` | Click events |
| `compare_sets` | `dict[str, list[str]]` | Temporary compare carts (no TTL) |

No queue system. No background jobs. Connector runs, catalog refreshes, and Wikidata ingestion are all synchronous admin-triggered HTTP calls.

---

## H. How to Run Locally

```bash
pip install -e ../kara       # install core library first
pip install -e .             # install kara-api

kara-api --port 8090         # http://localhost:8090/docs
kara-api --host 127.0.0.1 --port 3000 --reload   # dev mode
```

- First boot seeds `./kara-data/listings.xwjson` with 250 synthetic listings.
- Set `KARA_STORE_FILE` to an existing store to skip seeding.
- Set `KARA_SEED_ON_EMPTY=0` to disable seeding entirely.
- Default admin: `admin@kara.sa` / `admin12345` (change in production).

**Runtime deps**: `fastapi>=0.104`, `uvicorn[standard]>=0.24`, `pydantic>=2.0`. Dev: `pytest>=7.0`, `httpx>=0.27`.

---

## I. Tests Available and Tests Missing

### test_api.py (smoke tests via TestClient)

| Test | Coverage |
|---|---|
| health | `/health` returns status, version, listing count |
| search | `/search/listings` paginated with intelligence cards |
| CRUD | POST create → 201; PATCH update; GET retrieve + intelligence; DELETE → 204 + 404 |
| pricing & scoring | `/pricing/estimate` → fair value; `/deals/score` → category + deltas |
| mojaz | Status ∈ {not_available, redirect_available} |
| favorites + compare + leads | POST/GET favorites; POST /compare (3 listings); POST /leads/click |
| admin KPIs | `/admin/kpis` returns active_listings |
| price history + ratings | 12-month arrays; 6-score ratings array |
| makers | Aggregated make list |
| auth flow | Register, login, /me, invalid credentials → 401 |
| admin login | admin@kara.sa:admin12345 → role=admin |
| connectors | List connectors; haraj disabled by default |

### Missing tests

- No catalog CRUD or VIN decode tests
- No complex filter combinations (region, fuel_type, transmission, featured_only, text search)
- No dealer profile tests (`/dealers/{id}`)
- No saved search tests
- No connector run/reconciliation tests
- No edge cases: invalid enums silently dropped in search, malformed payloads
- No concurrency tests
- No compare set expiry or stale-favorite cleanup tests

---

## J. Risks, Unclear Parts, and Questions

### Critical risks

**User data lost on restart**: users, favorites, searches, leads, and compare sets are volatile (state.py:36–40). A server restart clears all user sessions. `auth_store.py:6` notes this as a P0 upgrade to `xwauth-identity`.

**Default credentials in plain config** (settings.py:22): `KARA_ADMIN_PASSWORD=admin12345` shipped as default. No startup warning if not overridden. An unattended production deploy exposes admin routes.

**Dev mode admin bypass** (deps.py:50–51): if `KARA_ADMIN_TOKEN` is unset, all `/admin` and connector-run routes are open to any caller. Missing env var in production = full admin exposure.

**Compare sets accumulate with no TTL** (compare.py:37): sets are created with 10-char random IDs, stored in memory forever until restart. No cleanup mechanism.

**Stale favorites** (account.py:38–46): deleted listings remain in users' favorite ID sets; `GET /favorites` filters them at read time but does not remove them from the set.

**Catalog exceptions silently swallowed** (state.py:50, 63): if xwjson import fails, falls back to JSON with no log. If catalog network refresh fails on cold start, startup continues silently (state.py:70–71 comment: "never block startup on the network").

### Architectural issues 

**Intelligence computed on every read**: `mapping.py:66–80` calls `PricingEngine` + `DealScoreEngine` on every card fetch (search results, listing GET, compare, favorites). No caching. For a search returning 60 listings, 120 engine invocations happen per request. Fine at MVP scale; will not hold under load.

**Pagination not uniform**: `/search/listings` enforces limit 1–100 (search.py:46–47); `/catalog/vehicles` allows up to 20,000 (catalog.py:114); `/admin/fraud` is soft-limited only (admin.py:22, 38). An unbounded catalog or fraud query can stall the server.

**Enum coercion drops invalid values silently**: `_enum()` helper (search.py:16–22) returns `None` for unknown values rather than a 422 error. A misspelled `seller_type=delaer` is ignored without feedback to the client.

**No request logging middleware**: no structured log of endpoint, latency, user ID, or errors. Debugging production issues requires adding this before any real traffic.

**CORS fully permissive** (app.py:64–65): `allow_methods=["*"]`, `allow_headers=["*"]` — any origin from the allowlist can make any request. Appropriate for MVP; needs narrowing for production.

**VIN validation loose** (catalog.py:140–141): accepts length 11–17; real VINs are exactly 17. No checksum validation.

### Open questions

- What persistence backend replaces the in-memory `UserStore`? Is `xwauth-identity` the plan?
- Where should `KARA_ADMIN_PASSWORD` validation (must-change) happen — startup, first login, or CI?
- Are compare sets intended to be ephemeral (session-scoped) or shareable (link-in-URL)?

---

## K. Suggested First Improvements

### Risk analysis

1. **Warn on default admin password**: in `state.startup()`, log a loud warning if `KARA_ADMIN_PASSWORD == "admin12345"` and the environment is not clearly dev (e.g., `KARA_ENV != "dev"`).

2. **Fail on missing admin token in production**: if `KARA_ADMIN_TOKEN` is unset and `KARA_ENV=production`, raise on startup rather than silently opening all admin routes.

3. **Add compare-set TTL**: store `created_at` with each set in `compare_sets`; evict entries older than 24 hours in a startup sweep or on next read.

4. **Persist user accounts**: swap `UserStore` for a JSON/xwjson-backed implementation before going to production. The P0 path (xwauth-identity) is already noted in auth_store.py:6.

5. **Cap all paginated endpoints consistently**: enforce `limit <= 100` across `/catalog/vehicles` and `/admin/fraud` the same way search does.

### Architectural analysis

6. **Cache intelligence per listing version**: hash `(listing.id, listing.updated_at, store.count())` as a cache key for `card()`. Avoids re-running both engines on every search-result item.

7. **Add request logging middleware**: one FastAPI middleware that logs `method, path, status, latency_ms, user_id` to stderr/stdout in structured JSON.

8. **Return dropped filter fields in search**: modify the search response to include a `dropped_params: list[str]` field listing any query params that were silently ignored (invalid enum values). Helps client debugging.

9. **Validate seller phone format**: add E.164 or KSA-format regex validation to `ListingCreate.seller_phone` and `seller_whatsapp` to prevent raw PII in unexpected formats.

10. **Add `/v1/` prefix**: version the API before the first external consumer. A one-line router prefix change now is much cheaper than a migration later.
