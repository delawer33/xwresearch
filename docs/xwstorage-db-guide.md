# xwstorage-db — how it actually works, and how to use it

The database under kara, mawtarx, and markibx. This doc exists because the same question keeps
getting re-litigated from scratch and answered inconsistently ("it's very slow" / "it's fine"),
usually by quoting one benchmark number without its workload. Both verdicts are wrong as stated.
The engine has one dominant property; once you know it, every performance question answers itself.

**Measured 2026-07-19 against source-tree v0.0.1.6** (Linux, local SSD, ~7 KB listing-shaped docs
with 4-version chains). Re-measure before quoting these on different hardware.

## The one thing to understand

**It is a RAM database with a file-shaped persistence layer, and it writes whole collections.**

Records live in Python dicts in RAM. A collection is loaded lazily — nothing at `open()`, then
the *entire* collection on first touch — and stays resident. Reads are served from those live
dicts. Writes mutate RAM, then serialize **the whole collection** back to its file.

Everything below follows from that sentence.

| | cost | why |
|---|---|---|
| point `get()` | **0.0006 ms** | returns a reference into the resident dict |
| indexed `find()` | **~0.015 ms** | hash index → live rows, zero deserialization |
| write, `sync` | **~12 ms per 1,000 resident rows** | rewrites the entire collection file |
| write, `batch`/`wal` | **0.105 ms**, flat in N | file write deferred to `flush()` |
| `flush()` | **~12 ms per 1,000 resident rows** | the same whole-collection write, once |
| first touch | **~16 ms per 1,000 rows** | hydrate + rebuild indexes from file |
| resident RAM | **~7 KB per listing-shaped doc** | per process — not shared between workers |

## Is it faster than Postgres?

**On reads, yes, and not marginally** — a sub-microsecond `get` against an in-process dict is a
class Postgres cannot reach through a socket, and an indexed `find` hands back live rows with no
row marshalling. For a read-heavy API this is a real, defensible win.

**On writes, no, and it's structural.** Whole-collection rewrite is O(N) per write; Postgres is
O(log N) plus a WAL append and never rewrites the table. No configuration closes that gap — see
below for what configuration *does* fix. Don't carry "xwstorage-db is faster than Postgres" as a
general claim; it is workload-dependent, and stating it flat gets a design decided wrong.

## Durability is the single most important setting

`durability=` is chosen at `open()` and is **not auto-detected on reopen** — you must reopen with
the same value (same for `layout=`). The default is the slowest one.

| mode | per-write | crash window | use for |
|---|---|---|---|
| `sync` **(default)** | full collection rewrite | none | tiny collections only |
| `batch` | dirty flag | everything since last flush | offline bulk loads |
| `wal` | dirty flag + ledger append, replayed on open | none | **live services — the default you want** |
| `memory` | nothing | since last checkpoint | caches, ephemeral state |

Measured per-op insert into a 5,000-row collection: `sync` **59.8 ms**, `batch`/`wal`/`memory`
**0.106 ms** — a ~565× difference from one option. And `sync` degrades linearly with collection
size (9.3 ms at 1k rows → 248.7 ms at 20k), while `batch` stays flat at 0.105 ms regardless.

**Nobody in the product stack sets it.** `mawtarx-api/settings.py` reads `MAWTARX_DB_DURABILITY`
and defaults to empty, which leaves the engine on `sync`. At prod's ~15,473 listings that is
**~190 ms of blocked, GIL-held serialization per single write** — the cause of every "the store
is slow" report. Prefer `wal` over `batch` for anything live: same speed, no crash window.

## The rule that replaces guessing

> Write cost = (collection size) × (how often you flush). Batching is not an optimization here,
> it is the difference between working and not.

Deferring writes does not remove the O(N) rewrite — it decides how many writes share one. 1,000
inserts into a 20k collection cost 249 s under `sync` and ~0.25 s under `batch` with one flush.

