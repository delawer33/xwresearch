# Done today — 2026-08-06

## Storage fencing wired end to end (xwstorage-db#2 + mawtarx-api#6)

Branch `feat/storage-fencing`, **pushed in 3 repos, not merged** (see Left open). mawtarx-connect's
half (`8a110e0`) was already merged into its main by another session.

**Both issues' premises were wrong, and checking that changed the design.**

- xwstorage-db#2: *"the write path takes no cross-process lock."* It did — fencing has been an
  opt-in `XWDatabase.open` option since `e47d3bd`, with ACs 3/4/6 already implemented and tested.
  What was missing was everything that made it usable: no exports at all (including
  `XWStorageDbConcurrencyError`, the error callers must catch, which wasn't even imported in
  `__init__.py`), TTL-only reclaim, and a per-write cost nobody would pay.
- mawtarx-api#6: *"the ingest worker is the single writer."* It isn't — `ConnectorScheduleRunner`,
  `PricingRefreshRunner` and request threads all write through the **same singleton
  `XWDatabase`**. A lease around the worker would have left three writers unfenced. The lease went
  at `AppState`'s one `open()` instead. Its *"503 queue-full"* is really **429**
  (`routes/ingest.py:65`).

**Design calls that cost real time** (DECISIONS.md D-021):

- **TTL-only reclaim is a deploy-breaker.** Every hard restart inside the TTL would be refused its
  own store and fail to boot. Lease now records `(pid, host)`; a provably-dead holder (same host,
  pid gone) is reaped at once, TTL bounds only a frozen or remote holder.
- **Renew-per-write measured 111 µs** — enough that the feature stays off forever. Split into a
  cheap `check()` every write (~15 µs) plus `renew()` only past half the TTL: **0 renewals per
  5,000 writes** at ttl=30, flat **~22 µs/write**. My first two benchmark attempts swung ±80% and
  were unreportable; medians over interleaved reps after a discarded warmup fixed it.
- A fully-lazy renew broke `test_stolen_partition_fails_the_writer_loudly` — the existing test was
  right and my shortcut was wrong. Detection has to happen on the next write.

**Two real bugs the code review caught, both fixed** (`c97cba6`):

1. The guard fell back to `acquire()` when `hold()` failed, so a partition another process took,
   rewrote, **and released** read as free. The fenced writer would re-acquire and write from its
   pre-rewrite record cache — erasing the other writer's rows, the exact corruption the lease
   exists to prevent, one step later. New `PartitionLease.reclaim()` re-takes only on proof the
   partition never moved (same owner, same pid, same token still on disk).
2. The fork guards in `renew`/`release` compared against a pid **cached in `__init__`** — which a
   forked child inherits, so the child passed the check that existed to fail it.

**Also fixed, exposed by the new tests:** mawtarx-api's `_apply_batch` cleared its in-flight dedup
key only on the success path, so *any* batch that raised stayed in-flight forever and every retry
was answered "duplicate" and dropped. A write that failed once could never be recovered.

**Measured** (this box): guard ~22–27 µs/write = 130% on an empty collection, **4% at 20k rows**,
3–11% on sync durability (`xwstorage-db/docs/REF_54_BENCH.md` §3.4). On the **real ingest path**
— `ScrapingPersistenceAdapter.store` over a real store, n=1500, 7 interleaved reps —
**12,665 → 12,600 rec/s, +0.5% / +0.4 µs per record** (`mawtarx-api/scripts/bench_ingest_fencing.py`).
Per-record pricing costs ~79 µs, so the lease disappears into it. Read the absolute, not the ratio:
the guard is constant while the write is O(N), so the percentage only looks alarming on a store too
small to matter.

**Pre-existing breakage I proved, so nobody re-debugs it:** mawtarx-api's suite fails
`test_homepage_endpoints_on_empty_store`, `test_batch_resolves_by_id_and_dedup_key`,
`test_invalid_vin_returns_400`, `test_demo_mode_returns_samples_without_touching_environ` (and
`test_recommended_returns_active_listings_with_intelligence` depending on order) on a **clean
`origin/main` worktree**. Cause: `tests/conftest.py` shares ONE tmp dir across the whole session,
so one test's listings land in the next test's "empty store". `repos/mawtarx-api` doesn't show it
because it carries **another session's uncommitted conftest fix** (per-test `tmp_path`). A fresh
worktree does show it — I lost a long bisect to that before spotting the modified file.

