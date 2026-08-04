# Done today — 2026-08-04

(2026-08-03's entry was overwritten by request; it survives in git at `4569261`.)

## markibx-connect#1 — the ADR 0010 depth engine finally has a driver

~970 lines of reviewed corroboration machinery sat in markibx's core unreachable behind one
`NotImplementedError`. Built the two missing halves in markibx-connect (`675b9da`, `8155438`):

- `llm_depth.py` — a concrete `ILlmClient` (`LlmSampler`), duck-typed against the core Protocol
  with an injected transport, so all 27 of its tests run offline with no key.
- `scripts/run_depth_extraction.py` — walks the generations with nothing in `fields`, poorest make
  first, deterministically (so raising `--limit` **resumes** a sweep rather than reshuffling it),
  through the core's existing adapter → engine → writer → review queue. No pipeline logic
  reimplemented. Per-make completeness before/after.

**The issue's proposed validator would have destroyed correct data.** It specified
`city ≤ combined ≤ highway`. That ordering is a combustion-car habit — an EV is most efficient in
town, so its city MPGe is the *highest* of the three. Measured on the committed seed: the specified
rule flags **46** rows of which only **10** are actually broken, so it would have withdrawn 36
correct electric generations (`bmw:i3` 124/113/102, `fiat:500e` 121/116/103). The real invariant is
that combined lies *between* city and highway (it's a 55/45 harmonic blend). Implemented that;
markibx ADR 0014 + root D-018 record why.

Everything else in the issue reproduced exactly: 22 distinct fact fields populated of 376, 1,623
generations with nothing in `fields`, 363 mpg rows.

## markibx core — fuel-economy coherence as a real rule (`1d245c6`)

Put the cross-field rule in the **core**, not in the EPA ingest that had the bug, because two
callers in two repos need it and the cascade runs core → connect. `fuel_economy.py`, plus:

- 4th validate-seed soundness rule `incoherent-fuel-economy`; grandfathers **nothing** (every
  offender was repairable).
- `PromotionWriter.promote` now **refuses** a write that would leave an impossible triple (new
  additive `blocked` field); `CorroborationRunner` files that as a `physically_incoherent` review
  item instead of reporting a promotion that never happened.
- 30 facts withdrawn from 10 generations via the logged `demote` path. `emissions_co2_g_km` on
  those rows **kept** — suspect by association but not proven wrong (#46's precedent).
- EPA ingest: the fuel-economy group now comes from **one modal row** as a unit, CO₂ from that same
  trim. An incoherent modal triple drops the group and is reported rather than seeded.

## Facts learned (not obvious from git log)

- **`check_soundness` never runs on the API boot path** — only from the CLI (the D-012 deploy
  gate); boot uses the fail-soft loader. So adding a soundness rule cannot take a service down.
  Worth knowing before adding a 5th.
- **Two definitions of "identity-only" coexist and differ by 162 rows.** The driver's target set is
  "nothing in `fields`" = 1,623; `markibx depth` reports 1,461 because `curation_depth` also counts
  a provenance-tagged **year span** as a fact (it lives on the top-level `year_*` attributes, not in
  `fields`). Both are right; don't reconcile them. Pinned in the driver's docstring (`8155438`).
- **`test_rerunning_the_ingest_against_the_same_fixture_changes_nothing` (markibx) can never pass.**
  It resolves paths via `parents[6]` and a worktree hardcoded as `mkx-4`: it `IndexError`s from a
  plain checkout and skips from any other worktree. It is neither passing nor meaningfully failing
  today — someone should re-point or delete it.
- **`xwapi.scrapping.HttpFetcher` is GET-only**, so an LLM POST can't reuse it. Reused its
  `TokenBucketRateLimiter` and kept a ~15-line urllib POST locally (the idiom
  `spine_ingest/epa_specs.py` already uses). A `post_json` on `HttpFetcher` is the right long-term home.
- **No LLM client exists anywhere in `xw*`.** The `xwauth-connect` `openai.py`/`anthropic.py` files
  are IdP federation, not model APIs — don't grep-and-assume.
- **Pre-existing test breakage, proven not assumed** by baselining the same files in a clean
  detached checkout: markibx 8 failures (`test_spine*`, `test_spine_seed_gcc_identity*`,
  `test_toyota_ingest_resolve_integration`), markibx-connect 2 (`year_harvester is None`). Suites
  otherwise 652 and 367 pass.

## Left open

- **DEPLOY NOT DONE — the whole reason to care.** The install ssh call was blocked by this session's
  command classifier. Both venvs (`/opt/markibx-api/.venv`, `/opt/mawtarx-api/.venv`) still carry
  `combined_mpg` on `toyota:camry:xv50` and have no `fuel_economy.py`, i.e. **the dev box is still
  serving the 10 impossible triples.** Everything is staged and pre-flight-probed on the box
  (`/tmp/markibx-src.tar.gz`, `/tmp/markibx-connect-src.tar.gz`; all three apps import OK on both
  venvs). It needs: `pip install` markibx into **both** venvs + markibx-connect into
  `/opt/markibx-api/.venv` in ONE ssh call (2-min watchdog), then restart markibx-api,
  markibx-connect-api, mawtarx-api. Deploy lock was acquired and released cleanly.
- **markibx-connect#1 left OPEN**, deliberately — code is landed and pushed, but the seed repair
  isn't live. My outcome comment could not be posted: `api.github.com` POSTs time out repeatedly
  (reads and `git push` over HTTPS work fine). Comment text is saved at
  `scratchpad/issue-comment.md` — post it when the network settles.
- **The `--live` path has never reached a real endpoint** — no API key in this environment. Request
  construction, parsing, failure handling and the full pipeline are covered offline. A full sweep is
  1,623 × 3 = **4,869 API calls**; the driver prints that budget before doing anything.
- **Another session (`8dbbc0e3`) was editing `repos/markibx/src/exonware/markibx/` and
  `tests/1.unit/test_curation_depth.py`** while I pushed markibx `main` (`30ff4f9..1d245c6`). They
  may be working on top of a moved main — worth a heads-up before they merge.
- `country_origin` is carried by 140 seed generations but is **absent from
  `car_spec.CAR_SPEC_FIELDS`**, so the depth client can't ask for it (the parse allowlist would drop
  it). Adding it to the schema is a separate additive change.
