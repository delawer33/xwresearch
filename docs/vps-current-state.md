# VPS — how the karaa ecosystem runs *right now*

**Live-verified 2026-07-17** against `exonware-riyadh-01` (149.104.105.145) by
read-only inspection (`systemctl`, `ss`, `docker ps`, env files, Caddyfile, data
dirs). Secrets were never copied out; every `*_SECRET` / `*_TOKEN` / `*_PASSWORD`
value below is shown as `<REDACTED>`. (Previous full snapshot: 2026-07-10.)

## ⚠️ This is a snapshot, not a standard

Read this before trusting anything below:

- This describes **how the one production box happens to be wired on 2026-07-10** —
  nothing more. It is **not a specification, not a standard, not a target
  architecture, and not a promise.**
- **It is not how things "must" be.** No claim here should be read as "this is the
  correct/blessed way to run the stack." It is just what someone set up, by hand,
  at some point.
- **It is not a fact that prod will stay like this**, or that any future
  environment (a second server, a rebuild, a container migration, a teammate's
  box) will look anything like it. Ports, paths, venvs, the auth gate, even which
  services exist can all change without this doc changing.
- The box is **hand-configured with no CI/CD and no config-as-code** — the running
  state is the source of truth, and it drifts. Where this doc and the actual server
  disagree, **the server is right and this doc is stale.** Re-verify live before
  relying on any specific number.
- Treat it as an orientation map for "what is probably running and roughly how,"
  never as a contract.

## Host

