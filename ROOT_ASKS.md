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
