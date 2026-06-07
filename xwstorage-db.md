# xwstorage-db — Developer Report

**Package:** `exonware-xwstorage-db` v0.0.1.5 | **License:** Apache 2.0 | **Python:** 3.12+

---

## A. What the Repo Does

`xwstorage-db` is the **XW-native embedded database engine** for the eXonware stack. It provides:

- Single-process, file-backed embedded database (no server to run)
- XWJSON-native persistence: collections stored as `.xwjson` binary files
- CRUD with schema validation, foreign key constraints, CHECK constraints, defaults, type coercion
- In-memory indexing: hash (equality), sorted (range/prefix), trigram (fuzzy/fulltext)
- ACID transactions with savepoints and rollback
- Row-level security (RLS) via a simple rule DSL
- Streaming I/O: JSON, JSONL, CSV, Parquet, xwjson
- Snapshot/backup with SHA256 manifest and point-in-time recovery
- Admin CLI: integrity check, vacuum, backup, schema inspection
- Optional FastAPI routes for snapshot management

**Design boundary:** Owns persistence and query execution internals only. Must NOT depend on `xwstorage-connect`. Can consume shared contracts from `xwstorage`. xwstorage-connect may use this as an engine driver (not the reverse).

---

## B. Backend Architecture

- **Single-process embedded engine** — `EmbeddedEngine` class, zero-config, file-backed
- **Pure Python 3.12+**, async-first API
- **Facade-first:** public API via `XWDatabase` + `XWDatabaseConfig`
- **Protocol contracts:** `IDatabaseEngine` (extends `IStorageEngine`), `IQueryExecutor`, `IScriptBackend`
- **In-memory indexes:** rebuilt deterministically on every open (not persisted to disk)
- **Transactions:** multi-collection batching with per-collection snapshot rollback
- **Query execution:** regex-based SQL-like XWQS parser → `QueryPlan` → engine execution

**Core mandatory dependencies:** `exonware-xwsystem`, `exonware-xwstorage`, `exonware-xwjson == 0.9.0.24`, `exonware-xwquery == 0.9.0.16`

---

## C. Main Folders and Files

```
src/exonware/xwstorage/db/
├── __init__.py              — Public API: XWDatabase, XWDatabaseConfig, all error types, indexes, migrations, snapshot ops
├── facade.py (301 lines)    — XWDatabase: open(), execute_script(), insert(), find(), create_collection(),
│                              create_index(), transactions, subscriptions, materialized views, stream I/O
├── engine.py (494 lines)    — EmbeddedEngine: CRUD, indexes, FK validation, security rules, schema validation,
│                              transactions, in-memory record cache
├── catalog.py               — Catalog, CollectionDef, FieldDef, IndexDef, ForeignKeyDef (all @dataclass)
├── indexes.py               — HashIndex (O(1)), SortedIndex (bisect, range/prefix), TrigramIndex (Jaccard fuzzy)
│                              + build_index() factory
├── query_runner.py          — parse_to_plan() (regex SQL-like parser), execute_plan() (WHERE/SELECT/ORDER/LIMIT/
│                              GROUP BY/JOIN/aggregates)
├── txn.py                   — DatabaseTxn: insert/update/delete with savepoints + snapshot rollback
├── constraints.py           — validate_document(), apply_defaults(), CHECK eval, type coercion, unique check
├── security_rules.py        — parse_rule(), row_is_allowed() (RLS DSL: "select: owner_id == $user_id")
├── import_export.py         — detect_format(), read_stream(), write_stream(), stream_ingest(), export_stream()
│                              (JSON / JSONL / CSV / Parquet / xwjson)
├── snapshot.py              — take_snapshot(), restore_snapshot(), list_snapshots(), delete_snapshot()
│                              (SHA256 manifest per snapshot)
├── maintenance.py           — run_integrity(), repair_all(), vacuum() (rewrite for compaction), backup()
├── migrations.py            — Migration, MigrationRegistry, add_collection(), add_field() helpers
├── cli.py                   — xwstorage-db CLI: integrity / vacuum / backup / schema subcommands
├── xw_io.py                 — load_json(), save_json() (xwjson codec), signature() (SHA256 change detection)
├── errors.py                — XWStorageDbError, XWStorageDbConfigError, XWStorageDbEngineError, XWStorageDbQueryError
├── _stack.py                — Pinned imports: exonware.xwjson, exonware.xwquery
├── version.py               — __version__ = "0.0.1.5"
└── fastapi_routes/
    └── snapshots.py         — mount_snapshot_routes(): POST /snapshots, GET /snapshots, POST /restore,
                               DELETE /snapshots/{id}, GET /pitr
tests/
└── 0.core/ (14 test files)  — CRUD, indexes, FK, schema, RLS, transactions, import/export, subscriptions, migrations
docs/
├── REF_22_PROJECT.md        — Scope, on-disk layout, roadmap
└── FEATURE_PARITY.md        — 26-row competitive matrix (100% parity claimed)
```

