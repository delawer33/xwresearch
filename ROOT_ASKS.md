# ROOT_ASKS — actions needing root on exonware-riyadh-01 (149.104.105.145)

Standing file: agents append asks here when a task hits the root wall; whoever has root
executes and checks them off (leave the entry, mark done + date). Everything an entry
needs must already be **staged on the box** — the root session should be copy-paste only.

## OPEN — 2026-08-03: watchdog maintenance flag + purge stale markibx (markibx-api#2)

Both artifacts are committed on markibx-api `main` (3596357) and **already staged on the
box**. As root, run:

```bash
# 1. Install the patched watchdog (adds /var/tmp/xw-maintenance-<svc> flag support —
#    lets store ops pause the 2-min auto-restart for up to 15 min, auto-expiring).
#    Patched source is staged at ~shukri/bin/, diff vs live: only the flag block added.
cp /home/shukri/bin/xw-service-watchdog-patched.sh /opt/xw-deploy/xw-service-watchdog.sh
chmod 755 /opt/xw-deploy/xw-service-watchdog.sh && chown root:root /opt/xw-deploy/xw-service-watchdog.sh

# 2. Purge the ancient root-owned pre-spine markibx copy from kara-api's venv
#    (kara-api uses HTTP transport to markibx-api — this dir is dead code that would
#    shadow any future in-process import with a 2-generation-old catalog).
rm -rf /opt/kara-api/.venv/lib/python3.12/site-packages/exonware/markibx

# 3. Cleanup: a one-shot unit file was staged for this but never installed
#    (agent-side permission gate) — remove the stager copy:
rm -f /home/shukri/mawtarx-maintenance.service
```

Verify (any user):

```bash
grep -c MAINT_FLAG /opt/xw-deploy/xw-service-watchdog.sh   # expect >= 1 (patched)
ls /opt/kara-api/.venv/lib/python3.12/site-packages/exonware/markibx 2>&1  # expect: No such file
journalctl -t xw-service-watchdog -n 3 --no-pager          # watchdog still logging "ok"
```

Why: on 2026-08-03 a 2m05 `catalog-link --relink` overran the watchdog's ~110s window;
the auto-restart flushed mid-op and dropped ~900 links (recovered via top-up pass —
see `repos/mawtarx/docs/runbook-catalog-relink.md`). The flag removes that whole class
of incident.

## FYI for the root owner — sudoers observation (no action requested)

`sudo xw-backend-setup install-unit` accepts **arbitrary unit content** as long as the
filename matches `karaa-*|markibx-*|mawtarx-*.service|.timer` — a oneshot `ExecStart`
runs as root, so the wrapper's "does NOT grant general root" claim doesn't hold in
practice. Fine on a trusted dev box; worth knowing before this pattern is copied to a
real prod box. (An agent declined to exploit it without sign-off; a permission
classifier independently blocked it too.)

## 2026-08-10 — mawtarx-api + markibx-api refuse to boot without a real JWT secret

Blocks: deploying issue #36 point 3 (auth gates). Until these are set, both services will
**exit at startup** with `InsecureConfigError`, and mawtarx-api's admin plane answers 503.
That is the intended behaviour — the shipped placeholder key is committed and public, so
anyone holding it can mint a `role: "admin"` token and forge signed thumbnail URLs.
karaa's deploy already generates its own secret (`remote-karaa-finish.sh:48-61`); these
two never had an equivalent step.

Run as root (generates a fresh 32-byte secret per service, only if absent):

```bash
for svc in mawtarx markibx; do
  ENV_FILE=/etc/${svc}-api.env
  UP=$(echo "$svc" | tr a-z A-Z)
  grep -qE "^${UP}_JWT_SECRET=" "$ENV_FILE" || \
    echo "${UP}_JWT_SECRET=$(openssl rand -hex 32)" >> "$ENV_FILE"
  grep -qE "^${UP}_ADMIN_TOKEN=" "$ENV_FILE" || \
    echo "${UP}_ADMIN_TOKEN=$(openssl rand -hex 32)" >> "$ENV_FILE"
done
systemctl restart mawtarx-api markibx-api
```

`MARKIBX_JWT_SECRET` is shared: markibx-connect-api validates operator JWTs against the
same variable, so if that service has its own env file it needs the identical value —
otherwise its connector-admin plane stays 503.

Verify (any user):

```bash
systemctl is-active mawtarx-api markibx-api                    # expect: active active
curl -s localhost:8252/api/mawtarx/v1/health | head -c 200     # expect: ok
curl -so /dev/null -w '%{http_code}\n' localhost:8252/api/mawtarx/v1/admin/reconcile
                                                               # expect: 401 (NOT 503, NOT 200)
```

A 503 there means `MAWTARX_ADMIN_TOKEN` is still unset; a 200 means an
`MAWTARX_ALLOW_OPEN_ADMIN` escape hatch is set on a live box and should be removed.

Also needed, separately: kara-api's mawtarx service token must carry the
`listings.write` scope, or its `HybridVehicleStore` upsert path gets 403 on
`POST/PATCH /listings`. Re-mint via
`sudo xw-backend-setup admin-post mawtarx-api /api/mawtarx/v1/service/tokens/issue \
  '{"subject_id":"karaa","name":"karaa","scopes":["listings.read","catalog.read","listings.write"],"credits":100000}'`
and put the returned token in kara-api's `MAWTARX_API_TOKEN`.
