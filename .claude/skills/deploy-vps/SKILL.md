---
name: deploy-vps
description: Deploy changes from the kara/karaa, mawtarx, or markibx repos to the exonware-riyadh-01 VPS, and verify the deploy worked. Use when the user asks to push, deploy, ship, or update one of these repos on the server, or asks whether a server-side change will break something.
---

# Deploy to exonware-riyadh-01

> **⚠️ THIS BOX IS DEV, NOT PRODUCTION** (confirmed by the owner 2026-07-31).
> `exonware-riyadh-01` / `149.104.105.145` (karaa.net, mawtarx.com, markibx.com) is the
> **development/staging** environment — not a customer-facing production deployment. Still be
> careful (it's shared by multiple agent sessions, holds the only convenient real-data corpus,
> and a bad deploy blocks other people's work), but do NOT reason about it as prod: a brief
> service stop for an offline data op is acceptable here, and "prod" language elsewhere in these
> docs means "this live dev box", not a separate production tier.

> **Companion doc:** `docs/vps-current-state.md` is the live-verified snapshot of
> how the box is actually wired right now (services, ports, venvs, env files,
> Caddy routes, data dirs). Read it for *what's running*; this skill is *how to
> ship to it*. It's a snapshot, not a spec — where it and the running server
> disagree, the server wins and the doc is stale, so re-verify live before
> relying on any specific number.

## Server access

```bash
KEY=~/.ssh/exonware_riyadh_shukri_rsa
ssh -i $KEY shukri@149.104.105.145
```

No CI/CD. No git on the server. Every deploy is: build locally → tar the working
tree → scp → extract into a fresh staging dir on the VPS → install into the right
venv → restart the right unit(s) → verify. **`sudo` is NOT passwordless** — it's
scoped to three wrappers (`xw-backend-ctl`, `xw-backend-logs`, `xw-backend-setup`);
see `vps-current-state.md`'s "Access" section for exactly what each covers and the
ACL shortcut that often avoids `sudo` entirely. Ignore the
`sudo: unable to resolve host exonware-riyadh-01` warning that prints on every
sudo call — it's a DNS quirk, not a failure; the command still runs.

## Service map — read this before touching anything

| Product | Repo dir (local) | systemd unit | venv (real one) | Port | Public domain | Env file |
|---|---|---|---|---|---|---|
| Karaa | `repos/kara-api` | `karaa-api.service` | `/opt/karaa-api/.venv` | 8132 | karaa.net | `/etc/karaa-api.env` |
| Karaa lib | `repos/kara` | *(imported by kara-api, not a service itself)* | — | — | — | — |
| markibx API | `repos/markibx-api` | `markibx-api.service` | `/opt/markibx-api/.venv` (**shared**) | 8242 | markibx.com | `/etc/markibx-api.env` |
| markibx connect | `repos/markibx-connect-api` | `markibx-connect-api.service` | `/opt/markibx-api/.venv` (**same venv as markibx-api**) | 8244 | markibx.com/api/markibx-connect | — |
| mawtarx API | `repos/mawtarx-api` | `mawtarx-api.service` | `/opt/mawtarx-api/.venv` | 8252 | mawtarx.com | `/etc/mawtarx-api.env` |
| mawtarx connect | `repos/mawtarx-connect-api` | `mawtarx-connect-api.service` | `/opt/mawtarx-connect-api/.venv` (**separate venv**, not shared with mawtarx-api) | 8253 | mawtarx.com/api/mawtarx-connect | — |
| markibx core | `repos/markibx` | *(library only)* | installed into **both** `/opt/markibx-api/.venv` and `/opt/mawtarx-api/.venv` | — | — | — |
| mawtarx core | `repos/mawtarx` | *(library only)* | installed into `/opt/mawtarx-api/.venv` only | — | — | — |

**Traps that will bite you if you skip this table:**

- **`/opt/kara-api` vs `/opt/karaa-api` — two different directories exist.** Only
  `karaa-api.service` runs (confirm with `systemctl list-units | grep -i kara`
  — there is no `kara-api.service`). `/opt/kara-api/.venv` is a legacy leftover
  from before the karaa rename; it still holds `libxwjson_abi.so`, which
  `mawtarx-api.service` and `markibx-api.service` both reference via
  `XWJSON_ABI_LIB=/opt/kara-api/libxwjson_abi.so` in their env files — so don't
  delete it. But never install a package update there expecting it to reach
  the live site; always target `/opt/karaa-api/.venv`.
- **markibx-api and markibx-connect-api share one venv.** Push `markibx` core
  changes there once, but restart *both* services.
- **mawtarx-api and mawtarx-connect-api do NOT share a venv**, unlike the
  markibx pair. Don't assume symmetry.
- **`mawtarx` (core) depends on `markibx` (core)**, and both mawtarx-api and
  markibx-api embed markibx in-process. If you change `markibx/src/exonware/markibx/`,
  it needs pushing to **both** venvs it lives in, not just the one for the repo
  you think you're changing. Check what's actually installed before assuming
  it's current:
  ```bash
  /opt/<venv>/.venv/bin/pip show exonware-markibx   # version (often unhelpful, doesn't bump on every change)
  /opt/<venv>/.venv/bin/python -c "import exonware.markibx as m, os; print(sorted(os.listdir(os.path.dirname(m.__file__))))"
  # compare the file list against src/exonware/markibx/ locally — missing files = stale install
  ```
- **`kara-api` calls `mawtarx-api` over HTTP, not in-process** (`mawtarx_client.py`,
  proxied routes in `routes/mawtarx_proxy.py`). `/pricing`, `/deals`, `/catalog`,
  `/connectors` are *always* proxied through to mawtarx-api regardless of
  `KARAA_LISTINGS_MODE`. **`KARAA_LISTINGS_MODE` read `local` on 2026-07-18** (live, via
  `/api/karaa/v1/health`, which reports `listings_mode`) — but this note said
  `hybrid` as of 2026-07-10 and nobody has confirmed the change was intended.
  In `local` the site serves ONLY karaa's own rows (2.5k) and none of mawtarx's
  (~12.9k), so if listing counts look low, check this FIRST. Always re-read
  `health` rather than trusting either value here — so `/search/listings`, `/listings/{id}`,
  `/mojaz/{id}`, `/dealers`, `/makers`, `/map/availability` are served from
  karaa-api's **`HybridVehicleStore`**, which federates its own xwjson store with
  mawtarx-api's listings pulled over HTTP (`MAWTARX_API_URL`). Net: mawtarx-api
  being up affects karaa.net's *listing counts* too, not just the intelligence
  routes — if you deploy mawtarx-api, re-check karaa-api. **Restart trap:** the
  mawtarx half warms in a background thread, so `/search/listings` shows only the
  few-hundred local rows for a few seconds post-restart before the ~10k federated
  total appears (see verify step below). `local` = own store only; `mawtarx` =
  pure proxy — prod is neither.
- **There's an old shared script pair** —
  `markibx-api/scripts/vps-markibx-mawtarx-deploy/{pack-bundle.sh,remote-install.sh}`
  — that bundles and reinstalls all 8 packages (markibx, markibx-connect,
  markibx-api, markibx-connect-api, mawtarx, mawtarx-connect, mawtarx-api,
  mawtarx-connect-api) in one shot, stopping all four services unconditionally
  before it even builds anything. It's all-or-nothing and has no pre-restart
  safety check — a broken `pyproject.toml` in any one of the 8 leaves every
  service down until manually fixed. Prefer the manual per-repo procedure
  below for anything short of a full-stack release; it's slower but each step
  is independently verifiable and nothing stops until the replacement is known
  to import cleanly.

## Deploy procedure (do this for every repo you touch)

### 0. Acquire the single-writer deploy lock — BEFORE anything else

Box is shared by multiple agent sessions; one silently reverted another's live deploy
(see `vps-current-state.md`). **Hold the lock install-through-verify** so no other
session installs/restarts underneath you.

```bash
KEY=~/.ssh/exonware_riyadh_shukri_rsa
ssh -i $KEY shukri@149.104.105.145 '/home/shukri/xw-deploy-lock acquire <session-id> "deploy <repo>"'
# 0=held. 1=DENIED (someone's mid-deploy) → STOP; `xw-deploy-lock status` shows who.
# Don't `break` a live lock — it auto-expires after 30 min if that session died.
```

Advisory (root-owned `xw-backend-ctl` can't enforce it) — works only if every agent does
this step. Release in Cleanup. Missing on the box? `scp xw-deploy-lock.sh` up + `chmod +x`.

If the task's *last* step needs config beyond a venv install/restart (an env var, a
`mask`), run `~shukri/xw-access-preflight` first — GRANTED/BLOCKED up front so you scope it
right (or hand the blocked step to a human) instead of dying at the wall; gaps + grant
requests in [`access-gaps.md`](access-gaps.md).

### 0b. Know what you're about to ship

```bash
cd repos/<repo>
git status --porcelain     # uncommitted changes ship too — tar is of the working tree, not git archive
git log --oneline -3       # what's already committed that isn't on the server yet
```

### 1. Build-test locally, before touching the server

This is the single most valuable step — it catches a broken `pyproject.toml`
or import error while the cost of being wrong is zero (nothing on the server
has been touched yet).

```bash
cd repos/<repo>
rm -rf /tmp/build-check
python3 -m venv /tmp/build-check >/dev/null 2>&1
/tmp/build-check/bin/pip install --quiet hatchling >/dev/null 2>&1
/tmp/build-check/bin/pip install --no-deps . 2>&1 | tail -15
rm -rf /tmp/build-check
```

If it doesn't say `Successfully installed`, stop — do not proceed to the
server. (This caught a corrupted `[project.optional-dependencies]` block in
`mawtarx/pyproject.toml` that would otherwise have stopped all four
markibx/mawtarx services mid-deploy with no way back but a manual fix.)

If the repo bundles non-`.py` data (e.g. `data/*.json` vocab files), also
check it lands in the wheel — `hatchling` includes everything under the
`packages` path by default regardless of `.gitignore`, but verify once per repo:

```bash
python3 -m venv /tmp/wheel-check >/dev/null 2>&1
/tmp/wheel-check/bin/pip install --quiet hatchling >/dev/null 2>&1
/tmp/wheel-check/bin/pip wheel --no-deps -w /tmp/wheel-out . 2>&1 | tail -5
unzip -l /tmp/wheel-out/*.whl | grep -i <expected-file>
rm -rf /tmp/wheel-check /tmp/wheel-out
```

### 1b. Pre-flight — probe the TARGET venv (read-only), before any write

The local build-test proves the wheel *builds*; it does NOT prove the code *imports against what
the prod venv actually carries*. Do a read-only import probe against **every** venv you'll install
into, while nothing has been overwritten and a failure costs zero:

```bash
ssh -i ~/.ssh/exonware_riyadh_shukri_rsa shukri@149.104.105.145 '
XWJSON_ABI_LIB=/opt/kara-api/libxwjson_abi.so XWBASE_ALLOW_GIL=1 \
  /opt/<target-venv>/.venv/bin/python -c "from exonware.<pkg_api>.app import create_app; create_app(); print(\"probe OK\")"
'
```

(`XWBASE_ALLOW_GIL=1` replicates what the systemd units set — without it xwbase refuses to build
the app on a GIL Python and you get a false failure.)

- **A drifted `main` = a coordinated multi-package release, not a one-package deploy.** If the repo
  renamed/split a module or gained a dep since the last deploy, the target venv is probably missing
  or holds a *stale build* of a shared lib — and **the version string won't reveal it** (same
  `0.0.1.x`, older bytes — the `pip show` version does not bump on every change). Probe surfaces
  it as an `ImportError` in one call; guessing surfaces it as a live half-deployed venv.
