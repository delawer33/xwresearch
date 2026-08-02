# Done today — 2026-08-02

## mawtarx reprice CLI + pricing-7 to both venvs (deployed)

`mawtarx reprice` / `reprice_all(store)` — a bounded loop over the existing
`refresh_stale_buckets`, no new pricing logic (a version mismatch already reads stale via
`bucket_is_stale`). mawtarx `ddf5804`, pushed.

Deploy finding: **the pricing-5 gap was karaa-api, not mawtarx-api.** `/opt/mawtarx-api/.venv`
was already pricing-7; `/opt/karaa-api/.venv` was the stale one (5→7). After restart its own
`PricingRefreshRunner` reflowed all 2,311 local rows to `mawtarx-pricing-7` — so on the box
"reprice" is restart-driven, and the CLI must **not** run against a live store dir concurrently
(two writers). Closed GH #4/#5/#6/#7/#14; #8 and #2 remain.

## GCC activation — charted, and the connector reality checked

Grilled the plan and wrote it to `repos/mawtarx-connect/docs/` (not wayfinder, per user):
`gcc-activation-plan.md`, `gcc-connector-field-notes.md` (living, seeded), `adr/0001`.
Done-bar per country = **(a) data-live + (b) best-achievable coverage & max normalization** —
an effort bar, not a listing count. Order UAE→KW→QA→BH→OM.

Facts that changed the plan, all verified in code:

- **The prod runner sweeps `sweep_profiles.py._DEFAULTS` (7 Saudi), NOT `collect.yaml`.** Two
  different config surfaces; the roadmap conflated them. `_DEFAULTS` is in-package Python →
  enabling a country is a **code deploy, shukri-writable, not root-gated**. GCC does not wait
  on the boss's reconcile step.
- **Reconcile is per-source and first-baseline-safe** — a new country's first full sweep only
  seeds a baseline, so activation can't falsely expire its rows or touch Saudi.
- Registry claimed 1,514 sources / 1,926 provider cards; only **~48 have a real `fetch()`** and
  8 have tests. opensooq spans 19 countries, dubizzle 7 (no AE), hatla2ee 5 — several reachable
  but unwired. Native currency already emitted per-source; the unproven part is native currency
  *through pricing*.

## Registry cleanup — 1,514 → 245 sources (−20,753 lines)

Executed ADR 0001 in mawtarx-connect (`789b959`). Deleted 52 files: the generated catalogs
(wave3 ×807 profiles, wave2_agencies 166, wave2_marketplaces 139, wave2_special 40, agencies_*
108, dealers), their orphaned `_agency.py`, 9 provider cards, 29 `_probe_*` scratch scripts.
Kept `_public_listing.py` (18 live regional files use it), the `_gen_wave*` generators
(reversible), and the 7 walled scrapers — which already documented their walls, so "park with
note" needed no edits.

Verified, not assumed: all 47 collect.yaml sources + all 8 `_DEFAULTS` still resolve and
`build_adapter()` cleanly. Two tests broke — they asserted on `synthetic.global`, which lived in
the deleted `wave2_special`; repointed at the surviving `synthetic` (same `non_listing_source`
semantics). Suite green.

## Liveness-probe harness (written, not yet run)

`scripts/probe_country.py` (`a5fb808`). One page per source through the connector's own
`xwapi.scrapping` stack; reports raw / normalized / **persistable** counts, field fill, currency.
Exists because **a block looks exactly like "no results"** — zero rows is never a pass. Verdicts
split the real failure modes: `EMPTY`, `PARSE_BROKEN`, `CONTRACT_FAIL`, `BLOCKED`, `ERROR`,
`TIMEOUT`, `OK`. DISABLED sources skipped by default.

Paid off before running: `--list` (registry-only, no network) surfaced three registered sources
my hand-seeded notes had missed — `cars24.ae`, `sellanycar.ae`, and **`q84sale.kw` (4Sale, a
major Kuwaiti marketplace)**. Field-notes corrected; the registry now wins over the tables.

## create-connector skill rewritten (215 → 121 lines)

