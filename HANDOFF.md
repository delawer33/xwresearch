# HANDOFF — markibx global-first plan (continuation)

Written 2026-07-28. All state below **verified live**, not read from docs. Prior context:
`repos/markibx/docs/global-first-plan.md` (the plan), memory `spine-deployed-p0`.

## Where things stand (done + shipped)

- **markibx `main` `b80987c`, markibx-connect `main` `1f8c826`, markibx-api `main` `d01ab63` — all pushed, in sync with origin.**
- **Spine is DEPLOYED to prod (P0 done).** `GET https://markibx.com/api/markibx/v1/catalog/resolve?make=Toyota&model=Camry&year=2021&market=GCC` → 200, real XV70 sheet (was 404 for the entire prior history of the project). All 5 services 200; karaa.net unaffected (`listings_mode: local`).
- **5 issues integrated to markibx `main`** (346 tests pass / 1 skip; `--validate-seed` OK; spine = 247 generations / 45 makes; ADRs 0001–0009):
  - **#17** nameplate direction-repair + cross-make audit (bmw 59→43, mercedesbenz 72→49, lexus 20→12 distinct model_norm on the real corpus).
  - **#13** DBpedia CC BY-SA posture → ADR 0008, `licensing.py`, `NOTICE.md`, new `Generation.year_harvester` (harvester name, e.g. "dbpedia").
  - **#12** operator merge review/reverse (`markibx merge` CLI + `merge_review.py`/`split_decisions.py`).
  - **#11** re-key fabricated `DATA-` codes → `LOCAL-GEN-1`; new `Generation.year_source` (trust tier, e.g. "listings") + `year_confidence`.
  - **#10** widen ingest to 45 makes + coverage report (`repos/markibx/docs/mkx-10-coverage-report.md`; ingest tooling in markibx-connect `scripts/ingest_all_makes.py` etc.).
- **Fixed a pre-existing wheel-build bug** (`spine_seed` dir force-include duplicated tracked files) — a real reason the spine was never deployable.

## Remaining work

### P2 — retire the legacy catalog (hard break) — NOT STARTED
Per markibx ADR 0003. Delete `CatalogVehicle`/`CatalogCar`/`ICatalogStore`/`catalog_key`/`seed_top_ksa_models`; rewrite consumers to spine-native types (`resolve_sheet`/`CanonicalRegistry`). **Blast radius (verified live imports):**
- `mawtarx`: `catalog_link.py`, `types.py`, `pricing_methods/catalog_msrp.py`
- `mawtarx-api`: `state.py`, `routes/catalog.py`, `models.py`
- `kara-api`: `state.py`, `mawtarx_stores.py`, `models.py`
- `markibx-api`: `routes/catalog.py`, `state.py`, `mountable_schemas.py`, `mountables_store.py`
- `markibx` core: 14 files (`catalog*.py`, `contracts.py`, `store_catalog.py`, `spine*.py`, `cli.py`, `__init__.py`, …)

**Largest unverified risk:** `kara-web` / `markibx-web` may render legacy catalog fields — no Python grep sees this; check the frontends before cutover. markibx.com is publicly ungated, so external consumers of `/catalog/car/*` break silently. This is destructive + a coordinated multi-repo deploy — treat carefully, verify pricing on karaa.net after.

### P3 — link mawtarx listings through the spine — NOT STARTED
Rewrite `mawtarx/catalog_link.py` to resolve through the spine's `resolve()` seam (keep the precision ladder; a listing whose year selects no generation links at model level and says so). Launch price stays native `{amount,currency,market}` with derived `original_launch_price_sar` (ADR 0006).

### #18 — EXCLUDED (human): HITL ruling on ~269 split-or-merge nameplate candidates. `help wanted`, not for an agent.

## Debt / cleanup (do before calling the deploy clean)

1. **markibx-api PROD venv is hand-patched.** `/opt/markibx-api/.venv`'s `xwbase` + `xwbase_media` were **copied from `/opt/mawtarx-api/.venv`** (not a clean pip install; no dist-info for the copied `xwbase_media`). Root cause: markibx-api `main` needs a newer `xwbase` *build* than prod carried — **same version string `0.0.1.6`, older bytes** (lacked `exonware.xwbase.errors.missing_dependency`). Proper fix: a coordinated markibx-api + `xwbase` + `xwbase-media` pip release. **No backup was taken.**
2. **Pre-existing seed fragmentation.** `bmw:730li`-style powertrain-fragment *models* exist in the seed; with the `DATA-` shells correctly removed (#11), `resolve` now falls through to a sibling fragment for years no real generation covers (e.g. "BMW 7 Series 2012" → `bmw:730li:gen1`). #17's normalizer stops *new* ones at ingest; existing ones need a re-seed/curation pass.
3. **markibx-connect: 2 pre-existing test failures** (verified present before today's merge): `test_dbpedia_year_range_harvester.py::test_xv10_..._live` (live DBpedia shape) and `test_entity_connectors.py::test_mecha_sources_registered[dbpedia_mecha_construction]` (a `mecha` connector registered with `entity_types=('equipement',)` — looks like a typo). Fix or xfail.
4. **Worktrees + `integrate/plan` branch still exist** under `repos/markibx*/.claude/worktrees/` — remove when satisfied (`git worktree remove`).

## Must-know gotchas (each cost real time this session)

- **Worktree tests import MAIN's code.** Shared `.venv` editable install points at the main checkout. In a worktree run `PYTHONPATH=<worktree>/src <repos>/.venv/bin/python -m pytest` — never `task test`, never reinstall the shared venv. (AGENTS.md §6b.)
- **Deploy pre-flight is now step 1b in the `deploy-vps` skill** — a read-only `create_app()` probe per target venv BEFORE any write. A drifted `main` = coordinated multi-package release; probe every service sharing the venv. Skipping this is what caused the P2-adjacent rabbit hole today.
- **Prod app-build sanity needs env:** `XWBASE_ALLOW_GIL=1 XWJSON_ABI_LIB=/opt/kara-api/libxwjson_abi.so` (xwbase refuses a GIL Python otherwise → false failure).
- **SSH to prod may be blocked by the auto-mode classifier** even with allowlist rules present — needs explicit user go or a permissive session mode. Key `~/.ssh/exonware_riyadh_shukri_rsa`, `shukri@149.104.105.145`.
- **Watchdog restarts services ~every 2 min** → install everything in ONE ssh call, sanity-import before restart. `markibx-api` + `markibx-connect-api` **share** `/opt/markibx-api/.venv` (restart both); `markibx` core installs into **both** `/opt/markibx-api/.venv` and `/opt/mawtarx-api/.venv`.

## Verify quickly

```bash
# local (markibx main)
cd repos/markibx && ../.venv/bin/python -m pytest --no-header -o addopts=-q   # 346 pass / 1 skip
../.venv/bin/python -m exonware.markibx.cli --validate-seed
# prod spine
curl -s "https://markibx.com/api/markibx/v1/catalog/resolve?make=Toyota&model=Camry&year=2021&market=GCC"
```
