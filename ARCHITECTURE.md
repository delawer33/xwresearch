# ARCHITECTURE.md — what exists and how it's wired

The map. Per-repo detail lives in that repo's own `CLAUDE.md`; this file is the index and the
cross-repo truth. Who you are and how to think, and where this map sits in company priority:
`CLAUDE.md`. How we work: `AGENTS.md`.

## The one thing to understand: who serves what

`kara-api` (port 8130) is the live product API — users, auth, website, and car data. Its
car data can come from its own **xwjson** store or from **`mawtarx-api`** (which resolves
**markibx** in-process); which endpoints go where is configurable (`listings_mode` + the
mawtarx wiring). `listings_mode` decides how much of mawtarx karaa serves: `hybrid` federates
its own xwjson data **with mawtarx-api's listings** over HTTP, `local` serves only its own
(prod read `local` on 2026-07-18 — verify via `/health`, and see the deploy skill). Card
price/deal is **read from the listing** (D-007); the standalone `/pricing`+`/deals` routes
**proxy** to mawtarx-api. `markibx-api` is unused.
Deploy/config detail: `docs/vps-current-state.md`; code detail: `repos/kara-api/CLAUDE.md`.

karaa is in development right now.

## The product repos

> **Ports below are the code defaults — what you get running locally.** The VPS passes an
> explicit `--port` two higher (karaa-api 8132, mawtarx-api 8252, markibx-api 8242). Both are
> correct; don't reconcile them. Server truth: `docs/vps-current-state.md`.
>
> **`repos/` is not guaranteed to mirror production, or to be current.** Before concluding
> "nothing does X," run **`/pull-repos`** and confirm every repo in this table exists locally
> (`git ls-remote https://github.com/Exonware/<name>` checks one you lack). An absent or stale
> repo looks exactly like a nonexistent feature.

| Repo                                           | Role                                                                                                            | Status                                                  |
| ---------------------------------------------- | --------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------- |
| `kara` (`exonware.karaa`)                      | **Buyer personalization only** (`recommend.py`, ~380 lines). Its engines/stores/catalog/scrapers were deleted 2026-07-15 (`efd4517`) and now live in mawtarx/markibx. | LIVE but tiny — add nothing else here   |
| `kara-api` (`exonware.karaa_api`)              | The real HTTP API and the actual product — port **8130**, prefix `/api/karaa/v1`. Primary dependency is **mawtarx**, not `kara`. Routes are **`XWActionRouter`** (43 files; HTTP + WS-RPC from one handler). | **LIVE** — active |
| `kara-connect` (`exonware.karaa_connect`)      | **Deprecated shim** — re-exports `exonware.mawtarx_connect`; zero providers, imported by nobody. Also holds a dead untracked `karaa_connect_api` stub that shadows the real one if installed — see its `CLAUDE.md`. | deprecated — don't add here |
| `karaa-connect-api` (`exonware.karaa_connect_api`) | The **real** connect facade — merged in-process into kara-api at `/api/karaa-connect/v1`, forwards to markibx-connect-api (:8244) + mawtarx-connect-api (:8253). 100% `XWActionRouter`. Standalone port **8133**. | **LIVE** |
| `kara-web`                                     | Frontend (Vite/TS) users actually see — karaa.net                                                               | LIVE — active                                           |
| `mawtarx` (`exonware.mawtarx`)                 | Listings + intelligence core (pricing/deals/fraud/mojaz); resolves markibx in-process                           | **load-bearing** — prod pricing/deals/catalog           |
| `mawtarx-api` (`exonware.mawtarx_api`)         | HTTP for mawtarx — port **8250**; kara-api proxies some car-intelligence endpoints here (current server config) | **load-bearing**, real                                  |
| `mawtarx-connect` (`exonware.mawtarx_connect`) | Marketplace scrapers (625 registered) — the **library**                                                          | being built; **no crawl runs** (no collect/daemon, no cron) |
| `mawtarx-connect-api`                          | HTTP surface for mawtarx-connect — port **8253**. A `karaa-connect-api` upstream. Plain `APIRouter`.            | **LIVE service** — up, even though no scraping runs     |
| `mawtarx-web`                                  | Frontend for mawtarx.com                                                                                        | LIVE                                                    |
| `markibx` (`exonware.markibx`)                 | Car knowledge base (specs/catalog); used in-process by mawtarx                                                  | **load-bearing** (via mawtarx)                          |
| `markibx-api` (`exonware.markibx_api`)         | HTTP for markibx — port **8240**                                                                                | **mostly stub (501)**; unused — markibx runs in-process |
| `markibx-connect` (`exonware.markibx_connect`) | Car-fact connectors (NHTSA / Wikidata) — the **library**                                                         | being built                                             |
| `markibx-connect-api`                          | HTTP surface for markibx-connect — port **8244**. A `karaa-connect-api` upstream. Plain `APIRouter`.            | **LIVE service**                                        |
| `markibx-web`                                  | Frontend for markibx.com (**not** gated at the edge, unlike karaa/mawtarx)                                       | LIVE                                                    |

