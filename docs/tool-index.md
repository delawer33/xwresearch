# Tool index — does an xw lib already solve this?

Task → platform lib → repo, so a new feature reaches for an existing tool instead of getting
reinvented. **Status** tells you whether the tool is proven in this product or just available.

> **Re-derived 2026-07-26** against synced HEADs of all 12 product repos: **9 directly imported,
> 12 not.** Imported, by file count: `xwapi` 188, `xwstorage` 26, `xwbase` 15, `xwauth` 13,
> `xwschema` 11, `xwsystem` 10, `xwjson` 3, `xwentity`/`xwdata` 1 each. Still zero: `xwnode`,
> `xwquery`, `xwsyntax`, `xwmodels`, `xwencrypt`, `xwbots`, `xwchat`, `xwgis`, `xwscript`,
> `xwui`. "Not imported" ≠ unused — `xwaction` and `xwrouter` show 1 direct import each but are
> everywhere via `xwapi`'s `XWActionRouter` and the engine switch.
> Counts go stale; re-run `/pull-repos` before trusting them.

| Need to... | Reach for | Status |
|---|---|---|
| Log / cache / serialize | `xwsystem` | **live** — everywhere |
| Encode/decode JSON fast (the estate codec) | `xworjson` — **private GitHub repo, NOT in `repos/`**, not on PyPI | **live estate-wide since 2026-08-07** — the sole auto-selected JSON backend; stock orjson is deleted from all code (xwsystem parser registry, xwjson engine, xwrouter encoder, xwsyntax decoder). ⚠️ **Absent → silent stdlib-json fallback**: nothing warns, `task doctor` doesn't check, and any perf figure measured that way is wrong-codec. After every venv rebuild, `pip show xworjson`; reinstall with `git clone https://github.com/Exonware/xworjson.git && repos/.venv/bin/pip install ./xworjson` (Rust build, needs rustup; pip pulls maturin itself). VPS venvs unverified as of 2026-08-10 |
| Read/write one field of a large JSON doc without loading the whole file | `xwjson` (usually via `xwstorage-db`) | **live** |
| Persist product data (the actual database) | `xwstorage-db` (`exonware.xwstorage.db`) | **live** — most-imported storage surface. **Read [`xwstorage-db-guide.md`](xwstorage-db-guide.md) before any write-path or capacity work** — the default durability is the slow one, and the write path takes no cross-process lock unless you ask for one (`options={"fencing": ...}`, next row) |
| Cross-process file lock (one writer at a time) | `xwsystem` (`io.FileLock`) | **live** — kernel `flock`/`msvcrt`, crash-safe, `SHARED`/`EXCLUSIVE`. Was `open(...,"x")`-based and broken until 2026-07; anything that hand-rolled a lockfile should use this |
| Replace a whole small file without ever leaving it half-written (state/checkpoint/baseline JSON) | `xwsystem` (`io.safe_write_text` / `safe_write_bytes` / `atomic_write`) | **live** — temp-file + rename in `io/common/atomic.py`, creates parent dirs. Two traps: **`backup=True` is the default**, so every write leaves a `.bak` sibling next to your state file unless you pass `backup=False`; and **`append=True` is not atomic at all** (it plain-opens `"a"` and returns early) — pair appends with `io.FileLock`, next row, or use `task done:append` for `DONE_TODAY.md`. Don't hand-roll `write to .tmp then os.replace` — aqarx's sweep-baseline store and run ledger go through this |
| Own *part* of a resource across processes that come and go (who may touch which section) | `xwsystem` (`io.LeaseRegistry`) | **live, one caller** — scoped leases in one JSON file: hierarchical scope overlap, all-or-nothing multi-resource acquire, TTL + dead-pid reap, per-kind TTL, steal-with-reason. Stdlib-only and **path-loadable** (`spec_from_file_location`) so a latency-critical caller skips the ~1.4s `exonware.xwsystem` import. Wired into the agent-collision hook (`scripts/repo_lease.py`) |
| Cross-process ownership with a fencing token (reject a resumed stale writer) | `xwstorage-db` (`PartitionLease`, exported) | **live 2026-08-05** — opt in with `options={"fencing": "<service-role>"}` on `XWDatabase.open`; second live opener refused with the holder named, stolen-partition writer fails on its next write, dead holder reclaimed without waiting out the TTL. Flat ~22-27us/write (4% at 20k rows, that repo's `REF_54_BENCH` §3.4). **Cooperative** — a root is only as safe as its least careful writer, so wire every writer or none. Callers — every writer of the mawtarx store root, as the cooperative rule demands: mawtarx-api's `AppState` open as `mawtarx-api` (ON by default, `MAWTARX_DB_FENCING=0` to disable), the `mawtarx` CLI's four write commands as `mawtarx-cli` (read-only ones take no lease), mawtarx-connect's `collect.py`/`backfill_normalize.py`. A partition that another process took **and released** still fences you — the guard reclaims only on proof it never moved, because writing on from a pre-rewrite record cache is the corruption the lease exists to stop (xwstorage-db#2, mawtarx-api#6, both closed 2026-08-06) |
| Store a `(timestamp, value)` series (price history, metric trends) | `xwstorage-db` → `db.timeseries()` | **live** — mawtarx's observed price history (`price_series.py`). Range/downsample/retention built in; don't hand-roll one. `points` is a property, `first`/`latest` are methods |
| Shared money/value type | `xwschema` (`Price`) | **live** — every core+api repo |
| Per-entity-class schema registry + migrations | `xwschema.registry` | **live** — markibx-api mountables |
| Login / sessions / tokens / MFA | `xwauth-identity` (`exonware.xwauth.id`) | **live** — all 3 API repos |
| Signed image-thumbnail proxy (no hotlinking) | `xwbase` (`.media`) | **live** — all 3 API repos |
| HTTP fetch with rate-limit/policy for a connector | `xwapi.scrapping` | **live** — mawtarx-connect, markibx-connect, aqarx-connect. **Its `sources/` sub-package is not generic**: 6,215 lines of *real-estate-portal* adapters belonging to aqarx, reading an `AQARX_SYNTHETIC_FALLBACK` env var from inside the platform layer. 305 ids register there but only 12 do real HTTP (`ARCHITECTURE.md` → aqarx). Use the `BaseScraper`/`IScraper`/`INormalizer` contracts and the rate limiter; do **not** treat `sources/` as a place to add car connectors — mawtarx keeps its own in `mawtarx-connect` |
| HTTP route | `xwapi` (`APIRouter`) | **live** — engine comes from xwbase's switch; prod resolved to `xwrouter` 2026-07-18, FastAPI is the fallback |
| One decorator = HTTP endpoint + native WebSocket-RPC | `xwapi`'s `XWActionRouter` (built on `xwaction`) | **live and now the default** — kara-api, karaa-connect-api, mawtarx-api, mawtarx-connect-api, and markibx-api are all on it. markibx-connect-api is the one holdout (plain `APIRouter`, routes defined inline in `app.py`, no `routes/` package). Use `XWActionRouter` for new routes. **Two traps fixed/found 2026-08-04 (xwaction#1, D-019):** `exonware-xwaction` was unimportable on a clean install (unconditional `xwport_abi` import — now guarded, and the binder is a `native` extra), and **`rate_limit=`/`security=` on a route are decorative**: `SecurityActionHandler` only runs when the action passes `handlers=[...]`, which no product action does. Don't assume a declared limit is enforced. |
| Expose the same actions to an AI agent over MCP | `xwapi` (`server/engines/mcp.py`, `mcp_protocol.py`, `mcp_stdio.py`) | **live 2026-08-09** (xwapi#2, `50a919f0`) — `create_app(engine="mcp")` registers actions properly and **fails closed**: it raises unless you pass an explicit `IMCPAuthorizer` (or opt out); denials are JSON-RPC `-32003`, not `isError`. The facade can't carry per-tool scopes — bind them at the router. First product consumer: mawtarx-api's opt-in read-only surface (`mcp.py`, its #11). Don't hand-roll an MCP server for a service that already has actions |
| Persistent memory + relevance search for an LLM agent (entities, relations, episodes) | `xwmemory` | **new 2026-07-26, standalone** — replaces FalkorDB under Graphiti using xwstorage-db (BM25+vector) + xwnode (topology). Nothing in this workspace imports it. The storage-only tool surface is **gone as of 2026-07-26**: `add_memory` enqueues onto a per-group FIFO and real `graphiti_core` LLM extraction runs async, and both search tools delegate to graphiti_core's hybrid recipes (BM25+cosine+RRF, graph-distance rerank). Consequence: the whole tool surface now **hard-requires the `[graphiti]` extra plus a live LLM/embedder** — there is no degraded text-only mode, by design. Benchmarks are still 250-node scale; read `repos/xwmemory/CLAUDE.md` before believing anything else about it |
| Scoped auth on a route | `xwapi.fastapi_routes.require_scopes` | **live** |
| Cached endpoint response | `xwapi.caching` (`XWApiCache`, `cached_endpoint`) | **live** — kara-api |
| Federate login to an external IdP (Google, etc.) | `xwauth-connect` | **unwired** — nothing federates today |
| OAuth/OIDC primitive from scratch | `xwauth` (core) | **unwired directly** — go through `xwauth-identity` instead |
| External DB connector (SQL/NoSQL/graph/vector) | `xwstorage-connect` | **unwired** — has a fake-XOR encryption gotcha, fix before trusting |
| Real at-rest encryption | `xwencrypt` | **unwired** — the correct fix for `xwstorage-connect`'s XOR stub |
| Model a graph/tree structure | `xwnode` | **unwired** — markibx's catalog parent/child inheritance is hand-rolled, not this |
| Query language over in-memory/graph data | `xwquery` | **unwired** — `xwstorage-db`'s query parser is a fragile regex parser that should probably become this |
| Parse/transpile between structured text formats | `xwsyntax` | **unwired** — feeds `xwquery` |
| Unified entity (schema+actions+data+state) | `xwentity` | **live** — markibx's mountable-entity vertical only |
| Bulk operations over entity collections | `xwmodels` | **unwired** — needs `xwentity` adoption first |
| Convert/merge data across formats | `xwdata` | **live** — markibx's mountable-entity vertical only |
| Entity-native language transpiling to Rust/C++/TS/Python/Go/WASM | `xwscript` | **unwired** — heavyweight, not a typical-feature tool |
| Chat/bot integration (Telegram/Discord/Slack) | `xwbots`, `xwchat` | **unwired** — no chat feature in karaa today |

## Workspace tooling (`scripts/`, all wired to `task`)

Not libraries — the scripts that make the repos runnable. Written 2026-07-27; check here before
writing another venv/CI helper.

| Need to... | Run | Notes |
|---|---|---|
| Know if the environment is sane | `task doctor` | Only tool that catches **stale editable paths** (a lib moved `src/` → `ports/python/src/`; the old dir imports as an empty namespace package) and **shadowed packages**. Exits non-zero on those two only |
| Build/repair the shared venv | `task venv` (`-- --dry-run`) | Two-phase by necessity — see below |
| Find the right interpreter | `scripts/find-python.sh [--check]` | `$XW_PYTHON` > active venv > `repos/.venv` > `python3`. Every repo `Taskfile` uses it; never hardcode `repos/.venv` |
| Reproduce CI locally (~60s) | `task ci:local -- <repo>` | Clones 28 siblings into a scratch dir, builds the venv, runs doctor + pytest |
| Regenerate the CI workflows | `task ci:gen` | One template → 12 repos. Edit `scripts/ci-workflow.yml.template`, never the copies |
| See who is editing what right now | `task claims` | Live repo leases across all agents. `task claims:reap` clears dead holders, `task claims:decide` records an ASK-OWNER verdict, `task claims:install` registers the hook. Protocol: `AGENTS.md` §"Repo leases" |
| Record a session's work in `DONE_TODAY.md` | `task done:append -- --file entry.md` | The **only** safe way to write that file — `/done-today` and `/checkpoint` both append to it from concurrent sessions, and an `Edit`-style read-modify-write drops the other entry (it was found 0 bytes on 2026-08-05). Locks with `xwsystem` `io.FileLock`, re-reads inside the lock, atomic replace. Exit 3 = the heading is an older day: ask the user, then `--new-day [--archive-to <p>]`. `task done:date` shows the current heading |
| Test the workspace's own tooling | `task test:workspace` | `tests/` at the root — the lease hook and the `DONE_TODAY.md` appender. `task test` covers product repos only |

Three facts these encode, each of which cost an afternoon to find:

- **`uv pip install -e` over the whole workspace cannot resolve.** Four packages carry
  contradicting exact pins (`exonware-xwsystem` is pinned `==0.9.0.39`, `==0.9.0.43` **and**
  `==0.9.0.79`). So `task venv` installs editables `--no-deps` first, third-party after — for a
  local checkout the working tree *is* the version. `task venv -- --show-pinners` names who wants
  what. Release builds still have to reconcile them.
- **Nothing `exonware-*` is on PyPI** (all 404). A CI job that checks out one repo and installs
  its own dependencies can never work; it has to clone the siblings first.
- **`xwaction` imports `xwport_abi` unconditionally** and no such distribution exists anywhere.
  `repos/.venv` carries the stub from `xwmemory/docker/xwport_abi_stub`; without it every
  importer of `xwaction` dies at collection.

## Rule of thumb

Before writing a new utility, grep this table, then check the target repo's own `CLAUDE.md`
for its verified used-by list and gotchas — a lib being "available" doesn't mean it's free of
sharp edges (several rows above link to a real bug found in that repo's own doc).

## Keeping this current

When a session verifies a new library adoption (or confirms one that's here is now wired in),
update the **Status** column in place — don't add a second row for the same capability.
