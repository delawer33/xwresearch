# Done today — 2026-08-03

## markibx structural-soundness pass — all slices #39–#46 implemented, closed, deployed

Ran the whole #38 plan-of-record in one day via parallel opus subagents (I reviewed,
committed, closed). Commits: markibx 709b20b + 30ff4f9, markibx-connect 80872a3 + f44aacc +
a71c092 + ac48992, mawtarx ac55608.

- **#39 audit script** (`markibx-connect scripts/audit_demand_coverage.py`): fresh-scp-pull
  acceptance test, classifier verified two independent ways (92.15% row agreement + 40/40
  hand sample). Live-store truth is worse than the local audit said: **66.4% resolve, not
  77.4%** — 1,921 yearless opensooq rows + dubizzle (absent locally) depress it; upstream
  mawtarx-connect gap, not membership. Demand worklist: 244 nameplates = 80% of volume.
- **#40 soundness gate**: 3 rules (year overlap / nameplate-year bleed >30y / shell
  shadowing) wired into `validate_seed`, known offenders grandfathered in a committed
  allowlist meant to shrink — and it did: **29 → 13** by end of day.
- **#41 root cause of the gen1 collapse**: the widening reached Wikidata through ONE
  predicate (`P31 car-model ∧ P176 manufacturer`); gen entities without P176 (Elantra HD)
  and "model series"-typed hubs (Accent, Patrol) were invisible — Camry split by labeling
  luck. New 5-mechanism extractor; dry run over all 244: **23 splittable / 175 residue**.
  Accent/Sonata/Fortuner/Versa have NO generation entities upstream at all → LLM-umbrella
  work, measured not assumed.
- **#42/#43 fill + aliases**: +54 makes / +1,392 models / +1,452 shells via the widening
  ingest (45 verified QID pins), 19 Arabic make aliases + ~50 model rules. Make-miss
  **5.3% → 0.14%**. Model-miss target missed (12.8% vs ~6%): root cause is the identity
  query rejecting `Q59773381` series-typed nameplates (audi arrived as a4b5…b9 fragments,
  no `audi:a4`) — filed #47.
- **#44 splits (ADR 0013)**: 13 catch-alls retired, 55 source-anchored gens minted across
  23 nameplates; shell-pinned facts dropped, not migrated. Demand-head LOCAL-GEN-1
  resolves **563 → 0**; corpus resolve dipped 66.4→61.9 — the honest degradation the ADR
  defends. The 134→~500 real-OEM-code target is unreachable from Wikidata (labels are
  prose); structural goal holds, code-count metric doesn't.
- **#46 year hygiene**: +58 dated gens, 21 proven-bad ranges withdrawn (label-equality is
  the wrong Wikidata guard — all six Mustang gens are labelled "Ford Mustang"; series-edge
  is the discriminator). Found+fixed a parse bug: WDQS dates lack the leading `+`, so
  P580/P582 parsed 0/38 — same bug latent in wikidata_generations.py (chip filed).
- **#45 deploy + relink**: markibx 30ff4f9 shipped to both VPS venvs, 3 services restarted
  and verified live (Camry 2019→XV70, Audi resolves). Dev store: renormalize re-bucketed
  638 rows; catalog-link --relink + top-up → **18,189 / 87.2% linked** (12,721 exact-year,
  4,098 honest model-level). Runbook: `mawtarx docs/runbook-catalog-relink.md`.

Ops lessons paid for in wall-clock: full `--relink` takes 2m05 on 20k rows and **overruns
the 2-min watchdog window** — the service's post-restart flush ate ~900 links; always chase
with a no-`--relink` top-up pass (40s, fits). And `pip --force-reinstall` does NOT remove
files hand-copied into a venv outside pip's RECORD — both VPS venvs still serve the 13
retired gen files (5,270 gens vs 5,257), so ~404 listings still resolve to retired shells.

## mawtarx-api#2 — retired the process-global synthetic-fallback flag (3 repos, pushed)

`POST /providers/{id}/test?mode=demo` set `KARAA_SYNTHETIC_FALLBACK` on `os.environ`, and the
in-process `ConnectorScheduleRunner` sweeps on a background thread in the **same** process — so
a demo test could make a concurrent sweep fabricate rows into the real store. The flag now
travels in `ScrapeRequest.params`. Pushed to remote `main`: mawtarx-connect **b916580**,
mawtarx-api **5647884**, kara-api **46609a5**. Suites: connect 361 pass/1 skip (24 new),
kara-api 165 (was 155), mawtarx-api 8 of 21 (rest unrunnable, below).