- `exonware-riyadh-01`, Ubuntu 24.04.4 LTS, x86_64, ~15 GiB RAM.
- **Multi-tenant.** The karaa/mawtarx/markibx stack shares this box with several
  unrelated projects (see [Co-tenants](#co-tenants-not-part-of-this-ecosystem)) —
  memory and ports are contended, so RAM headroom is tight.
- Edge is a single **Caddy** on :80/:443 (TLS, HSTS, security headers). Every app
  service binds **loopback only** (`127.0.0.1:<port>`); nothing but Caddy and SSH
  is exposed publicly for our stack.

## The services (this ecosystem)

Six long-running systemd services, each an isolated `/opt/<svc>/.venv`, each a
dedicated unix user, all bound to loopback:

| Service (systemd unit) | Port | venv | WorkingDir / data | User | Public route |
|---|---|---|---|---|---|
| `karaa-api.service` | 8132 | `/opt/karaa-api/.venv` | `/var/lib/karaa-api` | `karaa-api` | karaa.net + `:8137` preview |
| `mawtarx-api.service` | 8252 | `/opt/mawtarx-api/.venv` | `/var/lib/mawtarx-api` | `mawtarx-api` | mawtarx.com `/api/mawtarx/*` |
| `mawtarx-connect-api.service` | 8253 | `/opt/mawtarx-connect-api/.venv` (**own venv**) | `/opt/mawtarx-connect-api` | `mawtarx-connect-api` | mawtarx.com `/api/mawtarx-connect/*` |
| `markibx-api.service` | 8242 | `/opt/markibx-api/.venv` (**shared**) | `/var/lib/markibx-api` | `markibx-api` | markibx.com `/api/markibx/*` |
| `markibx-connect-api.service` | 8244 | `/opt/markibx-api/.venv` (**shared with markibx-api**) | `/var/lib/markibx-api` | `markibx-api` | markibx.com `/api/markibx-connect/*` |
| `xwauth-id-gate.service` | 8051 | `/opt/xwauth-id-gate/.venv` | `/opt/xwauth-id-gate` | `xwgate` | (internal — the site-gate) |

All six units were **active** and every API health endpoint returned **HTTP 200** at
verification time (2026-07-17); host up 15 days. karaa-api reports
`{"status":"ok","version":"0.0.2","listings":15473,"listings_mode":"hybrid"}`.

ExecStart is a console entry / `python -m …cli --host 127.0.0.1 --port <port>` for
each (e.g. `karaa-api --host 127.0.0.1 --port 8132`;
`python -m exonware.mawtarx_api.cli … --port 8252`).

**venv sharing traps (asymmetric — do not assume symmetry):**
- `markibx-api` **and** `markibx-connect-api` share `/opt/markibx-api/.venv`. A
  markibx-core change is installed once but **both** services must be restarted.
- `mawtarx-api` and `mawtarx-connect-api` do **not** share a venv.
- `/opt/kara-api/.venv` (note: **`kara`**, no second `a`) is a **legacy leftover**,
  not a running service — but it still holds `libxwjson_abi.so`, which markibx-api
  and markibx-connect-api reference via `XWJSON_ABI_LIB=/opt/kara-api/libxwjson_abi.so`.
  karaa-api instead uses `/opt/karaa-api/libxwjson_abi.so`. Don't delete `/opt/kara-api`,
  and don't install updates there expecting them to reach the live site.

## The edge (Caddy) — domain → upstream

TLS-terminated public domains, from `/etc/caddy/Caddyfile`:

| Public | Serves | `/api/*` proxies to | Auth-gated? |
|---|---|---|---|
| `karaa.net`, `www.karaa.net` | SPA `/var/www/kara-web` | `/api/*`,`/docs*`,`/openapi.json` → karaa-api :8132 | **yes** (gate, `site=kara`) |
| `:8137` (IP preview) | same `kara_site` snippet | → karaa-api :8132 | **yes** (gate) |
| `mawtarx.com`, `www.mawtarx.com` | SPA `/var/www/mawtarx-web` | `/api/mawtarx/*` → :8252, `/api/mawtarx-connect/*` → :8253 | **yes** (gate, `site=mawtarx`) |
| `markibx.com`, `www.markibx.com` | SPA `/var/www/markibx-web` | `/api/markibx/*` → :8242, `/api/markibx-connect/*` → :8244 | **yes** (gate, `site=markibx`) |

- The **site-gate** (`xwauth-id-gate`, :8051) is wired as Caddy `forward_auth` in
  front of karaa.net / `:8137` / mawtarx.com **and markibx.com**. Requests to `/_gate/*`
  reverse-proxy straight to it. **markibx.com is now edge-gated too** — every `/api/markibx/*`
  route (incl. `/health`) 302s to `/_gate/login?site=markibx` (verified 2026-07-30; this
  reverses the earlier "public" note). So verify markibx deploys over **loopback on the box**
  (`curl http://127.0.0.1:8242/...`), not the public domain.
- **Gate passwords for `site=mawtarx` and `site=markibx` were (re)created and verified working
  2026-08-04** (per the box owner) — both logins succeed. The gate is a single shared
  access-password per site (`POST /_gate/login?site=<site>`, form fields `password` + `next`);
  it is NOT an app-level identity, so `require_admin` API routes can still 403 behind it. The
  passwords themselves are a secret — they are not stored in this repo.

## Config wiring (env files)

Non-secret keys that define how the pieces talk (from `/etc/<svc>.env`):

- **karaa-api** (`/etc/karaa-api.env`):
  - `KARAA_LISTINGS_MODE=hybrid` (verified 2026-07-16) → listings/search/mojaz/dealers/map
    are served from a **`HybridVehicleStore`** that federates karaa-api's **own** xwjson
    store with mawtarx-api's listings (local listing wins on id collision). Requires
    `MAWTARX_API_URL` set (it is); if unset it falls back to own-store-only. (`local` =
    own store only; `mawtarx` = pure proxy — neither is what prod runs.)
  - **Matched pair — deploy both or neither:** the hybrid half fetches via mawtarx-api's
    `GET /listings/snapshot`, and a miss **degrades silently to zero remote rows, nothing
    logged**. Shipping karaa-api against a mawtarx-api without that route served 2,560 of
    15,472 listings and looked healthy (2026-07-16).
  - **Restart gotcha:** the mawtarx half warms in a *background thread*, so for a few
    seconds after a `karaa-api` restart `search/listings` returns only the local rows
    (~2.5k) before the federated total (~15.5k) appears. A low count right after restart
    is warm-up, not data loss — re-query.
  - Proxy URLs it holds anyway: `MAWTARX_API_URL=…:8252/api/mawtarx/v1`,
    `MAWTARX_CONNECT_API_URL=…:8253/…`, `MARKIBX_CONNECT_API_URL=…:8244/…`
    (car-intelligence routes forward to mawtarx-api; see per-repo `CLAUDE.md`).
  - Store paths: `KARAA_STORE_FILE=/var/lib/karaa-api/data/listings.xwjson`,
    `KARAA_CATALOG_FILE=…/catalog.xwjson`, `KARAA_SYSTEM_DB_DIR=…/data/system`.
  - `XWJSON_ABI_LIB=/opt/karaa-api/libxwjson_abi.so`.
- **mawtarx-api** (`/etc/mawtarx-api.env`): holds `MAWTARX_MARKIBX_API_URL=…:8242/…`
  and a markibx token, though per the architecture mawtarx embeds **markibx core
  in-process** (the systemd description says so). Treat the configured URL as
  present-but-secondary; verify before assuming a call actually crosses HTTP.
- **markibx-api** / **markibx-connect-api**: `MARKIBX_CATALOG_FILE=/var/lib/markibx-api/data/catalog.xwjson`,
  `MARKIBX_SEED_ON_EMPTY=1`, both `XWJSON_ABI_LIB=/opt/kara-api/libxwjson_abi.so`.

## Access — sudo is scoped, not passwordless

`shukri`'s sudo is limited to three NOPASSWD wrappers (`sudo -l` is the source of truth,
re-check before trusting this — wrapper set verified 2026-07-21, `xw-backend-setup`
subcommands widened 2026-08-04): `xw-backend-ctl`
(start/stop/restart/status on the six units above plus any `karaa-*`/`markibx-*`/`mawtarx-*`
unit), `xw-backend-logs` (a `journalctl -u <unit> [args...]` wrapper), and `xw-backend-setup`
— which bootstraps new services (`ensure-user <name>`, `install-env <name> <src>`,
`install-unit <src>`, `daemon-reload`, `enable|start|stop|restart|status <unit>`; names must
start with `karaa-`/`markibx-`/`mawtarx-`) **and now also runs two scoped admin ops on
existing services** (added 2026-08-04, per the box owner):

- `xw-backend-setup admin-post <unit> <api-path> <json>` — POST to an admin API route on a
  running service, as that service. This is the **reconcile** path: it lets `shukri` arm
  reconcile without touching the root-600 env file. Preferred invocation:
  `sudo xw-backend-setup admin-post mawtarx-api /api/mawtarx/v1/admin/reconcile '{"enabled":true,"acknowledge_drop":true}'`.
- `xw-backend-setup check-mawtarx-token <unit>` — verify a service's mawtarx service token
  (Karaa↔Mawtarx wiring): `sudo xw-backend-setup check-mawtarx-token karaa-api`.

Plain `sudo cat`, `sudo -u <user>`, or any other `sudo <cmd>` still fails (password required,
none set). SSH access for `shukri` is active (confirmed 2026-08-04).

`ensure-user <name>` also grants `shukri` a default ACL (`rwx`, inherited by new files) on the
new `/var/lib/<name>` — confirmed via `getfacl`. The same ACL pattern already existed on at
least `/opt/mawtarx-api/.venv`, so **try a direct `pip install`/`ls` as `shukri` (no `sudo`)
before assuming you need root** — several `/opt/*/.venv` dirs are already writable this way;
an unverified one just gives `Permission denied`, which costs nothing to check.

**Real gaps** (the standing scoped-grant request lives in
[`../.claude/skills/deploy-vps/access-gaps.md`](../.claude/skills/deploy-vps/access-gaps.md);
run `~shukri/xw-access-preflight` on the box for the live GRANTED/BLOCKED picture):

- **No read or safe-incremental-write path for an *existing* service's env file** (e.g.
  `/etc/mawtarx-api.env`). `install-env` only *replaces* a file wholesale and is scoped to new
  services; no wrapper can `cat` one, and `/proc/<pid>/environ` is unreadable to `shukri`.
  Changing an arbitrary var still needs a human with real root — don't blind-overwrite guessing
  at contents. **Reconcile is the exception and is no longer blocked**: it is armed at runtime
  through the admin API via `sudo xw-backend-setup admin-post` (see Access above), not by editing
  `MAWTARX_RECONCILE_ENABLED`. (That env var blocked reconcile from 2026-07-29 until the
  `admin-post` wrapper landed 2026-08-04.)
