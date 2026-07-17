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

## 1. Orient — find out what's actually true

Start with the target repo's own `CLAUDE.md` — it's the source of truth for that repo, and it
carries the gotchas.

Then **verify against code, not prose**:

- `grep` the imports. Who actually calls this? A registry entry, a README claim, or a config
  flag is not evidence that something runs.
- `git log -S"<symbol>"` tells you when a thing landed and, via the commit message, often why.
- Ask "what would be true if this were live?" and check *that* — a route registered, a caller
  in product code, a service in the deploy config.

State what you found plainly, including the unflattering version. "Merged and benchmarked but
zero production routes" is the useful answer; "the new transport is live" is a lie that costs
the next agent an hour.

## 2. Reuse-check — it probably already exists

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

**Performance claims need numbers and a scope.** The WS-RPC benchmark is the cautionary tale:
"6–23× faster" was true for trivial payloads and *false* for 5 KB payloads and the real
`/catalog/vehicles`, where plain HTTP keep-alive still won. Never report a speedup without the
payload shape it holds for. Budgets live in each repo's `docs/REF_54_BENCH.md`.

## 6. Review — hunt for bugs, don't confirm your work

`/self-review` (your own just-finished change, read as a hostile reviewer) and `/code-review`
(the working diff). Security findings block; see `GUIDE_64_SECURITY.md` for depth.

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

**Guides worth opening** (`repos/muhdocstools/docs/guides/`, index at `docs/INDEX.md`):

| When you need… | Read |
|---|---|
| The tie-breaker for any design conflict (Five Priorities) | `GUIDE_00_MASTER.md` |
| Code implementation standards (the 130-KB heart) | `GUIDE_31_DEV.md` (+ `_PY` / `_TS` / `_RUST`) |
| Architecture playbook / dependency direction | `GUIDE_13_ARCH.md`, `REF_41_DEPENDENCY_DIRECTIONS.md` |
| Code review · security · testing · benchmarking | `GUIDE_35_REVIEW.md` · `GUIDE_64_SECURITY.md` · `GUIDE_51_TEST.md` · `GUIDE_54_BENCH.md` |
| Where a doc/log belongs + filename format | `GUIDE_41_DOCS.md`, `GUIDE_00_MASTER §4/§7` |
| Release & deploy | `GUIDE_61_DEP.md` |

**Release / version / publish toolchain** (`repos/muhdocstools/tools/ci/`, JSON-defined):

```bash
repos/muhdocstools/tools/ci/commands.sh help              # list commands
repos/muhdocstools/tools/ci/commands.sh help upload_auto  # usage for one command
```

| Command | Does |
|---|---|
| `version verify --project-path repos/<pkg>` | Confirm `version.py` is the single source of truth (release-blocking if drifted) |
| `version auto-bump <pkg>` | Bump + propagate across `version.py`, `pyproject.toml`, headers |
| `quick_release status\|push\|release\|hotfix` | End-to-end validate → bump → tag → build → publish |
| `pypi_cleanup exonware-<pkg>` | Dry-run report of superseded PyPI builds to prune |

`CI_VERBOSE=1` for step-by-step logs. Cross-package commands that walk `PACKAGES.txt` need
adaptation here (see the caveat).

**Its env/ports tooling doesn't apply to us** — don't burn time rediscovering that.
`tools/ci/venvs/setup_venvs.py` needs `PACKAGES.txt`/repo-root discovery (our stack manages its
own venvs via `/run-local-stack`); the port scripts resolve via `XW_SYSTEM_ROOT`; `auto_venv.ps1`
is PowerShell-only. Our live port map is `docs/vps-current-state.md` + per-repo `CLAUDE.md`, not
the umbrella `ports.txt`. `tools/infra/vps.example.json` is only a schema — real values live in a
gitignored `.secrets/vps.json` in the umbrella repo, never here.

**muhdocstools' own `docs/skills/` + the `/xw` orchestrator are a different system** — markdown
workflows for a custom convention, not Claude Code skills. Read them for workflow logic; they
don't run here. Ours are in `.claude/skills/`.

The 60+ one-shot maintenance scripts (`rename_*`, `normalize_*`, `python_to_rust.py`) and
`tools/logo-gen/` stay in `repos/muhdocstools/` — reference them in place, don't copy a stale
duplicate here.
