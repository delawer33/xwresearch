# 011 — How does karaa get mawtarx price-estimations (estimations only, NO listing federation)?

- Type: `wayfinder:research` (AFK — resolved by code investigation)
- Status: **resolved** 2026-07-30
- Blocked by: —
- Assignee: —

## Question (reframed by the 2026-07-30 user correction)

**Correction:** karaa users must **NOT** see mawtarx's scraped listings — karaa serves its *own*
inventory and consumes mawtarx for **price estimations only**. This overturns 008's "federate to
hybrid" recommendation. Original framing (concurrency fix for hybrid *listing* federation) is moot.

New question: how does karaa price its own listings against the mawtarx market (so a seller's car
is valued against the whole market, not karaa's handful of rows) **without** federating/showing
mawtarx listings, and without the F2/F3 read-path saturation?

## Resolution (2026-07-30, code investigation)

**Already designed, already coded — no new concurrency design needed.**

`MawtarxComparablesPool` (`repos/kara-api/.../mawtarx_comparables.py`) exists for *exactly* this. Its
docstring: it was split out of `HybridVehicleStore` so a store can have "its OWN listings priced
against the real mawtarx market" **without** the listing-federation surface; it "does NOT serve
listings, resolve ids, or handle writes." It owns only a **cached remote snapshot** (TTL 600s,
bulk-fetched, background-refreshed) + comp queries over it.

`state.py:304–315` **wires it in `local` mode**: `elif s.listings_mode == "local" and
s.mawtarx_api_url:` → instantiate the pool, blocking first fill (`_do_refresh()`), `attach_to(store)`.
karaa's own listings are then priced at **write time** (`PricingRefreshRunner`, state.py:326) against
the mawtarx market snapshot. **No per-read-request outbound HTTP → the F2/F3 saturation (a *listing*
read-path problem) does not apply.** The correction's constraint (estimations only) *is* the path
this pool was built for.

**Decision:** keep `listings_mode=local` (karaa shows only its own inventory) + the
`MawtarxComparablesPool` for estimations. Do **not** enable hybrid listing federation. 011 needs no
engineering design.

**So why does live karaa.net show `comparable_count:0 / method:unavailable`?** The wiring requires
(a) a deployed karaa build that *contains* this local-mode-pool code, (b) `MAWTARX_API_URL` set in
karaa's prod env, (c) `MAWTARX_API_TOKEN` not 401'ing, and (d) mawtarx-api actually serving the real
~19k-row snapshot. One or more is false in prod (build likely predates this wiring; env unverifiable
without root). **Diagnosing + fixing that is a prod-ops task → folded into 013.** It is a
deploy/config problem, not a design problem.

Cross-links: revises 008; hands the remaining prod work to 013; the estimation *quality* still
depends on corpus density (003/004/012) and catalog-link (005).