- **No `mask`/`unmask`.** `xw-backend-ctl` allows start/stop/restart/… but not `mask`, and the
  `xw-service-watchdog@<svc>.timer` (below) is outside its unit allowlist — so you cannot keep a
  unit down. Any offline op (e.g. a store backfill) must finish inside the ~2-min watchdog
  window; align to just after a tick.

## Data layer — flat-file xwjson

Our stack stores everything in **xwjson flat files** under `/var/lib/<svc>/data/`
(via xwstorage + the `libxwjson_abi.so` native lib). Behaviour and tuning:
[`xwstorage-db-guide.md`](xwstorage-db-guide.md).

Nothing in this ecosystem uses a SQL database — the code that once could was deleted
2026-07-19. If you see `127.0.0.1:5432` on this box it is a `docker-proxy` for the
**co-tenant Supabase stack**, which belongs to an unrelated project.

At verification time the stores were **static snapshots**, not live-updating:

| File | Size | Last modified |
|---|---|---|
| `karaa-api/data/listings.xwjson` | ~2.1 MB | **Jun 30** (unchanged since) |
| `karaa-api/data/catalog.xwjson` | ~5.7 MB | Jun 10 |
| `mawtarx-api/data/mawtarx-data/` | — | Jun 29 |
| `markibx-api/data/markibx-data/` | — | Jun 28 |

