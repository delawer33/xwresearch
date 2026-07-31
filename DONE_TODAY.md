# Done today — 2026-07-31

## markibx Phase A — global-identity plan (merged to main + DEPLOYED)

Planned + implemented A0–A4, reviewed, merged, deployed to dev VPS. markibx `f84f051`,
markibx-connect `320e231`, markibx-api `953639c` — all pushed.

- **A0** ADR 0012: markibx = multi-domain machine registry, cars = domain 1. Reframed CONTEXT/CLAUDE/README.
- **A1** fixed the mandatory `FILTER(LANG="en")` drop in all 10 `markibx-connect/sources/wikidata*.py` —
  English now OPTIONAL+preferred, non-English captured as aliases (was silently dropping ~13% of breadth, skewed non-Western).
- **A2** multilingual model-level aliases across the breadth (live Wikidata sweep) — **1,543/3,533 models now carry aliases**.
- **A3** per-`Fact` `origin`→license, sheet-level `licensing{attribution,share_alike}`, `exclude_share_alike` on
  `/catalog/resolve`. Live-verified: DBpedia-year gens return CC-BY-SA + `share_alike:true`.
- **A4** cars-first `domain_profile.py` seam: car profile = old `SPINE_SPEC_FIELDS` byte-for-byte (car spine UNCHANGED),
  6 dormant non-car profiles, per-domain scoring denominator.

Learned: **widening ≠ enrichment** — the membership-widening path is a no-op for aliases (curated-gate skips the
already-widened breadth); alias enrichment must go through the make-generic `ingest_toyota_identity.run()` + `MANUFACTURER_QID_PINS`
(which `ingest_all_makes.py` LACKS → silently skips hyundai/suzuki/skoda/dongfeng/ford/mitsubishi).

## markibx free EPA depth pass (committed + DEPLOYED) — markibx `967e1e2`

Answered "can free depth get ≥half as good as LLM?" → **yes, for the US-sold mainstream.** Ran
`markibx-connect/scripts/ingest_epa_specs.py --live` (EPA FuelEconomy.gov bulk CSV, ONE HTTP request, $0)
now that breadth is 3,533 models. Measured before/after on a throwaway seed copy (`scratchpad/measure_fill.py`),
then applied to the real seed.

- **Gens with ≥1 of the 12 spec fields: 110 → 373 (+263, 3.4×).** 49,995 rows → 17,539 matched → 369 gens; 264 seed files changed.
- 6 fields 2.9% → ~9.9%: body_type, fuel_type, gearbox_type, drivetrain, displacement_l, cylinders. All `community` tier.
- Sane-checked: Clarity FCV→Hydrogen, Entourage→3.8L V6 Van, Mazda 5→2.3L 4cyl. **Zero test regressions** (same 9 pre-existing
  stale seed tests fail before AND after — confirmed by stash).

Learned / verified:
- **The spine seed dir IS the prod source-of-record — local == prod at the same commit.** No snapshot needed; run
  enrichment locally, the git diff *is* the deploy. Kills the local-vs-server question.
- **EPA = 1 bulk CSV (not per-model); matches by make-slug + curated-model-alias + year (NO QID).** Enrichment-only,
  idempotent, can't shadow oem/official curation (fact_merger tier guard, ADR 0007).
- **NHTSA fills 0 of the 12 scored fields** (dimensions/weight only) — deliberately NOT run; 224 requests for zero metric movement.
- **`wikidata_claims.py` pulls lineage/identity, NOT physical specs** — extending it is free non-US-biased coverage still on the table.

Deploy: markibx core into BOTH `/opt/markibx-api/.venv` + `/opt/mawtarx-api/.venv`; restarted markibx-api + markibx-connect-api
(mawtarx-api not restarted — its kara-web catalog shim uses identity, not EPA specs). Live-verified via `/catalog/resolve`.

## mawtarx catalog-link + hygiene — #14 shipped, then backfilled/purged on the dev store

Wayfinder tickets #005 + #009 → **Exonware/mawtarx#14**. Merged + pushed + deployed to the dev VPS:
mawtarx `469c062`, mawtarx-connect `a11bedb`, mawtarx-api `e619529`.

