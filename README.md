# eXonware Repo Ecosystem — Overview

---

## Two Families, One Namespace Each

```
exonware.xwauth.*              exonware.xwstorage.*
───────────────────            ──────────────────────
xwauth          (base)         xwstorage        (base/contracts)
xwauth-identity (first-party)  xwstorage-connect (connector runtime)
xwauth-connect  (external IdP) xwstorage-db      (embedded DB engine)
```

Each family shares a **pkgutil namespace package** — multiple PyPI distributions contribute to the same Python import namespace without depending on each other.

---

## xwauth Family

| Repo              | Package                    | Role                                                                                                                                    |
| ----------------- | -------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| `xwauth`          | `exonware-xwauth`          | OAuth 2.0 / OIDC core library: contracts, base classes, facade, tokens, sessions, federation, JOSE, SCIM, audit, webhooks, integrations |
| `xwauth-identity` | `exonware-xwauth-identity` | First-party login ceremonies: email/password, magic links, phone OTP, TOTP, WebAuthn/passkeys, MFA, organizations, B2B, SCIM, FGA       |
| `xwauth-connect`  | `exonware-xwauth-connect`  | External IdP connector: 250+ OAuth/OIDC providers (Google, Apple, Microsoft, GitHub, …), SAML, LDAP, regional providers                 |

**Invariant:** `xwauth-identity` never imports `xwauth-connect`. Both discover each other at runtime via `discover_connect_package()` / `discover_identity_package()`.

**Install combinations:**

- `xwauth` alone → OAuth 2.0 mechanics + client helpers, no login UI
- `xwauth` + `xwauth-identity` → full first-party IdP
- `xwauth` + `xwauth-connect` → federated SSO broker
- All three → complete auth platform

---

## xwstorage Family

| Repo                | Package                      | Role                                                                                                                                                                         |
| ------------------- | ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `xwstorage`         | `exonware-xwstorage`         | Shared contracts, error types, enums, path utilities, one concrete local (file-backed) connector                                                                             |
| `xwstorage-connect` | `exonware-xwstorage-connect` | Connector runtime: 50+ backend connectors (PostgreSQL, MongoDB, Neo4j, Redis, S3, …), HTTP API server, ACID transactions, MVCC, deadlock detection, RLS, encryption, caching |
| `xwstorage-db`      | `exonware-xwstorage-db`      | Embedded XW-native database engine: XWJSON-backed, CRUD, indexing (hash/sorted/trigram), transactions, snapshots, RLS, streaming I/O, admin CLI                              |

**Dependency direction:** `xwstorage-db` → `xwstorage` ← `xwstorage-connect`. xwstorage-connect may use xwstorage-db as an engine driver; xwstorage-db must NOT import xwstorage-connect.

---

## Cross-Family Integration

```
Application
    │
    ├─ xwauth / xwauth-identity / xwauth-connect
    │       │
    │       └─ IStorageProvider ──► xwstorage / xwstorage-connect
    │
    └─ xwstorage / xwstorage-connect
            │
            └─ optional embedded engine ──► xwstorage-db
```

Auth packages use storage packages via `IStorageProvider` (pluggable). `xwstorage-connect` can wire `xwstorage-db` as the embedded engine backend.

---

## Shared Base: xwsystem

All 6 repos depend on `exonware-xwsystem` (v0.9.0.x). It provides: security primitives, HTTP client, serialization, logging, `XWObject` base class, `PolicyContext` / `IAuthContextResolver` contracts.

---

## Versions at Time of Analysis (June 2026)

| Repo              | Version  | Status    |
| ----------------- | -------- | --------- |
| xwauth            | 0.0.1.11 | Alpha     |
| xwauth-identity   | 0.0.1.4  | Alpha     |
| xwauth-connect    | 0.0.1.11 | Alpha     |
| xwstorage         | 0.0.1.9  | Alpha     |
| xwstorage-connect | 0.0.1.9  | Alpha     |
| xwstorage-db      | 0.0.1.5  | Pre-alpha |

---

## Individual Reports

- [xwauth.md](xwauth.md)
- [xwauth-identity.md](xwauth-identity.md)
- [xwauth-connect.md](xwauth-connect.md)
- [xwstorage.md](xwstorage.md)
- [xwstorage-connect.md](xwstorage-connect.md)
- [xwstorage-db.md](xwstorage-db.md)