Only the `…/data/system/` dirs (auth users, sessions) are fresh (Jul 16). mawtarx-api also
carries a `system.bak.premerge.20260714-124342/` backup dir from a Jul 14 merge. These
mtimes describe the **on-disk local files only**. Do **not** read karaa-api's static
~2.1 MB file as the size of what the site shows: in `hybrid` mode (see the karaa-api
config above) karaa-api's *served* listing set was **15,473** (verified 2026-07-17; it was
~10.2k on 2026-07-10 — the federated total grows without karaa-api's own file changing),
dominated by **mawtarx-api's** listings pulled over HTTP — karaa-api's own store is only
a few-thousand-row snapshot. So "seeded, not growing" applies to karaa-api's *own* store,
not to the federated total the homepage serves.

## Scraping — a systemd runner, NOT cron (don't read `/etc/cron.d` and conclude "off")

- **`mawtarx-scraper-runner` (systemd *service*) sweeps ~7 Saudi sources.** Live-verified
  actively sweeping **2026-07-30** (PID last restarted 07-29 05:00 — the box is shared and
  units get restarted/reverted, so re-verify: `systemctl is-active mawtarx-scraper-runner` +
  `sudo xw-backend-logs mawtarx-scraper-runner`). Latest full sweeps that day: saudisale ~4.7k,
  syarah ~3.9k, opensooq ~2.7k, sayarat ~2.3k, samaco 64. mawtarx holds **~19k active listings**
  (incl. 5.1k legacy dubizzle NOT in the sweep set). The runner logs `reconcile=True`, but that
  is only the *runner-side request* — the destructive act is server-side gated. As of 2026-08-04
  that server-side gate can be **armed by `shukri`** via
  `sudo xw-backend-setup admin-post mawtarx-api /api/mawtarx/v1/admin/reconcile '{"enabled":true,"acknowledge_drop":true}'`
  (no longer requires editing the root-600 `MAWTARX_RECONCILE_ENABLED`). Confirm it took, then
  watch the next full sweep: reconcile only fires on a complete, non-truncated `full` sweep.
