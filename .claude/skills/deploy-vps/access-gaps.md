# VPS access gaps — grants to request from root

`shukri` (the deploy identity) can install into venvs and restart services, but two
gaps blocked or slowed real work on 2026-07-29. Run `xw-access-preflight` on the box
for the live picture; this is the standing request to whoever holds root to close them.
Each is a small, scoped change — none needs blanket root for agents.

## Gap 1 — no safe way to change one env var (RECONCILE RESOLVED 2026-08-04; general case still open)

**✅ Reconcile is unblocked (2026-08-04).** The owner did not add an env-edit verb; instead
reconcile is now armed through the admin **API** (no env file touched):
```
sudo xw-backend-setup admin-post mawtarx-api /api/mawtarx/v1/admin/reconcile '{"enabled":true,"acknowledge_drop":true}'
```
Token check landed alongside it: `sudo xw-backend-setup check-mawtarx-token karaa-api`.

**Still open — the general case:** changing an *arbitrary* var in an existing
`/etc/<svc>.env` (anything without its own admin route). `shukri` still cannot read it
(`cat` → denied, `sudo cat` → password, `/proc/<pid>/environ` → denied), and
`xw-backend-setup install-env` *replaces* the whole file, so a blind full-file replace would
drop `XWJSON_ABI_LIB` etc. → outage.

**Requested grant (pick one):**
- **Preferred — a merge verb** in `xw-backend-setup`, root-side, so no secret is ever
  exposed to shukri:
  ```
  sudo xw-backend-setup set-env-var <name> <KEY> <VALUE>   # read existing, set one key, rewrite 640 root:<name>
  sudo xw-backend-setup unset-env-var <name> <KEY>
  ```
- Or a read verb: `sudo xw-backend-setup show-env <name>` (lets an agent round-trip
  the file itself). Weaker — exposes all vars — but unblocks.

## Gap 2 — no `mask` (forces watchdog-window gymnastics on every offline op)

**Symptom:** an offline op (renormalize backfill, data migration) needs the service
down for its duration, but `xw-service-watchdog@<svc>.timer` restarts any inactive
unit every 2 minutes, and `xw-backend-ctl` has no `mask`/`unmask` (and the watchdog
timer is outside its unit allowlist). Every offline op must be squeezed under 120 s
and timed to a watchdog tick — fragile, and impossible for anything genuinely slow.

**Requested grant:** add `mask|unmask` to `ALLOWED_CMDS` in `/usr/local/sbin/xw-backend-ctl`
(one word). Then: `stop → mask → <offline op, any duration> → unmask → start`.

## Gap 3 (optional) — make the deploy lock enforced, not advisory

`xw-deploy-lock` (skill step 0) is advisory; a session that ignores it can still
clobber a live deploy (this happened 2026-07-29). To enforce, have the root-owned
`xw-backend-ctl` refuse `restart`/`stop` unless the caller holds the lock (a few
lines checking `~shukri/.xw-deploy.lock.d`'s holder against a caller-supplied id).
Lower priority than 1–2.

## Not a gap

Venv writes (`/opt/*/.venv`) already carry a `shukri` ACL — deploys need no sudo there.
