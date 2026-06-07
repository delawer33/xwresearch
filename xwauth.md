# xwauth — Developer Report

**Package:** `exonware-xwauth` v0.0.1.11 | **License:** Apache 2.0 | **Python:** 3.12+

---

## A. What the Repo Does

`xwauth` is the **OAuth 2.0 / OIDC authorization server core library** for the eXonware stack. It provides:

- Full OAuth 2.0 (RFC 6749/2.1) and OpenID Connect server-side implementation
- All 6 grant types: authorization code, client credentials, resource owner password, refresh token, device code (RFC 8628), token exchange (RFC 8693)
- Federation broker for 100+ external IdPs
- Token lifecycle (JWT + opaque), session management, JOSE (JWT/JWS/JWE/JWK)
- SCIM 2.0 (RFC 7644), webhooks, audit logging, policy decision
- Framework adapters: FastAPI, Flask, Django, SQLAlchemy
- PKCE (RFC 7636), PAR (RFC 9126), FAPI 2.0, SAML 2.0

**Philosophy:** xwauth is a library, not a service. Login UI, WebAuthn persistence, and first-party auth ceremonies live in `xwauth-identity`. External IdP connectors live in `xwauth-connect`. Both are optional companions that share the `exonware.xwauth` namespace.

---

## B. Backend Architecture

- **Pattern:** Contract (`I`-prefix Protocol) → Abstract (`A`-prefix ABC) → Concrete (`XW`-prefix facade)
- **Async-first:** 560+ `async def`, all public I/O methods are coroutines
- **Framework-agnostic core;** FastAPI/Flask/Django adapters in `integrations/`
- **Storage-agnostic:** `IStorageProvider` protocol; ships `MockStorageProvider` (in-memory) and `XWStorageProvider` (xwstorage adapter)
- **Lazy-loading:** optional via `exonware-xwlazy` (`[lazy]` extra)

**Core dependencies:** PyJWT ≥ 2.8, cryptography ≥ 41, authlib ≥ 1.2, oauthlib ≥ 3.2, webauthn ≥ 2.0, exonware-xwsystem == 0.9.0.39

---

## C. Main Folders and Files

```
src/exonware/xwauth/
├── facade.py              — XWAuth main entry point (convenience + full config init)
├── contracts.py           — I-prefix Protocol interfaces (IProvider, ITokenManager, ISessionManager, ...)
├── base.py                — A-prefix abstract base classes (ABaseAuth, ABaseProvider, ...)
├── defs.py                — Enums: GrantType, TokenType, ResponseType, SessionStatus, UserStatus, MFAMethod, ProviderType (200+)
├── errors.py              — Exception hierarchy (XWAuthError, XWOAuthError, XWTokenError, XWMFAError, ...)
├── api_paths.py           — HTTP path constants (/v1/oauth2, /v1/oidc, /v1/auth, /scim/v2, ...)
├── config/config.py       — XWAuthConfig dataclass (60+ fields)
├── core/
│   ├── oauth2.py          — OAuth2Server: /authorize, /token dispatch
│   ├── oidc.py            — OIDC id_token, nonce, hybrid flows
│   ├── pkce.py            — PKCE S256 challenge/verify
│   ├── par.py             — Pushed Authorization Requests (RFC 9126)
│   ├── saml.py            — SAML 2.0 SP profiles
│   ├── dcr.py             — Dynamic Client Registration (RFC 7591)
│   ├── logout.py          — Token/session revocation (RFC 7009)
│   └── grants/            — 6 grant type handlers
├── tokens/                — JWT, opaque, refresh, introspection, revocation, id_token signing
├── sessions/              — Session lifecycle, CSRF, persistence
├── users/                 — User entity, lifecycle
├── organizations/         — Org entity, CRUD
├── federation/            — FederationBroker, OIDC id_token validation, JWKS cache, IdP quirks
├── storage/               — IStorageProvider, MockStorageProvider, XWStorageProvider
├── jose/                  — JWT/JWS/JWE/JWK/JWA managers, key rotation
├── security/              — Password hashing, rate limiting, input validation
├── authorization/         — RBAC, ABAC, ReBAC, FGA engines
├── scim/                  — SCIM 2.0 service (RFC 7644)
├── audit/                 — AuditLogManager (27 event types), correlation IDs
├── webhooks/              — Webhook entity, manager, async delivery
├── integrations/          — FastAPI middleware, Flask, Django ORM, SQLAlchemy mixins
├── clients/               — OAuth2ClientManager, AsyncOAuth2Session, EntitySessionManager
├── handlers/              — Route handler utilities
└── ops/                   — Operational checklists (airgap, data residency, multi-region, compliance, ...)
```