- **It's a service, not a cron/timer** — `/etc/cron.d` holds only `e2scrub_all` +
  `exonware-security`, so a cron check finds nothing and mis-reads as "no scraping." The old
  Postgres `collect.py`/`daemon.py` path was deleted 2026-07-19; the runner
  (`python -m exonware.mawtarx_connect.runner`, from `feat/price-history-observed`) scrapes
  and POSTs batches to mawtarx-api's `/ingest/*`, keeping mawtarx-api the sole store writer.
- **haraj=0 / motory=0 every sweep is intentional gating**, not breakage (haraj WAF/partner
  deal; motory is a disabled stub) — they log no error, so a silent break looks identical.
- **The scrape output does NOT reach karaa.net** — karaa-api runs `listings_mode=local`, so
  the fresh ~18.5k listings benefit mawtarx.com only until karaa flips back to `hybrid`.

## Reliability & security bits

- **Watchdog:** `xw-service-watchdog@<svc>.timer` fires ~every 2 min for each of the
  five APIs — a liveness check that restarts any *inactive* unit (`is-active` fails → it
  runs `systemctl restart`). You can't stop it (no `mask`, see gaps above), so it also
  restarts a unit *you* stopped for an offline op — hence the 2-min-window rule.
- **Concurrent-agent deploys:** this box is shared by multiple agent sessions; one silently
  reverted a fresh deploy on 2026-07-29. An advisory single-writer lock (`~shukri/xw-deploy-lock`)
  now guards deploys — acquire it first per the `deploy-vps` skill's step 0.
- **CrowdSec** runs (`:6060`, `:8080` loopback) for intrusion detection; an
  `exonware-security` cron job is present.
- Postfix listens on loopback `:25` (local mail only).

## Co-tenants (NOT part of this ecosystem)

The box also runs several **unrelated** projects. They matter only because they
consume the same RAM/ports — none are part of karaa/mawtarx/markibx and none should
be assumed related:

- **Supabase** full docker stack (Postgres 17 on `:5432`/`:6543`, GoTrue, Storage,
  Realtime, Studio, PostgREST, imgproxy, Kong).
- **Appwrite** full docker stack (MariaDB, Redis, ~20 worker containers, Traefik on
  `:8300`/`:8301`).
- **Convex** (`:8500`–`:8502`), **PocketBase** (`:8090`).
- **`ethar-api`** (`/opt/ethar-api`, `:8232`) serving `etharaljawda.com` and the
  `:8237` preview via Caddy `ethar_site` — a separate product that happens to reuse
  the same xw* patterns.

## Deploying to this box

No CI/CD, no git on the server. Deploys are manual: build locally → tar the working
tree → scp → `pip install --force-reinstall --no-deps` into the right `/opt/*/.venv`
→ restart the right unit(s) → verify. The full, safety-checked procedure (and the
per-service traps) lives in the **`deploy-vps` skill**
(`.claude/skills/deploy-vps/SKILL.md`) — follow it rather than improvising. See
"Access" above for what needs `sudo` vs. what `shukri`'s ACL already covers.

## Ports: dev default vs. what this box runs (not drift — two environments)

Earlier notes called this "drift" and said 8130 was wrong. It isn't. **Each API's code
default is its dev port; this server passes an explicit `--port` two higher.** Both numbers
are correct in their own context — don't "fix" one to match the other.

| Service | Code default (local dev) | This box (explicit `--port`) |
|---|---|---|
| karaa-api | **8130** (`karaa_api/settings.py`) | **8132** |
| mawtarx-api | **8250** (`mawtarx_api/cli.py`) | **8252** |
| markibx-api | **8240** (`markibx_api/cli.py`) | **8242** |
| markibx-connect-api | — | 8244 |
| mawtarx-connect-api | — | 8253 |
| xwauth-id-gate | — | 8051 |

`ARCHITECTURE.md` lists the dev defaults (it maps the ecosystem, not this box). This file is
the authority for what the **server** runs. Verified 2026-07-17 via `ss -ltnp`.
