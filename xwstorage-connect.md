# xwstorage-connect — Developer Report

**Package:** `exonware-xwstorage-connect` v0.0.1.9 | **License:** Apache 2.0 | **Python:** 3.12+

---

## A. What the Repo Does

`xwstorage-connect` is the **connector runtime and control plane** for the eXonware storage stack. It provides:

- Unified `XWConnection` / `XWStorage` / `XWStorageDb` facade over 50+ heterogeneous backends
- Production storage features: ACID transactions, MVCC, deadlock detection, savepoints, isolation levels
- Security: row-level security (RLS), access control, encryption at rest, TLS config, audit logging
- Infrastructure: connection pooling, caching (LRU/LFU), batch operations, counters, change feed (WebSocket)
- Query translation: unified query → SQL / MongoDB / Cypher / vector / PostgREST
- Optional HTTP API server (FastAPI-based)
- Lazy-loaded connector registry: 120+ backends indexed at import, loaded on first use

**Philosophy:** Firebase-style ergonomics over heterogeneous backends. One facade, many engines. The connector packages themselves are lazy-loaded — only what's used gets imported.

---

## B. Backend Architecture

- **Pure async Python 3.12+**, no web framework in core library
- **Connector registry pattern** — pluggable backends with lazy install via xwlazy
- **Strategy pattern** — `StrategyManager` selects LSM_TREE / HASH_MAP / LRU_CACHE per operation
- **Protocol-based** — `IConnectorConfig`, `IStorageConnection` from `exonware-xwstorage`
- **Optional HTTP API** — FastAPI routes via `[api]` extra

**Primary dependency:** `exonware-xwstorage` (shared contracts)
**Stack integration:** xwentity, xwdata, xwnode, xwquery, xwaction (all optional)

---

## C. Main Folders and Files

```
src/exonware/xwstorage/connect/
├── __init__.py (3,448 lines)     — ALL core classes: XWConnection, XWStorage, XWStorageDb,
│                                   LocalStorageConnection, ConnectionPool, TransactionManager,
│                                   MVCCManager, LockManager, DeadlockDetector, IsolationManager,
│                                   CacheManager, BatchOperations, RLSPolicy, AccessControlManager,
│                                   AuditLogger, EncryptionAtRest, TLSConfig, BTreeIndex, etc.
├── mapping.py                    — translate_filter_to_sql(), translate_filter_to_postgrest(),
│                                   MappedQuery (SQL/mongo/cypher/vector/object/http path)
├── contracts.py                  — Re-exports IConnectorConfig, IStorageConnection from xwstorage
├── defs.py                       — Re-exports IsolationLevel, LockMode, TriggerEvent from xwstorage
├── errors.py                     — Re-exports XWStorageError, XWConnectionError from xwstorage
├── stack.py                      — Opt-in eager imports of XW stack
├── _connector_cfg_display.py     — CLI formatting for connector configs
├── _connector_field_synthesis.py — Config field generation (dataclass synthesis)
├── _connector_test_fields.py     — Test field factories
├── _acid_document_connection.py  — ACID guarantees for document operations
├── _strategy_connectors.py       — Strategy pattern binding
├── api/
│   ├── server.py (84 lines)      — XWStorageAPIServer (XWApiServer subclass)
│   ├── routes.py (38 lines)      — Health + surface route registration
│   ├── data_routes.py (524 lines) — Storage CRUD, batch, transactions, counters, change feed HTTP endpoints
│   └── compose.py (137 lines)    — Full app factory (host + port + storage path)
├── connectors/
│   └── xwstorage_connect_db_bridge.py — XWStorageDbRemoteConfig (HTTP config for remote DB)
└── core/ + data/                 — Lock manager and counter imports
tests/
├── 0.core/                — Core features, connectors, mapping
├── 1.unit/                — 220+ files: connectors, indexes, transactions, queries, auth, operations
├── 2.integration/         — Transaction integration, access control delegation
└── 3.advance/             — Security, performance
```

---

## D. Data Models and Entities

**Key dataclasses** (all in `__init__.py`):