## The platform layer (xw*)

18 shared libraries under `repos/xw*`. Each has its own `CLAUDE.md` stating what it is, when
to reach for it, its **verified** used-by list, and its gotchas. **Only 8 are actually
imported by product code** — the rest are available but unwired.

Task → library → status: **[`docs/tool-index.md`](docs/tool-index.md)**. Check it before
building any utility.

**Two layouts.** Most libs are flat (`src/exonware/<pkg>/`). **xwschema, xwaction, xwquery,
xwnode, xwmodels, xwentity, xwdata are polyglot** — Python at `ports/python/src/exonware/<pkg>/`,
**no `src/`** (a `src/`-rooted grep finds nothing there). Import paths are normal either way.

Two naming traps that bite every time:

- **`xwstorage` and `xwauth` cores are never imported directly.** All real usage goes through
  companion sub-packages that live in *different repos* but merge into the same namespace:
  `exonware.xwstorage.db` → repo `xwstorage-db`; `exonware.xwauth.id` → repo
  `xwauth-identity` (pip name `exonware-xwauth-id`). Repo folder, pip name, and import path
  diverge — don't assume `import exonware.xwstorage.db` means the code is in `repos/xwstorage`.
- The `exonware.xwauth` namespace is shared by three repos that **do not import each other** —
  they discover each other at runtime.

## Dependency direction (strict — never reverse)

```
karaa (live):      kara  ←  kara-connect  ←  kara-api        (kara-web calls kara-api over HTTP)
split (building):  markibx  ←  mawtarx  ←  mawtarx-connect
platform:          xwsystem  ←  (used by everything)
```

markibx never imports mawtarx. A listing links to a car by `catalog_key` (`make|model|year|trim`).

**The karaa arrows are legacy shape, not weight.** After the July 2026 split, `kara-api`'s real
dependency is **mawtarx** (imported in 26 files — stores, pricing, deals, mojaz, catalog), which
pulls `markibx` in-process. `kara` appears in **3** files, only for the recommender; `kara-connect`
is a shim that re-exports `mawtarx_connect`. So mawtarx+markibx must be installed in kara-api's
venv — they are not optional extras, they are the product.

## Data reality (do not get this wrong)

- **`kara-web` is the live website.** The 16-screen `repos/Karaa_Product_Engineering_Spec_*.md`
  is its design reference, not an unbuilt promise.
- **Local ≠ production.** Your laptop's data and the VPS's data differ a lot — don't reason
  about prod from your local store.
- **Everything runs on xwjson** (xwstorage-db / flat files) — server *and* local. **Postgres
  is not the store anywhere.** `PostgresVehicleStore` exists in mawtarx and is reachable via an
  opt-in setting whose own comment marks it `DANGEROUS`; nothing selects it. Don't infer a
  Postgres dev environment from that code or from mawtarx's older docs — there isn't one.

## Which repo do I touch for X?

| Task                                         | Repo                                                                                        |
| -------------------------------------------- | ------------------------------------------------------------------------------------------- |
| Website UI                                   | `repos/kara-web`                                                                            |
| A live API route / endpoint                  | `repos/kara-api` (car data is local or proxied to `mawtarx-api`, configurable)              |
| Prod pricing / deals / catalog intelligence  | `repos/mawtarx` — estimates are computed at **write** time and stored on the listing; every read serves the stored value. `/pricing`+`/deals` proxy to mawtarx-api. `repos/kara`'s engine is off the product path. |
| Which marketplaces exist / provider metadata | `repos/mawtarx-connect` — **not** `kara-connect`, which is a shim re-exporting it           |
| Buyer personalization / recommendations      | `repos/kara` (`recommend.py`) — the only thing left in that repo                            |
| Make/model/body-type autocomplete            | built in `mawtarx-api`, copy served by `kara-api` — see `repos/mawtarx-api/AUTOCOMPLETE.md` |
| New split-architecture work                  | `repos/mawtarx` / `repos/markibx` families                                                  |
| A shared utility (auth, storage, HTTP, …)    | **[`docs/tool-index.md`](docs/tool-index.md)** first — then that lib's `CLAUDE.md`          |

## More

- Terms: `docs/glossary.md`. Why a thing is the way it is: `DECISIONS.md`.
- Landed work (archived plans/reports): `docs/history/`.
- Server topology, ports, deploy config: `docs/vps-current-state.md`.
