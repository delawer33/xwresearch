# xwauth-identity — Developer Report

**Package:** `exonware-xwauth-identity` v0.0.1.4 | **License:** Apache 2.0 | **Python:** 3.12+

---

## A. What the Repo Does

`xwauth-identity` is the **first-party identity provider** component of the eXonware auth stack. It handles everything that happens when a *real user logs in*:

- Email/password, magic links, phone OTP
- TOTP, SMS MFA, email MFA, backup codes
- WebAuthn / passkeys (FIDO2)
- Anonymous sessions
- Account linking (federated → local identity)
- Organizations, SCIM 2.0, Fine-Grained Authorization (FGA)
- Full OAuth 2.0 / OIDC authorization server (identical feature set to `xwauth`)

**Invariant:** This package **never imports** `exonware.xwauth.connect`. When installed alongside xwauth-connect, it discovers the connect package at runtime via `discover_connect_package()`. The two packages share the `exonware.xwauth` namespace via pkgutil.

Previously named `xwlogin` (see `pyproject.xwlogin.toml`).

---

## B. Backend Architecture

- **Pattern:** I-prefix Protocols + A-prefix Abstract classes + XWAuth facade
- **Async-first:** Python 3.12+, full async/await throughout
- **Framework adapters:** FastAPI, Flask, Django (ORM + DRF), SQLAlchemy mixins
- **Pluggable storage:** `IStorageProvider` with three implementations (mock, xwjson, xwstorage)
- **WebAuthn backends:** memory (default) or Redis for challenges and credential index
- **Lazy loading:** optional via `[lazy]` extra (exonware-xwlazy)

**Only mandatory dependency:** `exonware-xwsystem == 0.9.0.43`. Does not depend on `exonware-xwauth`.

---

## C. Main Folders and Files

```
src/exonware/xwauth/identity/
├── __init__.py              — Discovery helpers: discover_connect_package(), connect_is_available()
├── facade.py                — XWAuth (992 lines): full auth server init + all method dispatch
├── config/config.py         — XWAuthConfig: 60+ settings
├── contracts.py             — I-prefix Protocols (IProvider, ITokenManager, ISessionManager, ...)
├── base.py                  — A-prefix abstract base classes
├── defs.py                  — Enums (GrantType, TokenType, ProviderType 300+, ...)
├── errors.py                — Exception hierarchy (20+ types)
├── api_paths.py             — HTTP route prefix constants
├── core/
│   ├── oauth2.py            — OAuth2Server
│   ├── oidc.py              — OIDC layer
│   ├── pkce.py              — PKCE S256
│   ├── par.py               — PAR (RFC 9126)
│   ├── saml.py              — SAML 2.0 SP
│   ├── dcr.py               — Dynamic Client Registration
│   ├── logout.py            — RP-initiated logout
│   └── grants/              — 6 grant type handlers (including device_code, token_exchange)
├── authentication/
│   ├── email_password.py    — Email + password flow
│   ├── magic_link.py        — Magic link generation/verification
│   ├── phone_otp.py         — SMS OTP flow
│   ├── webauthn.py          — WebAuthn registration/assertion (anti-enumeration enabled)
│   ├── webauthn_factory.py  — Factory: selects memory or Redis backend
│   ├── challenge_store.py   — In-memory WebAuthn challenge store
│   ├── challenge_store_redis.py — Redis-backed WebAuthn challenges
│   ├── webauthn_credential_index.py — In-memory passkey store
│   ├── webauthn_credential_index_redis.py — Redis passkey store
│   ├── anonymous.py         — Anonymous sessions
│   ├── account_linking.py   — Link federated account to local user
│   ├── attestation_trust.py — Attestation CA validation + cert pinning
│   └── mfa/                 — totp.py, sms.py, email.py, backup_codes.py
├── tokens/                  — JWT, opaque, refresh, revocation, introspection, id_token signing
├── sessions/                — Session lifecycle, CSRF, storage
├── users/                   — User entity, lifecycle (activation, suspension, deletion)
├── organizations/           — Org entity, manager, lifecycle
├── storage/
│   ├── interface.py         — IStorageProvider protocol + data model protocols
│   ├── mock.py              — MockStorageProvider (in-memory)
│   ├── xwjson_provider.py   — xwjson-backed storage
│   └── xwstorage_provider.py — XWStorage adapter
├── federation/              — FederationBroker, OIDC id_token validation, JWKS cache, IdP quirks
├── scim/                    — SCIM 2.0 (RFC 7644): Users, Groups, filter, PATCH
├── audit/                   — AuditLogManager (27 event types), correlation context vars
├── security/
│   ├── password.py          — bcrypt / argon2 hashing
│   ├── mfa_secrets.py       — AES256-GCM envelope for TOTP seeds
│   ├── backup_codes.py      — One-time recovery codes
│   ├── mfa_policy.py        — MFA enforcement policies
│   ├── rate_limit.py        — Per-minute + per-hour limiter
│   └── secrets_store.py     — Ephemeral OTP / magic link storage
├── authorization/           — RBAC, ABAC, ReBAC, FGA policy engine
├── webhooks/                — Webhook entity, manager, delivery + retry
├── clients/                 — OAuth2ClientManager, AsyncOAuth2Session
├── jose/                    — JWT/JWS/JWE/JWK managers
├── handlers/mixins/         — 19 composable HTTP handler mixins (auth_core, oauth2_extended, mfa, passkeys, scim, fga, ...)
├── integrations/            — FastAPI, Flask, Django ORM, Django DRF, SQLAlchemy
└── ops_hooks.py             — Operational lifecycle hooks
```

