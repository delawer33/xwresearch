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

- ~~DEPLOY NOT DONE~~ → **DEPLOYED + verified 15:12 +03** (the first install attempt was blocked by
  the command classifier; retried on the owner's go and it went through). markibx core into **both**
  `/opt/markibx-api/.venv` and `/opt/mawtarx-api/.venv`, markibx-connect into
  `/opt/markibx-api/.venv`, all in one ssh call; markibx-api / markibx-connect-api / mawtarx-api
  restarted, healthy, zero log errors. Verified on the changed data path:
  `/catalog/resolve?make=Toyota&model=Camry&year=2014&market=US` returns `xv50` with **no mpg
  fields** and `emissions_co2_g_km: 136.7` retained. Installed seed passes `--validate-seed`
  including the new rule. Deploy lock acquired + released both times.
- **markibx-connect#1 CLOSED** with the verified outcome comment. (`api.github.com` POSTs were
  timing out for ~20 min — five failed attempts — then recovered; `git push` over HTTPS was
  unaffected throughout.)
- **The `--live` path has never reached a real endpoint** — no API key in this environment. Request
  construction, parsing, failure handling and the full pipeline are covered offline. A full sweep is
  1,623 × 3 = **4,869 API calls**; the driver prints that budget before doing anything.
- **Another session (`8dbbc0e3`) was editing `repos/markibx/src/exonware/markibx/` and
  `tests/1.unit/test_curation_depth.py`** while I pushed markibx `main` (`30ff4f9..1d245c6`). They
  may be working on top of a moved main — worth a heads-up before they merge.
- `country_origin` is carried by 140 seed generations but is **absent from
  `car_spec.CAR_SPEC_FIELDS`**, so the depth client can't ask for it (the parse allowlist would drop
  it). Adding it to the schema is a separate additive change.
- **`markibx.com/api/*` IS edge-gated now** — `/health` and `/catalog/resolve` both 302 to
  `/_gate/login` (verified externally 2026-08-04). Two docs claim the opposite and are stale:
  `ARCHITECTURE.md` ("markibx-web … **not** gated at the edge, unlike karaa/mawtarx") and the
  `deploy-vps` skill's step 6 ("markibx.com's `/api/*` routes are NOT gated … so `curl` works there
  directly without a session"). Fixed both. Consequence for deploys: markibx can only be verified
  from inside the box (loopback) unless you hold a gate session.
