# ARCHITECTURE.md — what exists and how it's wired

The map. Per-repo detail lives in that repo's own `CLAUDE.md`; this file is the index and the
cross-repo truth. Who you are and how to think: `CLAUDE.md`. How we work: `AGENTS.md`.

## The one thing to understand: who serves what

`kara-api` (port 8130) is the live product API — users, auth, website, and car data. Its
car data can come from its own **xwjson** store or from **`mawtarx-api`** (which resolves
**markibx** in-process); which endpoints go where is configurable (`listings_mode` + the
mawtarx wiring). Right now prod runs `listings_mode=hybrid`: kara-api serves listings from a
store that federates its own xwjson data **with mawtarx-api's listings** (pulled over HTTP). For
intelligence it uses mawtarx two ways: card price/deal is computed **in-process** (`mawtarx_intel`),
while the standalone `/pricing`+`/deals` routes **proxy** to mawtarx-api. `markibx-api` is unused.
Deploy/config detail: `docs/vps-current-state.md`; code detail: `repos/kara-api/CLAUDE.md`.

karaa is in development right now.

## The product repos

> **Ports below are the code defaults — what you get running locally.** The VPS passes an
> explicit `--port` two higher (karaa-api 8132, mawtarx-api 8252, markibx-api 8242). Both are
> correct; don't reconcile them. Server truth: `docs/vps-current-state.md`.

| Repo                                           | Role                                                                                                            | Status                                                  |
| ---------------------------------------------- | --------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------- |
| `kara` (`exonware.karaa`)                      | Monolith core: listings, engines (pricing/deal/fraud/mojaz), catalog, cities, scraper sources                   | **LIVE** — stable (frozen ~2026-06-30)                  |
| `kara-api` (`exonware.karaa_api`)              | The real HTTP API — port **8130**, prefix `/api/karaa/v1`                                                       | **LIVE** — active                                       |
| `kara-connect` (`exonware.karaa_connect`)      | Provider registry (per-brand/country marketplaces)                                                              | LIVE                                                    |
| `kara-web`                                     | Frontend (Vite/TS) users actually see                                                                           | LIVE — active                                           |
| `mawtarx` (`exonware.mawtarx`)                 | Listings + intelligence core (pricing/deals/fraud/mojaz); resolves markibx in-process                           | **load-bearing** — prod pricing/deals/catalog           |
| `mawtarx-api` (`exonware.mawtarx_api`)         | HTTP for mawtarx — port **8250**; kara-api proxies some car-intelligence endpoints here (current server config) | **load-bearing**, real                                  |
| `mawtarx-connect` (`exonware.mawtarx_connect`) | Marketplace scrapers (625 registered)                                                                           | being built; **not running**                            |
| `markibx` (`exonware.markibx`)                 | Car knowledge base (specs/catalog); used in-process by mawtarx                                                  | **load-bearing** (via mawtarx)                          |
| `markibx-api` (`exonware.markibx_api`)         | HTTP for markibx — port **8240**                                                                                | **mostly stub (501)**; unused — markibx runs in-process |
| `markibx-connect` (`exonware.markibx_connect`) | Car-fact connectors (NHTSA / Wikidata)                                                                          | being built                                             |

## The platform layer (xw*)

18 shared libraries under `repos/xw*`. Each has its own `CLAUDE.md` stating what it is, when
to reach for it, its **verified** used-by list, and its gotchas. **Only 8 are actually
imported by product code** — the rest are available but unwired.

Task → library → status: **[`docs/tool-index.md`](docs/tool-index.md)**. Check it before
building any utility.

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
`kara-api` bridges the two worlds: besides `kara`, it imports `exonware.mawtarx` (which pulls
`markibx`) in-process to price listing cards — so mawtarx+markibx must be installed in kara-api's venv.

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
| Prod pricing / deals / catalog intelligence  | `repos/mawtarx` — kara-api runs its engines **in-process** for listing cards (`karaa_api.mawtarx_intel`) and **proxies** the standalone `/pricing`+`/deals` routes to mawtarx-api. `repos/kara`'s own engine is no longer on the product path. |
| Which marketplaces exist / provider metadata | `repos/kara-connect`                                                                        |
| Make/model/body-type autocomplete            | built in `mawtarx-api`, copy served by `kara-api` — see `repos/mawtarx-api/AUTOCOMPLETE.md` |
| New split-architecture work                  | `repos/mawtarx` / `repos/markibx` families                                                  |
| A shared utility (auth, storage, HTTP, …)    | **[`docs/tool-index.md`](docs/tool-index.md)** first — then that lib's `CLAUDE.md`          |

## More

- Terms: `docs/glossary.md`. Why a thing is the way it is: `DECISIONS.md`.
- Landed work (archived plans/reports): `docs/history/`.
- Server topology, ports, deploy config: `docs/vps-current-state.md`.
