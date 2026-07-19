---
name: create-connector
description: >
  Build or activate a marketplace car-listing connector in repos/mawtarx-connect —
  a scraper that pulls car adverts into the mawtarx listings DB. Use when the user
  says "add a connector / scraper", "wire up <site>", "activate <provider>", "scrape
  <marketplace>", "the connector for <site> is missing fields", or invokes
  /create-connector. Covers both activating one of the ~580 registered-but-dormant
  providers and adding a brand-new marketplace.
---

# Create / activate a connector

A connector pulls **car advertisements** (a specific unit for sale: price, mileage,
seller, city, photos) from one marketplace into the mawtarx listings DB. It is NOT a
car-spec source — manufacturer/government facts about a *model* belong in
markibx-connect, not here.

All paths below are relative to **`repos/mawtarx-connect/`**. Run Python with the
workspace venv: **`repos/.venv/bin/python`** (`collect.py` auto-activates it).

## The one rule: source-first

The **source** is the load-bearing artifact. Everything real flows through it.

| Layer | File | Role |
|---|---|---|
| **Source** (required) | `src/.../connectors/sources/<name>.py` | Scraper + Normalizer + `@register_source`. **This is the connector.** Every scrape — production (`collect.py`→`IngestionPipeline.run`→`build_adapter`), the debug runner, `Connector.sync` — resolves through here. |
| Provider (optional) | `src/.../providers/<name>.py` | A `ProviderInfo` metadata card (countries, category, legal_note, `source_id` pointer). Only needed so the connector shows in kara-api's provider directory / debug UI. **Not needed for ingestion.** |
| Config | `scripts/collect.yaml` | Which sources production actually runs, + per-source param overrides. |

**Request params live on the SOURCE**, via `register_source(..., default_params={...})`.
This is the canonical home; `collect.yaml` (or a caller) overrides per-key. Prod, debug,
and `sync` all read it, so they can't diverge. **Do NOT put runtime params in a
provider's `default_request_params()`** — production never calls it. (The only
legitimate provider override is when several presets share one scraper — e.g. the
`samaco_*` brand fronts layer `brands=[…]` over the shared source via `super()`.)

## Two workflows

- **Activate a dormant provider** — a `providers/<name>.py` `ProviderInfo` exists but has
  no scraper. Write the `sources/<name>.py` source (below), point `ProviderInfo.source_id`
  at it, add it to `collect.yaml`. Confirm the id: `grep -rn "source_id" providers/<name>.py`.
- **Add a new marketplace** — no files yet. Write the source; add a `ProviderInfo` only if
  you want directory/debug visibility; add to `collect.yaml`.

## Phase 0 — scrapability report FIRST (before writing any parser)

**Do not start implementing until you have reported what is and isn't scrapable and the
user has seen it.** Fetch a real listing/index page (use a subagent for site-structure
research — see below), then:

0. **Viability gate.** Is the data in the served HTML, or JS-loaded (a bare SPA bootstrap
   with no data looks identical to "no results")? Any anti-bot (DataDome/Cloudflare), or a
   ToS/robots ban / paid-partner-API-only source? If protected or CSR-only, mark it
   `DISABLED` and stop — never ship a scraper that fights anti-bot.
1. Find the data: is there an **English** version or JSON API? Prefer it (see Translate).
   Look for `__NEXT_DATA__`, `ld+json`, a REST/GraphQL endpoint, or a spec table.
2. **Dump every label/value pair on a real detail page.** Never declare a field
   "unavailable" without this dump — a field you assume is missing is usually just under a
   label you didn't look for.
3. Produce a per-field verdict: for each of make, model, year, trim, city, price, mileage,
   VIN, body_type, fuel_type, transmission, drivetrain, engine, color, seller info, photos —
   **scrapable (where from) / genuinely absent / hard (why)**.
4. **Report that map to the user. Ask about anything ambiguous.** Only then implement.

## Anatomy of a source file