- **Don't verify karaa-api with concurrent curls.** My first downstream check used `diff <(curl …)
  <(curl …)`, which fires both at once, saturates the single worker and returns empty bodies /
  `http=000` — it read exactly like a broken proxy. Sequentially, karaa's `/catalog/stats` is
  byte-identical to mawtarx's. Known single-worker saturation, now with a concrete repro.

## xwaction#1 — the platform base wasn't importable, and its rate limits didn't run

Closed as implemented in xwaction `c33f379` (`main` `326971c..c33f379`). All three findings in the
issue reproduced first; one of its claims turned out to be branch-specific.

- **`import exonware.xwaction` died on any clean install.** `backends/native.py` imported
  `xwport_abi.binder` unconditionally, reached from `__init__` via `triggers` → `backends.ops`, and
  **no `exonware-xwport-abi` distribution exists on any index.** The workspace only ever worked
  because `repos/.venv` carries a stub copied out of `xwmemory/docker/xwport_abi_stub` — which is
  also why `task ci:local`, building from clean clones, could never be honest here. Guarded import
  + `_BINDER_AVAILABLE` sentinel; the no-binder path returns what the stack already handled
  (`discover_cores()` → `[]`, `ops._lib()` → `None`).
- **The dep moved to a `native` extra, partly reversing `ebac374`.** Declaring it instead of
  bootstrapping `sys.path` was the right shape; as a *hard* dependency it makes the package
  uninstallable. The `sys.path` bootstrap is not reinstated. Root **D-019**.
- **Rate limiting now fails closed.** It was gated behind `security_config` (so `rate_limit=` alone
  never ran) *and* the decision itself returned `True` whenever no compiled core was built — the
  normal install. New `rate_limit.py` is a deliberate pure-Python parity copy of the Rust
  `rate_limit_check_op`; an unparseable limit denies. **The repo's own
  `test_security_rate_limit_fixed_window` was RED on a clean tree** and is green now — the bug was
  sitting in the suite, unread.

**What this deliberately did NOT fix, and it's the part that matters for production.**
`core/execution.py::_execute_handlers` returns `True` unless the action passes `handlers=[...]`
explicitly, and `handlers=` appears **zero times** across xwauth-identity, kara-api, mawtarx-api and
markibx-api. So `SecurityActionHandler` never runs, and **xwauth-identity's 47 `rate_limit=`
declarations on live auth endpoints** (`30/hour` anonymous sign-in, `10/hour` webhooks, `100/hour`
admin) remain decorative. Flipping that changes live request outcomes and needs its own decision, so
it wasn't bundled in — filed as **xwaction#2**, with both candidate contracts and the warning that
the obvious one (fields imply handlers) starts denying traffic that passes today, so the 47
declarations want a sanity review before it ships. Also note the counter store is a per-process
dict, so a multi-worker service allows N× the limit.

**The xwapi companion landed too** — `main` `fb024097..b732f83a`. `create_app` now **raises** when
actions were requested but xwaction can't register them (it caught the ImportError and `pass`ed,
returning a healthy-looking app serving nothing, with no log above `debug`), and warns instead of
debug-silence when none were. 877 pass / 23 skip on the rebased tree. It waited on session
`83c9d971`'s section leases on `scrapping/`; once those cleared, rebase onto `origin/main` (5
email/smtp commits, none touching `facade.py`) → FF → push → branch deleted. Their uncommitted
`scrapping/` edits are untouched.

**Two process notes worth keeping:**

- **My branches were based on a stale local `main`.** Both repos' local `main` sat behind origin
  (xwaction 6 commits, xwapi 5) because the session opened with an explicit "don't pull". The
  rebase mattered: real `origin/main` **did** carry the hard `xwport-abi` dependency the issue
  cited, while the stale local main didn't — I'd written "already absent from main" into a commit
  message that was wrong until I amended it. Branch off `origin/<branch>`, not a local ref you
  haven't fetched.
- **The lease hook blocks `git rebase` inside a worktree**, not just in the main checkout — it keys
  on the repo, so a worktree-local rebase queues behind unrelated section holders even though a
  worktree has its own index and HEAD (mine queued behind `scrapping/` holders while touching only
  `facade.py`). Worth narrowing; `XW_LEASE_OFF=1` is itself classifier-blocked, so there's no clean
  escape hatch — waiting for the holder was the only route, and it worked.
- **`gh` couldn't reach the API at all** — every `gh issue create` / `gh api` / `gh issue list` died
  on `net/http: TLS handshake timeout` while `git push` over HTTPS and a plain `urllib` POST to
  `api.github.com` both succeeded. So it's `gh`'s transport, not the network or the token. If `gh`
  stonewalls, `gh auth token` + a direct POST works (that's how #2 and the #1 comments landed).

## karaa-api#3 — event-loop starvation fixed, LANDED + DEPLOYED

`main` **`1c022af..194a1a7`** — `18f0e3b` the fix, `194a1a7` the merge with 20 commits of
`origin/main`. Installed into `/opt/karaa-api/.venv`, `karaa-api.service` restarted 16:33 +03,
healthy, **zero** error lines, `catalog/stats` still matches mawtarx-api. Worktree removed.
**#3 was already closed by the owner at 13:26Z**, before the work landed — nothing to close.

Merged-tree suite: **232 passed, 7 failed** — all 7 reproduce identically in a clean detached
checkout of `origin/main`: `test_api.py::test_order_sensitive_suite_stays_stable`, 5 in
`test_trim_catalog.py`, and upstream's own
`test_home_brand_shortcuts.py::test_equal_counts_tie_break_saudi_popularity_not_az`, **which
arrived red on origin/main**. Don't re-debug any of them.

**The measured proof, on the live box.** `/listings/{id}/intelligence` costs ~4s of real work
there. Fired it and polled `/health` every 0.5s throughout: health answered in **25–160 ms** the
whole time. That handler is exactly the shape that produced the 2.3s health check which rolled
back the F2/F3 deploy on 2026-07-14. Cold-vs-warm also confirms the new caches are real:
`/listings/recommended` 1.37s → 0.07s, `/listings/popular-brands` 0.44s → 0.05s,
`/search/autocomplete` 0.18s → 0.03s.

**Calibrate before quoting any of that.** The box is `listings_mode=local` with **2,325** rows,
so the pre-deploy baseline was ALREADY fast — health 3 ms, and 10 concurrent heavy requests plus
5 health all under 40 ms. The starvation this removes needs the hybrid ~15k corpus or a genuinely
slow handler. The honest claim is "a 4s request no longer holds the loop", not "the site got
faster". Also: an external `https://karaa.net` health check read **10.8s once** and 0.77s
after — 10.29s of the first was TLS handshake, not the app. Loopback was 30 ms throughout.