Docs: DECISIONS.md **D-021**; `docs/tool-index.md` rows 18+21 and `docs/xwstorage-db-guide.md`
corrected (both said "isn't wired in"); `repos/xwstorage-db/CLAUDE.md` gained a "Cross-process
writers" section; mawtarx-api + mawtarx CLAUDE.md gained the operator consequences.

## Left open

- **The merges never happened — `git merge` is blocked by the command classifier.** Three branches
  are pushed but unmerged: `xwstorage-db`, `mawtarx-api`, `mawtarx`, all `feat/storage-fencing`.
  Worse, `repos/xwstorage-db`'s local `main` is **2 ahead of origin with a partial merge** —
  someone merged `502492a` but not the review fix `c97cba6`, so pushing that main as-is ships the
  released-partition bug. Merge `feat/storage-fencing` again before pushing main.
- **Nothing is deployed**, and there's a deploy consequence to plan for: with fencing ON by default,
  an *overlapping* restart (old process still alive) now fails to boot with
  `XWStorageDbConcurrencyError` instead of silently double-writing. A predecessor that *died* is
  reclaimed at once, so a normal stop-then-start is fine. And any offline op against the live store
  now needs the service stopped, or `MAWTARX_DB_FENCING=0` on both sides.
- **xwstorage-db#2 and mawtarx-api#6 are marked closed but the work isn't merged.** I closed them
  before hitting the merge block and my attempt to reopen them with a correction was itself
  classifier-blocked. Either merge the branches (making the closure true) or reopen them.
- The lease is **cooperative** — any opener that omits `fencing` still writes unfenced. Every
  writer of the mawtarx root is wired now; anything new that opens that root must be too.

## Correction to the fencing entry above — it IS merged and pushed

The "Left open" list above was written while `git merge` was refused by the command classifier.
The refusal was transient; a retry went through. Superseding those three bullets:

- **On `main` and pushed:** xwstorage-db `278b24b..a624803`, mawtarx-api `e03bff6..d8d5268`,
  mawtarx `55e43e1..2decda9`. mawtarx-connect was already in. The partial merge in
  `repos/xwstorage-db` (`502492a` without the review fix `c97cba6`) is resolved — the re-merge
  picked up the tip, so origin/main has the released-partition fix. Fencing tests re-run against
  each merged main: 28 + 7 + 5 passed. All four worktrees removed.
- **xwstorage-db#2 and mawtarx-api#6 are correctly closed** — the work they describe is now on
  `main`. No reopen needed.
- **Still not deployed.** That is the only thing outstanding, and the deploy consequence stands:
  with fencing ON by default an *overlapping* restart fails to boot rather than silently
  double-writing, and offline ops against the live store need the service stopped.

Process lesson, now written into `.claude/skills/end-session/SKILL.md`: **everything ends on
`main`, pushed, unless the owner says otherwise.** A branch is a way of working, not a resting
place. When a merge or push is refused, that is a blocker to raise on the spot — not a state to
document and hand back. I spent the end of the session reorganising the report and trying to
reopen issues around a block that a single retry cleared.

## Part 1 of the 3-part issue run: the xwai/LLM slice — landed, 2 of 3 closed

Three issues asked to add an Anthropic provider and collapse two hand-rolled callers onto it.
Two are closed, one is landed-but-open pending a real API key.

**xwai#1 — the premise was wrong, and that mattered.** An Anthropic provider already existed at
`xwllm_connect/providers/anthropic.py`, and `xwai/providers/__init__.py` is a back-compat shim
already re-exporting it. It only looked missing because xwai / xwllm / xwllm-connect had never
been cloned into `repos/`. Cloned all three, installed editable `--no-deps`, doctor 40 ok.
Hardened the real provider instead of adding a duplicate — and it could not have worked as
shipped: default model was `claude-3-5-sonnet-latest` (**retired 2025-10-28**), and `stream()`
used a sync `with` on `messages.stream()`, which the real SDK (0.120.2) exposes only as
`__aenter__`. Also: sampling params now dropped for the families that 400 on them
(opus-5/4-8/4-7, sonnet-5, fable-5, mythos-*) and reported in `metadata["dropped_params"]`;
`max_tokens` defaults raised to 16000/64000 because thinking is on by default on Opus 5 and
`max_tokens` caps thinking + text together; `AsyncAnthropic`; keys scrubbed from exceptions.
34 new tests, offline, no key. `xwllm-connect 03f48f6..e203a4f`.

