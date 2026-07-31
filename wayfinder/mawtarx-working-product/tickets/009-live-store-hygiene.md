# 009 — Live-store hygiene: purge synthetic rows + guard re-pollution

- Type: `wayfinder:task` (AFK where safe; prod change is HITL via deploy-vps)
- Status: open
- Blocked by: —
- Assignee: —

## Question

~348 synthetic test rows (`zzperf`, `zzsold`, `zztestsrc`, `karaa`, …) sit inside the
live-shaped store, polluting counts, comps, and any "coverage" claim. Decide how the prod corpus
is guaranteed clean real data: a one-off purge of known synthetic `source` ids + an ingest guard
that keeps test sources out of the live store. Nothing to design — the decision is scope + the
safe execution path (service-down window, watchdog, per `renormalize`/backfill runbook).

Resolve to: the purge list + the standing guard + a safe execution plan (unblocks trustable
coverage/pricing measurements in 002/003/004).

## IMPLEMENTED (purge only) 2026-07-31 (branch `feat/mx-14-catalog-link-ingest`, unpushed; Exonware/mawtarx#14)

- **`mawtarx purge-synthetic`** + `hygiene.py` (`purge_synthetic_listings`, `is_synthetic`).
  Purges `source` starting `zz` (test fixtures) + `source == "synthetic"` (seed). **Dry-run by
  default** (destructive → opt in with `--apply`); coalesces deletes into one `bulk_persist()` flush.
- **Data-safety call (corrects the ticket's row list):** `karaa` is NOT purged by default. The
  ticket listed `karaa` among synthetics, but `source == "karaa"` is the FIELD'S DEFAULT VALUE
  (`VehicleListing.source`, types.py) — a row with an unset source reads as `karaa`, so a blind
  purge would delete legitimately first-party rows. Only swept with `--include-default-source`.
- `delete()` added to the `IVehicleStore` Protocol (all stores already implemented it). Full test
  coverage (dry-run, apply-keeps-real-and-default, include-default, file-store persistence).

**Not built (deferred):** the *standing ingest guard* against re-pollution. Lower priority — `zz*`
rows come only from test fixtures, never a real connector; `synthetic` is a deliberate seed. Revisit
if a real ingest path is found adding them. **Running the purge on prod is deploy/root-gated → 013.**

---
## PROD-RUN DONE 2026-07-31 (dev box)
`mawtarx purge-synthetic --store …/system --apply` run on the live dev store. **248 `source:synthetic`
rows deleted** (total 19,602 → 19,354); dry-run now reports 0. First-party rows untouched
(`--include-default-source` NOT used). Backup: `collections/listings.xwjson.bak-preop-20260731`.