Two classes + one registration. Contracts are `IScraper` / `INormalizer` from
`exonware.xwapi.scrapping.contracts`. Copy the shape from a real source — pick one whose
*fetch style matches yours* (JSON API vs HTML), but **verify it field-by-field yourself
before trusting it as a template; don't inherit another connector's bugs.**

```python
class <Name>Scraper:
    source = SOURCE_ID
    def fetch(self, request: ScrapeRequest) -> Iterable[RawRecord]:
        params = dict(request.params or {})
        page_start = int(params.get("page_start", 1)); page_end = int(params.get("page_end", 5))
        # …fetch pages, yield one raw dict per advert…

class <Name>Normalizer:
    def normalize(self, raw: RawRecord, source: str) -> NormalizedRecord | None:
        return { …the field contract below… }

@register_source(
    SOURCE_ID, meta=_META,
    default_params={"page_start": 1, "page_end": 5},   # + fetch_detail / category_id / etc.
)
def _factory(http: HttpFetcher | None = None) -> tuple[IScraper, INormalizer]:
    return <Name>Scraper(http=http), <Name>Normalizer()
```

The engine drives it as: `scraper.fetch(request)` → per raw → `normalizer.normalize(raw,
scraper.source)` → persist. A normalizer returning `None` drops that record silently.

## The field contract (what `normalize()` must emit)

`record_to_listing` (in `repos/mawtarx/.../store.py`) is the authority on what persists.

- **Won't persist at all without:** `make`, `model`, and a non-zero price. A record
  missing any of these is silently dropped — so guard against emitting junk that looks
  valid.
- **Definition-of-done required fields:** `make`, `model`, `year`, `trim`, `city` — **plus
  `vin` whenever the site exposes it** (VIN is the strongest dedup key; extract it wherever
  present).
- **Emit these keys** (see any real normalizer): `source`, `source_id`, `source_url`,
  `fetched_at`, `title`, `make`, `model`, `year`, `trim`, `price_value`, `price_currency`,
  `country`, `mileage_km`, `city`, `region`, `body_type`, `fuel_type`, `transmission`,
  `drivetrain`, `engine`, `color`, `vin`, `description`, `photos`, `seller_type`,
  `seller_id`, `seller_phone`, `seller_whatsapp`, `dealer_id`.
- **Scrape as many fields as possible.** If a field is genuinely too hard, **document why
  in a code comment** — never drop it silently.
- **The emit list IS an allowlist.** `record_to_listing` silently drops any key not on it
  (or not a first-class field) — an invented key (`cylinder_count`, `engine_size`) goes
  nowhere, and a discrete spec folded into free-text `engine` is unrecoverable. A useful
  field with no slot has two honest homes only: an **`extras`** dict (rich attrs — seats,
  doors, horsepower, cylinders), or **promote to first-class** (add to `VehicleListing` +
  the allowlist + API `ListingOut`). Flag which in the Phase-0 verdict; the user decides.
  Never fold-into-text or emit-and-hope.
- Price: emit **native** `price_value` + `price_currency` (e.g. `"KWD"`). Do NOT convert to
  SAR — that's a derived display value computed downstream (Plan B).

## Rules that keep the data honest

- **Everything English.** Prefer the site's English version/API. When none exists,
  translate **structured** fields (make/model/color/body/fuel/city) via a curated
  Arabic/other→English table in the source file — the pattern is `saudisale.py`'s
  `_BRANDS_AR` / `_MODELS_AR` (data, not logic; leave uncovered values native rather than
  guessing). Free-text `description` **may stay native**.
- **Use the shared normalizers.** `norm_body`, `norm_fuel`, `norm_transmission`,
  `norm_color` from `connectors/normalize.py`. If a site emits a label they don't map
  (e.g. a new Arabic color, an octane variant), **add it to `normalize.py`** — don't
  special-case it in the connector.
- **Dedup / VIN.** No VIN → dedup falls back to a per-connector key over
  `{trim, color, city}` (`repos/mawtarx/.../dedup.py :: CONNECTOR_TRUSTED_FIELDS`), needing
  2 fields that are populated **and actually vary**. A field that's populated but constant
  (a single-location dealer hardcoding `city`) is worthless there and must not be trusted.
  Extracting VIN wherever present sidesteps all of this.

