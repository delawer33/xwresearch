# 004 — What is "broad coverage" for Saudi, and can we crack haraj + dubizzle?

- Type: `wayfinder:research` (AFK)
- Status: **resolved** 2026-07-30
- Blocked by: —
- Assignee: —

## Question

Five sources produce in prod (syarah/sayarat/opensooq/saudisale/samaco). The two biggest holes:
**haraj** — the largest SA marketplace — is permanently 0 (WAF-blocked), and **dubizzle**'s 5.1k
rows are legacy and not actively swept. Define the Saudi coverage target (corpus size + freshness
cadence that reads as "complete" to a user, informed by 002's benchmark) and assess feasibility
of the two dark giants: what would it take to sweep haraj without bypassing its access controls
(the standing rule forbids that — is there a partner/API path?), and to reactivate dubizzle.

Resolve to: a coverage target (volume + freshness) + a feasibility verdict per dark source
(haraj, dubizzle) with the realistic path or a "defer/decline" call.

## Resolution (2026-07-30, research)

**Coverage target:** **~40–60k unique active SA listings** (post-dedup) to "feel complete" — but
that is reachable **only with Haraj**. Without Haraj the structural ceiling is **~15–20k** ≈ where
mawtarx sits today (~19k): mawtarx already covers the **dealer/aggregator layer** well (OpenSooq
~2.7k, YallaMotor ~6k, CarSwitch ~4k are small + heavily cross-posted); the gap is Haraj's
**individual-seller long tail**. **Freshness SLA:** new listing visible ≤24h, delisted gone
≤24–48h — the runner's designed daily-full + 3–6h-incremental cadence already matches this, *if*
reconcile is actually armed (root-gated, 013).

**Haraj → DEFER.** A real GraphQL scraper exists but the endpoint returns WAF/388; code correctly
refuses to spoof tokens and now raises-on-block (so 0 is honest, not silent). No lawful high-value
path: no public partner program found (Haraj is famously independent), and the one lawful surface
(robots-allowed hourly sitemap) yields only free-text posts → make/model/year, no structured
price/mileage. Recommend a time-boxed BD attempt for a partner feed; do **not** enable
`KARA_ENABLE_HARAJ` in prod. → recorded Out of scope (biggest coverage gap).

**Dubizzle → REACTIVATE (conditionally, cheap).** Honest Algolia-off-the-SERP scraper exists,
registered ACTIVE, in collect.yaml with a sweep profile — it's simply not in the prod runner's ~7
Saudi source set. Gating unknown: its card warns HTTP 403 and a live WebFetch of the SERP came
back empty (blocked or now client-rendered). **One live health-check** decides it: if the SERP
still server-renders Algolia hits → pure config flip, recovers ~5k+ rows; if 403 → defer like
Haraj. → ticket 012.