Three of the issue's own claims were wrong, and the corrections changed the fix:

- **`require_admin` is not the fix.** `deps.py:187` returns early when `MAWTARX_ADMIN_TOKEN` is
  unset ("dev default open") — exactly the box where this happened. Added the guard anyway
  (`mode=live` is an unauthenticated outbound scrape), but the param change is what closes it.
- **Worse mechanism than the issue's overlap window:** `test` pops-if-absent, `pull`
  pops-then-restores to force live. Interleave them and the flag stays set process-wide with
  **no request holding it, until restart** — a persistent condition, not a race.
- **The "origin of the 248 purged rows" claim is false, and the real rows may still be there.**
  Connector fallbacks stamp the **real** source id (`kavak_ae-syn-…`), while `is_synthetic()`
  matches only `source` `zz*`/`== "synthetic"` — so the 07-31 purge could not have caught them;
  those 248 were `seed_sample_data` rows. Fabricated rows do carry a precise fingerprint:
  `source_url` host **`example.invalid`** + `source_id` prefix `syn-`. Nothing has audited for
  them.

Measured, not assumed: **32 files / 33 read sites** (issue said ~20), every one already inside
`fetch(self, request)` so no signature changed; `import os` went dead in 30. Of the 7 UAE
sources activated today only **3** even have a fallback (opensooq, kavak.ae, hatla2ee).
`scripts/_gen_wave2_catalog.py` generated the same env read **inverted and default-ON**
(`!= "0"` → synthesize unless disabled) — regenerating that catalog would have reintroduced a
fabricator; now opt-in. `_host()`'s `.lstrip("www.")` reproduced live as `aseet.net` before
fixing. buyanycar's photos come from `ik.imagekit.io/yk64cmkix/…` — tenant in the **path**,
`allowed_host_suffixes` matches **hosts**, so allowlisting it would open the proxy to every
ImageKit tenant; left out deliberately, with a per-host unproxied counter + one-time WARNING so
the next missing host isn't silent.

Landing trick worth reusing: origin had moved under me (mawtarx-api +2, kara-api +17) and both
shared checkouts hold other agents' uncommitted files. Rebased in the worktrees and pushed
**branch → remote `main`** (a fast-forward there), so no shared dirty tree was ever touched.

## Kuwait (GCC #2) planned, then #5 (parallel sweeps) grilled apart into 4 issues

Planned country #2 end to end: PRD `mawtarx-connect#4` + slices #5–#14. Then grilled #5 alone
and it did not survive intact — three of its premises were wrong.

- **Host key.** #5 said "opensooq.sa/.ae/.kw are one host". They're `sa.`/`ae.`/`kw.opensooq.com`
  — three hostnames, one site, so a hostname key would multiply our rate per activated country.
  Key is eTLD+1 + a declared override (dubizzle is `www.dubizzle.sa` vs `dubizzle.com.kw`: one
  operator, two registrable domains — not inferable). Naive last-two-labels is also wrong:
  `haraj.com.sa` and `samaco.com.sa` collide. Rule: unknown suffix over-groups, never under.
