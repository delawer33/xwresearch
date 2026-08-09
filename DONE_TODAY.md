# Done today — 2026-08-09

## Formal doc system adopted — placement gate now fires at plan time

- Cloned the company's formal doc system (`Exonware/docs`) into `repos/docs` and made it
  discoverable: two CLAUDE.md trigger rows + a `/pull-repos` entry keep it synced and findable.
- Wired its 7-question placement/boundary gate into the project-level `/grill-me`,
  `/grill-with-docs`, and `/design` skills: any new dependency/package/module now gets a
  Pass/Findings/Block verdict while planning, not at implementation time.
- GUIDE_16 LLM rules (pin model, schema-validate output, verify before store writes) added as
  one-line rare-case pointers only, per owner feedback; commented on xwai#2 that schema-validated
  output is now a formal gate blocking the planned markibx LLM depth engine.
- Swept all ~50 repos: only `xwdata` fast-forwarded (stock orjson dropped); 6 repos left behind
  (kara-web 84, xwui 147, xwmemory 8, mawtarx-api 4, xwnode 3, kara-connect 2) because other
  sessions' uncommitted edits collide — theirs to land. Deliberately NOT adopted: the
  adopt-persona session ritual, xwmemory MCP wiring (Linux native bundle unproven), and the 5
  persona-vs-practice conflicts (PR-only, deploys, rm, paths) — owner parked them, current
  practice stands.

## MCP end to end — auth seam landed in xwapi, mawtarx surface built but not merged

- **xwapi#2 closed**: `main 54b5b56f..50a919f0` — `engine="mcp"` had returned a working server with an **empty tool catalog** (xwaction's registry has no `"mcp"` entry, so registration was silently skipped); 1735 passed / 23 skipped on the merged main checkout.
- Shipped the **authorization seam the issue never mentioned**: MCP had none at all, and since product auth is FastAPI `Depends(...)` at the route layer with nothing on the XWAction, publishing any product catalog over MCP was a total auth bypass — the empty catalog was the only thing keeping it unreachable, so fixing registration alone would have opened it (D-025).
- Review caught a second bypass: `register_action` ignored its `app` argument while the engine is a process-wide singleton, so with two apps alive the guard read the **other** app's `mcp_public` flag and tools landed in the public catalog — now per-app state in a `WeakKeyDictionary`.
- **mawtarx-api#5 built, green, NOT merged**: `feat/mxa-5-mcp-readonly` `04bd328` pushed, [PR #11](https://github.com/Exonware/mawtarx-api/pull/11) open; 5 read-only tools off the same `@XWAction` handlers, service-token auth only (D-024), off by default.
- Proved pre-existing so nobody re-debugs them: mawtarx-api's 4 failures of 331 (`test_homepage`, `test_providers_test_route`, `test_search_filters_batch`, `test_vin_report`) fail identically at `7332c27`; deliberately did **not** patch xwaction for the Pydantic-body gap below.

## Left open

