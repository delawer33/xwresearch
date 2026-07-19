<!-- docs/history/kara-api-backend-plan-2026-06-23.md
     Archived 2026-07-17 from repos/kara-api/BACKEND_PLAN.md (kara-api HEAD 9799944).
     LANDED: it produced the routes/v1/ consumer-marketplace surface (21 modules,
     verified present). Kept for the "why does routes/v1/ exist" answer; the live
     description of that surface is repos/kara-api/CLAUDE.md. Not current state. -->

# Karaa Backend — Rebuild Plan

**Date:** 2026-06-23  
**Spec:** Karaa_Product_Engineering_Spec_v2.0_16_Screens.md  
**Context:** The existing karaa-api was built as a data-intelligence API (scrapers, catalog,
pricing engine). The new spec turns it into a consumer marketplace. About 60% of what the spec
requires does not exist yet.

---

## Assumptions (pending client response)

These decisions affect scope. Marked throughout the plan where they apply.

| # | Question | Assumption used |
|---|---|---|
| Q1 | Seller reviews in V1? | Deferred to post-V1 |
| Q2 | AI vehicle summary — LLM or template? | Deterministic template for V1, no LLM dependency |
| Q3 | Recommended For You — personalized or simple? | Simple for V1 (best deal score, newest listings) |
| Q4 | Listing promotion — payment flow or admin flag? | Admin-set flag for V1, no payment flow |
| Q5 | Push notifications in V1? | Deferred to post-V1 |
| Q6 | WhatsApp notifications for saved searches in V1? | Deferred to post-V1 |

Update this table and the relevant phase sections when client responds.

---

## API contracts (agreed before implementation starts)

**URL prefix:** Old API stays at `/api/karaa/v1` during transition. All new endpoints go under
`/api/v1`. Frontend builds all new screens against `/api/v1` only. Old prefix removed only
after all screens confirm migration.

**Error format** (consistent across all endpoints):
```json
{ "error": { "code": "LISTING_NOT_FOUND", "message": "...", "requestId": "req_abc" } }
```

**Not-yet-built endpoints** return:
```json
{ "error": { "code": "NOT_IMPLEMENTED", "message": "Coming in phase X" } }
```

**API standards (§9.7):**
- All timestamps: ISO 8601 with timezone (`2026-06-23T10:00:00+03:00`)
- All money: integer halalas, never float — `72500` means SAR 725.00
- Pagination: `{ "items": [...], "total": 120, "offset": 0, "limit": 20 }`
- Request IDs: `X-Request-Id` header on every response
- Rate limiting: applied at the route level from Phase A — OTP endpoints strictest, public
  read endpoints lenient, write and contact endpoints moderate
- Idempotency keys: required on listing submit, media upload, message send, and Mojaz checkout

**Auth:** Bearer token in Authorization header (not cookies). This avoids CSRF complexity and
works cleanly for mobile web. The spec's "HTTP-only cookies where applicable" is satisfied by
the Bearer token approach for this product type.

---

## Phase A — Foundation *(~1 week)*

### A1. Data model

This is the first thing built. Every other phase depends on it.

**`ListingStatus` in `karaa/types.py`**
Add missing states: `PENDING_REVIEW`, `REJECTED`, `PAUSED`, `SOLD`, `EXPIRED`, `DELETED`.
Currently only `DRAFT` and `ACTIVE` exist.

**`User` in `karaa-api/users.py`**
Add fields per spec §8.1: `mobile_e164`, `status`, `display_name`, `avatar_url`, `city_id`,
`last_login_at`. Keep `email` for admin bootstrap. Schema-free store — old records return
`None` for new fields without migration.

**`VehicleListing` in `karaa/types.py`**
Add fields per spec §8.5: `seller_profile_id`, `dealer_profile_id`, `condition`,
`contact_preferences`, `expires_at`, `owner_user_id`.
Add `vin` encryption marker — VIN must be stored encrypted at rest (§12). Implement a
reversible encryption helper in `security.py`; apply on write, decrypt on read.