Cut the compliance ritual (mandatory 7-step verification, 3-listing cross-check, Phase-0
report-and-wait, prescribed output format) and kept the code-truth: architecture facts, the
`record_to_listing` allowlist contract, mergeability conventions, and the traps that each
shipped a real bug. Fixed two false claims: the "~580 registered-but-dormant" figure is
folklore (not in the code anywhere), and "catalog integration postponed" is stale —
`catalog_car_id` has resolved at ingest since #14.

## markibx structural-soundness pass — audit → plan → slices #39/#40/#41 shipped

Measured data audit (all real SA listings through the spine) found the completed global-first
plan produced hollow data: 96% of models are one catch-all `gen1` (134 real OEM codes of 3,763),
specs US/CA-market on fake gens, GCC layer = 6 facts on 1 car. Wrote
`markibx/docs/data-state-audit-2026-08-02.md`, added **Structural soundness** to CONTEXT.md,
grilled the plan → PRD **#38** + slices **#39–#46** on the markibx tracker. GCC money facts
deliberately deferred to the LLM umbrella (scrapers can't recover historical launch prices).

First 3 slices implemented via parallel opus subagents (I reviewed/committed):

- **#39** (mkx-connect `80872a3`) — standing demand-coverage audit script, fresh scp pull by
  default, classifier verified twice (independent counting path 92.15% row agreement + 40/40
  hand sample). **Live store truth: 66.4% resolve / 5.3% make-miss / 1.0% GCC** — worse than the
  local 77.4% because live adds dubizzle + **1,921 yearless opensooq rows** (upstream
  mawtarx-connect gap). 244-nameplate cumulative-80% worklist committed.
- **#40** (markibx `709b20b`) — 3 soundness rules in the validate-seed gate (overlap /
  nameplate-year-bleed >30y / shell-shadowing), 13+15+1 measured offenders grandfathered via
  committed shrinkable allowlist; new violations fail the same SeedError every gate blocks on.
- **#41** (mkx-connect `f44aacc`) — root cause of the gen1 collapse: widening's single entry
  predicate (P31 car-model ∧ P176 manufacturer) — gen entities without P176 and "model series"
  hubs were invisible; Camry split only by Toyota's labeling luck. New 5-mechanism extraction,
  QID-anchored. Dry run over the full worklist: **23/244 nameplates splittable (88 gens, 55
  new); 175 residue** — Accent/Sonata/Fortuner/Versa have NO generation entities upstream at
  all (verified live), so the LLM umbrella carries more split load than assumed. Residue
  slightly overstated: BMW chassis-code labels (F15/G05) escape the prefix sweep.

## Left open

- **Root xwresearch repo is unpushed** — 6 commits on local `main` incl. today's `db7f2c8`.
  My `git push` was blocked by the permission classifier; needs a manual push.
- **The boss handoff I sent may already be stale.** A new runbook commit prefers arming
  reconcile via admin over the `install-env`/sed procedure written in
  `wayfinder/…/013-ROOT-HANDOFF-reconcile.md`. Reconcile it before he acts.
- **The dev box runs pre-fix reconcile code.** A zero-baseline `ZeroDivisionError` in
  `should_skip_reconcile` was fixed upstream today but is not deployed — if reconcile is armed
  against a zero baseline first, it crashes. Check whether that fix needs shipping before the
  flag is flipped.
- **The probe has never touched a live site.** UAE = step 2 of the loop:
  `scripts/probe_country.py AE`.
- Iteration 0 is done (cleanup + harness), so **UAE is the next iteration**, unblocked.
- **markibx #42 (membership fill) + #43 (alias repairs) unblocked** — worklists committed;
  then #44 (splits, consumes #41's dry-run report + drafts the gen1-retirement ADR).
- **Pre-existing seed-drift test failures, not from today's work** (verified on clean trees):
  9 in markibx (`test_spine*`), 3 in mkx-connect (`year_harvester is None` in
  structured-depth/nhtsa tests). Someone should re-baseline them.
- mkx-connect has unrelated uncommitted leftovers (`.gitignore` Taskfile line, `.github/ci.yml`)
  from prior tooling work — not mine, left in place.
