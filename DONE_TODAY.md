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

## karaa-api#3 — event-loop starvation fixed, COMMITTED BUT NOT LANDED

`repos/kara-api` worktree `.claude/worktrees/ka-3-event-loop`, branch
`perf/unblock-event-loop`, commit **18f0e3b**. Not merged, not pushed, not deployed; **#3 left
open**. Suite 175 pass; the 6 failures in `test_api.py::test_order_sensitive_suite_stays_stable`
+ `test_trim_catalog.py` are **proved pre-existing** (identical in a clean detached checkout at
`13a9f8d`) — don't re-debug them.

**Why it didn't land: local `main` is 20 commits behind origin** — the same trap the entry above
records, twice in one day. A trial merge onto real `origin/main` leaves **2 conflicts**:
`authorizer.py` (trivial — upstream's `ANALYTICS_SCOPES` vs my `logger`) and
`routes/v1/sellers.py` (**not** mechanical: upstream's `get_seller` now does
`await state.identity.get(...)` inside the handler, and my refactor moved that body into a sync
function for `to_thread` — the resolution has to split the awaited identity lookup from the
offloaded inventory scan). Resolving security-adjacent auth code blind at session end, then
deploying it, is how the 2026-07-15 stale-deploy incident happened.

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
Consequence for the merge: `buyer_store()` is still an O(N) copy but far cheaper than at
`13a9f8d`, so my comments calling it "the expensive half" should be toned down on landing.

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