---

## D. Data Models and Entities

| Model | Key Fields |
|-------|-----------|
| **User** | id, email, phone, password_hash, status (UserStatus), attributes, created_at, updated_at |
| **Session** | id, user_id, expires_at, status (SessionStatus), csrf_token, attributes, last_accessed_at |
| **Token** | id, user_id, client_id, token_type, access_token, refresh_token, expires_at, scopes, attributes |
| **Organization** | id, name, slug, description, metadata, attributes, created_at, updated_at |
| **FederatedIdentity** | subject, issuer, idp_name, claims, linked_user_id, nonce, authorization_code |
| **AuditLog** | id, user_id, action, timestamp, resource, details, ip_address, user_agent |
| **DeviceCode** | device_code, user_code, client_id, scope, expires_at |
| **WebAuthnChallenge** | challenge_id, challenge_bytes, user_id, expires_at |

**Key enums:** `GrantType` (6), `TokenType` (4), `ResponseType` (7), `ClientType` (2), `SessionStatus` (4), `UserStatus` (5), `MFAMethod` (5), `AuthorizationModel` (4), `PasswordHashAlgorithm` (4), `ProviderType` (200+).

---

## E. APIs, Endpoints, and Services

**HTTP path prefixes** (`api_paths.py`):
`/v1/oauth2`, `/v1/oidc`, `/v1/oauth1`, `/v1/auth`, `/v1/users`, `/v1/admin`, `/v1/organizations`, `/v1/webhooks`, `/v1/scim/v2`, `/v1/system`, `/health`, `/metrics`

**Core service classes:**

| Class | File | Key Methods |
|-------|------|-------------|
| `XWAuth` | facade.py | `authorize()`, `token()`, `revoke()`, `introspect()` |
| `OAuth2Server` | core/oauth2.py | `authorize()`, `token()` (grant dispatch) |
| `TokenManager` | tokens/manager.py | `generate_access_token()`, `validate_token()`, `revoke_token()` |
| `SessionManager` | sessions/manager.py | `create_session()`, `get_session()`, `revoke_session()`, `list_user_sessions()` |
| `FederationBroker` | federation/broker.py | `exchange_with_upstream_idp()`, `create_or_update_local_identity()` |
| `ScimService` | scim/service.py | full CRUD on `/scim/v2/Users` and `/scim/v2/Groups` |
| `AuditLogManager` | audit/manager.py | `log_event()`, `query_logs()` |
| `PolicyDecisionService` | policy_decision.py | `evaluate_policy()`, `check_access()` |
| `WebhookManager` | webhooks/manager.py | `subscribe()`, `deliver()` |

**Grant types in `core/grants/`:** authorization_code, client_credentials, resource_owner_password, refresh_token, device_code, token_exchange.

---

## F. Auth, Security, Config, and Env Variables

**`XWAuthConfig`** (`config/config.py`) — 60+ fields, grouped:

| Group | Notable Fields |
|-------|---------------|
| JWT/OIDC | `jwt_secret`*, `jwt_algorithm` (HS256), `oidc_issuer`, `oidc_id_token_signing_pem`, token lifetimes |
| OAuth 2.0 | `require_exact_redirect_uri`, `require_state_in_authorize`, `pkce_s256_only`, `oauth21_compliant` |
| FAPI 2.0 | `fapi20_compliant`, `fapi20_require_par`, `fapi20_require_jar`, `fapi20_require_dpop_or_mtls` |
| Session | `session_timeout` (86400s), `max_concurrent_sessions` |
| MFA | `password_hash_algorithm` (BCRYPT), `mfa_totp_max_failed_attempts` (5), `mfa_at_rest_key_b64` |
| WebAuthn | `webauthn_rp_id`, `webauthn_origin`, `webauthn_challenge_backend` (memory/redis) |
| Rate limit | `rate_limit_enabled`, `rate_limit_requests_per_minute` (60), `rate_limit_requests_per_hour` (1000) |
| Dev | `allow_mock_storage_fallback`, `dev_return_secrets_in_response` (never in prod) |

`*` required.

**No env vars defined** — configuration is purely via `XWAuthConfig` or convenience params passed to `XWAuth()`.

**Protocol profiles:** A (≥98% conformance), B (≥99% + FAPI 2.0 + PAR), C (≥99.5% + JAR + DPoP/mTLS + SAML strict).

---

## G. Database, Storage, Queues, and Background Jobs

- **Storage:** `IStorageProvider` protocol — pluggable. Ships `MockStorageProvider` (in-memory, dev only) and `XWStorageProvider` (delegates to `exonware-xwstorage`).
- **Data persisted:** Users, Sessions, Tokens, AuditLogs, DeviceCodes, WebAuthnChallenges.
- **JWKS cache:** TTL-based in-memory cache (`federation/jwks_cache.py`), 3600s default.
- **WebAuthn store:** memory or Redis backend, configured via `webauthn_challenge_backend`.
- **No built-in job queue.** Webhook delivery (`webhooks/delivery.py`) is async but has no persistent queue — delivery is best-effort.

⚠️ **Production risk:** If `XWAuth` is initialized without explicit storage, it **silently** falls back to `MockStorageProvider` (data lost on restart). See section J.

---

## H. How to Run Locally

```bash
pip install "exonware-xwauth[dev]"

# Run tests
pytest tests/                          # all
pytest tests/0.core/                   # core OAuth 2.0 flow (fast, CI-ready)
pytest tests/1.unit/                   # unit tests
pytest tests/2.integration/            # integration tests
pytest tests/3.advance/test_security.py  # security tests

# Protocol governance check
python scripts/protocol_governance_check.py

# Microbenchmark
python -m exonware.xwauth.bench --iterations 2000
```

**Minimal usage:**
```python
from exonware.xwauth import XWAuth

auth = XWAuth(
    backend="local",
    format="xwjson",
    address="data/xwauth.xwjson",
    jwt_secret="your-secret-key"
)

response = await auth.authorize({
    'client_id': 'myapp',
    'redirect_uri': 'https://example.com/cb',
    'response_type': 'code',
    'state': 'xyz',
    'code_challenge': challenge,
    'code_challenge_method': 'S256',
})
token = await auth.token({
    'grant_type': 'authorization_code',
    'code': response['code'],
    'client_id': 'myapp',
    'redirect_uri': 'https://example.com/cb',
    'code_verifier': verifier,
})
```

---

## I. Tests Available and Tests Missing

**Available (158 test files):**

| Path | Focus |
|------|-------|
| `tests/0.core/` | Authorization code flow, device code, session extraction, storage durability, protocol conformance, import validation |
| `tests/1.unit/` | User model/lifecycle, JOSE (JWT/JWS/JWE), PKCE edge cases, policy decision, ops checklists |
| `tests/2.integration/` | Full OAuth 2.0 flows, user + OAuth, multi-provider, complete auth journey, error recovery |
| `tests/3.advance/` | Security threat modeling, attack vectors, crypto validation |

**Markers:** `xwauth_core`, `xwauth_unit`, `xwauth_integration`, `xwauth_advance`, `xwauth_security`, `xwauth_performance`.

**Tests missing / gaps observed:**
- No test for the silent `MockStorageProvider` fallback in production (`allow_mock_storage_fallback` not set)
- No test verifying `XWAuth` raises on missing storage in the base package (only identity tests this)
- FAPI 2.0 profile B/C startup validation not tested at the Python API level
- `ops/` modules (25+ checklist files) have limited test coverage — mostly structural
- Framework integrations (`integrations/fastapi.py`, `integrations/flask.py`, `integrations/django/`) have no dedicated tests visible in `tests/`