**On-disk layout:**
```
{root}/
  catalog.xwjson             # collections, fields, indexes, constraints
  collections/{name}.xwjson  # records: {"records": [...]}
  indexes/                   # index metadata (future persistence; currently in-memory)
  snapshots/snap-{ts}/       # point-in-time backup + sha256_manifest.json
```

---

## D. Data Models and Entities

All defined in `catalog.py`:

**`Catalog`**: `version: int`, `collections: dict[str, CollectionDef]`

**`CollectionDef`**:
```
name, pk_field (default "id"), fields: dict[str, FieldDef],
indexes: dict[str, IndexDef], foreign_keys: list[ForeignKeyDef],
json_schema: dict | None, security_rules: list[str], checks: list[str]
```

**`FieldDef`**: `name, required, unique, type_name, default, checks: list[str]`

**`IndexDef`**: `name, field_name, kind ("hash"|"sorted"|"trigram"), unique, fields: list[str]`

**`ForeignKeyDef`**: `field_name, ref_collection, ref_field, on_delete ("restrict"|"cascade"|"set_null")`

**`QueryPlan`** (`query_runner.py`):
```
collection, filter_field, filter_value, sort_field, descending, limit,
project_fields, aggregate, group_by, join_collection, join_left_field,
join_right_field, raw
```

**`TxnOp`**: `kind ("insert"|"update"|"delete"), collection, payload`

**Enums** (`defs.py`):
- `DatabaseMode`: EMBEDDED
- `ScriptDialect`: XWQS, GENERIC

---

## E. APIs, Endpoints, and Services

**`XWDatabase`** (`facade.py`) — primary user-facing API:

```python
db = await XWDatabase.open(XWDatabaseConfig(name="mydb", root_path=Path("/tmp/mydb.xwdb")))

# Schema
db.create_collection("users", pk_field="id")
db.create_foreign_key(collection, field, ref_collection, ref_field, on_delete)
db.set_collection_schema(collection, json_schema_dict)
db.set_security_rules(collection, ["select: owner_id == $user_id"])
db.set_access_context({"user_id": "alice"})

# CRUD
doc = db.insert("users", {"id": "1", "name": "Alice"})
rows = db.find("users", filter_field="name", filter_value="Alice")

# Indexes
db.create_index(collection, name, field_name, kind="hash"|"sorted"|"trigram")
db.drop_index(collection, name)

# Transactions
async with db.begin_transaction() as txn:
    txn.insert("users", doc)
    txn.update("users", pk, patch)
    await txn.create_savepoint("before_update")
    # auto-commits on exit; rollback on exception

# XWQS queries
result = await db.execute_script("SELECT id, name FROM users WHERE name = 'Alice' LIMIT 10")
result["rows"]

# Saved queries + views + subscriptions
db.save_query("active_users", "SELECT * FROM users WHERE status = 'active'")
result = await db.run_saved_query("active_users")
await db.refresh_materialized_view("v_active", query_text)
sub_id = db.subscribe_query("active_users", query_text, callback)
await db.poll_subscriptions()

# Streaming I/O
await db.stream_ingest(source="file.csv", sink="users", fmt="csv")
await db.export_stream(source="users", target="export.jsonl", fmt="jsonl")

# Maintenance
db.check_integrity()
db.vacuum()
db.backup(label="pre-migration")
```

**Admin CLI:**
```bash
xwstorage-db --root /path/to/mydb.xwdb --name mydb integrity
xwstorage-db --root /path/to/mydb.xwdb --name mydb vacuum
xwstorage-db --root /path/to/mydb.xwdb --name mydb backup --label "v1"
xwstorage-db --root /path/to/mydb.xwdb --name mydb schema
```

**FastAPI routes** (`fastapi_routes/snapshots.py` — mount into host app):
```
POST   /snapshots          — create snapshot
GET    /snapshots          — list snapshots
POST   /restore            — restore from snapshot
DELETE /snapshots/{id}     — delete snapshot
GET    /pitr               — point-in-time recovery timeline
```