**New `sellers.py` in karaa-api**
`SellerProfile` dataclass + `SellerProfileStore` (XWDatabase collection `seller_profiles`).
Follow the `UserStore` pattern exactly.
Fields per spec §8.2: `id`, `user_id`, `seller_type` (PRIVATE/SHOWROOM),
`verification_status`, `phone_verified`, `id_verified`, `rating_average`, `rating_count`,
`median_response_seconds`, `joined_at`, `city_id`.
Wire into `AppState.startup()`.

**New `dealers.py` in karaa-api**
`DealerProfile` dataclass + `DealerProfileStore` (XWDatabase collection `dealer_profiles`).
Fields per spec §8.3: `id`, `owner_user_id`, `legal_name`, `display_name`,
`commercial_registration_number_encrypted`, `verification_status`, `logo_url`,
`cover_image_url`, `business_hours`, `location` (lat/lng), `rating_average`, `rating_count`.
CR number must be encrypted at rest, same as VIN.
Wire into `AppState.startup()`.

**New `listing_images.py` in karaa-api**
Photos are currently plain URL strings on the listing. The spec §8.6 defines a proper entity.
`ListingImage` dataclass + `ListingImageStore` (XWDatabase collection `listing_images`).
Fields: `id`, `listing_id`, `url`, `sort_order`, `is_cover`, `moderation_status`,
`width`, `height`.
This replaces the URL string list on listings. Required for cover selection, reordering,
and moderation (Screen 05).

**New `valuations.py` in karaa-api**
Valuations are currently computed on request and discarded. The spec §8.7 requires them to
be stored: `id`, `listing_id`, `fair_value_low_sar`, `fair_value_mid_sar`,
`fair_value_high_sar`, `deal_rating`, `market_delta_sar`, `confidence`, `comparable_count`,
`model_version`, `calculated_at`.
`ValuationStore` backed by XWDatabase collection `valuations`.
On `GET /listings/:id/valuation`, check if a recent valuation exists; compute and store if
not or if stale (configurable TTL, default 24h).

**`Lead` update**
Add `seller_user_id` and `deduplication_key` fields. Deduplication key = hash of
`(buyer_user_id, listing_id, channel)`. One lead record per combination within a 24h window.
On `POST /listings/:id/contact-events`, check deduplication before inserting.

**`Favorite` update**
Add snapshot fields per spec §8.9: `price_snapshot_sar`, `deal_rating_snapshot`,
`market_delta_snapshot_sar`. Captured at the moment the listing is favorited.
Used by D4 price drop tracking.

### A2. Auth — OTP flow

Replace `/auth/register` + `/auth/login` with:
```
POST /api/v1/auth/otp/request   — takes mobile_e164, sends 6-digit OTP; rate-limited to
                                   3 requests per number per 10 minutes
POST /api/v1/auth/otp/verify    — takes mobile_e164 + code, returns JWT; max 5 attempts
                                   before lockout; OTP expires after 10 minutes
POST /api/v1/auth/logout
GET  /api/v1/me
```

SMS stubbed in dev (OTP logged to console, any 6-digit code accepted).
Keep `/auth/login` alive for admin account.
Security: do not expose whether a mobile number belongs to an existing user — always return
the same response from `/otp/request` regardless.
Log suspicious patterns (too many attempts from one IP) to the audit log.

### A3. OpenAPI contract

Once A1 and A2 are done, export the full spec at `/api/v1/openapi.json`. Every endpoint —
including `501` stubs — must appear with correct request/response shapes. Publish to the
frontend team. Update after every phase.

### A4. URL remapping

Move existing endpoints to the new `/me/` prefix:
- `/favorites` → `/api/v1/me/favorites`
- `/searches` → `/api/v1/me/saved-searches`

Keep old paths alive during transition. Remove after frontend confirms migration.

---

## Phase B — Core buyer experience *(~1 week)*

Unblocks Screens 01, 02, 03, 04, 07, 15.

### Homepage data (Screen 01)

**`GET /api/v1/listings/trending-searches`**
Return the top 10 search terms from the last 7 days. Track query strings on every
`GET /api/v1/listings` call — store in a `search_queries` collection, aggregate by frequency.