| Class | Key Fields |
|-------|-----------|
| `LocalConnectorConfig` | address, base_path, atomic_writes, security, connector_type |
| `Transaction` | transaction_id, isolation_level, state, savepoints, start_time |
| `TransactionMetadata` | transaction_id, start_time, operation_count, wait_time |
| `Version` (MVCC) | version_id, resource, transaction_id, data, created_at, previous_version_id, status, committed_at |
| `EncryptionMetadata` | algorithm, key_id, nonce, associated_data, timestamp |
| `TLSConfig` | tls_version, verify_certificates, ca_cert_file, client_cert_file, cipher_suites |
| `MappedQuery` | table_or_collection, sql, mongo_filter, cypher, vector_query, object_path, http_path, postgrest_params |
| `XWStorageDbRemoteConfig` | base_url, timeout_s |

**Key enums** (re-exported from xwstorage + own):

| Enum | Values |
|------|--------|
| `IsolationLevel` | READ_UNCOMMITTED, READ_COMMITTED, REPEATABLE_READ, SERIALIZABLE |
| `LockMode` | SHARED, EXCLUSIVE |
| `VictimSelectionStrategy` | DEFAULT, YOUNGEST, LEAST_WORK, LONGEST_WAIT |
| `VersionStatus` | UNCOMMITTED, COMMITTED, ABORTED |
| `EvictionPolicy` | LRU, LFU |
| `WritePolicy` | WRITE_THROUGH, WRITE_BACK |
| `TLSVersion` | TLS_1_2, TLS_1_3 |
| `EncryptionAlgorithm` | AES_GCM_128, AES_GCM_256, FERNET |
| `CounterType` | INTEGER, FLOAT |

---

## E. APIs, Endpoints, and Services

**Python API (`__init__.py`):**

```python
# High-level entry
get_storage_facade(backend="embedded") -> XWStorage

# Connection
conn = XWConnection(auth=None, config={"connector": "local", "address": "...", "format": "json"})
await conn.write(path, data)
await conn.read(path)
await conn.exists(path)
await conn.delete(path)
await conn.query(collection, filter_expr)
async with conn.transaction() as txn:
    await txn.write(path, data)

# Transactions
txn_mgr = TransactionManager()
txn = txn_mgr.begin_transaction(isolation_level=IsolationLevel.READ_COMMITTED)
await txn.create_savepoint("before_update")
await txn.commit()

# Connection pooling
pool = ConnectionPool(connector_factory, min_size=1, max_size=10)
conn = await pool.get_connection()
await pool.return_connection(conn)

# Caching
cache = CacheManager(max_size=100, eviction_policy="lru")
cache.put("key", value)
value = cache.get("key")

# Counters
counter_mgr = CounterManager()
counter = await counter_mgr.get_or_create("requests", CounterType.INTEGER)
await counter.increment(1)

# Access control
acl = AccessControlManager(auth_provider)
ok = await acl.check_access_context(policy_context, resource, action)

# MVCC
mvcc = MVCCManager()
mvcc.create_snapshot(tx_id, timestamp)
history = mvcc.get_revision_history(resource, limit=10)

# Deadlock detection
detector = DeadlockDetector(lock_mgr, victim_strategy=VictimSelectionStrategy.YOUNGEST)
```

**HTTP API** (`api/data_routes.py`, prefix `/v1` by default):

| Method | Path | Action |
|--------|------|--------|
| POST | `/v1/storage/{path}` | write / upsert |
| PUT | `/v1/storage/{path}` | save |
| GET | `/v1/storage/{path}` | read |
| GET | `/v1/storage/{path}/exists` | exists check |
| DELETE | `/v1/storage/{path}` | delete |
| POST | `/v1/storage/query` | query (collection + filter) |
| POST | `/v1/storage/execute` | execute raw query string |
| POST | `/v1/storage/batch` | batch ops |
| GET/POST/DELETE | `/v1/connections/{conn_id}` | connection management |
| POST/POST/POST | `/v1/transactions/{tx_id}/commit|rollback|write` | transaction control |
| POST/POST/GET | `/v1/counters/{name}/increment|decrement` | counters |
| WS | `/v1/changefeed` | pub/sub change events |
| GET | `/xwstorage.connect/health` | health check |
| GET | `/xwstorage.connect/surface` | API surface discovery |

---

## F. Auth, Security, Config, and Env Variables

**Access control (`__init__.py:952`):**
- `AccessControlManager(auth_provider)` — if auth_provider has `check_permission_context()`, delegates; otherwise falls back to scope parsing if `allow_local_fallback=True`
- `PolicyContext` + `policy_context_from_principal()` from `xwsystem.security`

