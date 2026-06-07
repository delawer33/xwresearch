# xwstorage — Developer Report

**Package:** `exonware-xwstorage` v0.0.1.9 | **License:** Apache 2.0 | **Python:** 3.12+

---

## A. What the Repo Does

`xwstorage` is the **shared contracts and core layer** for the eXonware storage stack. It provides:

- Protocol interfaces (`IConnectorConfig`, `IStorageConnection`, `IStorageEngine`) used by all storage packages
- Abstract base classes (`AStorageConnection`, `AStorageFacade`)
- One concrete backend: **local file-backed connector** (JSON or xwjson binary)
- High-level facades (`XWConnection`, `XWStorage`, `XWDB`) that are backend-agnostic
- Enums for isolation levels, lock modes, trigger events, transaction states
- Path utilities for nested JSON operations
- An HTTP bridge config for connecting to a remote xwstorage-db instance

**Philosophy:** The core package stays lean. Connector-heavy behavior lives in `exonware-xwstorage-connect`. Database engine internals live in `exonware-xwstorage-db`. The core boundary is enforced by `scripts/check_package_boundaries.py`.

---

## B. Backend Architecture

- **Pattern:** I-prefix Protocol → A-prefix Abstract → XW-prefix Concrete
- **Async-first:** all public I/O methods are `async def`
- **Lazy loading:** optional via `exonware-xwlazy` (indexed at import, loaded on first use)
- **Env variable:** `XWSTORAGE_LAZY_CONNECTORS` enables lazy connector mode

**Core dependencies:** `exonware-xwsystem == 0.9.0.39`, `exonware-xwformats == 0.9.0.33`

**Optional extras:** `[xw]` (full XW stack), `[lazy]` (xwlazy), `[full]` (all connectors pre-installed), `[stack]` (xwjson through xwaction), `[dev]` (pytest, black, isort, mypy).

---

## C. Main Folders and Files

```
src/exonware/xwstorage/
├── __init__.py            — Public API re-exports + lazy registration (try/except on xwlazy import)
├── contracts.py           — IConnectorConfig, IStorageConnection, IStorageEngine (Protocols, @runtime_checkable)
├── base.py                — AStorageConnection, AStorageFacade (abstract bases with batch defaults)
├── facade.py              — XWConnection, XWStorage, XWDB (backend-agnostic facades)
├── defs.py                — IsolationLevel, LockMode, TriggerEvent, TransactionState, VictimSelectionStrategy
├── errors.py              — XWStorageError, XWConnectionError, XWLocationError
├── local_connection.py    — LocalConnectorConfig + LocalStorageConnection (only concrete in core)
├── path_utils.py          — split_path, get_nested, set_nested, del_nested (nested JSON path ops)
├── stack.py               — Opt-in eager imports of xwjson, xwnode, xwdata, ..., xwaction
├── version.py             — __version__ = "0.0.1.9"
└── connectors/
    ├── registry.py        — ConnectorRegistryFacade (minimal stub)
    └── xwdb_bridge.py     — XWDBRemoteConfig (HTTP bridge config for remote engine)
tests/
├── conftest.py            — Global fixtures: temp_dir, sample_data, test_path, json_format
├── 0.core/                — Core connector tests, safety tests, workspace smoke tests
├── 1.unit/                — 220+ test files: connectors, indexes, operations, queries, transactions
└── 2.integration/         — test_strict_access_control_delegation.py
scripts/
└── check_package_boundaries.py  — Enforces: core must not import connect or db
```

---

## D. Data Models and Entities

**`LocalConnectorConfig`** (`local_connection.py:46`):
- `address: str | Path` — storage file path
- `base_path: str | Path | None` — security-restrict writes to this directory
- `atomic_writes: bool` — write via `.tmp` + rename
- `security: bool` — enable path traversal checks
- `connector_type: str = "local"`

**`LocalStorageConnection`** (`local_connection.py:69`):
- `config: LocalConnectorConfig`
- `data_format: str` — `"json"` or `"xwjson"` / `"xwj"` (binary)
- `backend_type = "local"`
- Tracks `_known_paths: set[str]` and `_db_file: Path`

**`XWDBRemoteConfig`** (`connectors/xwdb_bridge.py:17`):
- `base_url: str` — remote database API endpoint
- `timeout_s: float = 30.0`