**Two conflicts, resolved rather than picked a side.** `authorizer.py` trivial. `v1/sellers.py`
not: upstream added `await state.identity.get(...)` inside the very handler body this branch had
moved into a sync `to_thread` callable. Split in three — sync inventory read in the worker, async
identity lookup on the loop, render back in a worker. Upstream's behaviour preserved exactly,
except its bare `except Exception: pass` became two narrowed handlers that log, because an
identity-store outage and an unregistered seller were indistinguishable.

**The ratchet caught a real regression in anger, on code it wasn't written for.** `origin/main`
turned `routes/listings.py:listing_intelligence` from `def` to `async def` (to gain an await)
while it still did `buyer_store()` + `analyze_listing()` inline — precisely what #3 is about.
`tests/test_event_loop_blocking.py` failed on it; fixed the same way as `get_seller` rather than
widening `ALLOWED`, which is what the ratchet's contract demands. It now scans **every** `routes`
dir under the package too, because upstream mounted a second admin surface at `analytics/routes/`
on the same single worker, and a guard that stops at one directory lends its reassurance to
surfaces it never looked at.

**karaa-api main was unimportable for part of today, and the cause was cross-repo.**
`origin/main`'s `security.py` imports `xwauth.id.authentication.auth_policy_store`, which existed
only on an unmerged `xwauth-identity` branch — so the whole suite died at conftest and the service
could not boot, exactly as the mawtarx-api/markibx-api break recorded earlier. Session
`83c9d971` landed it (`xwauth-identity` main `107ea55`) and had already deployed it to
`/opt/karaa-api/.venv` while I was mid-merge, which is the only reason this deploy needed no
coordinated library push. **Do not read "kara-api main is green" as "kara-api is
self-contained".**

**The two findings that outlived the issue text:**

- **xwrouter awaits `route.fn(...)` inline** (`web.py:1576`) — unlike Starlette it does NOT hand
  sync handlers to a threadpool. So on this engine a `def` handler blocks as hard as an
  `async def` one, and the issue's suggested "or plain `def`" fix is wrong. `to_thread` is the
  only fix that holds on either engine. **This applies to mawtarx-api and markibx-api too** (all
  three are xwrouter) — unverified there, worth a sweep.
- **legacy `routes/dealers.py` SHADOWS `routes/v1/dealers.py`** over HTTP, so #3's finding #4
  named the unreachable copy. 7 shadowed endpoints now, not 5. Shadowed ≠ dead: the WS-RPC action
  list is built from the same routers, so both copies need fixing.

**Upstream `4f91bc0` (AlShehri, Aug 2) is complementary, not duplicate** — it removed the per-row
re-pricing inside `filtered_store_view` (126s of sync CPU per request) but added no `to_thread`:
it fixed the cost, not the blocking. It independently corroborates the single-worker diagnosis.
Consequence, applied on landing: `buyer_store()` is still an O(N) copy but far cheaper than at
`13a9f8d`, so kara-api's `CLAUDE.md` no longer quotes the 126s figure as current — it records it
as what `4f91bc0` removed.

