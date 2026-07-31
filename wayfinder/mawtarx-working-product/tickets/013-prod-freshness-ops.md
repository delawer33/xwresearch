# 013 — Get prod onto pricing-7 + reconcile on + (later) hybrid federation

- Type: `wayfinder:task` (HITL — needs a human with real root; via deploy-vps)
- Status: open — BLOCKED on human root/ops access
- Blocked by: — (root access has a path now: the user's boss holds root — see below)
- Assignee: —

## Question

Graduated from 008 + 003. Prod serves `mawtarx-pricing-5`; code is pricing-7; reconcile is off;
karaa is `local`/2311 not federated. Execute the freshness plan:

1. **Deploy pricing-7 into BOTH `/opt/mawtarx-api/.venv` and `/opt/karaa-api/.venv`** (karaa embeds
   mawtarx in-process — upgrading only mawtarx-api leaves karaa on pricing-5). Restart both units.
2. **Re-price sweep** — deploy alone does NOT re-price (estimates are write-time; the version
   mismatch only forces recompute through the refresh/reconcile sweep). Run a re-price pass to
   flush pricing-5 → pricing-7 across the corpus.
3. **`MAWTARX_RECONCILE_ENABLED=1`** in `/etc/mawtarx-api.env` (default "0" = off; the runner
   already requests reconcile but it's server-gated → currently a no-op).
4. **Do NOT flip to hybrid** (user correction — karaa shows only its own listings). Instead, make
   the **`local`-mode estimations path** actually work in prod (see 011): confirm the deployed
   karaa build contains the `MawtarxComparablesPool` local-mode wiring (`state.py:304-315`), that
   `MAWTARX_API_URL` + `MAWTARX_API_TOKEN` are set in karaa's env and the token doesn't 401, and
   that mawtarx-api serves the real ~19k snapshot. Success = karaa listing intelligence returns
   `comparable_count > 0` (not `method=unavailable`).

**Access path (2026-07-30):** the env edits touch *existing* service env files, which the scoped
sudo (`shukri`) can't incrementally edit, and there's no `mask` to hold a unit past the ~2-min
watchdog. **The user's boss holds real root and can be asked.** Deliverable for this ticket is a
precise checklist the boss can run (env keys to set, deploy commands, verification GETs) — not an
agent-run change.

Also: **correct `docs/vps-current-state.md`** (stale/self-contradictory): line 55
`listings:15473,hybrid` → `2311,local` (verified 2026-07-30); lines 94–106 `KARAA_LISTINGS_MODE=
hybrid` → `local`; lines 174–178 served set 15,473 → 2311 `local`; add a pricing-freshness line
(prod=pricing-5, code=pricing-7, reconcile off). Line 198 is already correct — leave it.

Resolve to: prod on pricing-7 + reconcile armed (verified via read-only GET), corrected VPS doc,
and hybrid flipped once 011 lands — or a precise checklist handed to whoever holds root.
