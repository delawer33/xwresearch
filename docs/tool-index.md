# Tool index — does an xw lib already solve this?

Task → platform lib → repo, so a new feature reaches for an existing tool instead of getting
reinvented. **Status** tells you whether the tool is proven in this product or just available.

> **Re-derived 2026-07-17** against synced HEADs of all 12 product repos: **9 directly imported,
> 9 not.** "Not imported" ≠ unused — `xwaction` is everywhere via `xwapi`'s `XWActionRouter`.
> Counts go stale; re-run `/pull-repos` before trusting them.

| Need to... | Reach for | Status |
|---|---|---|
| Log / cache / serialize | `xwsystem` | **live** — everywhere |
| Read/write one field of a large JSON doc without loading the whole file | `xwjson` (usually via `xwstorage-db`) | **live** |
| Persist product data (the actual database) | `xwstorage-db` (`exonware.xwstorage.db`) | **live** — most-imported storage surface. **Read [`xwstorage-db-guide.md`](xwstorage-db-guide.md) before any write-path or capacity work** — the default durability is the slow one, and the write path takes no cross-process lock (a fencing-lease primitive exists but isn't wired in) |
| Cross-process file lock (one writer at a time) | `xwsystem` (`io.FileLock`) | **live** — kernel `flock`/`msvcrt`, crash-safe, `SHARED`/`EXCLUSIVE`. Was `open(...,"x")`-based and broken until 2026-07; anything that hand-rolled a lockfile should use this |
| Cross-process ownership with a fencing token (reject a resumed stale writer) | `xwstorage-db` (`db.fencing.PartitionLease`) | **built, unwired** — stronger than a plain lock for single-writer stores; not yet exported or called by any write path |
| Store a `(timestamp, value)` series (price history, metric trends) | `xwstorage-db` → `db.timeseries()` | **unwired** — range/downsample/retention built in, used by zero product repos. Don't hand-roll one |
| Shared money/value type | `xwschema` (`Price`) | **live** — every core+api repo |
| Per-entity-class schema registry + migrations | `xwschema.registry` | **live** — markibx-api mountables |
| Login / sessions / tokens / MFA | `xwauth-identity` (`exonware.xwauth.id`) | **live** — all 3 API repos |
| Signed image-thumbnail proxy (no hotlinking) | `xwbase` (`.media`) | **live** — all 3 API repos |
| HTTP fetch with rate-limit/policy for a connector | `xwapi.scrapping` | **live** — mawtarx-connect, markibx-connect |
| HTTP route | `xwapi` (`APIRouter`) | **live** — engine comes from xwbase's switch; prod resolved to `xwrouter` 2026-07-18, FastAPI is the fallback |
| One decorator = HTTP endpoint + native WebSocket-RPC | `xwapi`'s `XWActionRouter` (built on `xwaction`) | **live and now the default** — kara-api runs 43 files on it; karaa-connect-api is 100%. mawtarx-api / markibx-api still plain `APIRouter`. Use it for new routes. |
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

## Rule of thumb

Before writing a new utility, grep this table, then check the target repo's own `CLAUDE.md`
for its verified used-by list and gotchas — a lib being "available" doesn't mean it's free of
sharp edges (several rows above link to a real bug found in that repo's own doc).

## Keeping this current

When a session verifies a new library adoption (or confirms one that's here is now wired in),
update the **Status** column in place — don't add a second row for the same capability.
