# 012 — Dubizzle reactivation: live SERP health-check, then config flip

- Type: `wayfinder:task` (AFK health-check; prod runner-config is HITL via deploy-vps)
- Status: open (frontier)
- Blocked by: —
- Assignee: —

## Question

Graduated from 004. Dubizzle has a real, honest Algolia-off-the-SERP scraper (registered ACTIVE,
in `collect.yaml`, has a sweep profile) — it's just not in the prod runner's ~7 Saudi source set,
and ~5.1k legacy rows sit unswept. But its card warns HTTP 403 and a live SERP WebFetch came back
empty. **One live health-check decides it**: fetch a dubizzle.sa SERP page and confirm Algolia
hits still server-render into the HTML (`extract_hits` finds `objectID`s).

- If YES → pure ops flip: add dubizzle to the prod runner's source/profile set (config, no code);
  daily sweep + reconcile refreshes/ages the ~5k rows. Recovers ~5k+ real SA listings cheaply →
  directly helps the pricing-coverage lever (003) and coverage target (004).
- If NO (403 / client-rendered now) → defer to the Haraj class (partner feed / decline the bypass).

Resolve to: the health-check result + either the runner-config change (done via deploy-vps) or a
defer verdict with why.

---

## VERDICT 2026-07-31 — DEAD / BOT-BLOCKED. Defer to Haraj class. NO code change.

Live probe of the exact connector URL (`https://www.dubizzle.sa/en/vehicles/cars-for-sale/?page=1`,
plain GET, connector's own UA): HTTP 200 `server: cloudflare` but body only **24 KB** — a JS
**fingerprint interstitial** (`Fingerprint` module, 49 refs), **zero `"objectID"`** (the
connector's sole Algolia selector). It computes a fingerprint, POSTs it, and only then reloads the
real SERP. A plain-HTTP fetcher (all `DubizzleScraper` is — no JS) gets the challenge → `extract_hits`
returns `[]` → `fetch()` breaks page 1 → **silent 0 rows** (the ticket's exact "succeeds scraping 0"
trap). Not a markup change (selectors are fine, offline `test_dubizzle.py` still 4 passed) — an
**access-control wall**. Running the challenge JS = bypassing it → forbidden by repo CLAUDE.md.

**The ticket's premise was also stale:** dubizzle is NOT disabled in-repo — it's ACTIVE everywhere
(`sources/dubizzle.py:271`, `sweep_profiles.py:72-78`, `collect.yaml:45-47`, and in the computed
`runner.default_sources()` sweep set; all added in `1fc874b` 2026-07-22). There is **no
`status="disabled"` to flip.** Prod's exclusion ("5.1k legacy dubizzle NOT in sweep set",
vps-current-state.md:187) must be a **root-gated `MAWTARX_SWEEP_PROFILES` override / older build** —
invisible in this checkout. So a "config-only flip" recovers nothing; if prod were made to include
it, it would fire silent 0-row sweeps.

**Path forward (not this ticket):** partner/official feed (provider card already says
`PARTNER_API`/`PARTNER_AGREEMENT`) — the sanctioned route, same class as Haraj. Follow-ups:
(a) someone with root should confirm the prod dubizzle exclusion is deliberate, else a future deploy
of main silently starts 0-row dubizzle sweeps; (b) doc-hygiene — the module docstring's "Verified
live for SA" is now a false-positive; worth a live-smoke xfail marker so the next agent doesn't
re-probe cold (deferred — dead branch, no code change). The 5.1k dubizzle rows in mawtarx are
legacy/static; nothing in this repo revives ingestion.