**`GET /api/v1/listings/popular-categories`**
Return body type counts from active listings (sedan, SUV, pickup, etc.) sorted by count.
Simple aggregation over the vehicle store.

**`GET /api/v1/listings/popular-brands`**
Return make counts from active listings sorted by count. Same approach.

**`GET /api/v1/listings/recommended`**
Per assumption Q3: return listings sorted by deal score descending, newest first.
No personalization in V1. Frontend uses this for the "Recommended For You" section.

### Search (Screen 02)

**`GET /api/v1/listings`**
Remap existing search under new prefix. Add missing filter params:
- `seller_verified` (boolean) — filter by `seller_profile.verification_status = verified`
- `has_mojaz` (boolean) — filter listings where a Mojaz report is available
- `sort=best_match` — combine deal score + freshness + data completeness. Other sort values
  already exist: `best_deal`, `lowest_price`, `highest_price`, `lowest_mileage`, `newest`.

**`GET /api/v1/search/autocomplete`**
Returns make/model/trim suggestions for a query string. Backed by the catalog. Used for the
search field autocomplete on Screens 01 and 02. Response:
```json
{ "suggestions": [{ "type": "make", "value": "Toyota" }, { "type": "model", "value": "Toyota Camry" }] }
```

### Listings (Screens 02, 03)

**`GET /api/v1/listings`** and **`GET /api/v1/listings/:id`**
Remap under new prefix with updated response shape.

**`GET /api/v1/listings/:id` — 410 Gone**
When listing status is `DELETED` or `EXPIRED`, return HTTP 410 (not 404). Required for SEO
(§15).

**`GET /api/v1/listings/:id/view`**
`POST` (or triggered internally on GET): increment view counter on the listing. Exclude owner
views (check `owner_user_id == current_user.id` when auth is present). Store `view_count` on
the listing record. Used by Screen 11 My Listings.

**`GET /api/v1/listings/:id/valuation`**
Returns stored valuation if fresh, computes and stores if stale. Response shape per spec §5.2.

**`GET /api/v1/listings/:id/similar`**
Filter by same make/model/year ± 1, exclude current listing, return top 6 by deal score.

**`POST /api/v1/listings/:id/contact-events`**
Reshapes existing `/leads/click`. Stores `seller_user_id` and `deduplication_key`.
Returns 200 even when deduplicated (silent deduplication, no error to the user).

**`POST /api/v1/listings/:id/report`**
Creates a moderation report on a listing. Fields: `reason` (enum), `description`.
Stored in `moderation_reports` collection. Handled in Phase F admin tooling.

**`GET /api/v1/listings/:id/ai-summary`** *(assumption Q2: template-based)*
Returns a short structured summary built from listing fields — no LLM call. Template:
"This {year} {make} {model} is priced SAR {delta} {below/above} the market estimate with
{mileage} km." Extend the template as more fields become available.
If client decides on LLM (Q2), this endpoint becomes an LLM call with caching per listing.

### Sellers (Screen 07)

**`GET /api/v1/sellers/:id`**
Returns SellerProfile. For now, synthesizes from listing data for scraped-listing sellers.
Real SellerProfile entity (from A1) serves data for registered sellers.

**`POST /api/v1/sellers/:id/report`**
Creates a moderation report on a seller. Same structure as listing report.

### Dealers (Screen 15)

**`GET /api/v1/dealers`**
List dealers. For Phase B: derived from listing data. DealerProfile entity (from A1) plugs in
during Phase C.

**`GET /api/v1/dealers/:id`**
Returns dealer profile. For Phase B: synthesized. Phase C: real DealerProfile entity.

**`GET /api/v1/dealers/:id/listings`**
Filter active listings by `dealer_profile_id`. Paginated.

### Compare (Screen 04)

**`POST /api/v1/compare`** and **`GET /api/v1/compare/:id`**
Already exist. Update response to include winner fields per spec §4 requirements:
```json
{
  "winners": {
    "best_value": "listing_id_1",
    "lowest_mileage": "listing_id_2",
    "best_seller_trust": "listing_id_1"
  }
}
```
Winner logic: best_value = lowest `market_delta_sar`; lowest_mileage = lowest `mileage_km`;
best_seller_trust = highest `seller.rating_average`. Return `null` for a winner when tied or
data is missing — never fabricate.