---

## F. Auth, Security, Config, and Env Variables

**`XWDatabaseConfig`** (`defs.py`):
- `name: str = "default"` — logical DB name
- `root_path: Path | None = None` — filesystem path (defaults to `{cwd}/{name}.xwdb`)
- `mode: DatabaseMode = DatabaseMode.EMBEDDED` — only EMBEDDED supported
- `options: dict[str, Any] = {}` — extensibility

**Row-level security** (`security_rules.py`):

Rule DSL: `"action: field op rhs"`
- `action`: `select` | `update` | `delete` | `all`
- `field`: dotted path (e.g., `owner_id`, `profile.user_id`)
- `op`: `==` | `!=` | `in`
- `rhs`: literal, `null`, `true`/`false`, `(list,values)`, or `$context_var`

Examples:
```python
db.set_security_rules("documents", ["select: owner_id == $user_id", "delete: owner_id == $user_id"])
db.set_access_context({"user_id": "alice"})
rows = db.find("documents")  # only alice's documents returned
```

**Optional xwauth audit hook** (`engine.py:279-283`, `335-339`, `365-369`):
- Tries `from exonware.xwauth.identity.audit import audit_db_mutation` on insert/update/delete
- Gracefully skipped if xwauth-identity is not installed (`try/except ImportError`)
- This is a designed feature (not a bug): optional xwauth integration without a hard dependency

**No env variables** defined in this package.

---

## G. Database, Storage, Queues, and Background Jobs

**Storage format:** Binary XWJSON via `exonware-xwjson`. Not human-readable JSON text.

**Write path:** `engine.insert()` → `constraints.validate_document()` → update `_records_cache` → `xw_io.save_json()` → write `collections/{name}.xwjson`.

**Atomic writes:** Per-collection file rewrite on every save. No WAL in xwstorage-db itself (xwjson handles durability at the codec level).

**Indexing:** All three index types (HashIndex, SortedIndex, TrigramIndex) are **in-memory only**, rebuilt from collection data on every `XWDatabase.open()`. Index metadata files in `indexes/` directory are future work.

**Transactions:** `DatabaseTxn` takes snapshots of affected collection data before writes. On `rollback()`, restores from snapshot. Best-effort atomicity: if two collections are written and the second fails after the first succeeds, the first is already committed (no global WAL).

**Subscriptions:** In-memory polling model. `poll_subscriptions()` re-executes all tracked queries and compares SHA256 signatures. Fires callbacks on change. No persistent subscription state.

**No queues, background jobs, or distributed cache.**

---

## H. How to Run Locally

```bash
pip install -e ".[dev]"    # from repo root; installs pytest, black, isort, mypy
# or:
pip install -r requirements-dev.txt && pip install -e .

# Run tests
pytest                          # all (tests/0.core/ only)
pytest tests/0.core/ -v
pytest -k "test_embedded_crud"  # specific test

# CLI
xwstorage-db --help
xwstorage-db --name mydb --root /tmp/mydb.xwdb integrity
xwstorage-db --name mydb --root /tmp/mydb.xwdb vacuum
```

**`pytest.ini`:** `pythonpath = src ../xwstorage/src` (includes xwstorage contracts), `asyncio_mode = auto`.

---

## I. Tests Available and Tests Missing

**Available (14 test files in `tests/0.core/`):**

| File | Coverage |
|------|---------|
| `test_embedded_engine.py` | CRUD, index creation, async open |
| `test_indexes.py` | HashIndex lookup/remove, SortedIndex range/prefix, TrigramIndex fuzzy search |
| `test_fk_schema_txn.py` | Foreign key restrict/cascade, JSON Schema validation, transaction rollback on FK violation |
| `test_security_rules.py` | RLS filtering (select/update/delete denied), `==`/`!=`/`in`/context vars |
| `test_constraints_migrations.py` | CHECK constraints, defaults, COUNT aggregate, migration registry |
| `test_import_export.py` | JSON/JSONL/CSV round-trip, stream_ingest chunking/error handling, export_stream |
| `test_query_runner_join_nested.py` | Nested path WHERE, JOIN with ON, ORDER BY DESC, projection |
| `test_query_runner_index_hint.py` | Index hint selection, `find(use_index=...)` |
| `test_txn_savepoints_isolation.py` | Savepoint create/rollback, isolation level APIs |
| `test_maintenance.py` | backup(), vacuum(), check_integrity() |
| `test_saved_queries_views_subscriptions.py` | save_query, run_saved_query, materialized views, poll subscriptions |
| `test_engine_index_pk.py` | Primary key handling, auto-UUID, index by PK |

