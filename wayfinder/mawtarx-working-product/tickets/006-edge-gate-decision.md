# 006 — Edge-gate decision for mawtarx.com

- Type: `wayfinder:grilling` (HITL)
- Status: parked — deferred to the consumer-marketplace phase (in scope, not dropped)
- Blocked by: consumer phase (post-API, frontend-team availability) — see 001
- Assignee: —

## Question

The consumer marketplace is real in code but sits entirely behind `xwauth-id-gate` (every request
302→login). A public consumer product requires opening it. Decide: open publicly, invite-only
beta, or zone-gated (public browse + gated account/console)? What auth does a Saudi buyer need to
see listings vs to reveal a seller's contact (PDPL-metered today)?

Resolve to: the gate posture for launch + which zones are public vs authenticated.