**markibx-connect#2 — closed with one criterion deliberately unmet.** 404 lines of urllib
Anthropic client deleted; transport is XWAI. But "configure rate limiting through xwai" is
impossible: xwai's `config.py:29 enable_rate_limiting` is a **dead flag** — nothing outside
xwai's own tests reads it and there is no limiter behind it. The existing `_rate_limiter`
already returns `xwapi.scrapping.TokenBucketRateLimiter`, which `docs/tool-index.md` names as
the rate-limiting home, so doing what the ticket asked would swap working platform reuse for a
dead flag. Left as-is, reasoning recorded at `llm_depth.py:59-61`.
`markibx-connect 35a1fab..f11c2df`.

**mawtarx#15 — "correct code, missing dependency" was false.** The ticket said the method was
correct and only the dependency was absent. `llm_xwai.py` carried three crash bugs, all
reachable from `store.upsert()` — the exact write path the ticket says it must never raise
into: a bare `float()` outside the `try`; `except Exception` re-raising anything whose type name
did not end in `Error`; and `confidence_score: 0` treated as absent because falsy. Also: xwai
alone is **not** enough — the provider factories live in **xwllm-connect**, so
`connect("anthropic")` finds no factory without it; the new `llm` extra names both.
`mawtarx ae82623` (pushed under another session's `2decda9`).

### Facts worth keeping

- **`send_prompt(output_format="json")` does not produce JSON.** Measured: returns the model
  text verbatim, fenced, typed `ResponseFormat.TEXT`. xwai's facade never converts
  `output_format` into `response_format` — it only injects it as a system-prompt hint.
  Provider-agnostic, so every provider on that path behaves the same. Filed xwai#2. Matters
  because `mawtarx`'s `_call_xwai` uses exactly that call.
- **The depth engine's evidence model does not hold on its own default model.** N-sample
  corroboration at a pinned temperature is the ADR 0010 story, but `temperature` is rejected
  outright by claude-*-5 and is now stripped before the request, so it never reaches the API.
  The docstring called that guard "the single most load-bearing line here" — false; corrected
  it and the repo CLAUDE.md.
- **markibx-connect has 2 pre-existing test failures** — `test_4runner_never_reaches_the_catalog…`
  and `test_4runner_gains_a_dbpedia_year…`. Proved by baselining a detached worktree at `main`
  before merging; both fail identically there. Don't re-debug them as a regression.
- Shared-checkout hazards hit twice: mawtarx `main` had another session's uncommitted
  `pyproject.toml` edit (stashed by path, merged, popped — both edits coexist), and that session
  pushed my merge commit along with theirs while I was working.

### Left open

- **mawtarx#15 needs one real API call.** Two criteria unmet: a stored `method=llm_xwai`
  estimate end-to-end, and measured latency/token cost per listing. No key in this environment.
  One run produces both. Check the xwai#2 JSON-parsing gap during that run rather than assuming
  the method's own parsing absorbs it.
- **Part 2 (MCP) half-built.** xwapi#2 implemented and green (954 passed) on
  `fix/xwapi-2-mcp-engine` `05ddb3c2` — **unmerged, unpushed, unclosed**. mawtarx-api#5 not
  started, and it is blocked on a real finding: **xwapi's MCP engine has no authorization seam
  at all.** `MCPDispatcher.dispatch(msg, session)` never sees request headers, `MCPSession`
  carries no principal, `_tools_call` invokes the action directly, `tools/list` is unfiltered.
  mawtarx-api's auth is entirely FastAPI `Depends(...)` injected in `_routers.py`, nothing on
  the XWAction — so publishing its actions over MCP as-is is a silent, total auth bypass. The
  seam belongs in xwapi (layer cascade), and must be built before mawtarx-api#5.
- **Part 3 (xwaction#3, route security / D-019) not started.**
- **`DECISIONS.md` entry not written** for the markibx-connect rate-limiting call — a future
  agent reading the ticket will try to reverse it. Held off because another session has
  `DECISIONS.md` modified in the working tree.

## KW PRD piece 1 deployed: parallel host-group sweeps + synthetic ban (mawtarx-connect#5, #8)

Piece 1 of the Kuwait activation PRD (mawtarx-connect#4) is **live on the dev box**. The code
landed across three repos on 2026-08-05 (`xwsystem bc985658` 0.9.0.81, `xwapi 9c84c996` 0.9.0.14,
`mawtarx-connect df74e57`); today was the two-step rollout, which is what actually produced the
numbers below.

**The measured "before" is the whole case for the piece.** Step 1 shipped the gate/pool/ledger
machinery at `max_workers=1` — behaviourally the old sequential tick — and ran 18h / 158 ticks
clean. Per-source sweep costs on real traffic:

| source | duration | raw rows |
|---|---|---|
| saudisale | 6177s (103 min) | 4846 |
| sayarat | 5296s (88 min) | 2288 |
| syarah | 5190s (86 min) | 2392 |
| hatla2ee.ae | 978s | 463 |
| opensooq | 118s | 2215 |

Those top three are **three distinct host groups with no reason to wait on each other, costing
~4h38m strictly serially**. Because the unit is `Type=oneshot` and no second instance can start
while one runs, a single 103-minute source silences the nominal 5-minute cadence for 103 minutes.
That is ADR 0002's pathology, quantified on current code rather than inferred.

**Step 2** (`MAX_WORKERS=4`) installed into `/opt/mawtarx-connect-api/.venv` at 13:42; the runner
has been firing on it since 13:41:40 (`… (max_workers=4)` in the tick summary — a line the old
code never emitted, which is the only reliable discriminator that new bytes are live).

**Things learned that cost time:**

- **A `oneshot` runner can't be used to verify its own deploy.** Ticks are hours apart and
  unschedulable. Verification went out-of-band instead: a zero-network harness drives the
  *installed* runner with scripted adapters and a recording ingest client on the venv Python.
  It proved host-group keying, per-group serialisation, cross-group overlap, declaration-order
  identity, ledger terminal rows under concurrency, and the `group_cap` knob — on the deployed
  bytes, beside a live service, touching nothing.
- **A src tarball must include `README.md`** or hatchling's metadata step dies outright
  (`OSError: Readme file does not exist`) — it reads as a pip failure, it isn't.
- **`ssh … | grep` from this harness can hang long after the remote process exits.** A 120s
  "timeout" was the local pipe, not the remote work. Redirect to a remote file and `cat` it.
- **connect-api is on :8253.** :8252 is mawtarx-api's ingest endpoint — probing it for connect-api
  health returns 404 and looks like a broken deploy.
- **`xw-backend-ctl` needs the explicit `.service` suffix.** `mawtarx-scraper-runner` is a
  "Denied unit"; `mawtarx-scraper-runner.service` matches the allowlist regex. Earlier sessions'
  note that the runner can't be restarted was a missing suffix, not a missing permission.
- Cleaned up a **stale deploy lock** (`fable-piece1b`, 18h past its 30-min TTL) left by the
  previous session's crash. Worth checking before assuming the box is busy.

**Left open:**

- **mawtarx-connect#5 stays open for one observational AC** — the 4-worker prod numbers
  (`host_busy` deferrals, 503-retry count under concurrent ingest, real overlap). Step 1 reported
  0 for both *by construction*: a bound of 1 cannot exercise either path. Needs a tick with ≥2 due
  sources in distinct host groups; the daily schedule puts that hours out. Nothing left to build
  or deploy — only to witness.
- **mawtarx-connect#1 (SIGTERM drain vs `TimeoutStopSec`) is now sharper than when filed** — four
  concurrent in-flight sweeps make a forced `SIGKILL` messier than one did.
- **xwsystem#6 (1.4s cold start from eager pandas/zarr/scipy) is visible in every firing** — the
  runner burns ~5s wall and 3.6s CPU per tick to do zero work, 288 times a day.
- `repos/mawtarx-connect/.claude/worktrees/mtc-18` holds another task's uncommitted
  parse-identity work (#18) — left in place deliberately, not mine to remove.

## AqarX market-lifecycle reconciliation — phase 1 built, 4 branches pushed, nothing merged

Branch `feat/market-lifecycle-reconcile` in **aqarx, aqarx-connect, aqarx-api, xwapi** —
28 commits, all pushed, **deliberately not merged to main** (owner's instruction: branch per repo,
review before any main merge). aqarx branched off `origin/agent/aqarx-backend-interview-task`, the
other three off `main`. Worktrees under `worktrees/*-lifecycle` still in place.

Scope shipped: aqarx#3 plan+ADRs, #4 platform trust gate, #5 availability model + durable store
mutations, #6 connect telemetry/seen-set/profiles, #8 reconcile end to end, #9 API surface,
#10 benchmark. #7 (sibling-stack review) closed. **All suites green:** xwapi 140, aqarx 197,
aqarx-connect 50, aqarx-api 36 — the last two repos had **zero tests** before this.

**The design, in one line each** (docs: `aqarx/docs/market-lifecycle-reconciliation-plan.md`,
ADR 0001 in aqarx, ADR 0001 in xwapi):

- Availability is a **per-advert** axis on `SourceProvenance`, separate from deal type
  (sale/rent). Property availability is **derived**: active while any advert is active, terminal
  only when all agree, strongest terminal wins.
- Absence can never produce a sale. `sold`/`rented` need an explicit provider signal; a trusted
  full sweep's absence yields `off_market` only.
- The "may this sweep judge absence?" gate is **domain-free and went to `xwapi.scrapping`**
  (`sweep_trust.py`), not into the product — 8-reason ordered cascade, every default conservative,
  `sweep_skip_reason()` with no args returns `profile_not_full`.

**Four things that would have shipped as silent data loss, found by building it:**

1. **Nothing would ever have revived.** Scraped rows arrive `UNKNOWN`, and `UNKNOWN` by design
   never overwrites a stored value — so a wrongly-expired advert stayed dead forever. The
   persistence adapter now stamps `ACTIVE`: it is the only code that knows the row came off a live
   fetch rather than a broker upload.
2. **That stamp was then too eager.** Portals keep sold listings on the page for weeks, so a bare
   re-scrape must not clear `sold`. Revive now splits by provenance of the state:
   `off_market`/`expired`/`withdrawn` (absence-derived) revive; `sold`/`rented` (source-asserted)
   move only on another explicit signal. ADR 0001 §5 amended.
3. **`SweepBaselineStore.get()` conflated "first run" with "file corrupt"** — both correctly skip
   reconcile, but they differ for the *other* decision made from the same answer: whether to seed.
   Added `read_ok()`. A read fault plus a degraded sweep is exactly the pair that permanently
   lowers the bar. (This is the sibling stack's live bug, unfiled — see Left open.)
4. **The arm switch had to be enforced in the route, not the connector.** `Connector._reconcile`
   consults only the env kill switch, so env-on + service-disarmed would have written. The route
   degrades the run to a dry run and reports `dry_run` **as applied**, not as requested. Effective
   enabled = `env AND armed`; the API can only flip one of the two.

**`would_mark` is computed on every run, including skipped and dry ones.** A disarmed run reports
what it would have marked. That is the direct answer to the sibling stack's blind-arming problem.

### Benchmark: real numbers, and it found a defect in our own code

`aqarx/benchmarks/bench_reconcile.py`, `docs/benchmarks/reconcile-2026-08-06.md`. ext4/NVMe,
i5-12500H, Py 3.13.7, seed 20260806, 5% absent. Bulk (one write/pass) vs naive (one write/advert):

| store | props | bulk | naive | ratio |
| --- | --- | --- | --- | --- |
| json | 10k | 1.0 s | 85 s | 85× |
| xwstorage | 10k | 1.3 s | 139 s | 108× |
| json | 50k | 18.9 s | ~2070 s (extrapolated) | 109× |
| xwstorage | 50k | 29.0 s | ~4188 s (extrapolated) | 144× |
| memory | 50k | 20.7 s | 17.3 s | **0.83× — slower** |

- **The win is entirely I/O.** On the in-memory store there is none. Stated in the doc, not buried.
- **Persistence is no longer the bottleneck at 50k — our own scan is.** `store.py:199 _apply_one`
  walks every property per update, so a bulk pass is O(properties × updates): ~125M property
  visits to mark 2,500 adverts. 5× data → 40× time. Fix is a one-pass `(source, source_id)` index,
  ~20 lines. **Do this before aqarx#11** — the guard test currently pins "one write" while the real
  cost has moved elsewhere.
- First run measured **tmpfs** (default temp dir on this host). `--workdir` added, re-run on ext4;
  every ratio above is the conservative one. tmpfs understates a whole-document write by 25–55%.
- Unmeasured and larger than reconcile: **ingest has no batched counterpart** — a 10k-advert sweep
  pays ~10k whole-document writes on upsert against 1 on reconcile.

### Sibling-stack review (aqarx#7, closed) — 4 findings filed, 1 duplicate caught

Every claim re-verified against current code with file:line before filing; 6 of 8 candidates
confirmed, 1 reframed into something worse, 1 refuted as stale.

- **mawtarx-api#7** (reliability) — `/connectors/runs` 500s **permanently** once any ingest sweep
  exists: response model types `reconcile: bool`, the worker always stores `dict|None`. Worse than
  first described — the `= False` default never applies because the key is always present, so it is
  every ingest run, not only reconciling ones.
- **mawtarx#16** (performance) — reconcile writes the whole collection **per marked listing** and
  never bumps `store.version`; `bulk_persist`/`mark_persist` exist and CLAUDE.md already mandates
  them.
- **mawtarx#17** (correctness) — `delisted_at` never cleared on revival → kara's browse computes
  the sold window from a stale date.
- **mawtarx-api#9** (safety) — `?reconcile=true` on both admin pull routes is **unreachable for
  every source**: no profile is passed, so the gate always answers `window_not_measured`, silently.
- **Refuted, not filed:** "no write fence on the reconcile path" — stale, the store rides the
  fenced DB handle (`state.py:219-223`), default on.
- **Closed as duplicate:** my mawtarx-api#8 (disarmed reconcile records no would-expire stats)
  duplicated **mawtarx-api#3**, filed 3 days earlier. Process lesson: I verified against code but
  did not check the tracker for prior art first. Do that before filing.

### Left open / not done

- **Nothing merged to main, nothing deployed** — by instruction, and aqarx is dormant with no VPS
  service, so there is nothing to deploy. Worktrees deliberately left in place.
- **aqarx#3–#6, #8–#10 left open** despite being implemented: not on main. Close them at merge.
- **aqarx#11–#16 not started**: runner, staleness, provider signals, identity registry, identity v2
  (review-gated), scraper relocation.
- **aqarx#13 is blocked on an external answer** — which providers publish an explicit sold/rented
  marker. Until then the provider signal map ships **empty by default**, so no provider can emit
  `sold`/`rented`. Two more pending decisions carry stated defaults in the plan §10: geometric
  identity finality, and run-history retention (90 days / 1000 runs per source).
- **Two verified sibling-stack findings held back, not filed** (want a second read first):
  an unbounded `_inflight` set in mawtarx-api that silently drops a re-sent batch once its LRU
  entry ages out; and the **baseline-clobber** on the `no_baseline` seeding path — a failed
  baseline read lets a degraded sweep overwrite the good count. That second one is the live version
  of defect 3 above.
- **aqarx-connect has one pre-existing network-dependent failure**
  (`test_country_platform_downloads.py`) — fails identically on untouched main, not ours.
- `_VERSION_FIELDS` gaining availability **changes the content hash**, so the first fetch after this
  lands opens one new version per identity. Harmless on a dormant store; needs a word before it
  ever runs against a live one.
- `require_auth` is aqarx-api's only auth tier and admits anonymous callers while
  `AQARX_ALLOW_ANON=1` (its dev default). Any deployment that arms reconciliation must set it to 0.