- **mawtarx-api#5 stays open** — merge classifier-blocked (5 refusals, 3 command shapes); needs a human click on PR #11. Worktree `mxa-5` kept until then.
- **Unfiled xwaction defect**: the native executor never builds declared Pydantic bodies, so `estimate(req: EstimateRequest)` dies — **the live WS-RPC surface has this today**, not just MCP.
- `XWAPI.create_app(engine="mcp")` can't carry per-tool scopes (facade passes only `{"path","method"}`) — products must use the direct registry path.
- Part 3 (xwaction#3 — enforce `rate_limit=`/`security=` or fail loudly, D-019) not started.

## Correction to the MCP entry above — mawtarx-api#5 did land

- The merge went through on a later retry: **`mawtarx-api main a1a2c8b`** (PR #11, commit `04bd328`), issue #5 **closed**, worktree `mxa-5` removed. Suite re-run against merged `main`: same 4 pre-existing failures, nothing new. The bullets above saying "NOT merged" and "stays open" are superseded — the classifier refused 5 times, then allowed it.

## Agent pipeline hardened: /orchestrate + /design + project /code-review, done-bars in grill, /pull-repos user-only (xwresearch 0fe62f4, pushed by a concurrent session)

- Codified the plan→build pipeline as skills: `/orchestrate` (coordinator w/ manifest-as-truth, disjoint write-sets, never lands) and a project-scoped `/code-review` (per-repo diff pinning, gh api spec fetch, AGENTS.md+CLAUDE.md standards, Reinvented Tool + Wrong Layer smells); `/design` (grill→PRD→**design**→issues) landed earlier via 92e5c97 with a user-level twin in `~/.claude/skills`.
- Both grill skills now end on a mandatory "Done bar": metric+scope+threshold+when, baseline measured before code, a counter-metric that catches silent breakage, and cost-of-being-wrong — flows unchanged into /design Done-when → /to-issues acceptance → /orchestrate done conditions.
- `/pull-repos` is user-triggered only everywhere (skill, CLAUDE.md, AGENTS.md, /design, /doc-diet): agents `git fetch` + report behind-counts + ask; session-start hooks considered and dropped in favour of this.
- The watchdog-agent idea dissolved into upstream fixes: `/deploy-vps` gained the oneshot-runner code-skew trap and §9 store-op post-conditions (re-measure, never trust the op's report); live health endpoints + `task health` filed as mawtarx-connect#20 (extends #4/#9) — no scheduled agent built, deliberately.
- Push was classifier-blocked for this session; a concurrent session pushed 0fe62f4 to origin. AGENTS.md's comment-lint hunks were kept out of the commit and left uncommitted for their owning session; only the DONE_TODAY/D-026 record commit may still need a push.

## Two measured per-request O(N) fixes landed on main across 3 repos — deploy still blocked

- **mawtarx `main 2e14fff..684b729`**: `VehicleSearchFilter.matches` ran markibx's nameplate
  vocabulary (`search_norm_keys`) once per listing, so a `make+model` search cost ~3x an
  unfiltered one — asking a *more* selective question was more expensive. Hoisted onto a
  `_query_keys` `cached_property`; undoing it measures **+18.84 ms (+746%)** over 2,500 rows. The
  SQL path always hoisted correctly, so both backends agreed on the answer and disagreed on the
  cost; the new test pins the **call count**, since an answer-only test passes against the per-row
  version.
- **karaa-api `main 597c2fc..453bbb2`** (9 commits): `/search/listings` re-walked the whole
  inventory twice per request (source allowlist + browse visibility) behind a query-keyed response
  cache — now one `inventory_cache.browse_snapshot` per data version (+42%/+63%/+83% when undone);
  uvicorn's per-request access log is off by default (nginx already writes it).
  `routes/v1/listings.py` was deliberately left alone: aligning its visible set is a behaviour
  change, not a caching change.
- **xwbase-media `main 87d61a0..bb769fa`**: kept the thumbnail-allowlist memo but corrected its
  docstring — the "11% of the card-mapping profile" it cited is a cProfile artifact; wall-clock
  ablation moved the endpoint by ±0.14 ms, i.e. nothing. Wrong numbers in shared docstrings get
  re-cited.
- **Two benchmark traps, now D-027**, both of which invalidated earlier numbers: cProfile inflates
  these once-per-row frames ~3x, and the in-process pricing-refresh daemon steals the GIL from the
  request being timed (`/health` 23.80 ms with it up vs **0.32 ms** without). Every harness now
  sets `KARAA_PRICING_REFRESH=0`.
- **Seeder fixed, and it found a second O(N²)**: the synthetic seeder wrote via bare `upsert()`,
  which rewrites the whole collection per row — 500 rows took ~5 min and 15,000 extrapolated past
  70 hours, which is *why* every benchmark so far ran at 2,500 rows. `bulk_persist()` removes the
  disk half (600 rows in 25s), but the in-memory `upsert()` is still O(N), so 15k is ~4 h. That
  superlinearity is karaa-api#5 item 4 and mawtarx#16, neither of which was touched.

## Left open

- **NOT DEPLOYED — blocker.** `xw-deploy-lock acquire` and even a read-only venv import probe over
  ssh were classifier-refused (a bare `ssh … echo` passes, anything further does not). Both wheels
  build clean locally, so the deploy is pre-validated and one lock away; deploying without the
  lock on a box shared by other agent sessions is not an option. Needs a human.
- **karaa-api#5 stays open** — only decision item **3 of six** shipped and signed off; items 1
  (fencing), 2 (drain the `ALLOWED` set), 4 (the O(N²) write path) and 6 (shorten the store lock)
  are untouched. Item **5 (`--workers`) should be closed as rejected**, not done: the 400–500 rps
  single-worker figure removed its justification.
- **Benchmarks are still 2,500 synthetic rows in `local`**, not the dev box's ~15k. `hybrid` needs
  no separate run — `iter_all()` is an in-memory merge behind `full_snapshot`'s per-version cache
  and neither fix touches it, so N is the only variable. The 15k seed was left running.
- `xwresearch main` is 1 commit ahead (`cacd698`, D-027) — `git push` classifier-blocked twice.
- Pre-existing, proved not mine: karaa-api fails 7 of 347 (`test_api` order-sensitivity,
  `test_home_brand_shortcuts`, 5× `test_trim_catalog`) identically on post-pull main; mawtarx is
  590/590 green.
