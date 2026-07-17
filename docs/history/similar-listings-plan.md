# Similar Listings — fallback ladder + dedicated endpoint

**Date:** 2026-07-16
**Reported by:** Daria, 2026-07-14 — "Estimate Car Price sometimes shows no Similar Listings; there should be 3."
**Repos touched:** `kara-api`, `kara-web` (no mawtarx/markibx change)

---

## The bug

The Estimate result page's "Similar Listings" strip makes **one** call
(`kara-web/src/views/estimate.ts` → `fetchSimilarListings`):

```
GET /search/listings?make=<Make>&model=<Model>&year_min=<y-2>&year_max=<y+2>&limit=6
```

and renders the first 3. That's the whole feature — a plain inventory search pinned to
**exact make + model**, with **no fallback**. Matching is by normalized slug: query and
stored listing both go through markibx `canonical_make`/`canonical_model`, and a listing is
kept only if `make_norm` AND `model_norm` match exactly (`mawtarx/types.py:1012-1016`).

So when inventory holds <3 active listings for that exact make+model, the strip shows
0–2 cards. Confirmed against Daria's examples:

| Car | Behaviour | Why |
|---|---|---|
| Bentley Bentayga | 3 cards ✅ | enough active ads |
| Omoda E5 2024 | empty | brand-new Chery sub-brand, ~0 ads |
| Audi RS Q8 2023 | empty | rare variant, ~0 ads (see D3) |
| BAIC BJ40 2023 | 1 card | niche brand, 1 ad |

**Not the cause:** normalization. Verified deterministic and identical on both sides —
`Omoda/E5 → omoda/e5`, `Audi/RS Q8 → audi/rsq8`, `BAIC/BJ40 → baic/bj40`. A query and a
correctly-scraped listing *will* match. The pool is simply empty.

### Two secondary defects found

- **D2 — the year filter is dead.** Frontend sends `year_min`/`year_max`
  (`estimate.ts:807-808`); the route parameters are `min_year`/`max_year`
  (`search.py:60-61`). Unknown query params are ignored, so the ±2-year window is
  **never applied** — "similar" listings currently span all years. This *loosens* the
  search, so it isn't the cause of the empty strip, but it means the set isn't
  year-scoped as intended. Fixing it in isolation would make sparse cars *worse*, so it
  must land together with the ladder.
- **D3 — variant naming.** `"RS Q8"` → `rsq8`, but the same car stored as `"Q8"` → `q8`
  and will not match. Out of scope here (data-quality; belongs with the S1 make/model
  normalization work) — logged, not fixed.

---

## Decisions

- **D-A — Dedicated endpoint, not a reuse of `/search/listings`.** The existing
  `/listings/{id}/similar` needs a real listing id; the estimate flow has none (the user
  typed a hypothetical car). The ladder also needs multiple passes over inventory, which
  would be N HTTP round-trips if driven from the browser.
- **D-B — `/search/similar`, not `/listings/similar`.** `routes/insights.py` mounts before
  `routes/listings.py` and shadows static `/listings/...` paths; `/search/*` is collision-free.
- **D-C — Logic lives in `kara-api`, not `mawtarx`.** This is presentation/recommendation
  policy, not listings-core domain. `routes/search.py` already owns comparable post-filter
  policy (body_type/condition/drivetrain/color). Keeping it here also keeps the blast
  radius to one backend repo and one deploy, and avoids a mawtarx version bump on a
  load-bearing prod library.
- **D-D — No price-band rung.** Under FX Plan B, `price_sar` is engine-internal and is
  `0.0` for non-SAR listings. A cross-make price band built on it would silently
  mis-bucket. The ladder uses year/body-type only.
- **D-E — Response is a superset of what the frontend already reads.** `{items, match_level}`
  with `items` as the **same `ListingCardOut[]`** `/search/listings` returns. The caller
  already does `res.items || []`, so nothing about card rendering changes.

---

## Endpoint contract

```
GET /search/similar

Query:
  make        str   required
  model       str   required
  year        int   optional  — centres the ±2 window
  trim        str   optional
  body_type   str   optional  — if absent, inferred from inventory
  limit       int   default 3, 1..12

200 → {
  "items": ListingCardOut[],          # identical shape to /search/listings items
  "match_level": "exact" | "model" | "make_body" | "body" | "none"
}
```

`match_level` reports the **broadest** rung that contributed, so the UI can label the strip
honestly ("Same model" vs "Similar cars you may like"). Additive — safe to ignore initially.

Same `@cached_endpoint` treatment as `search_listings`: ttl 30, data-version cache key
(skip caching when `data_version()` is None).

