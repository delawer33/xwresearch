# AGENTS.md — how we work

Read this before writing or changing any code. Vocabulary is shared with the muhdocstools
`GUIDE_XX` methodology (Five Priorities, I→A→XW, REF/GUIDE numbering) so the two systems don't
drift; the loop below is what governs day-to-day.

---

## The loop

**Orient → Reuse-check → Design → Implement → Verify → Review → Land → Record**

Scale it to the work. A typo fix is Implement→Land. A one-repo bugfix skips Design. Anything
touching a contract, a route, or two repos runs the whole thing. Skipping a step is fine;
*pretending* to do one is not.

---

## Working here — shared box, uneven access, ground-truth first

Hard-won; ignore one and you lose an hour:

- **The box is shared and concurrently edited.** Other sessions touch the same `repos/*` at once —
  you'll see `pyproject.toml`/test churn that isn't yours. **Commit scoped**
  (`git commit -- <path>`, never `git add -A`) or you land someone else's half-done work.
  A `git pull`/checkout in a repo whose editable install a running process or ingest imports
  shifts code under it mid-run — finish or stop background jobs first. **Leases enforce this**
  — see below.
- **Repo leases: work in a worktree, lease the main checkout.** A `PreToolUse` hook
  (`scripts/repo_lease.py`) coordinates the *main* checkouts; worktrees need no coordination and
  are the normal way to work. What you'll actually meet:
  - Edits auto-take a **section** lease (the file's directory, or the file itself in a flat
    directory like `providers/`). Non-overlapping sections run in parallel; overlapping ones are
    denied with a ready-made `git worktree add` line — take it, don't argue with it.
  - **Name your paths when committing.** `git commit -- <your files>` is allowed while another
    agent is in the checkout; bare `git commit`, `-a`, `add .`, `add -A` are refused because they
    sweep up their half-written work. `reset`/`checkout`/`stash`/`pull` are refused outright while
    someone else holds a section — there is no scoped form.
  - A **merge or rebase in progress** makes that repo exclusive. Merging N repos at once takes all
    N leases or none.
  - **ASK-OWNER means stop and ask the human**, quoting both intents — it fires on shared files
    (`pyproject.toml`, `__init__.py`, `version.py`) where a path can't tell you if the two changes
    collide. Their answer is recorded once via `task claims:decide` and never asked again.
  - `task claims` shows who holds what · `task claims:reap` clears dead holders ·
    `XW_LEASE_OFF=1` bypasses the hook (say so if you use it) ·
    `task claims:install` registers it in a new environment ·
    `task claims:take` / `task claims:drop` for a deliberate wide claim.
- **Push access is uneven.** Backend repos (markibx\*, mawtarx\*, kara-api) push; **`kara-web` and
  `markibx-web` are 403** — frontend changes go through their owners. Check before promising a deploy.
- **The VPS is dev, and env is root-owned.** Service secrets (e.g. `XWBASE_SERVICE_TOKEN`) live in
  `/etc/*.env` you can't read; a deploy that flips a fleet default (e.g. WS transport) can break on
  an env mismatch you only see at restart. Probe the target venv/env first (deploy-vps skill).
- **Cap the caution; lead with the number.** Don't re-verify state already established (ship on the
  prior green unless told to re-check), and state the concrete count, not the vision — "3,533 models but
  ~0% depth (identity-only shells)", not "the universal catalog" — before endorsing a plan.

---

## 1. Orient — find out what's actually true

Start with the target repo's own `CLAUDE.md` — it's the source of truth for that repo, and it
carries the gotchas.

Then **verify against code, not prose**:

- `grep` the imports. Who actually calls this? A registry entry, a README claim, or a config
  flag is not evidence that something runs.
- `git log -S"<symbol>"` tells you when a thing landed and, via the commit message, often why.
- Ask "what would be true if this were live?" and check *that* — a route registered, a caller
  in product code, a service in the deploy config.
- **Check what the name actually resolves to at runtime**, not what's nearest on disk. Files on
  disk can be dead: deleted from git, untracked, and still sitting there. A `find` hit is not
  an implementation.
- **When a claim is cheap to test against the running system, test it.** One `curl` against the
  VPS beats an hour of reading.