### Favorites (Screen 08)

**`POST /api/v1/me/favorites/:listing_id`**
Add snapshot fields on save: `price_snapshot_sar`, `deal_rating_snapshot`,
`market_delta_snapshot_sar`. Capture current valuation at save time.

---

## Phase C — Seller and dealer experience *(~1.5 weeks)*

Unblocks Screens 05, 10, 11. Requires Phase A auth.

### Seller listings (Screens 05, 11)

Add `owner_user_id` to all listings created via `/me/listings`.

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/me/listings` | Caller's listings. Returns `view_count` and `lead_count` per listing. |
| POST | `/api/v1/me/listings` | Create. Status starts `DRAFT`. Required fields per spec §6 (Screen 05). |
| GET | `/api/v1/me/listings/:id` | Single listing detail for the owner. |
| PATCH | `/api/v1/me/listings/:id` | Update. 403 if caller is not owner. Triggers price drop check (see D4). |
| POST | `/api/v1/me/listings/:id/submit` | `DRAFT` → `PENDING_REVIEW`. Triggers duplicate check. Auto-approves for now (`PENDING_REVIEW` → `ACTIVE` immediately). Real moderation queue in Phase F. |
| POST | `/api/v1/me/listings/:id/pause` | `ACTIVE` → `PAUSED` |
| POST | `/api/v1/me/listings/:id/resume` | `PAUSED` → `ACTIVE` |
| POST | `/api/v1/me/listings/:id/mark-sold` | `ACTIVE` or `PAUSED` → `SOLD` |
| POST | `/api/v1/me/listings/:id/duplicate` | Copy all fields, new ID, status `DRAFT` |
| DELETE | `/api/v1/me/listings/:id` | Soft delete — status `DELETED`, record stays |
| POST | `/api/v1/me/listings/:id/media` | Create `ListingImage` records. Accept multipart upload. Validate MIME type (JPEG/PNG/WEBP only). Store URL. Max 20 images per listing. |
| PATCH | `/api/v1/me/listings/:id/media/:image_id` | Update sort_order or is_cover |
| DELETE | `/api/v1/me/listings/:id/media/:image_id` | Remove image |

**Listing expiry:** Set `expires_at` at publish time (default 60 days from publish — confirm
with client). Background job transitions `ACTIVE` → `EXPIRED` daily (see Background Jobs).

**Pricing guidance on create:** When seller sets a price, call the pricing engine and return
the market range in the create/update response. Seller sees it as "AI Suggested Market Range"
in Screen 05.

**Duplicate check on submit:** Call the existing dedup engine from `karaa/dedup.py` when a
listing is submitted. If a near-duplicate exists, flag the listing for manual review instead
of auto-approving. Log the flag in the moderation reports collection.

**Listing promotion** *(assumption Q4: admin flag only)*
Add `is_promoted` boolean field to listings. Admin can set it via Phase F admin endpoints.
Promoted listings appear first in `best_match` sort. No payment flow in V1.

### Dealer profile (Screen 15)

Wire the real `DealerProfile` entity from A1:

```
GET    /api/v1/dealers/:id               — returns full DealerProfile
PATCH  /api/v1/dealers/:id               — update dealer info (owner only)
POST   /api/v1/dealers/:id/verify        — submit for verification (triggers admin queue in F)
```

`business_hours` stored as structured JSON:
```json
{ "sat": { "open": "09:00", "close": "18:00" }, "fri": null }
```
All times in `Asia/Riyadh` timezone.

### Dashboard (Screen 10)

**`GET /api/v1/me/dashboard`**
```json
{
  "listings": { "active": 3, "pending_review": 1, "draft": 2, "sold": 5, "expired": 0 },
  "total_leads": 42,
  "unread_messages": 7,
  "saved_cars": 12,
  "price_drop_alerts": 2,
  "saved_searches": 4,
  "profile_completion": 80
}
```

**Profile completion score:** percentage of filled optional fields on User + SellerProfile.
Fields counted: display_name, avatar_url, city_id, phone_verified, id_verified.
Each field = 20 points. Always returned as integer 0–100.

### User block (general)

**`POST /api/v1/users/:id/block`**
Prevents all contact from blocked user. Stored in `user_blocks` collection.
Check on message send — return 403 if sender is blocked by recipient.
Separate from conversation-level block in Phase D.

---

## Phase D — Retention and communication *(~2 weeks)*

Unblocks Screens 08, 09, 13, 16.

**Messaging protocol for V1:** polling. Frontend polls `GET /conversations` and
`GET /conversations/:id/messages` every 10–15 seconds. WebSockets deferred to post-V1.

### D1. Messaging (Screen 09)

New XWDatabase collections: `conversations`, `messages`.

```
GET    /api/v1/conversations
POST   /api/v1/conversations              — buyer initiates, body: { listing_id }
GET    /api/v1/conversations/:id
GET    /api/v1/conversations/:id/messages — paginated, newest last
POST   /api/v1/conversations/:id/messages — body: { text }; rate-limited to 20/min per user;
                                            checks user_blocks before inserting