---

## The fallback ladder

Accumulate until `limit` is reached; each rung excludes ids already taken. Stop early.

| # | `match_level` | Filter |
|---|---|---|
| 1 | `exact` | make + model + trim + year±2 |
| 2 | `model` | make + model (any year, any trim) |
| 3 | `make_body` | same make + same body_type, **excluding** that model |
| 4 | `body` | same body_type, any make |
| 5 | `make` | same make, any body — **excluding** that model |

Rung 5 was added after live verification: `body_type` is optional on the estimate
form, and when the model has no ads at all there is nothing to infer it from, so
rungs 3–4 both no-op and Omoda E5 / Audi RS Q8 fell through to an empty strip —
the exact bug this exists to fix. Rung 5 makes the fix independent of that field.

- **Rung 1** stays strict so common cars (Bentayga) still show true same-model comps.
  The ladder only engages for the sparse tail.
- **body_type resolution:** `body_type` param → else majority body_type of that make+model
  across the whole store (even non-visible rows, since it's a lookup not a result) → else
  rungs 3–4 are skipped and we return what rungs 1–2 found.
- **Ordering within each rung:** closest year to target first, then newest. No price sort
  (D-D).
- **Visibility:** every rung runs through the same `filter_listings_by_allowlist` +
  `browse_visible` gate as `/search/listings`. Sold/draft/expired never leak in.

---

## Frontend change (`kara-web`)

`fetchSimilarListings` becomes a call to the new route. Delta is ~4 lines in one function:

- route `/search/listings` → `/search/similar`
- drop the dead `year_min`/`year_max`; send `year` + `trim`
- body reading unchanged (`res.items || []`)
- `match_level` unused for now (labeling is a follow-up)

---

## Test cases

Against a seeded temp store (`Settings(seed_on_empty=True)`), plus synthetic fixtures:

1. **Dense model → `exact`, 3 items** — the Bentayga case; ladder must not engage.
2. **Sparse model (1 ad) → 3 items, `match_level` broadened** — the BAIC BJ40 case.
3. **Absent model (0 ads) → 3 items via body fallback** — the Omoda E5 / RS Q8 case;
   strip is never empty when the body_type is resolvable.
4. **Unknown make+model, unresolvable body_type → `none`, empty items, HTTP 200** —
   degrade honestly, don't 500.
5. **No duplicate ids across rungs.**
6. **Rung 1 strictness** — a same-make different-model car never appears while ≥3
   exact matches exist.
7. **Visibility** — a SOLD/DRAFT listing never appears at any rung.
8. **`items` shape parity** with `/search/listings` (`intelligence`, `primary_photo_thumb`).

---

## Shipped + verified (2026-07-16)

Live on `exonware-riyadh-01`, verified against production inventory (15,472 listings):

| Car | Before | After | Rung |
|---|---|---|---|
| Bentley Bentayga 2021 | 3 | **3** | `exact` — control; ladder correctly stays out |
| BAIC BJ40 2023 | 1 | **3** | `make_body` — BJ40, BJ40 C, BJ80 |
| Audi RS Q8 2023 | 0 | **3** | `make` — Audi A4, Q7, A5 |
| Omoda E5 2024 | 0 | **3** | `body` (with `body_type`); `make` → 2 without it |

Note RS Q8 → plain **Audi Q8** confirms D3 live: the same car listed as `Q8`
normalizes to `q8` and never matches an `rsq8` query. The ladder recovers it
rather than fixing the data.

### Deploy note (the expensive lesson)

Shipping this required a platform sync nobody had done: `/opt/karaa-api/.venv` was
~5 days stale, so kara-api `main` (3 undeployed commits) needed `xwapi` + `xwbase`
+ `xwaction` with it. Two traps worth recording:

- **Don't pin a platform lib to a "minimal" middle commit.** Pinning `xwapi` to
  `b5eb0c51` to dodge the xwaction cascade produced a combination nobody runs, and
  the app started but never attached `app.state` (health 500). Shipping the
  locally-proven HEAD combo fixed it. Match what the working venv actually runs.
- **`hybrid_store` and mawtarx-api's `GET /listings/snapshot` are a matched pair.**
  Deploying kara-api without mawtarx-api leaves the snapshot 404ing; the fetch
  degrades silently to 0 remote rows, and prod quietly served 2,560 of 15,472
  listings with nothing in the log. If you ship one, ship both.

## Out of scope

- D3 variant naming (`RS Q8` vs `Q8`) — data quality, goes with S1.
- UI relabeling per `match_level` — follow-up once the endpoint is live.
- Backfilling inventory for new Chinese brands — connector work.