**Enums** (`defs.py`):

| Enum | Values |
|------|--------|
| `IsolationLevel` | READ_UNCOMMITTED, READ_COMMITTED, REPEATABLE_READ, SERIALIZABLE |
| `LockMode` | SHARED, EXCLUSIVE |
| `TriggerEvent` | BEFORE/AFTER INSERT/UPDATE/DELETE |
| `TransactionState` | ACTIVE, COMMITTED, ROLLED_BACK |
| `VictimSelectionStrategy` | DEFAULT, YOUNGEST, LEAST_WORK, LONGEST_WAIT |

**Batch result shapes** (`base.py`):
- Save/delete: `{"success": int, "failed": int, "errors": [{"path": str, "error": str, "type": str}]}`
- Load: `{path: data | None}`
- Exists: `{path: bool}`

---

## E. APIs, Endpoints, and Services

**`XWConnection`** (`facade.py:32`) — low-level:
```python
XWConnection(auth=None, config=dict | None, connection=None)
# config: {"connector": "local", "address": "...", "format": "json"}
await conn.save(data, path)
await conn.load(path)
await conn.exists(path)
await conn.delete(path)
await conn.write(path, data)   # alias for save
await conn.read(path)          # alias for load
await conn.batch_save(items)
await conn.batch_load(paths)
await conn.batch_exists(paths)
await conn.batch_delete(paths)
await conn.ping()
```

**`XWStorage`** (`facade.py:64`) — high-level:
- Same interface as XWConnection plus: `backend`, `format`, `address`, `trigger_manager` properties.

**`XWDB`** (`facade.py:104`) — with schema:
- Same as XWStorage plus optional `schema` validation on every write.

**`LocalStorageConnection`** extended methods:
```python
await conn.copy(source_path, dest_path)
await conn.move(source_path, dest_path)
await conn.list_files(pattern=None, recursive=False)
await conn.get_metadata(path)  # size, modified_time, created_time, is_file
await conn.bulk_store(operations)
await conn.bulk_retrieve(paths)
await conn.execute_query(query, params)  # stub, returns []
```

---

## F. Auth, Security, Config, and Env Variables

**Security in `LocalStorageConnection`** (`local_connection.py:109-121`):
- Rejects null bytes, newlines, carriage returns in paths
- When `security=True`: rejects `..` traversal and absolute paths
- When `base_path` set: verifies resolved path stays within base_path

**Env variables:**
- `XWSTORAGE_LAZY_CONNECTORS` — enables lazy connector loading (checked in test scripts)

**No auth enforcement in core.** Auth object is passed through to facades but not evaluated. Access control enforcement lives in `xwstorage-connect` (`AccessControlManager`) and integrates with `xwauth` via `IAuthContextResolver`.

---

## G. Database, Storage, Queues, and Background Jobs

**Local connector (`local_connection.py`):**
- Single `.json` file with nested dict structure
- `format="xwjson"` uses binary xwjson codec (WAL support when xwjson ≥ 0.10)
- `atomic_writes=True`: write to `.tmp` then `os.rename()` (atomic on POSIX)
- No sharding, replication, or background compaction in core

**Remote bridge (`connectors/xwdb_bridge.py`):**
- `XWDBRemoteConfig(base_url, timeout_s)` — HTTP client config for remote xwstorage-db
- No in-process database loading (deprecated; removed from core per `xwdb_bridge.py:33-44`)

**No queues, background jobs, or caching** in this package.

---

## H. How to Run Locally

```bash
pip install "exonware-xwstorage[dev]"

# Run tests
pytest tests/0.core/           # fast core tests
pytest tests/             # all (221 failures in connector tests — expected without connectors)

# Verify lazy loading
python test_lazy_loading.py
python test_google_lazy_loading.py

# Check package boundaries
python scripts/check_package_boundaries.py
```

**Minimal usage:**
```python
from exonware.xwstorage import XWConnection

conn = XWConnection(config={"connector": "local", "address": "/path/to/storage.json"})
await conn.save({"key": "value"}, "my/path")
data = await conn.load("my/path")
await conn.delete("my/path")
```

---

## I. Tests Available and Tests Missing

**Available:**