---

## D. Data Models and Entities

| Model | Key Fields | Location |
|-------|-----------|----------|
| **User** | id, email, phone, password_hash, status (UserStatus), attributes, created_at, updated_at | users/user.py |
| **Session** | id, user_id, expires_at, status (SessionStatus), csrf_token, attributes, client_id | sessions/session.py |
| **Token** | id, user_id, client_id, token_type, access/refresh token, expires_at, scopes | storage/interface.py (Protocol) |
| **Organization** | id, name, slug, description, metadata, attributes | organizations/organization.py |
| **AuditLog** | id, user_id, org_id, tenant_id, correlation_id, action, timestamp, context | audit/manager.py |
| **WebAuthnChallenge** | challenge_id, challenge_bytes, user_id, expires_at | authentication/challenge_store.py |
| **WebAuthnCredential** | credential_id, public_key, sign_count, attestation_type, user_id | authentication/webauthn_credential_index.py |
| **DeviceCode** | device_code, user_code, client_id, scope, expires_at | storage/interface.py (Protocol) |

**Key enums:** same as `xwauth` plus `ProviderType` (300+ entries including all regional/AI providers).

---

## E. APIs, Endpoints, and Services

**HTTP path prefixes** (same as `xwauth`): `/v1/oauth2`, `/v1/oidc`, `/v1/auth`, `/v1/users`, `/v1/admin`, `/v1/organizations`, `/v1/webhooks`, `/scim/v2`, `/v1/system`, `/health`, `/metrics`.

**19 composable handler mixins** in `handlers/mixins/`:

| Mixin | Endpoints |
|-------|-----------|
| `auth_core` | /authorize, login, logout |
| `oauth2_extended` | /token, /revoke, /introspect |
| `client_registration` | Dynamic Client Registration (RFC 7591) |
| `user` | CRUD on /v1/users/* |
| `password` | Password reset/change |
| `otp` | OTP send/verify |
| `magic_link` | Magic link send/verify |
| `mfa` | TOTP enroll/verify, backup code use |
| `passkeys` | WebAuthn register/authenticate |
| `sessions` | Session list/revoke |
| `organizations` | Org CRUD + member management |
| `saml` | Assertion consumer, SAML metadata |
| `scim` | RFC 7644 /Users, /Groups CRUD |
| `fga` | Fine-grained authorization policy |
| `webhooks` | Webhook CRUD + delivery status |
| `admin` | Admin operations |
| `system` | Health, metrics, discovery |
| `oauth1` | OAuth 1.0 (RFC 5849) |
| `oauth_form_post` | OAuth form-post response renderer |

**XWAuth facade** (`facade.py`) — 6 grant types, WebAuthn factory, device code lifecycle, back-channel logout.

---

## F. Auth, Security, Config, and Env Variables

**`XWAuthConfig`** has the same 60+ fields as `xwauth` (see [xwauth.md](xwauth.md) section F) **plus:**

| Field | Default | Notes |
|-------|---------|-------|
| `allow_mock_storage_fallback` | `False` | Must be `True` explicitly for dev mode — raises XWConfigError otherwise |
| `webauthn_anti_enumeration_login` | `True` | Returns generic errors to prevent user enumeration |
| `webauthn_discoverable_login` | `True` | Passkey-first, username-optional |
| `webauthn_allow_insecure_defaults` | `False` | Blocks test deployments on non-HTTPS |
| `mfa_at_rest_algorithm` | `"aes256-gcm"` | TOTP seed encryption |
| `mfa_at_rest_key_b64` | derived from jwt_secret | 32-byte AES key |

**Env variables:**
- `XWSTACK_SKIP_XWLAZY_INIT` — skip xwlazy hook at import
- `XWAUTH_IDENTITY_DISABLE_CONNECT_DISCOVERY=1` — disable runtime discovery of xwauth-connect

**Security features verified in code:**
- PKCE: S256 only, plain rejected
- CSRF: state parameter required by default
- Password hashing: bcrypt or argon2 (configurable)
- TOTP seeds: AES256-GCM envelope encryption at rest
- WebAuthn: attestation CA bundle validation, cert pinning
- Rate limiting: per-minute + per-hour, configurable thresholds
- Backup codes: one-time use, stored hashed
- MFA failure delay (`mfa_failure_delay_ms`) for timing attack mitigation

---

## G. Database, Storage, Queues, and Background Jobs

- **Storage:** `IStorageProvider` protocol — same interface as xwauth. Three implementations: `MockStorageProvider` (dev), `XWJsonProvider` (xwjson-backed), `XWStorageProvider` (xwstorage adapter).
- **ORM integrations:** SQLAlchemy mixins, Django ORM models (in `integrations/`).
- **JWKS cache:** TTL-based, 3600s default.
- **WebAuthn state:** Memory (default) or Redis. Configured via `webauthn_challenge_backend` and `webauthn_credential_index_backend`.
- **No built-in job queue.** Webhook delivery has retry logic but no persistence queue.
- **Audit events:** logged via `AuditLogManager` with context vars (ASGI-compatible correlation IDs).

---

## H. How to Run Locally

```bash
pip install "exonware-xwauth-identity[dev]"   # core + pytest + pytest-asyncio

pytest tests/0.core/     # architecture boundary, API keys, security primitives
pytest tests/1.unit/     # provider tests, authentication flows, OAuth unit tests
pytest -m xwauth_identity_core  # fast boundary tests only
```

**Minimal usage:**
```python
from exonware.xwauth.identity.facade import XWAuth

auth = XWAuth(
    backend="local",
    format="xwjson",
    address="data/xwauth.xwjson",
    jwt_secret="your-secret-key",
)
# or with explicit storage:
auth = XWAuth(storage=my_storage_provider, jwt_secret="your-secret-key")
```

**With xwauth-connect discovery:**
```python
from exonware.xwauth.identity import connect_is_available, discover_connect_package
if connect_is_available():
    connect = discover_connect_package()
    # mount connect's SSO routes into your app
```

This is a library — not a standalone server. Wrap with FastAPI/Flask/Django using the handler mixins.

---

## I. Tests Available and Tests Missing

**Available (31 test files):**

| Path | Focus |
|------|-------|
| `tests/0.core/test_architecture_boundary.py` | Verifies identity never imports connect |
| `tests/0.core/test_import.py` | Canonical imports, lazy provider resolution |
| `tests/0.core/test_api_keys.py` | API key authentication |
| `tests/0.core/test_security_primitives.py` | PKCE, CSRF, rate limiting |
| `tests/1.unit/providers_tests/` | Google, Apple, Microsoft, GitHub, Samsung, LDAP, callback providers, registry |
| `tests/1.unit/authentication_tests/` | Email/password, magic link, OTP, anonymous, MFA, account linking |
| `tests/1.unit/handlers_tests/` | OAuth form-post |
| `tests/1.unit/oauth_tests/` | Token endpoint, grant types |

**Tests missing / gaps:**
- No integration tests — only `tests/0.core/` and `tests/1.unit/` exist (no `2.integration/`, `3.advance/`)
- WebAuthn registration/assertion flows not tested end-to-end
- MFA enrollment + verification not covered in existing test files
- Organization lifecycle (create, add member, archive) not tested
- SCIM 2.0 endpoints not tested
- FGA policy evaluation not tested
- handler mixins have no HTTP-level tests visible

---

## J. Risks, Unclear Parts, and Questions

**J1 — Duplicated contracts with `xwauth` (type fragmentation)**
`IProvider`, `ITokenManager`, `ISessionManager`, `IAuthenticator`, `IAuthorizer` are defined identically in both `xwauth/contracts.py` and `xwauth-identity/contracts.py`. Nominally different types despite structural equivalence. A provider class from xwauth-connect implementing `xwauth.contracts.IProvider` does not satisfy `xwauth-identity.contracts.IProvider` nominally, requiring duck-typing workarounds. ~500 lines duplicated with no mechanism to stay in sync. (See also: [xwauth.md J2](xwauth.md))

**J2 — Unclear package boundary with `xwauth` base**
Both packages implement OAuth2Server, TokenManager, SessionManager, User, Organization, FederationBroker, ScimService — a near-complete duplication. The documented split ("identity = first-party login; xwauth = contracts + federation") is not reflected in the file structure. New contributors cannot determine which package to add a feature to without reading both repos.

**J3 — Absolute imports block code sharing**
`xwauth-identity` uses absolute imports (`from exonware.xwauth.identity.X import Y`) throughout, while `xwauth` uses relative imports. This prevents straightforward extraction of shared logic between the two packages without copying it.

**J4 — Limited test coverage**
31 test files cover mostly unit-level concerns. No integration or advance test tiers exist. WebAuthn, SCIM, FGA, organizations, and MFA flows — the features unique to this package — have minimal test coverage. Given the security-critical nature of these flows, this is a significant gap.

**J5 — Discovery function duplication**
`discover_connect_package()` in this package and `discover_identity_package()` in xwauth-connect are byte-for-byte identical 35-line patterns. If one is updated (e.g., async support, different cache eviction), the other silently diverges. Should live in xwsystem as `discover_optional_package(module_name, disable_env_var)`.

**J6 — Redis dependency is undeclared for WebAuthn at scale**
WebAuthn in production typically requires Redis (`webauthn_challenge_backend="redis"`). Redis is an optional dependency, but there is no warning or documentation in the config class about the production requirement. Memory backend loses challenges on restart.

---

## K. Suggested First Improvements

**K1 — Add integration tests for WebAuthn, MFA, and SCIM (highest priority)**
These are the core differentiating features of this package and have no integration tests. Add `tests/2.integration/` covering: WebAuthn register → authenticate flow, TOTP enroll → verify, SCIM user create/patch/delete.

**K2 — Unify contracts into xwsystem (or a shared xwauth-contracts package)**
Same recommendation as xwauth K2. Eliminates the type-checking fragmentation and the 500-line duplication.

**K3 — Document the package boundary explicitly**
Add a `CONTEXT.md` and `docs/PACKAGE_BOUNDARY.md` that define: what lives only in identity (first-party ceremonies, WebAuthn credential store, MFA secrets), what lives only in xwauth-connect (external IdP connectors), and what is shared (OAuth 2.0 mechanics). This resolves contributor confusion about where to add features.

**K4 — Switch to relative imports**
A one-pass `sed` or `isort` conversion. Makes the package easier to test in isolation and consistent with xwauth.

**K5 — Add Redis to `[prod]` extra and document it**
Create a `[prod]` extra that includes `redis>=4.0.0` and add a note in `XWAuthConfig` docstring that `webauthn_challenge_backend="redis"` is required for multi-process deployments.