- **Wrong layer.** `xwsystem.threading.contracts.IConcurrencyControl` is declared with **no sync
  implementation** — the keyed gate belongs there (xwsystem#5). And
  `PolicyHttpFetcher._build_limiters` has zero host awareness though `TokenBucketRateLimiter`'s
  own docstring says one-per-host, while `request(url)` has the host in hand → shared per-host
  limiter goes in xwapi#1. mawtarx-connect#5 shrank to wiring.
- **The actual blocker nobody had seen.** `POST /ingest/batch` enqueues on a **256-item queue
  drained by ONE writer** doing whole-collection rewrites under `sync` durability, and returns
  **503** when full — while `HttpIngestClient._post` does `raise_for_status()` with no retry. So
  naive parallelism ⇒ failed sweeps ⇒ no `complete()` ⇒ the source never seeds its reconcile
  baseline. That's the exact hazard the parallelism was for. mawtarx-api#4 + bounded 429/503
  retry in the client.

Measured on the box, and it's worse than the ADR claimed: the **16:03 tick was still running at
18:04** (~2 h), while the three firings before it finished in ~12 s each (all `not_due`). Unit is
`Type=oneshot`, `Restart=no`, `TimeoutStopUSec=2min`, `EnvironmentFile=/etc/mawtarx-runner.env`
(root-gated), re-fired every 5 min at `:28` — **a long tick blocks every later firing**, so the
5-minute cadence is decorative, not just laggy. Also `run-ledger.json` is `0600 mawtarx-runner`:
shukri can't read it, so verification goes via logs or the API.

Committed: mawtarx-connect `5f0617d` (ADR 0002 rewritten + plan section), mawtarx `076dc40`
(ADR 0003 native-market-only, left over from the previous session). Neither pushed.

## mawtarx-connect#3 — reconcile now requires a MEASURED window (3 repos, pushed + deployed)

Closed the trap the UAE activation hand-measured windows around. `reconcile_allowed` was
`name == FULL`, and `synthesize_profile` applies its 200-page default **only when the adapter
declared no `page_end`** — nearly every adapter declares one. Measured, not estimated:

**184** eligible listing sources · **15** declared in `_DEFAULTS` · **170** synthesized ·
**159** of those with a window <100 pages · **156** of them exactly **3** — and all 170 reported
`reconcile_allowed == True`.

Fix: `SweepProfile.measured`, `reconcile_allowed = name == FULL and measured`. The 15 declared
entries claim it; `synthesize_profile` never can. **Eligibility 184 → 15**, which is exactly the
set the prod runner schedules, so no live behaviour changed.

Facts that changed the shape of the fix, all verified in code:

- **`IngestionPipeline.run` — not `base.py` — is the path `POST /connectors/pull` takes**, and
  *both* reconciled after checking only `max_records`: no kill-switch, no baseline, no collapse
  threshold. An admin pull could mass-expire a source with `MAWTARX_RECONCILE_ENABLED=0`. Both now
  route through a new `reconcile_gate` into the one `mawtarx.reconcile_safety` gate.
- **The override YAML was a second way in.** Re-cutting `params` now retires the measurement
  unless the override re-asserts it — otherwise `page_end: 3` in `MAWTARX_SWEEP_PROFILES` reopens
  the same hole from config instead of code.
- `window_measured` rides the ingest wire; **absent = unmeasured**, and it out-ranks
  `reconcile_disabled`, so an unmeasured sweep also stops **seeding the baseline** — else the
  reconcile-off period teaches each source that a 3-page count is normal.
- It had to go on the **pydantic model**, not just the service: the complete handler builds
  `IngestSweepCompleteIn(**raw)` and forwards `model_dump()`, so without it the flag is silently
  dropped and every unit test on `_apply_complete` still passes.

Rejected the issue's other option (floor the synthesized window to 200): it fabricates the same
false confidence one order up, and multiplies 156 sources' blind pulls ~66×. ADR **0003** —
renumbered from 0002 mid-session because a concurrent session took that number.

mawtarx `acaa718`, mawtarx-connect `8cfd75d`, mawtarx-api `e03bff6`, all pushed. Suites:
mawtarx-connect 399 pass, mawtarx 421 pass. Filed mxc **#15** (window exhaustion, **gates**
mawtarx#8), mxc **#16** (swallowed fetch errors), mawtarx-api **#3** (shadow mode).

### Deploy — and the stale venv it exposed

**`/opt/mawtarx-connect-api/.venv` (what `mawtarx-scraper-runner` executes from) carried a markibx
from June 28: 9 files of 36, no `spine.py`, no `normalize.py` — at the identical `0.0.1` version
string.** It was internally consistent (June mawtarx + June markibx) until my August mawtarx landed
needing `exonware.markibx.normalize`; the connect-api app *and* the runner module both went to
`ModuleNotFoundError`, one watchdog tick from a crash. Fixed forward with markibx `30ff4f9` there —
the same build the other two venvs already carried as of 17:10 today. **Corollary: the runner had
been normalizing against 5-week-old vocab** while the server used current.

**The step-1b pre-flight probe passed and still missed it** — `mawtarx_connect_api.create_app()`
doesn't import `exonware.mawtarx` eagerly. What caught it was the step-4 check *asserting the new
symbols*, not merely importing the app. Probe `create_app` AND the symbols you shipped.

9 installs across 3 venvs in one ssh call; `mawtarx-api`, `mawtarx-connect-api`, `markibx-api`,
`markibx-connect-api` restarted, all active, 0 tracebacks, karaa.net 200, `catalog/stats` proxy
still matching. Verified: `sold=0`/`expired=0` (nothing flipped); wire carries
`syarah=True`/`opensooq.ae=True`/`autoscout24.de=False`; and on the live venv a measured full sweep
verdicts `reconcile_disabled` with the switch off, `window_not_measured` either way when unmeasured.

`markibx.com/api/*` returns **302** at the edge — `ARCHITECTURE.md` says it is *not* gated there.
Checked at both the start and end of the session, so the doc is stale, not a regression from this
deploy.

## Cross-agent repo leases — COMMITTED; one owner command from live

Grilled + built + reviewed + committed a lease system so 5+ concurrent sessions stop clobbering
one checkout. **Committed:** `xwsystem` **20e1be0e**, workspace **0a5b446** + **a1732e9**.
Still changes no running behaviour until the hook is registered — `task claims:install`, then
new sessions pick it up. That one write to `~/.claude/settings.json` is classifier-blocked for
me, so it stays the owner's command.

Design that survived the grill: **worktrees stay normal; leases cover only the main checkout.**
Three kinds — `section` (a sub-path; non-overlapping sections both proceed), `vcs` (repo-wide,
one git command), `merge` (in-flight transition, excludes everything). What makes two agents
committing to one checkout safe is a **pathspec**: `git commit -- <paths>` ignores the rest of
the index, so the hook refuses index-wide git (`commit` bare/`-a`, `add .`/`-A`, `reset`,
`stash`, `pull`) while another agent holds a section. Undecidable cases (shared files like
`pyproject.toml`) return **ASK-OWNER**, and my verdict is recorded in `decisions.jsonl` so the
same pair is never asked twice.

Code: `xwsystem` `io/common/lease.py` (`LeaseRegistry` + `ILeaseRegistry` in `io/contracts.py`,
exported, version → 0.9.0.80) + `scripts/repo_lease.py` (hook + `claims/take/drop/reap/steal/
decide/install-hook`) + `Taskfile` `claims:*` + `test:workspace` + `tests/test_repo_lease.py`.
**46 lease unit tests** (incl. an 8-process race) + **71 workspace tests**, all green;
`xwsystem` io suite 468 pass.

A two-axis review round then found five more defects, each now pinned by a test — the pattern is
that every one of them **failed silently**, which is the only failure mode that matters for a
guardrail:
- The multi-repo merge acquired **repo-by-repo**, so a 3-repo merge could hold repo A while being
  denied on B — the half-held set the registry's atomic acquire exists to prevent. `AGENTS.md` was
  claiming "all N leases or none" while the hook did the opposite.
- **Nothing ever released a `merge` lease**, and `Stop` refreshed it every turn → one `git merge`
  owned a repo exclusively for the rest of the session. Now released as soon as git reports no
  `MERGE_HEAD`/rebase dir.
- The bash path had **no workspace guard** (the edit path did), so git in an unrelated project on
  this box got leased.
- An owner-approved shared-file edit **proceeded without taking a lease** → invisible to
  `task claims`, unprotected by the index-wide git check. And the decision key used
  `conflicts[0].scope`, so the printed `claims:decide` command could key differently from the next
  lookup — the owner answers once and gets asked again.
- Fail-closed re-listed the git subcommands **by hand**, including `commit`/`add` (index ops, not
  destructive). Now derived from the taxonomy sets.

Then a last inconsistency of my own design: a same-file conflict polled for 60s before denying,
justified by "a one-line append is short" — but section leases live until session end, so the poll
could never succeed. WAIT now applies only to `vcs` leases (a1732e9).

Measured facts, none of them guessable from the code:

- **Concurrency is real and it's separate sessions, not subagents**: 4 transcripts were being
  written in the same minute (18:11–18:12), 152 in this project. So `session_id` is a valid
  holder identity — and the documented `PreToolUse` payload has **no agent id**, so subagents
  would have been indistinguishable.
- **A workspace-root hook would not have protected anything.** Sessions root in 4 different
  places (`xwresearch`, `…-repos`, `…-repos-mawtarx-connect`, `…-claude-worktrees-*`), each
  loading a *different* project settings file. Registration has to be user-level.
- **`import exonware.xwsystem` costs 1.36s** vs 0.046s bare, of which **648ms is
  `io.serialization` eagerly importing pandas/zarr/scipy** — a live violation of
  `AGENTS.md:132`, and it taxes every workspace CLI. Even fixing it leaves ~350ms in that
  1151-line `__init__`, so the hook path-loads `lease.py` regardless (stdlib-only, no relative
  imports, asserted by test). Path-loading also keeps it working when the venv is broken.
- **Worktree vs main needs no git subprocess**: a worktree's `.git` is a *file*, a main
  checkout's is a directory.
- **Bash bypass is ~3 writes/session, not a flood**: of 10,233 Bash calls, 1,250 are git ops
  and ~433 write into `repos/` via `sed -i`/`cp`/`>>`/heredocs. v1 polices git only.
- **`providers/` holds 663 flat files.** A plain directory-scope rule made every connector
  conflict with every other — the most common parallel task here. Hence flat-wide dirs → per
  file, and a `#files` sentinel so a module scope doesn't swallow its subtree.
- **`Stop` fires at the end of every turn**, and a subagent shares its parent's `session_id` —
  releasing on either would have made every lease last one reply. Only `SessionEnd` releases.
- Path-loading a module with dataclasses needs `sys.modules[spec.name] = mod` before
  `exec_module`, or `dataclasses` raises on `cls.__module__` being None.

## Left open

- **The runner is mid-sweep on pre-fix code** (started 16:03, `TimeoutStartUSec=infinity`). Its
  eventual `complete` sends no `window_measured`, so the server will record
  `window_not_measured` for that one sweep — fail-safe working, and it won't seed a baseline. The
  **next** tick should record `reconcile_disabled`; glance at the run row to confirm the turnover.
- **mxc#15 (window exhaustion) now gates mawtarx#8.** `runner.py`'s `truncated` only tests
  `max_records`, and `syarah`/`haraj` declare none — so it can never trip for them. This change
  made that exposure *bounded* (15 probed windows instead of 184 unverified), not fixed.
- **Could not verify the live `MAWTARX_RECONCILE_ENABLED` value**: root-owned env, `/admin/reconcile`
  401s without an admin credential, `/proc/<pid>/environ` denied to shukri. Verified the decision
  table for both values instead.
- **`/opt/karaa-api/.venv` deliberately left on the older mawtarx** (no `window_measured`).
  karaa-api never reconciles and the change is additive; touching the live product's venv risked
  the same stale-markibx cascade for zero gain. It is now a known fleet inconsistency.
- **`git log --author` cannot separate sessions on this box** — every agent session commits as
  `delawer33 <shukry.aliev@mail.ru>`, so today's concurrent sessions' commits are
  author-identical to mine. Select by SHA/branch when logging or reporting, not by author.
- Docs not synced: `vps-current-state.md` should record that the scraper runner runs from
  `/opt/mawtarx-connect-api/.venv` (not `/var/lib/mawtarx-runner/venv`, which exists but is
  unused), and the markibx-staleness finding above.
- **#5 is blocked on two xw\* releases** (xwsystem#5 gate, xwapi#1 limiter) that must be built,
  released and installed into `/opt/mawtarx-connect-api/.venv` before the connect wiring deploys
  — a coordinated multi-package deploy, so probe the target venv first.
- Rollout is deliberately **two deploys**: `max_workers=1` (behaviour-identical) then 4. If the
  ingest queue saturates at 4, fix the *writer* (batch durability in code) — `MAWTARX_DB_DURABILITY`
  is root-gated, so the env tune isn't available to me.
- ~~**mawtarx-connect#3** … still unguarded in code.~~ **Closed + deployed later the same day** —
  see the section above.
- ~~The two doc commits are unpushed~~ — both went out on the back of the #3 push
  (mawtarx-connect `5f0617d`, mawtarx `076dc40`); the four new issues are published.
- **Both API repos are uncollectable in this workspace** — `security.py` imports
  `exonware.xwauth.id.authentication.auth_policy_store`, absent from the local
  `xwauth-identity` (local `e170c3d`, origin `f392da3`). mawtarx-api already was; **kara-api
  joined it via today's upstream auth commits**, so its suite can't run on its new base either.
  Consequence: my 13 mawtarx-api route tests have never executed. `/pull-repos` + `task doctor`
  unblocks both.
- **kara-api local `main` is 18 behind on purpose** — the incoming diff includes
  `pyproject.toml`, which another agent has uncommitted there; a pull would overwrite it.
- **#2 not closed.** Its own Fix section is done, but S2 (audit the live store for
  `example.invalid`-fingerprinted rows; extend `is_synthetic` to see them) and S3 (reject-guard
  at `ScrapingPersistenceAdapter.store()`, store.py:1011 — the single funnel every scraped row
  passes) remain.