**Tests missing / gaps:**
- No `tests/1.unit/`, `tests/2.integration/`, or `tests/3.advance/` directories exist yet (layout documented in `tests/README.md` but empty)
- Snapshot/restore (`snapshot.py`) not directly tested — only tested via `maintenance.py` `backup()`
- Parquet import/export conditionally skipped in `test_import_export.py`
- Multi-collection transaction partial-failure atomicity not tested (only single-collection covered)
- FastAPI snapshot routes (`fastapi_routes/snapshots.py`) not tested
- Large dataset performance not tested (no advance tests)
- xwauth audit hook (optional `audit_db_mutation`) not tested with or without xwauth-identity installed

---

## J. Risks, Unclear Parts, and Questions

**J1 — Indexes are rebuilt on every open (no persistence)**
All three index types are in-memory and rebuilt from the full collection file on `EmbeddedEngine.__init__()`. For large collections this is a startup cost paid every time the database is opened. `indexes/` directory exists in the on-disk layout but index persistence is listed as future work. No warning is shown when opening a large collection.

**J2 — Multi-collection transactions are not truly atomic**
`DatabaseTxn.commit()` writes each collection file sequentially. If the process crashes between the second and third collection write, the database is left in a partially-committed state. There is no global WAL or two-phase commit. The docs say "best-effort atomicity."

**J3 — Regex-based XWQS parser is fragile**
`query_runner.py:parse_to_plan()` uses regular expressions to parse SQL-like queries. Complex queries (subqueries, nested conditions, quoted strings with spaces, escaped characters) likely produce incorrect `QueryPlan` objects silently. There is no parser error path — `parse_to_plan()` always returns a `QueryPlan`, even for malformed input.

**J4 — `EmbeddedEngine` is 494 lines mixing concerns**
`engine.py` handles CRUD, FK validation, constraint checking, index management, security rule evaluation, schema validation, transaction coordination, and optional audit hooks. These are 7 distinct concerns in one class. Testing any one concern requires constructing the full engine state.

**J5 — Optional xwauth audit hook via bare `try/except ImportError`**
`engine.py` lines 279-283 attempt to import `exonware.xwauth.identity.audit` inside insert/update/delete methods. This is a design choice (lazy optional dependency, not a bug), but it means every mutation call attempts an import resolution in the Python module cache. If xwauth-identity is installed but the audit function signature changes, the failure is silently swallowed.

**J6 — `XWDatabaseConfig.options` dict has no schema**
The `options: dict[str, Any]` field is documented as an "extensibility dict" but no options are currently read from it. Callers passing options receive no validation or feedback.

---

## K. Suggested First Improvements

**K1 — Add index persistence**
Write index data to `indexes/{collection}/{name}.index` on every mutation and load it on open instead of rebuilding. Use a checksum to detect stale index files and fall back to rebuild. This eliminates the startup cost for large collections and is a prerequisite for production use.

**K2 — Add a WAL for multi-collection atomicity**
Write a WAL entry before each collection file write in `DatabaseTxn.commit()`. On open, check for incomplete WAL entries and either complete or roll them back. This makes multi-collection transactions truly atomic against process crashes.

**K3 — Replace regex parser with a proper XWQS parser**
Use `lark` or `pyparsing` (both available via PyPI) to parse XWQS. Define the grammar once, handle quoting and escaping correctly, and return parse errors on invalid input. The current regex approach will silently produce wrong results for any non-trivial query.

**K4 — Split `EmbeddedEngine` into focused classes**
Extract: `ConstraintValidator`, `IndexManager`, `ForeignKeyResolver`, `SecurityRuleEvaluator`, `SchemaValidator`. Each becomes independently testable. `EmbeddedEngine` becomes a coordinator that delegates to these. The interface of each extracted class is its single responsibility.

**K5 — Add `tests/1.unit/` for snapshot and import/export**
`snapshot.py` and `import_export.py` are substantial modules (150 + 378 lines respectively) with zero direct unit tests. Add `tests/1.unit/test_snapshot.py` (take → restore → list → delete round-trip, SHA256 manifest validation) and `tests/1.unit/test_import_export.py` (Parquet, large JSONL streaming, error handling callbacks).