## Before you call it done — 7-step verification (mandatory)

Run every step; show the numbers. Most connector bugs this project has seen were caught
(or missed) here.

1. **Pagination sanity** — page 1 and page 2 listing IDs must be **disjoint**.
2. **No first-match regex over loosely-scoped text** — locate the *authoritative* element
   first, then match inside it. (A page-wide "grab the first city-looking string" is how
   `bahraincars` stored the wrong city for everyone.)
3. **Dumped all label/value pairs** before writing off any field as unavailable.
4. **Manual cross-check against 3 real listings**, field-by-field, output vs live page —
   show before/after for each field. Do this with a direct harness, no DB:
   ```python
   from exonware.mawtarx_connect.connectors import build_adapter, get_source_defaults
   from exonware.xwapi.scrapping.types import ScrapeRequest
   s, n = build_adapter("<source_id>")
   req = ScrapeRequest(source="<source_id>",
                       params={**get_source_defaults("<source_id>"), "page_end": 1})
   for raw in s.fetch(req):
       print(n.normalize(raw, s.source))
   ```
5. **Placeholder vs wrong-element.** Distinguish "the site genuinely shows a placeholder /
   the field is truly absent" from "my parser grabbed the wrong element." Record which — a
   genuine site gap is not a bug and must not be 'fixed' into a wrong value later. (e.g.
   OpenSooq SERP genuinely omits color/transmission — that's real, not a scraper miss.)
6. **Tests against captured real HTML**, not hand-typed fixtures. Capture pages into
   `tests/fixtures/<source>/`, load them in `tests/test_<source>.py`. Real fixtures are
   *preferred*; skip only if capturing is disproportionate to the change.
7. **Survival check** — the bug this project shipped most. Push a record through
   `record_to_listing` and print which scraped keys the `VehicleListing` **dropped**; any
   useful one is a bug (→ extras or promote). Emitting a field the pipeline discards ==
   not emitting it.
   ```python
   from exonware.mawtarx.store import record_to_listing
   rec = n.normalize(raw, s.source); lst = record_to_listing(rec)
   emitted = {k for k, v in rec.items() if v not in (None, "", [])}
   kept = {f for f in emitted if getattr(lst, f, None) not in (None, "", [])} | set(lst.extras or {})
   print("DROPPED:", emitted - kept)   # nothing useful may be here
   ```

## Run it

```bash
# one source into a throwaway local xwstorage-db dir
repos/.venv/bin/python scripts/collect.py --sources <source_id> --fresh \
  --xwdb /tmp/connector-check
```

Then re-query blank-rates per field and eyeball a sample. A **`raw=0 persisted=0` with a
clean DONE is a red flag**, not a success — a WAF/block or a broken selector looks
identical to "no results" unless the scraper distinguishes them (see `haraj.py` raising on
an HTTP-388 block).

## Don't

- Don't put runtime params in a provider's `default_request_params()` — production ignores
  it. Params go in `register_source(default_params=…)`; `collect.yaml` overrides.
- Don't trust a marketplace's own free-text "Category"/dropdown as a vehicle spec (it's
  seller-chosen noise) — `bahraincars` had 89% wrong `body_type` this way.
- Don't wire a markibx catalog (`split_model_trim`) — that integration is postponed.
- Don't bypass a site's access controls, robots rules, or rate limits. Ever.
- Don't mark done on a red/blocked scrape, a silent 0-result, or without the 3-listing
  cross-check.
- Don't change a live connector's dedup fields (`trim/color/city`) or `source_id` format
  without recomputing `dedup_key` on stored rows first — a drift orphans them, so re-scrapes
  duplicate instead of update.

## Output

End with: the per-field scrapability verdict, the 3-listing cross-check numbers, blank-rate
per field from a real run, which of the 7 verification steps passed (incl. the survival-check
DROPPED set — must hold nothing useful), and anything left as a genuine (documented) site
gap vs. a deferred fix.