- `_host`/`_logo` still duplicated verbatim in mawtarx-api + kara-api; per AGENTS.md §2 they
  belong in `exonware.mawtarx`, which both import. Not done — wouldn't widen a security fix
  into a load-bearing repo.
- The **`kara-api` remote is redirected**: GitHub answered the push with
  `Exonware/karaa-api.git` (repo renamed), local remote URL still the old name.
- mawtarx spec doc tracks this env var as open question **OQ-9** ("rename `KARAA_` →
  `MAWTARX_`") + finding I.1.2. Both moot — the variable is deleted, not renamed.
- **#49**: clean-reinstall exonware-markibx in both VPS venvs (one human command — remote
  file deletion is classifier-blocked for me); then run `/tmp/relink_dangling.py` (staged on
  the box) in a watchdog window to relink the ~404 shell rows.
- **#47**: series-typed nameplate fix in the widening identity query — the biggest remaining
  curatable model-miss block (audi 134 rows). #48: `baw` make mixes BAW and FAW Bestune.
- markibx-connect ~400 `__unknown__` + 698 `Other` parse-failure rows: upstream ticket still
  not filed (declared out of scope in the PRD as "filed separately").
- Next umbrella: the LLM depth engine — GCC money facts first, then the 175-nameplate
  `needs-generation-split` residue + 17 `needs_year_range`.