POST   /api/v1/conversations/:id/read     — marks all messages as read for caller
POST   /api/v1/conversations/:id/block    — blocks this conversation
POST   /api/v1/conversations/:id/report   — reports conversation to moderation
```

On `POST /conversations/:id/messages`: create in-app notification for the recipient
(type: `new_message`). Compute and update `seller_profile.median_response_seconds` if
recipient is the seller responding to the first buyer message.

### D2. Notifications (Screen 13)

New XWDatabase collection: `notifications`.

```
GET    /api/v1/me/notifications           — paginated; ?filter=unread|messages|saved_searches|
                                            favorites|listings|system
PATCH  /api/v1/me/notifications/:id/read
POST   /api/v1/me/notifications/read-all
```

Notification types (created internally by routes and background jobs):
- `new_message` — created by `POST /conversations/:id/messages`
- `listing_approved` — created by moderation approve action (Phase F)
- `listing_rejected` — created by moderation reject action (Phase F)
- `listing_expiring` — created by expiry background job (7 days before `expires_at`)
- `price_drop` — created by D4 price drop tracker
- `saved_search_match` — created by saved search background job
- `mojaz_report_ready` — created by payment webhook (Phase E)
- `account_verification_updated` — created by Phase F verification actions

`create_notification(user_id, type, entity_type, entity_id, action_url)` — internal helper
called by all the above. Never called directly from routes.

In-app only for V1. Push and WhatsApp deferred (assumptions Q5, Q6).

### D3. Saved searches (Screen 16)

Add missing endpoints to existing account routes:
```
PATCH  /api/v1/me/saved-searches/:id     — update name, filters, frequency, channels, is_active
DELETE /api/v1/me/saved-searches/:id
```

Add fields to `SavedSearch`: `frequency` (instant/daily/weekly), `channels` (in_app),
`is_active`, `last_matched_at`, `new_match_count`.

`new_match_count` is reset to 0 when the user views the matches
(`GET /api/v1/listings?saved_search_id=:id`).

### D4. Price drop tracking

When `PATCH /me/listings/:id` changes `asking_price_sar`:
1. Query all favorites where `listing_id` matches
2. Compare new price against each favorite's `price_snapshot_sar`
3. If lower: call `create_notification(user_id, "price_drop", ...)`
4. Update `price_snapshot_sar` on the favorite record to the new price

Runs synchronously inside the PATCH handler. No queue needed at this scale.

---

## Phase E — Mojaz and payment *(~1 week + external dependency)*

Blocked on signed Mojaz API agreement and payment gateway contract.
Build skeleton now, gate everything behind a feature flag (`KARAA_MOJAZ_ENABLED=0`).

```
GET  /api/v1/listings/:id/mojaz/status    — report availability for this listing
GET  /api/v1/listings/:id/mojaz/preview   — teaser: owner count, accident flag (locked fields)
POST /api/v1/listings/:id/mojaz/checkout  — initiate checkout; returns { checkout_url, order_id }
POST /api/v1/payments/webhook             — payment provider posts here on success/failure;
                                            verify signature before processing