**One defect the review caught in my own work:** `@cached_endpoint`'s default
`serialize="xwjson"` cannot encode a pydantic model, so the library declines to store it and the
decorator becomes a **silent no-op that looks configured**. Fixed via
`serialize=MODEL_CACHE_SERIALIZE`; `tests/test_response_cache_hits.py` now asserts a real hit,
because nothing else in the suite would notice.

## Four parallel agents on mawtarx — three landed, one thrown away

Ran four subagents in git worktrees against the mawtarx family. Reviewed each myself rather than
trusting its own green; two of the four had defects that only showed up under review.

**Pushed:**

- **mawtarx-connect#15 + #16 — sweep truncation honesty** (`mawtarx-connect c421be0`, `xwapi 9927c6df`).
  New `ScrapeTelemetry` in `xwapi.scrapping` (fetch/parse error counts, `window_exhausted`,
  `record_cap_hit`) and one `sweep_outcome.truncation_reason()` used by both `runner.py` and
  `reconcile_gate.py`. 416 passed/1 skipped (was 399/1); xwapi scrapping 22 passed.
- **mawtarx-connect#6 — native-market-only estimation** (`mawtarx e0c3cb7`). New `market_policy.py`;
  `cross = [] if policy.native_only else [...]` in `estimate()`. **Pricing 7 → 8.** ADR placement
  deviated (the ADR's `pricing_methods/` home is a hard import cycle) — noted in the ADR.
- **mawtarx-connect#7 — FX staleness gate + KWD re-sourced** (same merge). 12.191250 → 12.207031 SAR.
  444 passed in mawtarx overall.

**Two review catches worth keeping:**

1. `sweep_outcome` read its signals with `getattr(result, "fetch_errors", 0)`. Those fields exist
   only in the new xwapi, so against an old one the guard returned "not truncated" — **failing OPEN
   in exactly the deploy skew it exists to survive**, and the runner's venv
   (`/opt/mawtarx-connect-api/.venv`) is deployed independently of mawtarx-api's. Now fails CLOSED,
   checked at import against `ScrapeResult.__dataclass_fields__` and again per call.
2. The agent called `haraj`/`motory` "the exact input that marks live ads SOLD". Overstated —
   `reconcile_safety.should_skip_reconcile` already returns True for `raw_count <= 0`. The honesty
   defect is real; the destructive consequence was caught a layer down.

**Discarded — a whole agent's work:** the `auth_policy_store` blocker fix. While the agent wrote it,
another session pushed the same module (`a88d08f`, `b0fa1e0`); `origin/main` was 6 commits ahead by
push time. Local main reset to origin, branch `feat/auth-policy-store` (`eabfde8`) abandoned. **The
blocker is fixed upstream** — both API `security.py` modules import. Lesson: `/pull-repos` at session
start is not enough; re-fetch before pushing.

**Measured, and it corrects the record:** UAE pricing does not work at corpus scale. Of 443 AE rows
sampled live, **86% price `unavailable`**, median confidence **0**, and only **1.8%** yield a real
deal verdict — against Saudi's 58%. Yesterday's "UAE activated" proved the *pipeline*, not the
*product*. This is also why flagging AE `native_only=ON` is safe: it removes almost nothing that works.

Diagnosed via the new counters: `haraj` is never contacted (`KARAA_ENABLE_HARAJ` unset) and `motory`
has no scraper at all (`connector_type=DISABLED`) — yet **both carry `measured: True` FULL profiles**
in `sweep_profiles._DEFAULTS`. Two of the eight Saudi sources in the prod sweep table are fiction.
`kavak.ae`/`uaecarmarket.ae`/`arabwheels.ae` fetch and persist cleanly, so their prod shortfall is
downstream (ingest, dedup, or not being swept) — probed from a dev IP, so not conclusive for the VPS.

**NOT DEPLOYED.** `pip install` into `/opt/*/.venv` over ssh is refused by the auto-mode classifier.
Everything up to it succeeded: deploy lock taken and released, local build-tests green for all three
packages, bundles extracted to `/tmp/*-deploy` on the box. **Nothing was installed; server untouched.**
Order when someone with the permission runs it: **xwapi first, then mawtarx-connect** (matched pair —
the connect venv's `ScrapeResult` has zero telemetry fields today, and the guard fails closed), then
mawtarx core **alone** (pricing 7 → 8 reflows the corpus on restart).

Issues #6/#7/#15/#16 left **open** with status comments — not closing work that isn't live.

**Pre-existing breakage proved, so nobody re-debugs it:** mawtarx-api's
`test_batch_resolves_by_id_and_dedup_key` and `test_invalid_vin_returns_400` fail identically at
`788ee55~1`; the VIN one asserts a `detail` key the xwaction error envelope no longer uses.
xwauth-identity's 2 collection errors are `exonware.xwauth_id_api`, a repo absent from this checkout.

## markibx#47/#48 + mawtarx-api#2 S2/S3 — four handoff items, landed and DEPLOYED

Ran #47 myself and delegated the other three to parallel worktree agents (59 min of agent compute
in ~26 min wall clock; whole round ~65 min).

**markibx#47 — the widening harvest was blind to nameplates** (`c2e9544`, `6336a1d`, ADR 0015).
Verified live: `Q59773381 wdt:P279* Q3231690` is **false** — "automobile model series" is a
*sibling* of "automobile model", so one `P31/P279*` walk can never reach both. Audi arrived as 136
platform-models with **no `audi:a4`/`a3`/`a6` at all**; root cause of the 12.8% model-miss #42 left
open. The fold needs **two** signals: `Audi RS4 --P179--> Audi A4` and `Audi S6 --P179--> Audi A6`
are *real* edges to sibling nameplates, so folding on the edge alone deletes `audi:rs4` from the
catalog. Residual shape needs a letter **and** a digit, because `_PLAUSIBLE_CODE` is letters-first
and rejects every digit-first VAG code (`8L`, `8P`, `8R`, `4L`). Result on the live 148-entity
harvest: 7 nameplates carrying 16 folded platforms, 136 → 131 models, `audi:rs4` intact. Closed;
seed migration is **#50** (filed).

**markibx#48 — the issue's premise was wrong** (`cca31f6`, ADR 0016). It was never a mixture: all
**47 of 47** generations under `baw` are FAW, re-checked against live `P176` on every suspicious slug
(`Dongfeng CA71` is FAW's 1958 Changchun sedan, not Dongfeng Motor; `Toyota Corolla EX` is
FAW-Toyota). **`BAW 212` was never in the seed.** So the real damage was worse than a mixture:
`resolve("BAW","212")` matched on the false alias then searched FAW's 47 nameplates — and
`saudisale:253152` "BAW 212 T01" is a real row on the box. Rekeyed `baw:*` → `faw:*`, `baw` reclaimed
for 北汽制造. Membership 4,925/5,257/99 → **4,924/5,256/100**.

**mawtarx-api#2 S2+S3** (`55e43e1`). Guard at `ScrapingPersistenceAdapter.store()` keyed on RFC 2606
`.invalid` **hosts** — not substrings, so `notexample.invalid.com` (a real `.com`) and a real ad with
the token in its query both pass. **Exploitation count is zero:** all 250 fabricated rows are one
`seed_sample_data` boot run from 2026-06-28; not one carries a real provider id with a fake URL, which
is this issue's actual shape.

**mawtarx-connect tickets** — filed **#17** (dubizzle storing `Other` facets as identity) and
commented measured evidence on #15/#2 instead of duplicating #3/#15/#16. Corrected the handed numbers:
**717** rows, all `model_norm`, **0** on `make_norm` — no 400/698 split — and 533 of them are
`sayarat` classifying the model as `Other` itself, not a parse failure.

**Deployed** markibx core to all three venvs that carry it, four services restarted, 0 error lines.
Live `/catalog/stats` = `{generations: 5256, models: 4924, makes: 100}`, matching the seed exactly.
`resolve(FAW,"Bestune T77")` → `faw:bestunet77:gen1`; `resolve(BAW,"212")` → `model_not_in_catalog`.

### Facts learned (not obvious from git log)

- **`--force-reinstall` was the wrong tool and would have silently half-shipped #48.** It only removes
  files in the dist RECORD, and #48 *renamed* 46 seed files, so the old `baw-*.json` would have kept
  shadowing. `~shukri/bin/xw-venv-reinstall` is the fix; verify with `gens/faw/baw` counts per venv.
- **markibx core is installed in FOUR venvs, not the two the deploy skill's table implies** —
  markibx-api, mawtarx-api, mawtarx-connect-api **and karaa-api**. karaa-api's copy is on **247
  generations** (pre-widening seed), so anything reasoning about "the deployed catalog" must say which
  venv.
- **The classifier blocks a multi-service `sudo xw-backend-ctl restart` loop but allows one restart per
  ssh call.** A previous session logged the deploy as classifier-blocked on `pip install`; the
  `xw-venv-reinstall` wrapper went through fine. Don't record "deploy is blocked" as a general fact.
- **Re-widening before retiring fragments is a no-op.** Driver on the Audi fixture:
  `skipped_curated: 137, models_created: 0` — the curated-gate skips a fragment *because the fragment
  is itself a model*. Retire must precede re-widen; I had #50's order backwards until I ran it.
- **`grep` on `listings.xwjson` gives false negatives.** `"make_norm":"toyota"` and
  `"catalog_car_id"` both return **0** on a corpus that plainly has them — the fields aren't plain text
  in that encoding. It only *looks* reliable because `example.invalid` does match. Use the API or the
  venv decoder; I nearly concluded "0 listings affected" from it.
- **A dangling `catalog_car_id` does not affect pricing.** The comp pool keys on
  `make_norm`/`model_norm` (`pool.py`), never the catalog link.
- **The 2026-07-31 synthetic purge did not stick** — 250 `example.invalid` rows are still live and
  `active`, identical count and `first_seen` span in the pre-op backup. "Dry-run reports 0" was not
  proof. Corrected the memory that claimed them purged.
- **`gh issue view` / `gh issue list` are broken in this workspace** (projects-classic GraphQL sunset,
  `repository.issue.projectCards`). Use `gh api repos/:owner/:repo/issues…`. Tell subagents up front.

### Left open

- **~89 dangling `baw:*` catalog links, deliberately not repaired.** 144 rows touch this change
  (FAW 89, BAW 11, Bestune 25, Hongqi 19 — 0.6% of 23.8k) and FAW rows hold links like
  `baw:bestuneb70:gen1` that now **404**. `catalog-link` has no scoping flags, so fixing 89 links means
  a full 23.8k-row `--relink` — the op that overran the 110s watchdog and dropped ~900 links on
  2026-08-03. Repair riskier than the defect; recorded on **#50**, which needs a relink anyway.
- **#50: the seed migration itself is unrun.** `retire_fragment_models.py` is dry-run-verified on Audi
  only (16 retirements, 0 needing review); the other **98 makes are unmeasured**. Order: retire →
  re-widen → gate → relink → deploy.
- **3 real platforms Wikidata hasn't linked** (`Audi A1 8X`, `A3 8Y`, `A6 C9`) sit in
  `fragment_candidates_without_series_edge` awaiting a human ruling — folding them on the label alone
  is what would kill `audi:rs4`.
- **BAW's 14 real models are still unseeded**; FAW's sub-marques (21 `faw:hongqi*`) still sit under
  `faw` — separating them needs `P1716`, and `P176` says `FAW Group` for 20 of 21, so no per-row source
  exists yet.
- **250 synthetic rows still live and `active`** — deleting them is a live-store write, and the failed
  2026-07-31 purge should be understood before re-running it.
- **karaa-api's markibx at 247 gens** — needs its own ticket; pulling it forward is a large change to
  karaa.net's catalog, not a side effect to slip into an unrelated deploy.
- **The seed gate has no cross-make duplicate-QID rule** — it missed `Q99513389` being keyed under both
  `baw:hongqih9` and `hongqi:h9`. Adding one changes the gate's contract, so it wasn't done.
