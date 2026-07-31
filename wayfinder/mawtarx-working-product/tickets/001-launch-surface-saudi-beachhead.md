# 001 — Launch surface for the Saudi beachhead: consumer marketplace, B2B API, or both?

- Type: `wayfinder:grilling` (HITL)
- Status: **resolved** 2026-07-30
- Blocked by: —
- Assignee: —

## Question

Which surface do we make "work" first for Saudi — the public consumer marketplace (mawtarx.com),
the B2B/data API, or both at once? This is the gating decision: the consumer surface needs the
edge gate down (001-adjacent 006) and an end-to-end UX bar (007); the B2B API is already
token-metered with 20 real routers and is arguably closest to shippable. The choice fixes the UX
bar, the parity benchmark (002), and which foundation cracks are launch-blocking vs deferrable.

Resolve to: a named primary launch surface (+ optional secondary), and the one-sentence "a
Saudi user/client would call this working" statement it implies.

## Resolution (2026-07-30, HITL)

**API-first.** Make the mawtarx **API + the data/pricing intelligence it serves** the surface we
make "work" first — it's closest to shippable (20 real routers, metered, no consumer-UX debt) and
does not wait on the frontend team, whose availability is uncertain. The **consumer marketplace
(mawtarx.com) stays in scope but is deferred** ("must also be on its place") until the frontend
team can be connected.

**Whose success = "working": karaa's users — i.e. the Saudi car buyer/seller.** So the API is not
an abstract B2B endpoint; its first real consumer is **karaa**, and the bar is that a Saudi buyer/
seller experiences good data + trustworthy pricing *through karaa*.

**Consequences for the map:**
- The mawtarx→karaa data+pricing path (008) is **central**, not secondary. Federating karaa to the
  real corpus + un-staling prod pricing is now on the critical path → tickets 011, 013.
- Consumer-only decisions 006 (edge-gate) and 007 (lead-loop) → **parked/deferred** to the consumer
  phase, kept in scope.
- Parity (002) is measured on the *shipped* pricing/data karaa surfaces, not on a public site yet.