So: **never write rows one at a time to a large collection.** Use `XWDatabase.bulk_write()` (its
docstring is worth reading — it defers *other threads'* writes too, so keep the block short) or
`insert_many()`, which fires one persist for the whole batch. There is **no `update_many`**; wrap
the loop in `bulk_write()`.

## Traps

- **The engine write path takes no cross-process lock.** Its only synchronization is a
  `threading.RLock` inside one engine instance. Two processes opening the same DB root will still
  silently corrupt each other. **One writer process per database, always** — if a background job
  must write, run it inside the process that owns the store, not beside it.
  *Caveat to the old "no locking anywhere" claim:* a cross-process primitive now **exists** but is
  **not wired in** — `fencing.py`'s `PartitionLease` is an `O_EXCL`-file fencing-token lease
  (crash-safe as of the 2026-07 orphan-mutex fix) that rejects a stale writer resumed after
  ownership moved, which a plain `flock` can't. It is unexported and no write path calls it yet;
  wiring it into `engine.py` is the intended way to close the two-writer hole. `xwsystem.FileLock`
  (also cross-process, `flock`-based) is the *mutual-exclusion* tool for callers like the scraper;
  for the DB itself the fencing lease is the stronger fit.
- **RAM is the real capacity ceiling, not disk.** At ~7 KB/doc resident, per process, unshared
  across workers: 100k docs ≈ 0.7 GB, 1M ≈ 7 GB. Multiply by worker count. The
  exonware-riyadh-01 box has ~15 GB and is multi-tenant.
- **Anything unbounded in a document is an unbounded RAM cost**, because the whole collection is
  resident. mawtarx's `versions` chain was the live example and is now capped
  (`versioning.cap_versions`) — cap or downsample before building a feature that grows a field.
- **Every flush writes a `*.xwjson.backup.<ts>` copy and never removes it.** Over a long run this
  fills the disk; `mawtarx-connect/scripts/collect.py` hand-rolls pruning to survive it. Anything
  flushing on a cadence needs the same.
- **Indexes are rebuilt from the file on every open** (no index persistence), so first touch costs
  ~16 ms per 1,000 rows. It's lazy, so `open()` itself is free and the cost lands on first query.
- **Multi-collection transactions are best-effort, not atomic** — collection files are written
  sequentially with no global two-phase commit. A crash mid-commit can leave collections skewed.
- **`engine.get()` does a linear scan** despite a pk→row cache existing. Still fast, but `find()`
  with an index is the faster path for anything hot.

## Stale claims you'll encounter

- `benchmarks/20260610-vs-embedded/BENCH_VS_EMBEDDED.md` is rigorous and honest, but predates
  v0.0.1.6. Its "every mutation rebuilds **all** indexes from scratch" no longer holds — index and
  constraint bookkeeping is incremental now (`engine.py`, `_rebuild_all_indexes` is the
  out-of-band fallback only). Its write numbers are `sync`-mode and should not be quoted as the
  engine's write speed.
- `repos/xwstorage-db/CLAUDE.md` says there is no `update_many` — still true. It does not mention
  `insert_many`, which exists and batches its persist.

## What does NOT exist here

No cross-process coordination. No index persistence. No partial-collection writes. No
`update_many`. No connector matrix (that's `xwstorage-connect`, unwired, and its `EncryptionAtRest`
is XOR — see `docs/tool-index.md`).

## Time series — use this, don't grow a field

`db.timeseries(name)` returns a `SeriesSet` of `(timestamp, value)` points with **range,
downsample, and retention** built in, persisted under `{root}/timeseries/` as its own document —
so appending to a series does *not* rewrite a listings collection. Before hand-rolling any stored
time series, use this instead of growing a field on a document.

First consumer: mawtarx's observed price history (`price_series.py`, series set `listing_prices`).
Two edges it hit — `TimeSeries.points` is a **property** while `first`/`latest` are methods; and
the set is written only on `close()`/`save_timeseries()`, so a crash loses points a `wal`
collection would have kept. Persist it on the same cadence as your flush.

## More

Engine internals: `repos/xwstorage-db/src/exonware/xwstorage/db/engine.py` (the class docstring
documents all four durability modes accurately). Repo gotchas:
`repos/xwstorage-db/CLAUDE.md`. Task → library: `docs/tool-index.md`.