**Sync first — `/pull-repos`.** A stale checkout, an uncloned repo, and a dead file on disk all
look identical to "this doesn't exist." That skill exists because all three fired at once; its
"Why this exists" has the full story if you want it.

**A matching version string is not proof the API matches.** `xw*` repos reuse a version across
many commits — xwstorage-db sat 19 commits behind at an unchanged `0.0.1.7` while gaining the
`allow=` parameter xwmemory called. The pin looked clean; the tree was stale. So: **"this
parameter/function doesn't exist" is not a finding until you've fetched that repo.** Writing it
up as API drift sends the next agent to "fix" correct code.

Three ways a grep lies about usage:
- **stale** — the repo moved; you're reading last month's code.
- **absent** — the repo isn't cloned, so the feature is invisible.
- **indirect** — product code imports the facade, not the package (`XWActionRouter` from `xwapi`,
  never `exonware.xwaction`). Count what callers import.

State what you found plainly, including the unflattering version, and **scope the claim to what
you checked**: "no route *in the repos I synced* uses it" — not "it has zero production routes."

**Not every task earns the full four (grep+`git log -S`+`/pull-repos`+curl-prod).** That weight
is for shared-contract, cross-repo, or Technology/Product-layer changes, where being wrong is
expensive. A one-file `kara` tweak with no external callers doesn't need all four — spending a
day Orienting on a 10-minute change is its own bug. Match the depth to the blast radius, not to
habit.

## 2. Reuse-check — it probably already exists