- **Leases: all three live-run defects fixed, plus five from review** — see the section above.
  Committed (`xwsystem` 20e1be0e; workspace 0a5b446, a1732e9), `/code-review` run on both axes,
  `AGENTS.md` §"Repo leases" written, `DECISIONS.md` D-017 recorded, eager-import issue filed as
  **xwsystem#6**. The only thing left is the owner's `task claims:install`.
- **Leases: what deliberately did NOT get built** (so nobody re-derives it): per-repo
  `sections.yml` overrides (deferred until real ASK-OWNER hits say which repos need them),
  shell-parsing for non-git writes (~430 of 10,233 historical Bash calls write into `repos/`
  outside Edit/Write ≈ 3 per session — measured, accepted, git-only for v1), and any worktree
  automation / merge queue.
- **`xwsystem`'s suite has 15 pre-existing failures** unrelated to any of this — verified
  identically at a clean `HEAD` worktree. Causes: the `atomic` kwarg from another session's staged
  `json.py`, a dead-on-import `orjson_direct_parser`, a process-pool pickling test, path-validator
  expectations. Don't spend an hour blaming a lease change for them. (`task test` likewise shows
  pre-existing failures in kara-api / mawtarx-api / markibx / markibx-connect — other sessions'
  uncommitted work plus `exonware.xwauth...auth_policy_store` drift.)
- **A pipeline hides pytest's exit code.** `pytest ... | tail -4` reports `tail`'s status, so a
  failing suite reads as exit 0 — I believed a green suite for a while on exactly that. Check the
  summary line, not `$?`, or use `PIPESTATUS`.
- **`~/.claude/settings.json` registration is mine to run, not the agent's** — writing that file
  is classifier-blocked. `task claims:install` merges the block idempotently (backs up first);
  `task claims:install -- --print` shows it. Takes effect on the next new session; kill switches
  are `XW_LEASE_OFF=1` and `XW_LEASE_SHADOW=1` (log, never block).
- **`repos/xwsystem` has another session's staged change** (`io/serialization/formats/text/json.py`,
  staged not committed) sitting next to my uncommitted work. Commit scoped by path there, or I
  land their half-done edit.
