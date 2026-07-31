# 013 — Boss-runnable prod-freshness checklist (needs real root)

> **STATUS 2026-07-31 (box is DEV — see [[vps-is-dev-not-prod]]):**
> - ✅ **Step 2 (catalog-link backfill) DONE** — ran on the dev store via `shukri`'s venv+store ACL
>   inside a watchdog window. Identity coverage **~0% → 96.4%** (`unknown_identity` 697/19,354 per
>   `pool-health`). This is #005/#14 now real on the existing corpus.
> - ✅ **Step 3 (purge-synthetic) DONE** — 248 `source:synthetic` rows deleted (19,602 → 19,354);
>   first-party rows untouched. Backup kept: `collections/listings.xwjson.bak-preop-20260731`.
> - ⛔ **Steps 1/4/5/6 still gated** — `/etc/mawtarx-api.env` is **NOT readable by `shukri`**
>   (verified), so reconcile-on (5) and env checks (6) genuinely need root. Step 1 (pricing-7 into
>   both venvs) is a separate build/deploy; step 4 (re-price) rides on the sweeps once 1+5 land.
> - **Lesson:** catalog-link takes ~103s — it barely fits the 2-min watchdog window and squeezed a
>   chained purge out on the first attempt (purge flush didn't land; re-ran purge alone, ~24s). Run
>   heavy ops ONE per window, and set a generous **local** ssh timeout (the remote keeps running if
>   your view times out).


> Deliverable for ticket 013. Every step here needs **real root** on the VPS (the scoped
> `shukri`/`xw-backend-*` sudo can't edit existing service env files and has no `mask` to hold a
> unit past the ~2-min watchdog). Hand this to whoever holds root. Read-only verification GETs are
> safe for anyone. Steps are ordered so each is verifiable before the next.
>
> **Data-safety invariant (load-bearing):** karaa users must see ONLY karaa's own listings +
> mawtarx *price estimations* — never mawtarx's raw listing corpus. Nothing here flips karaa to
> hybrid/federated listings. Step 6 only makes the **estimation** path return real comps.

Paths assumed (confirm with `systemctl cat mawtarx-api karaa-api` before running):
- mawtarx-api venv `/opt/mawtarx-api/.venv`, env `/etc/mawtarx-api.env`, store dir
  `/var/lib/mawtarx-api/data/system` (xwstorage-db directory store).
- karaa-api venv `/opt/karaa-api/.venv`, env `/etc/karaa-api.env`.
- **Back up the store dir before any write step** (`cp -a /var/lib/mawtarx-api/data/system{,.bak-$(date +%F)}`).

---

## 0. Pre-flight (read-only — safe now, no root)

```bash
curl -s https://mawtarx.com/api/mawtarx/v1/valuation | grep -o 'mawtarx-pricing-[0-9]'   # expect: pricing-5 (stale)
curl -s https://mawtarx.com/api/mawtarx/v1/health                                        # expect: {"status":"ok"}
```
Record the starting pricing version. Success at the end = this reads `pricing-7`.

---

## 1. Deploy pricing-7 into BOTH venvs

karaa embeds mawtarx **in-process** — upgrading only mawtarx-api leaves karaa serving pricing-5
estimates. Upgrade both, restart both.

```bash
# in each venv, install the pricing-7 mawtarx (+ markibx spine it depends on)
/opt/mawtarx-api/.venv/bin/pip install -U <mawtarx pricing-7 wheel/sdist>  <markibx wheel>
/opt/karaa-api/.venv/bin/pip  install -U <mawtarx pricing-7 wheel/sdist>  <markibx wheel>
systemctl restart mawtarx-api karaa-api
```
Verify: `curl -s https://mawtarx.com/api/mawtarx/v1/valuation | grep pricing-7` → present.

## 2. Catalog-link backfill of the existing ~19k rows  ← makes wayfinder #005/#14 real

The #14 deploy (already live) only links **new** sweeps. Existing ~19k rows still have empty
`catalog_car_id`. Run the one-time whole-store backfill from the upgraded venv:

```bash
# DRY-CHECK first (relink=off, reports link_rate without touching unmatched):
/opt/mawtarx-api/.venv/bin/mawtarx catalog-link --store /var/lib/mawtarx-api/data/system --market GCC
```
Reads as: `catalog-link: N newly linked, M already linked, K unmatched (link_rate XX%)`.
It coalesces writes to one flush per collection (batch durability) — safe on the prod dir store.
Expect link_rate ~80%+; the `top unmatched` list is the curation queue for ticket 010.
**Restart mawtarx-api after** so the in-memory store reloads the linked rows.

## 3. Purge synthetic / fixture rows (wayfinder #009)

~348 `zz*`/`synthetic` test rows pollute the live corpus. **Dry-run first**, inspect `by_source`,
then apply. `source=="karaa"` (the field DEFAULT = real first-party rows) is NOT purged unless you
add `--include-default-source` — do **not** add it here.

```bash
/opt/mawtarx-api/.venv/bin/mawtarx purge-synthetic --store /var/lib/mawtarx-api/data/system            # dry-run
/opt/mawtarx-api/.venv/bin/mawtarx purge-synthetic --store /var/lib/mawtarx-api/data/system --apply    # delete
systemctl restart mawtarx-api
```

## 4. Re-price sweep (flush pricing-5 → pricing-7 across the corpus)

Estimates are **write-time** — a deploy alone does not re-price stored rows. Force a recompute
across the corpus. Simplest correct trigger: run one full scraper sweep (the runner re-writes rows
through the pricing-7 engine), OR the reconcile/refresh pass once step 5 is armed. Verify a sample
listing's `intelligence.method`/version reflects pricing-7 after the pass.

## 5. Arm reconcile (server-side gate)

The scraper runner already *requests* `reconcile=True`; it's a no-op until the server gate is on.

```bash
# in /etc/mawtarx-api.env
MAWTARX_RECONCILE_ENABLED=1
systemctl restart mawtarx-api
```
Only arm this once you trust sweeps are covering full sources (partial-sweep guard exists, but the
gate is the last safety). This is what marks disappeared listings sold.

## 6. Make karaa's `local`-mode estimation path return real comps (NOT hybrid listings)

Goal: a karaa listing's intelligence returns `comparable_count > 0` (today `method=unavailable`).
This is the **price-estimation** path only — karaa still serves its own 2,311 listings.

Confirm, in order:
1. Deployed karaa build contains the `MawtarxComparablesPool` local-mode wiring (`state.py:304-315`).
2. `/etc/karaa-api.env` has `MAWTARX_API_URL` + `MAWTARX_API_TOKEN` set and the token does **not** 401:
   ```bash
   curl -s -H "Authorization: Bearer $MAWTARX_API_TOKEN" \
     https://mawtarx.com/api/mawtarx/v1/listings/snapshot | head -c 200   # expect JSON, not 401
   ```
3. mawtarx-api serves the real ~19k snapshot (post-purge count).
4. Restart karaa-api; then verify a real listing returns comps:
   ```bash
   curl -s https://karaa.net/<a real listing intelligence route> | grep -o '"comparable_count":[0-9]*'
   ```
   Success = `comparable_count > 0`.

---

## Done when
- `valuation` reads `pricing-7` (step 0/1),
- catalog-link backfill reports a non-trivial link_rate and rows carry `catalog_car_id` (step 2),
- synthetic rows gone, first-party rows intact (step 3),
- reconcile armed (step 5),
- a karaa listing returns `comparable_count > 0` (step 6).

Then update `docs/vps-current-state.md` pricing-freshness + karaa-mode lines and close 013.