- **Probe every service sharing the target venv, not just the one you're shipping.** markibx-api
  and markibx-connect-api share `/opt/markibx-api/.venv` — a lib you bump for one must import for
  both before you restart either.
- If a shared lib is stale, stage *it* too (proper: `pip install` the built wheel; last resort:
  align from a sibling venv that already runs this era of code) and re-probe until every app on the
  venv imports — THEN proceed.

Cost of skipping this (2026-07-28): a markibx-api deploy that built fine locally turned into a
live multi-package rabbit hole — `main` needed a newer `xwbase`/`xwbase-media` than
`/opt/markibx-api/.venv` held, discovered only *after* force-reinstalling, with the running
service one watchdog-restart away from crashing markibx.com.

### 2. Tar the whole repo, not just `src/`

Tar `pyproject.toml`, `README.md`, and `src/` together so `pip install
<dir>` has everything it needs — don't rely on a stale `/tmp/<repo>` on the
server already having `pyproject.toml` from a previous run.

```bash
cd repos/<repo>
tar -czf /tmp/<repo>-src.tar.gz --exclude="__pycache__" --exclude=".git" --exclude=".venv" pyproject.toml README.md src
scp -i ~/.ssh/exonware_riyadh_shukri_rsa /tmp/<repo>-src.tar.gz shukri@149.104.105.145:/tmp/
```

