---
name: run-local-stack
description: Run the karaa product stack locally — mawtarx-api (car data, xwjson), kara-api (product API), and kara-web (Vite site) — wired together and each under a memory cap. Use when the user asks to run/start/serve/launch the services, the stack, the site, mawtarx/kara/kara-web locally, or to bring the local app up.
---

# Run the karaa stack locally

Three services, started in this order (each depends on the one before):

| # | Service | Repo | Port | Backend / role |
|---|---|---|---|---|
| 1 | **mawtarx-api** | `repos/mawtarx-api` | **8250** | car data + intelligence, on **xwstorage-db (xwjson)** |
| 2 | **kara-api** | `repos/kara-api` | **8130** | product API; `KARAA_LISTINGS_MODE=mawtarx` → proxies car data to mawtarx-api |
| 3 | **kara-web** | `repos/kara-web` | **8135** (Vite) | the site; proxies `/api` → kara-api |

Request flow: **browser → kara-web:8135 `/api` → kara-api:8130 → mawtarx-api:8250 → xwjson**.

## Just do it

```bash
.claude/skills/run-local-stack/run-stack.sh start        # all three, in order
.claude/skills/run-local-stack/run-stack.sh status       # active? memory each?
.claude/skills/run-local-stack/run-stack.sh logs mawtarx # journal for one service
.claude/skills/run-local-stack/run-stack.sh stop         # stop all
```
Then open **http://127.0.0.1:8135**. Start one at a time with
`start mawtarx|kara-api|kara-web`.

## The rule that is NOT optional on this machine

1. **Every service runs under a cgroup memory cap** (`systemd-run --user
   -p MemoryMax=2G -p MemorySwapMax=0`). This box is 14 GB with a 7.5 GB tmpfs
   `/tmp`; an unguarded runaway freezes the whole desktop. The cap makes the
   kernel OOM-kill the offending service instead. **Do not** launch these with a
   bare `nohup …/mawtarx-api &` — always cap. And do **not** set `MemoryHigh`
   below ~900 MB: the app's import baseline (weasyprint/reportlab/lxml/uharfbuzz)
   is ~900 MB, and a low soft limit throttles the whole process into an apparent
   hang.

## How it's wired (so you can debug / do it by hand)

- **venv:** the single `repos/.venv` has the whole editable stack (mawtarx,
  markibx, kara, all `xw*`). Use `repos/.venv/bin/{mawtarx-api,karaa-api}`.
- **Data dirs** are passed as absolute env vars so CWD doesn't matter:
  mawtarx → `repos/mawtarx-data/…`, kara → `repos/karaa-data/…`. mawtarx seeds
  200 sample listings on an empty store (`MAWTARX_SEED_ON_EMPTY=1`).
- **kara-api → mawtarx** wiring lives in `repos/kara-api/.env.local`
  (`KARAA_LISTINGS_MODE=mawtarx`, `MAWTARX_API_URL=http://127.0.0.1:8250/api/mawtarx/v1`).
  No service token is required locally (`MAWTARX_SERVICE_TOKEN_REQUIRED=0` →
  anonymous is allowed).
- **kara-web** runs `npm run dev` in `repos/kara-web` (node_modules already
  present); its `predev` links xwui. Vite binds `127.0.0.1:8135` and proxies
  `/api` → `http://127.0.0.1:8130` (`vite.config.ts` / `.env.local`).

## Verify it end to end

```bash
curl -s http://127.0.0.1:8250/api/mawtarx/v1/health                     # mawtarx
curl -s http://127.0.0.1:8130/api/karaa/v1/health                       # kara-api
curl -s "http://127.0.0.1:8135/api/karaa/v1/search/listings?limit=2"    # full chain via Vite proxy
```
Healthy mawtarx-api is ~220 MB and answers `/listings/recommended` in ~20 ms.
If a service is unhealthy, `run-stack.sh logs <name>` shows the journal (which,
unlike a `/tmp` logfile, survives a reboot).

## Notes

- These are **transient systemd --user units** — they do not survive a reboot
  (fine for dev). Re-run `start` after a reboot.
- Local ≠ prod. Production deploys are a different path — see the `deploy-vps`
  skill; do not confuse the two. Prod ports/domains differ (mawtarx-api 8252 /
  mawtarx.com, kara-api 8132 / karaa.net).
