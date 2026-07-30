# Done today — 2026-07-27

## Ecosystem sync

- Fetched all ~40 repos under `repos/`. Fast-forwarded kara-api, xwencrypt, xwgis, xwnode,
  xwquery, xwrouter, xwscript, xwsyntax, xwsystem, xwui (80 commits behind).
- Blocked by local dirty files: `kara-web` (15 behind), `xwui` (80 behind).
- Diverged, left untouched: `markibx` (12 ahead), `markibx-api` (7 ahead), `markibx-web`
  (2 ahead) — the catalog-spine work.
- Not cloned: kara-data, karaa-data, karaa-data-backfill, mawtarx-data, muhdocstools.

## Scraper status (verified live on the VPS)

- `mawtarx-scraper-runner` is LIVE and had been up 4 days. **`docs/vps-current-state.md` is
  stale** — its "Scraping — not running in prod" and "stores are static snapshots" sections
  are both wrong now.
- Stores are live-updating: `listings.xwjson` 62.7 MB (fresh), and
  `timeseries/listing_prices.xwjson` exists and is growing — observed price history is accruing
  (1,360 listings now have ≥2 price observations).
- karaa-api is `listings_mode=local` serving **2,286** listings while mawtarx holds **18,569**.
  The scraping is not reaching karaa.net.

## Data quality audit (18,569 live listings)

- Numeric health good: 0 dedup collisions, 1 bad year, 10 sub-1000 prices, 2 absurd mileages.
- `status` = active on 100% of rows (nothing can go sold — reconcile is hardcoded off).
- `vehicle_identity_id` empty on 100% — designed, no resolver exists.
- `condition` unknown 87%, `seller_type` unknown ~49%, `vin` 1%.
- Enum sprawl: 63 body_type / 31 fuel_type / 48 transmission distinct values — a lookup-table
  coverage gap in `mawtarx-connect/connectors/normalize.py`, not a bypassed code path.
- 92 rows are KWD, not SAR.

## Fixed: saudisale normalization

Root cause was **stale in-memory code**, not missing code. The normalization fixes were deployed
Jul 26 07:31, but the runner process had run since Jul 22 20:49 and Python caches modules at
import — so it executed pre-fix code for 5 days, mangling 3,928 model names into raw Arabic.

Restarted `mawtarx-scraper-runner.service` (16:03). It came back with 8 sources vs the old
process's 7, confirming the staleness. Data rewrites at each source's next daily sweep.

Note: `sudo xw-backend-ctl restart mawtarx-scraper-runner` is denied — the allowlist regex needs
the explicit `.service` suffix.

## Committed elsewhere today (my commits, from git, not this session)

Theme: the markibx catalog spine got real seed data, a console UI, and its fail-soft gap closed.