### 2b. ⚠️ A watchdog timer can restart the service mid-deploy

The "install now, restart later" flow below is **not** atomic: an independent
systemd watchdog restarts these units on its own schedule. Verified the hard way
on 2026-07-18 — between `pip install` and the sanity check, the watchdog
restarted `karaa-api` onto half-deployed code (new kara-api, stale markibx), it
crashed on an ImportError, and `Restart=on-failure` recovered it ~15s later once
the missing package landed.

Two consequences:

- **Install every package a repo needs in ONE ssh call**, before anything can
  restart. Don't install app code in one step and its updated library in
  another — that window is a live crash.
- **Do not rely on a service staying stopped.** Any "stop it, do X offline,
  start it" procedure (e.g. an offline data migration) can end up with the
  service running concurrently against the same files. The watchdog
  (`xw-service-watchdog@<svc>.timer`) fires **every 2 minutes** and restarts any
  inactive unit. **You cannot `mask` around it**: `xw-backend-ctl` allows
  start/stop/restart/… but NOT `mask`, and the watchdog timer's own name
  (`xw-service-watchdog@…`) is outside the wrapper's unit allowlist, so you can't
  stop it either (verified 2026-07-29). So an offline op MUST fit inside one
  2-minute window: align to just after a watchdog tick (they fire at even-minute
  `:09`) and finish well under 120 s — e.g. the mawtarx renormalize backfill
  opens the store in `batch` durability so it's one ~20 s write, not per-row.
  (2026-08-03: a 2m05 relink overran the window and the restart dropped ~900
  links — chase any long op with a no-`--relink` top-up. A maintenance-flag
  patch that lets `touch /var/tmp/xw-maintenance-<svc>` pause the watchdog ≤15
  min is committed in markibx-api 3596357 but awaits root install —
  markibx-api#2 / `ROOT_ASKS.md`; until it lands, the window rule above stands.)
  This watchdog is a *systemd* restarter and is SEPARATE from the step-0 deploy
  lock, which guards against *other agent sessions*; you need both.

### 3. Extract into a fresh dir on the server, install, but don't restart yet

```bash
ssh -i ~/.ssh/exonware_riyadh_shukri_rsa shukri@149.104.105.145 '
rm -rf /tmp/<repo>-deploy
mkdir -p /tmp/<repo>-deploy
tar -xzf /tmp/<repo>-src.tar.gz -C /tmp/<repo>-deploy
/opt/<correct-venv>/.venv/bin/pip install /tmp/<repo>-deploy --force-reinstall --no-deps
'
```

No `sudo` needed — `shukri` carries a direct ACL on these venv dirs (confirmed on
`/opt/mawtarx-api/.venv`; `Permission denied` on one that hasn't been granted yet is
a real gap to raise, not something `sudo` can route around here — `/opt/kara-api/.venv`
is partly root-owned, see `ROOT_ASKS.md`). Use the service
map above to get `<correct-venv>` right — this is where the `/opt/kara-api` vs
`/opt/karaa-api` mistake happens.

⚠️ `--force-reinstall` (and `pip uninstall`) only touch files in the dist's RECORD —
files ever hand-copied into a venv survive both and keep shadowing the shipped package
(2026-08-03: both venvs served 13 retired markibx gen files, registry 5,270 vs seed
5,257). When a venv may carry hand-copied history, use the clean-reinstall wrapper
instead: `~shukri/bin/xw-venv-reinstall <venv> <dist> <pkg-relpath> <wheel>`
(source: markibx-api `scripts/vps-markibx-mawtarx-deploy/xw-venv-reinstall.sh` —
uninstall + purge the import dir + wheel install). Verify after any suspect deploy by
comparing an installed-artifact count against the source of truth (e.g. gen count).

### 4. Pre-restart sanity check — import it before you restart it

The old process is still serving traffic at this point; a failure here costs
nothing. Set the same env vars the real systemd unit sets. You can no longer
`sudo cat /etc/<service>.env` to check them (see `vps-current-state.md`'s
"Access" section) — use its "Config wiring" table for the known ones
(`XWJSON_ABI_LIB` etc. — several services need it to import `xwstorage`/`xwjson`
at all), or ask someone with root for one that isn't documented there:

```bash
ssh -i ~/.ssh/exonware_riyadh_shukri_rsa shukri@149.104.105.145 '
XWJSON_ABI_LIB=/opt/kara-api/libxwjson_abi.so /opt/<venv>/.venv/bin/python -c "
import exonware.<package>
from exonware.<package_api>.app import create_app
app = create_app()
print(\"app builds OK\")
"
'
```

For a core library change (markibx/mawtarx), also assert the new symbols
exist (`hasattr(...)`, or import the new function/constant directly) — a
successful import doesn't prove the new code is actually there if the wheel
silently didn't bundle a file.

If this fails, fix it and re-run steps 1–4. **Do not restart the service on a
failing check.**

### 5. Restart, then verify from the inside

```bash
ssh -i ~/.ssh/exonware_riyadh_shukri_rsa shukri@149.104.105.145 '
sudo xw-backend-ctl restart <service>     # restart every service sharing the venv, not just one
sleep 2
sudo xw-backend-ctl status <service>
curl -s http://127.0.0.1:<port>/api/<prefix>/v1/health
sudo xw-backend-logs <service> --since "2 minutes ago" --no-pager | grep -iE "error|traceback|exception"
'
```

Then exercise the actual code path that changed, not just `/health` — hit the
new route, or a route that internally calls the new method, and check the
response body has real data, not just a 200:

```bash
curl -s "http://127.0.0.1:<port>/api/<prefix>/v1/<changed-route>"
```

**karaa-api specifically:** its `hybrid` store warms the mawtarx half in a
background thread, so `/search/listings?limit=1` returns a total of only a few
hundred (local rows) for the first few seconds after restart, then jumps to ~10k
once the mawtarx snapshot loads. Wait and re-query before concluding the deploy
dropped listings — a low count immediately post-restart is the warm-up, not a
regression. (`health` reports `listings_mode` + a `listings` count you can sanity-check.)

### 6. Verify from the outside

Confirm it's reachable over the real domain, through Caddy/TLS/DNS — not just
loopback on the box:

```bash
curl -s https://<domain>/api/<prefix>/v1/health
```

(`karaa.net`/`mawtarx.com` are gated by the xwauth-id site-gate via
`forward_auth`; `markibx.com`'s `/api/*` routes are NOT gated at the Caddy
level — the app gates its own console instead — so `curl` works there
directly without a session.)

### 7. Check downstream dependents

If you changed `mawtarx-api` or `markibx-api`, re-check anything that proxies
to it. `karaa-api`'s `/catalog`, `/connectors`, `/providers`, `/pricing`,
`/deals` always forward to mawtarx-api — diff the proxied response against
hitting mawtarx-api directly to prove it's really forwarding fresh data, not
serving something stale:

```bash
diff <(curl -s http://127.0.0.1:8132/api/karaa/v1/catalog/stats) \
     <(curl -s http://127.0.0.1:8252/api/mawtarx/v1/catalog/stats) && echo MATCH
```

### 8. Before treating any surprising data as a regression, check mtimes

If a stats/count endpoint looks smaller or different than expected after a
restart, don't assume the deploy caused it — check whether the underlying
data file's mtime predates your restart:

```bash
ls -la /var/lib/<service>/data/... 2>&1   # try without sudo first — ACL often covers this
```

A file untouched since before you started is not something you broke.

## Standing up a brand-new service (not updating an existing one)

Different flow — `xw-backend-setup` only bootstraps NEW services (unit/user name must start
`karaa-`/`markibx-`/`mawtarx-`):

```bash
sudo xw-backend-setup ensure-user <name>       # creates the user + /var/lib/<name>,
                                                # and grants shukri an ACL on it (rwx, inherited)
# build the venv directly as shukri, no sudo:
python3 -m venv /var/lib/<name>/venv
/var/lib/<name>/venv/bin/pip install --find-links=<local wheelhouse> <package>
# write .service/.timer under ~/ or /tmp, then:
sudo xw-backend-setup install-env <name> <src-env-file>
sudo xw-backend-setup install-unit <src-unit-file>
sudo xw-backend-setup daemon-reload
sudo xw-backend-setup enable <unit>
sudo xw-backend-setup start <unit>
```

`User=` in the unit must be `<name>`, never `root`. **A fresh venv has none of the
`exonware-*` packages an existing `/opt/*/.venv` already carries** — none are on public
PyPI, so build the whole local dependency chain as wheels from `repos/` (one `pip wheel
--no-deps -w <wheelhouse> <repo-path>` call per package; `pip install
--find-links=<wheelhouse> <top-level-package>` then resolves the graph) and ship them
together — public deps (`fastapi`, `httpx`, etc.) still resolve from PyPI normally
alongside `--find-links`. Two real gaps to expect: `tomli_w` (xwsystem's TOML
serializer) and `httpx` (xwapi's service client) are both imported eagerly by code that
isn't supposed to require them just to *import* the package — install them explicitly
rather than assuming a clean build means a clean import.

For a one-off command as the new service's user (e.g. proving a dry-run before trusting
the real unit), `sudo -u <name> <cmd>` does **not** work under the scoped sudo model.
Wrap it in a small oneshot `.service` (`User=<name>`, `ExecStart=<cmd>`), `install-unit`
+ `start` it, then read the result with `xw-backend-logs`/`status`.

## Cleanup

**Release the deploy lock (step 0) — only after the deploy is fully verified:**

```bash
ssh -i $KEY shukri@149.104.105.145 '/home/shukri/xw-deploy-lock release <your-session-id>'
rm -f /tmp/<repo>-src.tar.gz   # local scratch tarball
```

Release only when you're done touching the box; holding it through verification is
the point. If you abandon a deploy, release anyway (or let the 30-min TTL do it).

(Leave the `/tmp/<repo>-deploy` staging dir on the server — harmless, and
useful for the next person diagnosing what actually got shipped.)
