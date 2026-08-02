# 013 — Root handoff: the ONLY steps that still need sudo (reconcile)

> **For whoever holds real root on `exonware-riyadh-01` (149.104.105.145).**
> This is the residue of the boss-checklist ([013-BOSS-CHECKLIST.md](013-BOSS-CHECKLIST.md))
> after everything a non-root agent could do was done. Read-only `curl` verification GETs are
> safe for anyone; the two steps below need root because they touch `/etc/*.env`, which the
> scoped `shukri`/`xw-backend-*` sudo cannot read or edit (verified 2026-08-02 via
> `xw-access-preflight`: `xw-backend-ctl` denies `set-env`/`edit-env`/`mask`, and
> `xw-backend-setup install-env` REPLACES the whole file instead of merging).

## Already done (do NOT repeat — context only)

- ✅ **pricing-7 in both venvs** — `/opt/mawtarx-api/.venv` (already was) and `/opt/karaa-api/.venv`
  (upgraded 5→7 on 2026-08-02). Both services restarted; karaa-api's 2,311 rows reflowed to
  `mawtarx-pricing-7`.
- ✅ **catalog-link backfill** — identity coverage ~0% → 96.4% (2026-07-31).
- ✅ **purge-synthetic** — 248 synthetic rows removed (2026-07-31).
- ✅ **reprice tooling** — `mawtarx reprice` CLI now exists; but on the live store the reprice is
  restart-driven (the service's own `PricingRefreshRunner` reprices stale buckets on restart), so
  **after step 1 below the corpus reprices itself — no separate reprice command needed.**

So the product is on pricing-7 everywhere; the one remaining defect is that **nothing expires
dead listings** — a third of every pool is cars that left the market weeks ago and are still
marked active (measured: 33% not seen in >14 days, 100% still active). That is what reconcile fixes.

---

## STEP 1 (root) — Arm reconcile on mawtarx-api

⚠️ **Supervised change.** Enabling this causes a **one-time ~30% drop in active listings** as the
backlog of departed ads expires. That is correct behaviour but looks identical to an outage —
**forewarn anyone watching karaa.net / mawtarx.com before you do it.** The count-collapse safety
guard will NOT block this drop (it's real data leaving, not a broken scrape — intended).

```bash
# 1. back up the env file first (root-owned)
cp -a /etc/mawtarx-api.env /etc/mawtarx-api.env.bak-$(date +%F)

# 2. add the flag WITHOUT dropping the other vars — append if absent, else set:
grep -q '^MAWTARX_RECONCILE_ENABLED=' /etc/mawtarx-api.env \
  && sed -i 's/^MAWTARX_RECONCILE_ENABLED=.*/MAWTARX_RECONCILE_ENABLED=1/' /etc/mawtarx-api.env \
  || echo 'MAWTARX_RECONCILE_ENABLED=1' >> /etc/mawtarx-api.env

# 3. confirm it's there and nothing else changed
diff /etc/mawtarx-api.env.bak-$(date +%F) /etc/mawtarx-api.env    # expect: only the one line

# 4. restart the service
systemctl restart mawtarx-api
```

**Precondition to respect:** only arm this once you trust the scrapers are running *full* sweeps
(the reconcile logic already refuses to expire on a partial/truncated/first-baseline sweep — the
safety layer is complete; the flag is the last gate). If sweeps are thin, disappeared-but-real
cars could be marked sold.

**What happens next, automatically:** on the next *full* sweep per source, ACTIVE listings whose
ad id is no longer present get marked SOLD/expired (retained as history, not deleted). Then the
write-time engine + background runner reprice the shrunken pools onto pricing-7.

### Verify (anyone, read-only)

```bash
# staleness should fall toward zero over the next full-sweep cycle:
/opt/mawtarx-api/.venv/bin/mawtarx pool-health --store /var/lib/mawtarx-api/data/system | grep -i stale
# and disappeared rows should now carry a delisted_at (were 0 before):
```

Done when: active-listing count drops ~30% once (recorded against the prediction), disappeared
rows are `inactive` + retained, pool-health staleness ≈ 0, and estimates reflect the smaller pools.

---

## STEP 2 (root, optional) — Verify karaa's estimation path has a token

Only if karaa listings still return `comparable_count: 0`. This does **not** flip karaa to
federated listings — karaa keeps serving its own 2,311 rows; this only makes the *price
estimation* path find comps.

```bash
# read the karaa env (root) and confirm the mawtarx service token is set + valid:
grep -E 'MAWTARX_API_(URL|TOKEN)' /etc/karaa-api.env
# then, as anyone, confirm the token is accepted (expect JSON, not 401):
curl -s -H "Authorization: Bearer <the token>" \
  https://mawtarx.com/api/mawtarx/v1/listings/snapshot | head -c 200
```

If the token 401s or is missing, set/replace `MAWTARX_API_TOKEN` in `/etc/karaa-api.env` (same
backup-then-edit pattern as step 1), `systemctl restart karaa-api`, then verify a real karaa
listing returns `comparable_count > 0`.

---

## After both steps

Update `repos/mawtarx/docs/vps-current-state.md` (reconcile now on; karaa pricing-7) and close
GitHub `Exonware/mawtarx#8` + the `#2` umbrella's reconcile line.