---

## J. Risks, Unclear Parts, and Questions

**J1 — Silent MockStorage fallback (production data-loss risk)**
`xwauth/facade.py:135-139`: if no storage is provided, `MockStorageProvider()` is silently created with only an `INFO` log. Data is lost on restart. `xwauth-identity` fixes this by raising `XWConfigError` unless `allow_mock_storage_fallback=True` is explicitly set. The base package carries the dangerous behavior.

**J2 — Contracts duplicated across three packages**
`IProvider`, `ITokenManager`, `ISessionManager`, `IAuthenticator`, `IAuthorizer` are defined identically in `xwauth/contracts.py` and `xwauth-identity/contracts.py`. Type checking fails: a class implementing `xwauth.contracts.IProvider` does NOT satisfy `xwauth-identity.contracts.IProvider` nominally. Changes must be applied to 2–3 locations. ~500 lines of boilerplate with zero reuse.

**J3 — xwauth vs xwauth-identity feature overlap**
Both repos implement `OAuth2Server`, `TokenManager`, `SessionManager`, `User`, `Organization`, `FederatedIdentity`, `ScimService`, `AuditLogManager`, `WebhookManager`. The facade in xwauth is 281 lines; identity is 992 lines. Device code methods (`device_code_lookup_by_user_code`, `device_code_approve`) only exist in identity. WebAuthn helpers in xwauth return `{}`. The boundary between the two packages is undocumented.

**J4 — Facade import style inconsistency**
`xwauth` uses relative imports (`from .core.oauth2 import OAuth2Server`) while `xwauth-identity` uses absolute imports (`from exonware.xwauth.identity.core.oauth2 import OAuth2Server`). Mixing styles makes the packages harder to test in isolation and prevents straightforward code sharing.

**J5 — `ops/` modules untestable in isolation**
`xwauth/ops/` contains 25+ modules (airgap, data_residency, multi_region_auth, compliance_pack, ...) that appear to be checklist/documentation-as-code. Their interfaces are unclear and their test coverage is minimal.

**J6 — No enforcement of the identity/connect independence invariant**
The rule "identity never imports connect" is documented and has one test (`test_architecture_boundary.py`). There is no import hook, linting rule, or CI check that prevents accidental violations beyond that single test file.

---

## K. Suggested First Improvements

**K1 — Fix the silent MockStorage fallback (immediate, low risk)**
In `xwauth/facade.py`, change the silent fallback to match xwauth-identity: raise `XWConfigError` unless `allow_mock_storage_fallback=True` is explicitly passed. Add a test for the failure path.

**K2 — Unify contracts into `exonware-xwsystem`**
Move `IProvider`, `ITokenManager`, `ISessionManager`, `IAuthenticator`, `IAuthorizer` to `exonware.xwsystem.security.contracts` (or a new `exonware-xwauth-contracts` package). All three xwauth packages import from this single source. Eliminates ~500 lines of duplication and fixes the type-checking fragmentation.

**K3 — Document (and enforce) the xwauth / xwauth-identity split**
Add a `docs/PACKAGE_BOUNDARY.md` that explicitly lists which features live in which package. Add `pyproject.toml` import linting (e.g. via `flake8-tidy-imports`) to enforce that `xwauth` core does not import from `xwauth-identity`, and vice versa. Expand `test_architecture_boundary.py` to cover all cross-package import paths.

**K4 — Add a `CONTEXT.md`**
None of the three xwauth repos has a `CONTEXT.md`. This makes it hard for AI tools and new developers to understand the domain model. Create one that defines: Token, Session, Grant, Provider, Federation, Identity, Connect.

**K5 — Replace absolute imports in xwauth-identity with relative imports**
Relative imports are faster, testable in isolation, and consistent with xwauth. A one-pass sed/isort can handle this and unlocks sharing modules between the two packages without circular imports.