| Path | Focus |
|------|-------|
| `tests/0.core/test_core_connectors.py` | LocalConnector: save/load/delete/list, Protocol compliance |
| `tests/0.core/test_core_safety.py` | Path security validation (null bytes, traversal, absolute paths) |
| `tests/0.core/test_workspace_smoke.py` | Basic workspace integration |
| `tests/1.unit/connectors_tests/` | 150+ per-connector unit tests (most require connector packages) |
| `tests/1.unit/indexes_tests/` | Fulltext, R-tree, LSM, vector, universal indexes |
| `tests/1.unit/transactions_tests/` | Deadlock detection, MVCC, isolation levels |
| `tests/2.integration/test_strict_access_control_delegation.py` | xwauth integration for access control |

**Test statistics (latest run):** 1,291 passed, 221 failed (connector packages not installed), 60 skipped.

**Tests missing / gaps:**
- `tests/0.core/test_core_features.py` is entirely skipped (requires `MockAuthProvider` not in core)
- `XWStorage` and `XWDB` facades have no dedicated tests — only `XWConnection` is directly tested
- `path_utils.py` (`split_path`, `get_nested`, `set_nested`, `del_nested`) has no unit tests
- `connectors/xwdb_bridge.py` (remote HTTP bridge) has no tests
- Atomic write behavior (`atomic_writes=True`) not explicitly tested
- WAL behavior (xwjson format) not tested in core
- `stack.py` opt-in imports untested

---

## J. Risks, Unclear Parts, and Questions

**J1 — 221 failing tests are structural, not behavioral**
The 221 failures are all in `tests/1.unit/connectors_tests/` where connector packages (kafka, mongodb, mysql, etc.) are not installed. These tests exist in the `xwstorage` core repo but test xwstorage-connect functionality. This is a boundary violation: the core repo contains tests that belong in xwstorage-connect.

**J2 — `XWStorage` and `XWDB` facades untested**
`XWStorage` and `XWDB` in `facade.py` are the primary user-facing classes but have no direct tests. Only `XWConnection` has core coverage. If `XWStorage.trigger_manager` interaction or `XWDB.schema` validation breaks, no existing test catches it.

**J3 — `execute_query` is a no-op stub**
`LocalStorageConnection.execute_query()` returns `[]` unconditionally. This is the seam for query execution but is never implemented or tested in core. Callers may assume it works.

**J4 — `ConnectorRegistryFacade` is a minimal stub**
`connectors/registry.py` appears to be a placeholder. The real registry lives in `xwstorage-connect`. Code that imports from `exonware.xwstorage.connectors.registry` gets a stub, not the real registry.

**J5 — Auth object threading**
`XWConnection`, `XWStorage`, and `XWDB` all accept an `auth` parameter that is stored but never used within the core package. It is passed through without any validation. The contract for what `auth` must provide is not documented.

**J6 — Local connector file contention**
`LocalStorageConnection` loads the entire database into memory on open and writes the full dict back on every save. There is no file locking between concurrent processes. Two processes using the same `address` file will corrupt each other's state silently.

---

## K. Suggested First Improvements

**K1 — Move connector unit tests to `xwstorage-connect`**
The 221 failing tests in `tests/1.unit/connectors_tests/` belong in the `xwstorage-connect` repo. Moving them removes the structural failures from core CI and enforces the package boundary that `scripts/check_package_boundaries.py` is meant to protect.

**K2 — Add tests for `XWStorage` and `XWDB` facades**
Two lines of `conftest.py` and a 20-line test module cover the most-used public API. Add at minimum: `XWStorage` init, write/read/delete round-trip, and `XWDB` schema-validation-on-write.

**K3 — Add a docstring or ADR for the `auth` parameter contract**
Document what `auth` must implement (or remove it from core if it is always `None`). If it is intended to be an `IAuthContextResolver`, say so and add a type annotation.

**K4 — Add file locking to `LocalStorageConnection`**
Use `fcntl.flock` (POSIX) or `msvcrt.locking` (Windows) around reads and writes. Without this, multi-process use silently corrupts data. Add a test with two concurrent writers.

**K5 — Implement or remove `execute_query`**
Either implement a basic path-based query (filter by key prefix) or remove the method and raise `NotImplementedError`. A stub that silently returns `[]` is more dangerous than a clear `NotImplementedError`.