- **markibx spine seeded with GCC data (#33 2a)** — ranked SA listings by volume
  (8,315 rows → 7,355 after filtering → 945 make/model combos), then seeded the top 80%:
  44 makes, 221 generation identity rows. Identity-only (`fields={}`, `trims={}`), provenance
  flagged SA-volume-derived, **not OEM-verified**. Tests 129 → 158. Review pass logged three
  spec deltas + a `baw`/FAW normalizer bug that belongs upstream in mawtarx-connect.
- **markibx-api D-012 gap closed** — `_prefill_spine` let `require_spine()`'s RuntimeError
  escape as a bare 500, killing the whole connector pull when the spine failed its fail-soft
  boot. Now returns `{skipped: "spine unavailable"}` and the pull still persists catalog rows.
- **markibx-web** — spine console view (#32) + typed API client (#30) merged; `public/xwui`
  now ignored as a symlink too, not only a directory.
- **xwmemory extraction accuracy (#9)** — the bug was **falsified as a model-capacity
  problem**: a 4-model × 2-case bake-off at `temperature=0` extracted correctly every time,
  including the 7B default that produced it, and 9 repeat runs at graphiti's default
  `temperature=1` never reproduced it — it's stochastic. Default `llm.temperature` is now 0.
  No ontology added. 137 → 146 tests. Also: a prior GitHub comment on that issue claimed a fix
  had already shipped that existed in **no branch or reflog**. First CI in the repo was added
  and then reverted.
- **xwrouter 401 header bug** — duck-typed `HTTPException`/`HTTPError` were rebuilt from
  `status_code`+`detail` only, dropping the exception's `headers`, so a 401 raised with
  `WWW-Authenticate: Bearer` lost its challenge on any hand-written route (the `@XWAction`
  bridge carries headers through a different path, so it was invisible there). Found via
  markibx-api's admin-sync tests. Fast-forwarded to `main` and **pushed** (`f200ef0`). The two
  failures in that suite (`test_router_prefer_abi_when_requested`,
  `test_discover_cores_lists_rust_or_cpp`) are **pre-existing on origin/main** — no rust/cpp
  core is built on this box — verified by running them in a clean `origin/main` worktree.
- **Workspace plumbing** — Taskfiles + generated CI workflows for markibx / markibx-api /
  markibx-web; CLAUDE.md refreshes in all three (test-running, unpushed-work, how to actually
  run markibx-api locally — it is *not* in the shared venv; markibx-web's dev server cannot
  run from an xwresearch checkout).

## markibx global-first: grilled the plan, shipped PRD + issues

Design session only — no product code changed. PR [markibx#2](https://github.com/Exonware/markibx/pull/2)
(6 ADRs + `CONTEXT.md` + revised plan, `task test` 157 passed), PRD
[markibx#3](https://github.com/Exonware/markibx/issues/3), and 10 tracer-bullet issues #4–#13.

**The spine has never been deployed.** markibx-api is healthy in prod but `/catalog/resolve`
and `/catalog/browse/*` return **404**, and the prod venv contains **no spine files**. Prod
runs pre-spine markibx. That, not permissions, is why none of the catalog-spine work is visible.

**VPS access was never the blocker** — `shukri` holds explicit `rwx` ACLs on both
`/opt/markibx-api/.venv` and `/opt/mawtarx-api/.venv`, and `/var/www/markibx-web` is `drwxrwxrwx`,
so the SPA can be deployed directly. The 403 is **GitHub push** to `Exonware/markibx-web`, not the
server.

**Prod pricing does not read the catalog.** `DEFAULT_METHODS = ("inventory_comps",)` and the live
mawtarx-api process carries no `MAWTARX_PRICING_METHODS` override (read from `/proc/<pid>/environ`),
so `msrp_depreciation` — the only catalog-dependent method — is off. This is what makes retiring the
legacy catalog affordable, and it killed a compat-adapter design that was pure hedging.

**Where the data actually comes from** — measured live, and it overturned the plan:

| Source | Scale | Verdict |
|---|---|---|
| Wikidata `Q3231690` | 13,780 models | identity only — **6%** carry any year |
| DBpedia `dbo:Automobile` | 15,223 | **80%** carry production years — the real year source |
| EPA bulk CSV | 49,995 rows, 1984–2027 | **97%** carry displacement + cylinders — the real spec source |

- `wikidata_catalog.py`'s docstring claims production years are "reliably present". **False — 6%.**
  Its dimensions claim is also overstated (33%).
- The ingest's SPARQL makes the English label **mandatory**, silently dropping **1,842 models
  (13.4%)**, disproportionately non-Western. One-line fix.
- Wikidata's automobile-model entities **are** generations (real codes XV10→XV80), but market
  variants are separate entities (`Camry (XV80, China)`) — conflicts with D-c, resolved by ADR 0004.
- EPA↔spine match: **10.9% naive, 49.6% structural ceiling** (half the world's makes were never
  sold in the US). The gap is normalisation work.
- **EPA's blind spot lands on GCC**: of 15 common Saudi models, it lacks **Hilux, Patrol, Sunny,
  D-Max, Pajero**. Global breadth and GCC depth are now separate workstreams with different sources.
- **Horsepower is unobtainable free** — Wikidata 0.4%, and `eea_co2_eu` (the only free source
  declaring it) returns `[]`.
- 46 registered connectors, but only **17 car-capable, 14 keyless**. `nhtsa_canadian` returns a
  **4Runner for a Camry query** — no model filter. `rdw_netherlands` is keyed on Dutch licence
  plates, not models.
- `ingest_wikidata_models` exists and is global — but writes **legacy** rows, strips the `(XV70)`
  suffix the spine needs, and is **never called**.

**Stale docs corrected:** markibx's `CLAUDE.md` says "14 commits unpushed" — it is **0 ahead**,
fully pushed. This file's own "Ecosystem sync" entry above says markibx is 12 ahead; that was true
earlier today and no longer is.

Live legacy catalog for reference: **9,634 vehicles, 556 makes, 540 brands**.

## xwmemory #9: extraction accuracy — root cause was temperature, not model size

Fixed and pushed (`2cab805`). The real change is **one line**: `llm.temperature: 0` in
`config/config-ollama.yaml`, threaded through `GraphitiRuntime` into `LLMConfig`. Same 7B model,
no ontology, no prompt changes.

**What the evidence actually showed** — the issue assumed the 7B default was too weak. It isn't:

- 4 models x 2 episodes at temperature=0 (qwen-7b, gpt-4o-mini, deepseek-chat, qwen-72b):
  **8/8 passed**, including the same 7B model that produced the reported bug.
- The same 7B model at graphiti_core's default `temperature=1`, **9 repeated runs: 0 reproduced
  the bug.** So the original failure was one unlucky sample, not a model-capacity defect.
  Temperature=0 is defensible as the fix because it's the only mode that's *testable*, but it was
  never proven to be the specific cause — recorded that way in the DECIDE log, not overstated.

graphiti_core defaults `DEFAULT_TEMPERATURE = 1` and `graphiti_runtime` was never overriding it,
so every extraction call in the project's history sampled nondeterministically.

Shipped alongside: `graphiti_runtime/accuracy.py` (pure scoring harness, always tested) +
`scripts/extraction_accuracy.py` (live-money CLI, gated out of pytest like `live_llm_smoke.py`).
Suite **137 → 150 passed** (+9 mine, +4 from a concurrent merge).

**A GitHub comment on #9 claimed this work was already shipped, and it was fabricated.** It named
`graphiti_runtime/ontology.py`, config edits, a harness and a DECIDE log, with a described live
test transcript. None of it existed — not in the tree, `origin/main`, any branch, the reflog, or
dangling objects. Cost ~an hour to disprove. Recorded in xwmemory's `CLAUDE.md` so the next agent
doesn't build on it. Corrected publicly in a comment on #9.

Reverted my own CI commit (`5df74e9`) at the user's request — it was already pushed, so revert
rather than force-push, since a teammate is actively pushing to this repo.

## Left open

- **dubizzle now sweeps but returns raw=0** — 3 of 8 sources produce nothing (with haraj and
  motory, which are intentionally gated; dubizzle is not known to be). dubizzle is the largest
  source at 5,091 rows.
- `norm_fuel` / `norm_transmission` drop only Arabic junk, so `43`, `19`, `rt` still pass —
  needs a positive allowlist.
- Verify tomorrow that Arabic `model_norm` actually collapsed from 3,928.
- **markibx PR #2 is unmerged**, and issues #4–#13 all reference its ADRs — merge it first or the
  links dangle. markibx-web is still 7 ahead locally with **no push access** (403).
- **Do the frontends render legacy catalog fields?** Unverified, and no Python grep can answer it.
  This is the largest unknown blocking ADR 0003's legacy cutover. markibx.com is also publicly
  ungated, so any external consumer of `/catalog/car/*` would break silently.
- **A wrong generation merge is currently undetectable** — contributing-QID bookkeeping makes one
  recoverable, but nothing surfaces it until issue #12 lands.
- **DBpedia is CC BY-SA**, the only encumbered source, and load-bearing for 80% of year data.
  Share-alike posture undecided (issue #13) while the public API is already reachable.
- markibx's spine is deployable now (issue #4 is unblocked); nothing has been shipped to the VPS.
- **xwmemory has never run against real embeddings.** Every vector in its life has been
  `StubHashEmbedderClient` (768-dim shape, zero semantics) — so retrieval quality, the actual
  product promise, has **no measurement at all**. Ollama isn't even installed on this box. The
  768-dim `nomic-embed-text` embedder lock is an assumption inherited from migrated data, unverified
  against a real embedder. This is the gap I'd close before anything else in that repo.
- **xwmemory cutover still not executed** — FalkorDB remains live; runbook `CUTOVER_20260726_READY.md`
  is written and waiting. Nothing in the workspace imports xwmemory, so it's generating no learning
  until it actually carries the agent memory.
- xwmemory issue #9 left OPEN deliberately — the temperature fix is verified, but a larger-model
  bake-off on a stronger *local* model (14b/32b) was never run, and the fabricated comment means the
  issue's history is misleading to anyone reading it top-to-bottom.
- I reverted the xwmemory CI I'd added, so **that repo still has no CI** — which is exactly what made
  the fabricated-comment audit expensive. Unresolved by choice, not oversight.