**Path security (`__init__.py:209-215`):**
- Rejects null bytes, newlines, CR
- `security=True`: forbids `..` traversal and absolute paths
- `forbidden_addresses`: blocks `/etc`, `/sys`, `/proc`, Windows system32

**Encryption at rest (`__init__.py:1094-1177`):**
- `EncryptionAtRest` class; reference implementation uses XOR cipher (⚠️ NOT production-grade)
- Supports key rotation via `LocalKeyManager`
- Saves `EncryptionMetadata` alongside encrypted files

**TLS (`__init__.py:1214-1256`):**
- `TLSConfig.create_ssl_context()` — configures client certs, CA bundle, cipher suites

**Audit logging (`__init__.py:1015-1027`):**
- `AuditLogger` records: user_id, operation, resource, result + compliance events

**Env variables:**

| Variable | Default | Usage |
|----------|---------|-------|
| `XWSTORAGE_LAZY_CONNECTORS` | — | Enable lazy connector loading |
| `XWSTORAGE_API_HOST` | `127.0.0.1` | HTTP API host |
| `XWSTORAGE_API_PORT` | `8001` | HTTP API port |
| `XWSTORAGE_API_STORAGE_PATH` | `.data/xwstorage.connect` | Storage directory |

---

## G. Database, Storage, Queues, and Background Jobs

**Storage backends** (50+ via lazy-loaded connectors):

| Category | Examples |
|----------|---------|
| Embedded | Local filesystem (JSON/xwjson), RocksDB, LevelDB, LMDB |
| SQL | PostgreSQL, MySQL, Oracle, SQL Server, Supabase, SQLite |
| NoSQL | MongoDB, CouchDB, Couchbase, ArangoDB, RethinkDB |
| Graph | Neo4j, Neptune (Gremlin + SPARQL), Dgraph |
| Key-Value | Redis, DynamoDB, Aerospike, Riak, Memcached |
| Search | Elasticsearch, OpenSearch, Solr, MeiliSearch |
| Time-Series | InfluxDB, TimescaleDB, QuestDB |
| Vector | Pinecone, Weaviate, Qdrant, Milvus, LanceDB |
| Object Storage | S3, Azure Blob, GCS, Wasabi, Linode |
| Cloud Files | Google Drive, OneDrive, Dropbox, Box, Sheets |
| Message Queues | Kafka, RabbitMQ, NATS, Pulsar, ActiveMQ |

**Persistence features (local backend):**
- WAL via xwjson ≥ 0.10 when `format="xwjson"`
- Atomic writes via `.tmp` rename when `atomic_writes=True`
- ACID transactions with multi-collection batch and savepoints
- MVCC with per-transaction snapshot timestamps
- In-memory cache (LRU/LFU) with write-through/write-back policies

**No built-in job scheduler.** WebSocket change feed is in-memory pub/sub (not persistent).

---

## H. How to Run Locally

```bash
pip install "exonware-xwstorage-connect[dev]"

# Run tests
pytest tests/0.core/      # core, fast
pytest tests/             # all (221 failures expected without connector packages)

# Run HTTP API server
from exonware.xwstorage.connect.api.compose import create_full_xwstorage_http_app
app = create_full_xwstorage_http_app(host="0.0.0.0", port=8001)
# uvicorn app:app --host 0.0.0.0 --port 8001

# Verify lazy loading
python test_lazy_loading.py
python test_google_lazy_loading.py
```

**Env for HTTP server:**
```bash
export XWSTORAGE_API_HOST=0.0.0.0
export XWSTORAGE_API_PORT=8001
export XWSTORAGE_API_STORAGE_PATH=.data/xwstorage.connect
```

---

## I. Tests Available and Tests Missing

**Available (250+ test files):**

| Path | Focus |
|------|-------|
| `tests/0.core/` | Core features, local connector, mapping, workspace smoke |
| `tests/1.unit/connectors_tests/` | Per-connector config + connection tests (60+ connectors) |
| `tests/1.unit/indexes_tests/` | BTree, hash, fulltext, R-tree, LSM, vector indexes |
| `tests/1.unit/transactions_tests/` | MVCC, deadlock, isolation, savepoints |
| `tests/1.unit/auth_tests/` | OAuth, access control interface |
| `tests/2.integration/` | Transaction integration, access control delegation |
| `tests/3.advance/` | Security, performance |

**Test statistics:** 1,291 passed, 221 failed (connector packages not installed), 60 skipped.