**Layer cascade, not just utilities.** Company priority is Technology (`xw*`) > Products
(`markibx`/`mawtarx`) > Projects (`kara`/client repos) — strategic weight, not delivery urgency
(weekly delivery still runs on `kara`; see `CLAUDE.md`'s priority ladder). Before adding a
**feature**, not just a utility, to `kara`: does it belong in an `xw` library (generic,
non-car-specific capability)? In `markibx`/`mawtarx` (car-domain logic other products could
reuse)? Only build it in `kara` if neither holds — see `ARCHITECTURE.md`'s dependency-direction
section for why the direction is strict. If a week's work landed entirely in `kara`, that's a
signal to check whether some of it belonged one layer up, not proof it didn't.

**[`docs/tool-index.md`](docs/tool-index.md)** maps task → xw library → status, then that
library's `CLAUDE.md` gives you the entry point and the sharp edges. Do this **before** writing
any utility.

Never hand-roll: HMAC/signing/encryption (`xwencrypt`), image thumbnailing/proxying
(`xwbase.media`), HTTP fetch with rate limiting for a connector (`xwapi.scrapping`), a
graph/tree structure (`xwnode`), a data merge (`xwdata`), a parser (`xwsyntax`), logging /
caching / serialization (`xwsystem`).

`xwsystem` is the base of everything and is already on your import path — check it before
adding any third-party dependency.

## 3. Design — decide, and say why

- **Five Priorities**, in order, as the tie-breaker when concerns conflict:
  **Security → Usability → Maintainability → Performance → Extensibility.** Security blocks
  regardless of the other four. Cite the priority when you make a non-obvious tradeoff.
- **Dependency direction is strict** (`ARCHITECTURE.md`) — never reverse it. markibx never
  imports mawtarx.
- **Never remove a contract method** — deprecate first, remove in the next major.
- **Check `DECISIONS.md`** before re-litigating something. If you're about to reintroduce a
  stored `price_sar` or a SAR-denominated comparison, D-002 already killed that.
- New package, or a release gate? That's what the muhdocstools lifecycle
  (`/requirements → /idea → /project → /architecture → /plan → /dev-* → /review → /test ⇄
  /debug ⇄ /fix → /bench → /qa-gate → /release`) was built for — see the methodology layer
  below. For everyday work it's overkill; this loop governs.

## 4. Implement — the conventions

- **Package naming:** `exonware.{product}` package · `exonware-{product}` dist · `{product}` CLI.
- **Three-repo shape:** `{product}` = pure-Python core (no HTTP, no DB driver) ·
  `{product}-api` = thin HTTP layer, zero business logic · `{product}-connect` = external
  connectors / scrapers.
- **I → A → XW layering:** Interface (`contracts.py` — Protocols, the stable boundary every
  other package imports) → Abstract (`base.py`) → Concrete (facades).
- **Path comment as line 1** of every source file: `# exonware/{pkg}/src/exonware/{pkg}/<file>.py`.
- **Comments:** keep the WHY, drop the WHAT.
- **Cores are framework-agnostic:** plain dataclasses + enums, no ORM/Pydantic in a core.
- **Python ≥ 3.12.**
- **Lazy install:** heavy/optional deps import *inside the function that uses them*, exposed via
  a `pyproject.toml` extras group — not at module top-level. Foundation libs are on everyone's
  import path, so their cold-start cost is everyone's cost.
- **Write code that reads like its neighbours** — match the file's existing idiom, naming, and
  comment density over any rule here.

## 5. Verify — drive it, don't assume it

Tests passing is not verification that a change works; exercise the actual flow. The `/verify`
skill does this, `/run-local-stack` brings up mawtarx-api + kara-api + kara-web wired together.

`task test` runs every product suite (~4 min), `task test -- tests/test_foo.py` inside a repo.
**A collection error is the environment, not your change** — `task doctor`, then `task venv`.
Push-worthy work should also survive `task ci:local -- <repo>`, which rebuilds the workspace
from clean clones in ~60s and so catches what only your local venv was making pass.

**Performance claims need numbers and a scope.** The WS-RPC benchmark is the cautionary tale:
"6–23× faster" was true for trivial payloads and *false* for 5 KB payloads and the real
`/catalog/vehicles`, where plain HTTP keep-alive still won. Never report a speedup without the
payload shape it holds for. Budgets live in each repo's `docs/REF_54_BENCH.md`.

## 6. Review — hunt for bugs, don't confirm your work

`/self-review` (your own just-finished change, read as a hostile reviewer) and `/code-review`
(the working diff). Security findings block; see `GUIDE_64_SECURITY.md` for depth.

## 6b. Delegating to subagents

Every rule here was paid for in wall-clock on the xwmemory build (2026-07-26, 7 slices).

- **Default every subagent to Opus unless the user named a model.** When spawning agents (the
  `Agent` tool's `model`, or `agent(..., {model})` in a workflow), pass `opus` by default. Only
  pick a different tier when the user explicitly says which model to run on (e.g. "run the finders
  on sonnet", "use haiku for the cheap sweep") — then honour that. Don't silently inherit a
  smaller session model for delegated work.
- **They can't invoke `disable-model-invocation` skills.** Inline the loop you want instead of
  naming a skill they'll silently fail to load.
- **Forbid `SendMessage` in reviewers:** *"your final response text IS your report, just end your
  turn."* Reviewers otherwise burn cycles retrying sends to a parent name that doesn't resolve.
- **Forbid idling in coordinators:** *"don't wait on reviewers — write your report while they
  run; if one doesn't land, do that axis yourself."* Agents wait politely and invisibly.
- **Carry the previous slice's lessons into the next slice's prompt.** Cheap, and it's what made
  later agents delete their own unproven work instead of shipping it.
- **Two-axis review in parallel** (Standards + Spec, `/code-review`'s split) catches what one
  misses — a stale doc rule contradicting correct code, a fingerprint that could eat real data.
- **Verify their claims yourself**: re-run the suite, read the risky predicate, trace the API
  they say is missing. Sound reasoning on a false premise reads exactly like a real finding.
- **One tree, one agent.** Slices sharing a working tree must run sequentially; parallelism needs
  worktree isolation, and a shared `.venv` makes that non-trivial. Plan for sequential.
- **Worktree tests import MAIN's code, not the branch's.** The shared `.venv`'s editable install
  `.pth` points at the *main* checkout's `src`, so `task test` / bare `pytest` in a worktree
  silently tests main. Tell every worktree subagent to run
  `PYTHONPATH=<worktree>/src <venv>/bin/python -m pytest` (never `task test`, never reinstall the
  shared venv). Cost 2026-07-28: false-green risk across 5 parallel worktrees.
- **Scope "finalize" delegations tightly.** If the deliverable is commit + verify, forbid
  expensive re-runs (live network sweeps, full re-ingests) explicitly — an over-scoped finalize
  agent burned ~45 min on a live SPARQL re-sweep for an idempotency check the task never needed.
- **A background process a subagent spawns does NOT auto-resume the subagent.** A subagent that
  launches a detached job and ends its turn "waiting for a notification" just stalls. Either forbid
  detached jobs (finish in one turn) or resume it explicitly with `SendMessage` — cost 2026-07-28:
  three resume cycles on one agent.

## 7. Land

- **Commit or push only when asked.** If you're on the default branch, branch first.
- **Versioning:** SemVer with a 4th build-counter segment (`MAJOR.MINOR.PATCH.BUILD`, never
  reset). `version.py` is the single source of truth; `pyproject.toml` references it. Drift
  between them is **release-blocking**. Pre-1.0, MINOR may break — document it in release notes.
- **Deploying** kara/mawtarx/markibx to the VPS: the `/deploy-vps` skill. Server truth:
  `docs/vps-current-state.md`.

## 8. Record — leave the map true

- A **cross-repo fact** changed (what's live, a dependency, a port, where something lives)?
  → `/sync-ecosystem-docs`. It edits the owning doc in place rather than layering a second copy.
- A **decision** was made — a tradeoff, a rejected alternative, a constraint found the hard way?
  → `DECISIONS.md`, newest first.
- A **feature** shipped and the next agent will need to use it? → `/save-feature-docs`.
- A **plan/report landed** (done, tested, committed)? → move it to `docs/history/`.

**Doc/log placement (per-repo):** long-lived reference → `docs/REF_XX_*.md` mirroring the
`GUIDE_XX` number; time-stamped append-only entries → `docs/logs/<type>/` named
`<TYPE>_YYYYMMDD_HHMMSS_mmm_<DESC>.md` (types: changes, plans, reviews, decisions, tests,
benchmarks, releases). When in doubt keep it project-local — promotion is cheap, demotion hurts.

---

## Skills — use them, don't re-derive them

| Skill | When |
|---|---|
| `/create-connector` | Add or activate a marketplace scraper in `mawtarx-connect` |
| `/deploy-vps` | Ship kara / mawtarx / markibx to the VPS, and verify it landed |
| `/run-local-stack` | Bring up mawtarx-api + kara-api + kara-web locally, wired, memory-capped |
| `/status-report` | Human-readable summary of recent work across the ~30 repos |
| `/sync-ecosystem-docs` | Reconcile shared docs after a session changed a cross-repo fact |

---

## The methodology layer (muhdocstools)

The lead dev's canonical methodology + CI/ops tooling is vendored at **`repos/muhdocstools/`**
(two repos: `docs/` and `tools/`). Other devs work from it; our `AGENTS.md` shares its
vocabulary deliberately.

> **The caveat.** muhdocstools was written for the *real* eXonware umbrella monorepo — layer
> folders `00_GLOBAL/`, `01_SYSTEM/`, `03_BASE/`, `05_PRODUCTS/`, sibling-`exonware/`-parent
> layout. **This workspace is flattened** (every repo sits directly under `repos/`), so the
> tools' auto-discovery (`PACKAGES.txt`, `XW_SYSTEM_ROOT`) does **not** resolve here. Run them
> per-package with an explicit `--project-path repos/<pkg>`, or treat them as reference. The
> **guides are pure methodology and apply as-is.**

**Guides** — index at `repos/muhdocstools/docs/INDEX.md`. Start at `GUIDE_00_MASTER.md` (Five
Priorities); `GUIDE_31_DEV.md` is the implementation heart. They're pure methodology, so unlike
the tools they apply as-is.

**Release / version / publish** — `repos/muhdocstools/tools/ci/commands.sh help` lists
everything (`version verify`, `version auto-bump`, `quick_release`, `pypi_cleanup`).
`CI_VERBOSE=1` for step-by-step logs.

**Don't bother with** (so you don't rediscover it): its venv/ports tooling and
`vps.example.json` don't resolve here — we use `/run-local-stack` and
`docs/vps-current-state.md`. Its `docs/skills/` + `/xw` orchestrator are a *different* system
(markdown for a custom convention, not Claude Code skills — ours are `.claude/skills/`). The
60+ one-shot scripts stay in place; don't copy stale duplicates here.