GET  /api/v1/mojaz/reports/:id            — full report; 403 until purchase confirmed server-side
```

New XWDatabase collection: `mojaz_reports`.
Fields per spec §8.8: `id`, `listing_id`, `vehicle_id`, `external_reference_encrypted`,
`status`, `purchase_price_sar`, `vat_sar`, `purchased_by_user_id`, `purchased_at`,
`available_at`, `access_expires_at`.
External Mojaz reference encrypted at rest.

Payment webhook handler:
1. Verify provider signature — reject without processing if invalid
2. Mark `mojaz_report.status = purchased`
3. Call `create_notification(user_id, "mojaz_report_ready", ...)`
4. Log to audit log

Report access: check `purchased_by_user_id == current_user.id` and
`access_expires_at > now()`. Never derive access from client state.

VAT: store separately as `vat_sar`. Saudi VAT is currently 15%. Do not hardcode — make it
a configurable setting.

---

## Phase F — Admin tooling *(~1.5 weeks, can start in parallel with Phase D)*

All admin endpoints under `/api/v1/admin/*`. Require admin role. Return 403 for non-admins.
Secure the existing `/debug` page behind admin auth before this phase goes to staging.

### User management
```
GET    /api/v1/admin/users
GET    /api/v1/admin/users/:id
PATCH  /api/v1/admin/users/:id/status    — suspend, reactivate
DELETE /api/v1/admin/users/:id
```

### Verification queues
```
GET    /api/v1/admin/verification/sellers     — pending seller verifications
POST   /api/v1/admin/verification/sellers/:id/approve
POST   /api/v1/admin/verification/sellers/:id/reject
GET    /api/v1/admin/verification/dealers     — pending dealer verifications
POST   /api/v1/admin/verification/dealers/:id/approve
POST   /api/v1/admin/verification/dealers/:id/reject
```
Approval sets `verification_status = verified` on the profile. Creates a
`account_verification_updated` notification for the user.

### Listing moderation
```
GET    /api/v1/admin/moderation/listings      — ?status=pending_review
GET    /api/v1/admin/moderation/reports       — user-submitted reports
POST   /api/v1/admin/moderation/listings/:id/approve   — PENDING_REVIEW → ACTIVE
POST   /api/v1/admin/moderation/listings/:id/reject    — PENDING_REVIEW → REJECTED; body: { reason }
POST   /api/v1/admin/moderation/listings/:id/feature   — set is_promoted (assumption Q4)
```

### Moderation — messages and users
```
GET    /api/v1/admin/moderation/messages      — reported conversations
POST   /api/v1/admin/moderation/users/:id/ban
```

### Audit log
```
GET    /api/v1/admin/audit-log               — ?user_id=&action=&from=&to=; paginated
```
Append-only `audit_log` collection in XWDatabase. Write an audit entry on:
- Every admin action
- Every payment event
- Every Mojaz report access
- Every moderation action
- OTP suspicious activity

### Feature flags
```
GET    /api/v1/admin/feature-flags
PATCH  /api/v1/admin/feature-flags/:key      — body: { enabled: true/false }
```
Feature flags stored in XWDatabase collection `feature_flags`. Checked at runtime by routes.
Initial flags: `mojaz_enabled`, `payments_enabled`, `whatsapp_notifications_enabled`,
`push_notifications_enabled`.

### Valuation monitoring
```
GET    /api/v1/admin/valuations/stats        — coverage, confidence distribution, avg comparable count
```

### Mojaz and payment support
```
GET    /api/v1/admin/mojaz/reports           — all purchases
POST   /api/v1/admin/mojaz/reports/:id/refund
```

---

## Background jobs

xwapi `BackgroundTasks` is sufficient for event-triggered jobs. Scheduled jobs require a
separate process — use APScheduler or a cron-triggered script at MVP scale. No Celery needed.

### Job 1: Listing expiry *(scheduled, runs daily)*
Query all listings where `status = ACTIVE` and `expires_at < now()`.
Transition each to `EXPIRED`.
Create a `listing_expiring` notification 7 days before `expires_at`.

### Job 2: Saved search matching *(event-triggered + scheduled)*
**Event trigger:** fires when a listing transitions to `ACTIVE` (on publish or admin approve).
Queries all active saved searches, evaluates each against the new listing using the same
filter engine as `GET /api/v1/listings`. For every match where `frequency = instant`, create
a `saved_search_match` notification and increment `new_match_count`.

**Scheduled trigger:** runs daily for `frequency = daily`, weekly for `frequency = weekly`.
Batches all new listings since `last_matched_at` against each saved search. Same logic.

### Job 3: Seller response time *(event-triggered)*
Fires when a seller sends a first reply in a conversation.
Computes time delta from buyer's first message to seller's first reply.
Updates `seller_profile.median_response_seconds` (rolling median over last 30 responses).

---

## Security requirements

Mandatory before any environment beyond local dev:

- VIN, dealer CR number, Mojaz external reference: encrypted at rest (§12)
- OTP: max 5 verify attempts, max 3 resend requests per 10 minutes per number; suspicious
  IP patterns logged to audit log
- Rate limiting: OTP endpoints strictest; message send 20/min per user; public read lenient
- File upload (Phase C): MIME type validation, max file size 10MB per image
- Idempotency keys: listing submit, media upload, message send, Mojaz checkout
- Payment webhook: verify provider signature before processing — reject otherwise
- Admin routes: all require admin role; `/debug` page secured before staging
- Phone number not exposed in public HTML — masked until a contact action is used
- Report access (Mojaz): server-side check on every request — never trust client state

---

## Deferred to post-V1

These are out of scope for the first launch based on spec exclusions or assumptions above:

- Seller reviews (assumption Q1 — pending client confirmation)
- AI summary via LLM — using template for V1 (assumption Q2)
- Personalized recommendations — using simple sort for V1 (assumption Q3)
- Listing promotion with payment flow (assumption Q4)
- Push notifications (assumption Q5)
- WhatsApp Business API for notifications (assumption Q6)
- WebSockets for real-time messaging — using polling for V1
- Native iOS/Android apps (excluded explicitly in spec §2.5)
- Auctions/bidding (excluded in spec §2.5)
- Dark mode (excluded in spec §2.5)

---

## Frontend unblock schedule

| Phase complete | Screens unblocked |
|---|---|
| Phase A | Screen 06 (Login/OTP), public read-only screens with mocked data |
| Phase B | Screens 01, 02, 03, 04, 07, 15 — buyer-side browse and discovery |
| Phase C | Screens 05, 10, 11 — seller flow, dashboard, dealer page (full) |
| Phase D | Screens 08, 09, 13, 16 — favorites, messages, notifications, saved searches |
| Phase E | Screen 12 — Mojaz purchase (after business contract signed) |
| Phase F | Admin tooling — internal, not a customer-facing screen |

---

## Gap summary — existing API vs new spec

### Already exists and reusable
Search, listings read, catalog, pricing engine, deal scoring, Mojaz preview, compare,
favorites (path changes), dealers read, connectors/providers (internal tooling),
price history, fraud detection.

### Exists but needs reshaping or remapping
`/auth` → OTP flow; `/pricing/estimate` → `/listings/:id/valuation` stored entity;
`/leads/click` → `/listings/:id/contact-events` with deduplication; `/favorites` and
`/searches` → `/me/favorites` and `/me/saved-searches`; compare response → add winners;
`GET /listings/:id` → add 410 for deleted/expired; search → add missing filter params
and `best_match` sort.

### Does not exist at all
OTP auth, SellerProfile entity, DealerProfile entity, ListingImage entity, Valuation entity
(stored), listing lifecycle management, `/me/listings` ownership layer, view count tracking,
per-listing lead aggregation, search autocomplete, homepage aggregates (trending, popular,
recommended), AI summary (template), report listing/seller, compare winners, user block
(general), dashboard aggregate, conversations and messages, notifications, saved search
matching background job, listing expiry background job, seller response time computation,
price drop tracking, Mojaz checkout and payment webhook, audit log, feature flags, admin
verification queues, admin moderation queue.