**Tests missing / gaps:**
- HTTP API (`api/data_routes.py`) has no tests — 524 lines of endpoints untested
- `EncryptionAtRest` XOR reference implementation has no tests
- `AccessControlManager.check_access_context()` delegation to xwauth is the only integration test and it **currently fails** (`test_strict_access_control_delegation.py` in `_failures.txt`)
- `MVCCManager` snapshot isolation end-to-end not covered
- `DeadlockDetector` victim selection strategies (YOUNGEST, LEAST_WORK, LONGEST_WAIT) are in `_failures.txt`
- `TLSConfig.create_ssl_context()` untested
- WebSocket change feed untested

---

## J. Risks, Unclear Parts, and Questions

**J1 — 3,448-line `__init__.py` is a god module**
Every core class — `XWConnection`, `XWStorage`, `TransactionManager`, `MVCCManager`, `LockManager`, `DeadlockDetector`, `CacheManager`, `EncryptionAtRest`, `AuditLogger`, `ConnectionPool`, `BatchOperations`, `RLSPolicy`, `AccessControlManager`, `TLSConfig`, `BTreeIndex`, `HashIndex`, `CounterManager`, and more — lives in a single file. Navigating, testing, and modifying any one class requires loading all context from all classes. The deletion test: removing any single class would not reduce the file's complexity — it would just move it elsewhere, confirming each class earns its keep but the file itself is too deep.

**J2 — Encryption at rest uses XOR (explicitly "reference implementation")**
`EncryptionAtRest` uses XOR cipher (comments say "reference impl"). The enum `EncryptionAlgorithm` lists AES_GCM_128, AES_GCM_256, FERNET, but the actual implementation is XOR. Any caller who enables encryption at rest gets XOR, not AES. This is a silent security issue — no warning is raised.

**J3 — xwauth integration test fails**
`tests/2.integration/test_strict_access_control_delegation.py` is in `_failures.txt`. This is the only test verifying `AccessControlManager` delegates to xwauth. The integration between the two stacks is untested and broken.

**J4 — `_connector_cfg_display.py`, `_connector_field_synthesis.py`, `_connector_test_fields.py` are opaque**
Three private underscore-prefixed modules doing "config field generation (dataclass synthesis)". Their interface is not documented and they are not tested directly. Their deletion test is unclear — removing them may break connector config generation silently.

**J5 — Query optimizer returns `None` stubs without xwquery**
`StorageQueryOptimizer` returns `None` stubs when `exonware-xwquery` is not installed. Callers may not notice the degraded behavior. `_failures.txt` shows query tests failing because `parse_query` and `translate_query` return `None`.

**J6 — 221 failing tests include core behaviors**
Unlike xwstorage where failures are all connector-specific, the failures here include: deadlock victim selection, MVCC isolation, index operations, batch operations, and the xwauth access control integration. These are core features, not missing external dependencies.

---

## K. Suggested First Improvements

**K1 — Break `__init__.py` into focused modules**
Split by concern: `transaction.py` (TransactionManager, Transaction, Savepoint), `mvcc.py` (MVCCManager, Version), `locking.py` (LockManager, DeadlockDetector), `cache.py` (CacheManager), `encryption.py` (EncryptionAtRest, LocalKeyManager), `audit.py` (AuditLogger), `access_control.py` (AccessControlManager, RLSPolicy). Re-export from `__init__.py`. This is a pure mechanical split with zero behavior change and makes every class independently navigable and testable.

**K2 — Replace XOR encryption with AES-GCM or raise NotImplementedError**
Either: (a) implement AES-GCM-256 using the `cryptography` library (already a dependency of xwauth), or (b) raise `NotImplementedError("XOR is a reference implementation; install exonware-xwstorage-connect[crypto] for AES-GCM")`. Option (b) is safer and prevents silent data exposure.

**K3 — Fix the xwauth access control integration test**
`test_strict_access_control_delegation.py` is the only test covering the xwauth + xwstorage integration seam. Investigate why it fails and fix it. This is the most valuable integration test in the codebase.

**K4 — Add HTTP API tests**
`api/data_routes.py` is 524 lines with no tests. Add a `pytest-asyncio` test module using FastAPI's `TestClient` covering: write/read/delete, batch ops, transaction begin/commit/rollback, and counter increment/decrement.

**K5 — Add null-guard for query optimizer**
When `StorageQueryOptimizer` returns `None`, log a warning and return empty results rather than propagating `None` to callers. Document clearly in config that xwquery is needed for non-trivial queries.