- **#005** wired catalog-linking into `ScrapingPersistenceAdapter.flush()` (the real bulk seam, not the
  CLI-only path) — per-tuple cached resolver, one coalesced flush. Injected `state.catalog` at all 3 prod
  adapter sites (ingest_service, schedule_runner, connectors route).
- **Found + fixed a second bug the research missed:** the old linker persisted via `_save()`, which
  early-returns unless `_dirty` (never set) AND is **absent on the prod DB store** → `catalog_car_id` would
  have stayed empty even if the CLI ran. Replaced with `bulk_persist()`/`mark_persist()`.
- **#009** `mawtarx purge-synthetic`, dry-run default; `source=="karaa"` (the field DEFAULT) protected unless
  `--include-default-source`.

Then ran the two one-time store ops on the **live dev store** myself (no root needed — `shukri` has an ACL on
both the venv and `/var/lib/mawtarx-api/data/system`; only `/etc/*.env` is unreadable):

- **catalog-link backfill:** identity coverage **~0% → 96.4%** (`pool-health unknown_identity` 697 / 19,354).
- **purge-synthetic --apply:** **248** `source:synthetic` rows deleted (19,602 → 19,354); dry-run now 0.

Verified facts about the running system:
- **The box is DEV, not prod** (owner-confirmed) — documented in the deploy-vps SKILL.md header + memory.
- CLI needs `XWJSON_ABI_LIB=/opt/kara-api/libxwjson_abi.so XWBASE_ALLOW_GIL=1` or it dies "no usable xwjson backend".
- **catalog-link takes ~103s** — barely fits the 2-min watchdog window; chaining purge after it got the purge's
  flush squeezed out (re-ran purge alone, ~24s). One heavy op per window; set a generous *local* ssh timeout
  (the remote script keeps running even if the local view times out — that's what bit attempt 1).
- **Dubizzle (#012) is DEAD** — live probe: Cloudflare JS-fingerprint wall (24KB challenge, 0 listings). Also
  already ACTIVE in-repo, so the "config flip" premise was false; prod exclusion is a root `MAWTARX_SWEEP_PROFILES`
  override. No code change (correct). Recovery = partner feed, Haraj class.

## Left open

- **013 boss-checklist** (`wayfinder/mawtarx-working-product/tickets/013-BOSS-CHECKLIST.md`) — 4 items still
  need root (all touch `/etc/*.env`, which `shukri` can't read): pricing-7 into both venvs, `MAWTARX_RECONCILE_ENABLED=1`,
  re-price sweep (rides on the first two), and karaa `local`-mode comps-pool (token/env check → `comparable_count>0`).
- **Backfill rollback backup** left on the box: `…/system/collections/listings.xwjson.bak-preop-20260731` (67MB) —
  drop it once the linked store is trusted.
- **Did NOT arm reconcile** even where reachable — it marks listings sold and needs the "sweeps cover full sources"
  precondition; a deliberate decision, not a flip.

- **Depth residual is now measured, not guessed:** 6 fields EPA can't supply (doors, seats, horsepower_hp, torque_nm,
  top_speed_kmh, fuel_tank_liters) + ~90% of gens still bare shells (GCC-only/Chinese tail: BAIC, Changan, MG, Chery, Geely —
  no US-market EPA presence). That tail is the LLM-unique target. LLM cost estimate: ~$8 Haiku / ~$22 Sonnet for the GCC slice.
- **Free coverage not yet exhausted:** extend `wikidata_claims.py` for physical-spec P-props; run NHTSA for the full datasheet
  (dimensions/weight, orthogonal to the 12 fields).
- **Pre-existing red tests (NOT mine):** markibx ~9 stale seed-expectation tests, markibx-connect 2, markibx-api 1 — all verified
  pre-existing by stash. Worth a cleanup pass.
- **Known limitation:** non-Latin model aliases retain the make prefix ("هيونداي توسان") — `strip_make_prefix` is Latin-only.
- **Deferred:** A1 label helpers in `_entity_common.py` duplicate `spine_ingest/wikidata_identity.py`'s SPARQL-label fragment —
  consolidate when next touching either.
