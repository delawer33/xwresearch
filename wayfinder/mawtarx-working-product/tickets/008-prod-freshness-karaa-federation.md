# 008 — Prod freshness + karaa federation reconciliation

- Type: `wayfinder:research` (AFK; likely spawns a `task`)
- Status: **resolved** 2026-07-30
- Blocked by: —
- Assignee: —

## Question

Three prod-vs-code mismatches muddy "what's actually live": (a) prod pricing engine is
`mawtarx-pricing-5`, code is `pricing-7`; (b) karaa.net is `listings_mode=local` serving its own
2311-row SA store, **not** federated to the ~19k mawtarx corpus, while `vps-current-state.md`
claims "hybrid"/15,473; (c) reconcile is off, so un-rescraped rows keep stale estimates. Decide
what karaa should serve (its own store vs the federated mawtarx corpus) and what it takes to get
prod onto the current engine — this is the secondary "backend for karaa" goal, but the drift also
undermines any claim about what pricing users see today.

Resolve to: the intended karaa data source + a prod-freshness plan (engine upgrade + reconcile
posture) + a corrected `vps-current-state.md`.

## Resolution (2026-07-30, research; read-only live GETs on karaa.net)

**Corrected live state:** `karaa.net /health` → `listings:2311, listings_mode:local`; served rows
are karaa's **own** SA seed (`source:karaa`, many `price:0`, single-nameplate exotics → 0 comps by
construction, valuation `method=unavailable`). Listing intelligence reports
`pricing_model_version: mawtarx-pricing-5` (code = **pricing-7**). mawtarx.com is edge-gated (302).
So all three premises confirmed live: (a) prod pricing-5 vs code pricing-7; (b) karaa `local`/2311,
**not federated**; (c) reconcile off → stale estimates persist.

**Why local:** `KARAA_LISTINGS_MODE=local` in `/etc/karaa-api.env`, flipped from hybrid after the
**F2/F3 single-worker saturation incident** — hybrid's read path issues per-request blocking
outbound HTTP to mawtarx-api, saturating the single-worker karaa-api (health 2.3s → watchdog loop).
`local` is the safe posture that incident left behind.

**Intended source = federate to the ~19k mawtarx corpus (hybrid).** Rationale: karaa's own 2311-row
seed produces ~0 real valuations; the mawtarx corpus is the only pool that makes pricing non-zero,
and federation is the product's point ("backend for karaa"). But **do not flip until** (a) the
single-worker concurrency fix lands → **ticket 011**, and (b) root env access exists for the flip.
Beware the matched-pair trap: a snapshot miss **degrades silently to zero remote rows** — deploy
karaa-api + mawtarx-api together, re-query after warm-up.

**Prod-freshness plan → ticket 013** (blocked on human root access): deploy pricing-7 into **both**
`/opt/mawtarx-api/.venv` and `/opt/karaa-api/.venv` (karaa embeds mawtarx in-process), then a
re-price sweep (deploy alone doesn't re-price — estimates are write-time), and set
`MAWTARX_RECONCILE_ENABLED=1`. Both env edits touch existing service files → blocked on real root
(scoped sudo can't incrementally edit an existing service env; no `mask` to hold a unit past the
2-min watchdog).

**`docs/vps-current-state.md` is stale** (self-contradictory: line 198 right; 55, 94–106, 174–178
wrong — claim hybrid/15,473). Exact corrections carried into ticket 013.

## AMENDMENT (2026-07-30, user correction — supersedes the "federate to hybrid" recommendation)

**karaa users must NOT see mawtarx's listings.** karaa serves its OWN inventory (`listings_mode=
local`, kept) and consumes mawtarx for **price estimations only**. The resolution above
recommended federating karaa to the ~19k mawtarx corpus (hybrid) — **that is rejected.**

Corrected intended design: karaa stays `local` for listings; mawtarx is a **pricing-estimation
service** to karaa via `MawtarxComparablesPool` (a cached market snapshot used as the comp pool,
write-time pricing, no listing display) — see 011. The prod-freshness plan (pricing-7 + reconcile)
still stands; the **hybrid listings flip is dropped** from 013. `MAWTARX_RECONCILE_ENABLED` still
matters (keeps mawtarx's own corpus — the comp pool — fresh).
